from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.postgres_store import PostgresStore
from ddm_v2.schemas import (
    AuditAction,
    ComponentEntry,
    EmployeeEntry,
    LocationEntry,
    ObjectEntry,
    StationEntry,
    SyntaxEntry,
    ToolEntry,
    UserRole,
)

router = APIRouter(prefix="/api/v1/master", tags=["master"])


async def _create_item(store: PostgresStore, collection: str, prefix: str, payload: dict) -> dict:
    record = {**payload, "id": store.new_id(prefix)}
    return await store.upsert_collection_item(collection, record)


async def _update_item(store: PostgresStore, collection: str, item_id: str, payload: dict) -> dict:
    current = await store.find_by_id(collection, item_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Item not found")
    merged = {**current, **payload, "id": item_id}
    return await store.upsert_collection_item(collection, merged)


async def _delete_item(store: PostgresStore, collection: str, item_id: str) -> None:
    removed = await store.delete_collection_item(collection, item_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Item not found")


def _paginate(items: list, page: int | None, size: int) -> JSONResponse:
    """Return a PaginatedResponse dict when page is given, else a bare list with X-Total-Count header."""
    total = len(items)
    if page is not None:
        size = max(1, min(size, 500))
        offset = (page - 1) * size
        pages = math.ceil(total / size) if size else 1
        return JSONResponse(
            content={"items": items[offset : offset + size], "total": total, "page": page, "size": size, "pages": pages},
        )
    return JSONResponse(content=items, headers={"X-Total-Count": str(total)})


@router.get("/syntax")
async def list_syntax(page: int | None = None, size: int = 50, store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return _paginate(list(await store.list_collection("syntax_library")), page, size)


@router.post("/syntax", status_code=201)
async def create_syntax(
    payload: SyntaxEntry,
    store: PostgresStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    record = await _create_item(store, "syntax_library", "syn", payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.create, "syntax", record["id"], f"Created syntax {record['action_verb']}", new_value=record)
    return record


@router.put("/syntax/{item_id}")
async def update_syntax(
    item_id: str,
    payload: SyntaxEntry,
    store: PostgresStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    previous = dict(await store.find_by_id("syntax_library", item_id) or {})
    record = await _update_item(store, "syntax_library", item_id, payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.update, "syntax", item_id, f"Updated syntax {record['action_verb']}", old_value=previous, new_value=record)
    return record


@router.delete("/syntax/{item_id}", status_code=204)
async def delete_syntax(
    item_id: str,
    store: PostgresStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager)),
):
    removed = await store.find_by_id("syntax_library", item_id)
    await _delete_item(store, "syntax_library", item_id)
    await store.audit(user, AuditAction.delete, "syntax", item_id, "Deleted syntax", old_value=removed)
    return Response(status_code=204)


@router.get("/components")
async def list_components(page: int | None = None, size: int = 50, store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return _paginate(list(await store.list_collection("component_library")), page, size)


@router.post("/components", status_code=201)
async def create_component(payload: ComponentEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    record = await _create_item(store, "component_library", "comp", payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.create, "component", record["id"], f"Created component {record['name_en']}", new_value=record)
    return record


@router.put("/components/{item_id}")
async def update_component(item_id: str, payload: ComponentEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    previous = dict(await store.find_by_id("component_library", item_id) or {})
    record = await _update_item(store, "component_library", item_id, payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.update, "component", item_id, f"Updated component {record['name_en']}", old_value=previous, new_value=record)
    return record


@router.delete("/components/{item_id}", status_code=204)
async def delete_component(item_id: str, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed = await store.find_by_id("component_library", item_id)
    await _delete_item(store, "component_library", item_id)
    await store.audit(user, AuditAction.delete, "component", item_id, "Deleted component", old_value=removed)
    return Response(status_code=204)


@router.get("/tools")
async def list_tools(page: int | None = None, size: int = 50, store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return _paginate(list(await store.list_collection("tool_library")), page, size)


@router.post("/tools", status_code=201)
async def create_tool(payload: ToolEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    record = await _create_item(store, "tool_library", "tool", payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.create, "tool", record["id"], f"Created tool {record['name']}", new_value=record)
    return record


@router.put("/tools/{item_id}")
async def update_tool(item_id: str, payload: ToolEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    previous = dict(await store.find_by_id("tool_library", item_id) or {})
    record = await _update_item(store, "tool_library", item_id, payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.update, "tool", item_id, f"Updated tool {record['name']}", old_value=previous, new_value=record)
    return record


@router.delete("/tools/{item_id}", status_code=204)
async def delete_tool(item_id: str, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed = await store.find_by_id("tool_library", item_id)
    await _delete_item(store, "tool_library", item_id)
    await store.audit(user, AuditAction.delete, "tool", item_id, "Deleted tool", old_value=removed)
    return Response(status_code=204)


@router.get("/locations")
async def list_locations(page: int | None = None, size: int = 50, store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return _paginate(list(await store.list_collection("location_library")), page, size)


@router.post("/locations", status_code=201)
async def create_location(payload: LocationEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    record = await _create_item(store, "location_library", "loc", payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.create, "location", record["id"], f"Created location {record['name']}", new_value=record)
    return record


@router.put("/locations/{item_id}")
async def update_location(item_id: str, payload: LocationEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    previous = dict(await store.find_by_id("location_library", item_id) or {})
    record = await _update_item(store, "location_library", item_id, payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.update, "location", item_id, f"Updated location {record['name']}", old_value=previous, new_value=record)
    return record


@router.delete("/locations/{item_id}", status_code=204)
async def delete_location(item_id: str, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed = await store.find_by_id("location_library", item_id)
    await _delete_item(store, "location_library", item_id)
    await store.audit(user, AuditAction.delete, "location", item_id, "Deleted location", old_value=removed)
    return Response(status_code=204)


@router.get("/objects")
async def list_objects(page: int | None = None, size: int = 50, store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return _paginate(list(await store.list_collection("object_library")), page, size)


@router.post("/objects", status_code=201)
async def create_object(payload: ObjectEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    record = await _create_item(store, "object_library", "obj", payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.create, "object", record["id"], f"Created object {record['name']}", new_value=record)
    return record


@router.put("/objects/{item_id}")
async def update_object(item_id: str, payload: ObjectEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    previous = dict(await store.find_by_id("object_library", item_id) or {})
    record = await _update_item(store, "object_library", item_id, payload.model_dump(exclude={"id"}))
    await store.audit(user, AuditAction.update, "object", item_id, f"Updated object {record['name']}", old_value=previous, new_value=record)
    return record


@router.delete("/objects/{item_id}", status_code=204)
async def delete_object(item_id: str, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed = await store.find_by_id("object_library", item_id)
    await _delete_item(store, "object_library", item_id)
    await store.audit(user, AuditAction.delete, "object", item_id, "Deleted object", old_value=removed)
    return Response(status_code=204)


@router.get("/employees")
async def list_employees(page: int | None = None, size: int = 50, store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return _paginate(list(await store.list_collection("employees")), page, size)


@router.post("/employees", status_code=201)
async def create_employee(payload: EmployeeEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    body = payload.model_dump(exclude={"id"})
    body["skill_level"] = payload.skill_level.value
    record = await _create_item(store, "employees", "emp", body)
    await store.audit(user, AuditAction.create, "employee", record["id"], f"Created employee {record['name']}", new_value=record)
    return record


@router.put("/employees/{item_id}")
async def update_employee(item_id: str, payload: EmployeeEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    previous = dict(await store.find_by_id("employees", item_id) or {})
    body = payload.model_dump(exclude={"id"})
    body["skill_level"] = payload.skill_level.value
    record = await _update_item(store, "employees", item_id, body)
    await store.audit(user, AuditAction.update, "employee", item_id, f"Updated employee {record['name']}", old_value=previous, new_value=record)
    return record


@router.delete("/employees/{item_id}", status_code=204)
async def delete_employee(item_id: str, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed = await store.find_by_id("employees", item_id)
    await _delete_item(store, "employees", item_id)
    await store.audit(user, AuditAction.delete, "employee", item_id, "Deleted employee", old_value=removed)
    return Response(status_code=204)


@router.get("/stations")
async def list_stations(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("stations")


@router.post("/stations", status_code=201)
async def create_station(payload: StationEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    if any(station["id"] == payload.id for station in await store.list_collection("stations")):
        raise HTTPException(status_code=400, detail="Station ID already exists")
    if payload.employee_id and await store.find_by_id("employees", payload.employee_id) is None:
        raise HTTPException(status_code=400, detail="Employee not found")
    record = payload.model_dump()
    await store.upsert_collection_item("stations", record)
    await store.audit(user, AuditAction.create, "station", record["id"], f"Created station {record['name']}", new_value=record)
    return record


@router.put("/stations/{item_id}")
async def update_station(item_id: str, payload: StationEntry, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    if payload.employee_id and await store.find_by_id("employees", payload.employee_id) is None:
        raise HTTPException(status_code=400, detail="Employee not found")
    previous = dict(await store.find_by_id("stations", item_id) or {})
    record = await _update_item(store, "stations", item_id, payload.model_dump())
    await store.audit(user, AuditAction.update, "station", item_id, f"Updated station {record['name']}", old_value=previous, new_value=record)
    return record


@router.delete("/stations/{item_id}", status_code=204)
async def delete_station(item_id: str, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    removed = await store.find_by_id("stations", item_id)
    await _delete_item(store, "stations", item_id)
    await store.audit(user, AuditAction.delete, "station", item_id, "Deleted station", old_value=removed)
    return Response(status_code=204)


@router.get("/from-locations")
async def from_locations(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("from_locations")


@router.get("/to-locations")
async def to_locations(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("to_locations")


@router.get("/reference-points")
async def reference_points(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("reference_points")


@router.get("/precautions")
async def precautions(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("precautions")


@router.get("/glove-rules")
async def glove_rules(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("glove_rules")


@router.get("/ion-fan-bindings")
async def ion_fan_bindings(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("ion_fan_bindings")


@router.get("/mi-naming")
async def mi_naming(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("mi_naming_rules")
