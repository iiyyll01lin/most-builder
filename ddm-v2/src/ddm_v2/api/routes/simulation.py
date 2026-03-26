from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
try:
    from datetime import UTC
except ImportError:
    import datetime as _dt
    UTC = _dt.timezone.utc
from datetime import datetime
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import (
    ActionReassignRequest,
    AuditAction,
    LineBalanceRequest,
    UserRole,
)
from ddm_v2.services.auth_service import decode_access_token
from ddm_v2.services.simulation_service import run_line_balance

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])

# Thread pool used for running CPU-bound simulation in non-blocking mode.
_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sim-worker")

# Pending jobs submitted via POST /line-balance/async.
# Key: job_id  Value: snapshot of all data needed to run the simulation.
# Populated by the POST handler; consumed (and deleted) by the WS handler.
_pending_jobs: dict[str, dict[str, Any]] = {}


def _build_station_list(payload: LineBalanceRequest, store: JsonStore) -> list[dict[str, Any]]:
    station_lookup = {s["id"]: s for s in store.list_collection("stations")}
    employees = store.list_collection("employees")
    default_employee_id = employees[0]["id"] if employees else None
    stations: list[dict[str, Any]] = []
    for assignment in payload.stations:
        station = station_lookup.get(assignment.id, {"id": assignment.id, "name": assignment.id})
        stations.append(
            {
                "id": assignment.id,
                "name": station["name"],
                "employee_id": assignment.employee_id or station.get("employee_id") or default_employee_id,
                "sop_ids": list(assignment.sop_ids or []),
            }
        )
    return stations


