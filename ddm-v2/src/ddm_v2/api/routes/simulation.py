from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import ActionReassignRequest, AuditAction, LineBalanceRequest, UserRole
from ddm_v2.services.simulation_service import run_line_balance


router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])


@router.post("/line-balance")
def simulate(payload: LineBalanceRequest, store: JsonStore = Depends(get_store), user: dict = Depends(get_current_user)):
    stations = []
    station_lookup = {station["id"]: station for station in store.list_collection("stations")}
    for assignment in payload.stations:
        station = station_lookup.get(assignment.id, {"id": assignment.id, "name": assignment.id})
        stations.append({"id": assignment.id, "name": station["name"], "employee_id": assignment.employee_id})
    result = run_line_balance(
        project_id=payload.project_id,
        takt_time=payload.takt_time,
        station_assignments=stations,
        employees=store.list_collection("employees"),
        sop_versions=store.list_collection("sop_versions"),
        glove_rules=store.list_collection("glove_rules"),
        ion_fan_bindings=store.list_collection("ion_fan_bindings"),
    )
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