@router.post("/line-balance")
def simulate(payload: LineBalanceRequest, store: JsonStore = Depends(get_store), user: dict = Depends(get_current_user)):
    stations = _build_station_list(payload, store)
    try:
        result = run_line_balance(
            project_id=payload.project_id,
            takt_time=payload.takt_time,
            station_assignments=stations,
            employees=store.list_collection("employees"),
            sop_versions=store.list_collection("sop_versions"),
            glove_rules=store.list_collection("glove_rules"),
            ion_fan_bindings=store.list_collection("ion_fan_bindings"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    snapshot = result.model_dump()
    snapshot.update({
        "id": store.new_id("sim"),
        "timestamp": datetime.now(UTC).isoformat(),
        "project_id": payload.project_id,
        "created_by": user["name"],
    })
    store.list_collection("simulation_results").append(snapshot)
    store.save()
    store.audit(
        user,
        AuditAction.create,
        "simulation-result",
        snapshot["id"],
        f"Created line balance simulation for {payload.project_id}",
        new_value={"project_id": payload.project_id, "station_count": len(payload.stations)},
    )
    return result


@router.post("/line-balance/async", status_code=202)
async def simulate_async(
    payload: LineBalanceRequest,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Submit a line-balance simulation job and return a job_id immediately.

    Connect to ``WS /api/v1/simulation/ws/{job_id}?token=<bearer>`` to
    receive real-time progress events and the final result payload.
    """
    job_id = store.new_id("job")
    # Snapshot all store data the simulation needs so the background thread
    # never touches the live store (thread-safety).
    _pending_jobs[job_id] = {
        "payload": payload,
        "user": user,
        "stations": _build_station_list(payload, store),
        "employees": list(store.list_collection("employees")),
        "sop_versions": list(store.list_collection("sop_versions")),
        "glove_rules": list(store.list_collection("glove_rules")),
        "ion_fan_bindings": list(store.list_collection("ion_fan_bindings")),
        "store": store,
    }
    return {"job_id": job_id, "status": "accepted"}


@router.websocket("/ws/{job_id}")
async def ws_line_balance(
    websocket: WebSocket,
    job_id: str,
    token: str | None = None,
) -> None:
    """Stream real-time progress events for a simulation submitted via POST /line-balance/async.

    Authentication: pass the bearer token as ?token=<value> query parameter.
    Events are JSON objects: ``{"progress": <0-100>, "status": "<message>"}``.
    The final event carries ``"progress": 100`` plus a ``"result"`` key with
    the full ``LineBalanceResponse`` payload.
    """
    # Resolve the store directly from the ASGI app state — WebSocket objects do
    # not participate in the standard HTTP dependency graph so we bypass Depends.
    store: JsonStore = websocket.app.state.store
    # Authenticate before accepting the WebSocket upgrade.
    if token is None:
        await websocket.close(code=4001)
        return
    try:
        jwt_payload = decode_access_token(token)
    except jwt.PyJWTError:
        await websocket.close(code=4001)
        return
    username = jwt_payload.get("sub")
    user = store.state["users"].get(username) if username else None
    if user is None:
        await websocket.close(code=4001)
        return

    job = _pending_jobs.pop(job_id, None)
    if job is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def _progress_cb(pct: int, msg: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"progress": pct, "status": msg})

    def _run_simulation() -> None:
        payload: LineBalanceRequest = job["payload"]
        job_store: JsonStore = job["store"]
        try:
            result = run_line_balance(
                project_id=payload.project_id,
                takt_time=payload.takt_time,
                station_assignments=job["stations"],
                employees=job["employees"],
                sop_versions=job["sop_versions"],
                glove_rules=job["glove_rules"],
                ion_fan_bindings=job["ion_fan_bindings"],
                progress_callback=_progress_cb,
            )
            snapshot = result.model_dump()
            snapshot.update({
                "id": job_store.new_id("sim"),
                "timestamp": datetime.now(UTC).isoformat(),
                "project_id": payload.project_id,
                "created_by": job["user"]["name"],
            })
            job_store._raw_list("simulation_results").append(snapshot)
            job_store.save()
            job_store.audit(
                job["user"],
                AuditAction.create,
                "simulation-result",
                snapshot["id"],
                f"Created line balance simulation for {payload.project_id}",
                new_value={"project_id": payload.project_id, "station_count": len(payload.stations)},
            )
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"progress": 100, "status": "complete", "result": snapshot},
            )
        except ValueError as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"progress": -1, "status": "error", "error": str(exc)},
            )
        except Exception:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"progress": -1, "status": "error", "error": "Internal simulation error"},
            )

    loop.run_in_executor(_executor, _run_simulation)

    try:
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=120.0)
            await websocket.send_json(event)
            if event.get("progress") in (100, -1):
                break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/reassign-action")
def reassign(payload: ActionReassignRequest, store: JsonStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    for sop in store.list_collection("sop_versions"):
        for action in sop.get("actions", []):
            if action["id"] == payload.action_id:
                if action.get("station_id") != payload.from_station_id:
                    raise HTTPException(status_code=400, detail="Action not in source station")
                action["station_id"] = payload.to_station_id
                store.save()
                store.audit(user, AuditAction.update, "action-assignment", payload.action_id, f"Moved action to {payload.to_station_id}")
                return {"message": "Action reassigned successfully", "action": action}
    raise HTTPException(status_code=404, detail="Action not found")


@router.get("/history")
def history(project_id: str | None = None, limit: int = 20, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    limit = max(1, min(limit, 200))
    results = list(store.list_collection("simulation_results"))
    if project_id:
        results = [result for result in results if result["project_id"] == project_id]
    results.sort(key=lambda item: item["timestamp"], reverse=True)
    return {"total": len(results), "results": results[:limit]}


@router.get("/history/{sim_id}")
def history_detail(sim_id: str, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    snapshot = store.find_by_id("simulation_results", sim_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Simulation result not found")
    return snapshot


@router.delete("/history/{sim_id}", status_code=204)
def delete_history(sim_id: str, store: JsonStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed = store.delete_collection_item("simulation_results", sim_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Simulation result not found")
    store.audit(
        user,
        AuditAction.delete,
        "simulation-result",
        sim_id,
        f"Deleted simulation result {sim_id}",
        old_value={"project_id": removed.get("project_id"), "timestamp": removed.get("timestamp")},
    )
    return Response(status_code=204)


@router.delete("/history", status_code=204)
def clear_history(store: JsonStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed_count = len(store.list_collection("simulation_results"))
    store.state["simulation_results"] = []
    store.save()
    store.audit(
        user,
        AuditAction.delete,
        "simulation-result",
        "all",
        "Cleared simulation history",
        old_value={"removed_count": removed_count},
    )
    return Response(status_code=204)
