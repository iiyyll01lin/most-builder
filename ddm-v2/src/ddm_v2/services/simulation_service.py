from __future__ import annotations

from copy import deepcopy

from ddm_v2.schemas import LineBalanceResponse, SkillLevel, StationResult


def run_line_balance(
    project_id: str,
    takt_time: float,
    station_assignments: list[dict],
    employees: list[dict],
    sop_versions: list[dict],
    glove_rules: list[dict],
    ion_fan_bindings: list[dict],
) -> LineBalanceResponse:
    selected_sop_ids = {
        sop_id
        for assignment in station_assignments
        for sop_id in assignment.get("sop_ids", [])
        if sop_id
    }
    relevant_sops = [version for version in sop_versions if version["project_id"] == project_id]
    if selected_sop_ids:
        relevant_sops = [version for version in relevant_sops if version["id"] in selected_sop_ids]
    all_actions = [deepcopy(action) for version in relevant_sops for action in version.get("actions", [])]
    employee_map = {employee["id"]: employee for employee in employees}
    default_employee = employees[0] if employees else None
    station_results: list[StationResult] = []
    alerts: list[str] = []
    total_actual_time = 0.0
    cycle_time = 0.0

    for station in station_assignments:
        employee_id = station.get("employee_id") or (default_employee.get("id") if default_employee else None)
        employee = employee_map.get(employee_id) if employee_id else None
        if employee is None:
            alerts.append(f"Employee {station.get('employee_id')} not found for station {station['id']}.")
            continue

        station_actions = [action for action in all_actions if action.get("station_id") == station["id"]]
        standard_time = round(sum(float(action.get("seconds", 0)) for action in station_actions), 2)
        efficiency = float(employee.get("efficiency_factor", 1.0)) or 1.0
        actual_time = round(standard_time / efficiency, 2)
        cycle_time = max(cycle_time, actual_time)
        total_actual_time += actual_time
        required_gloves = sorted(
            {
                action.get("glove_type")
                or next(
                    (
                        rule["glove_type"]
                        for rule in glove_rules
                        if rule["object_category"] in {action.get("object_category"), "*"}
                    ),
                    "General Glove",
                )
                for action in station_actions
            }
        )
        ctq_actions = sorted([action["id"] for action in station_actions if action.get("is_ctq")])
        ion_fan_targets = sorted(
            {
                binding["object_name"]
                for action in station_actions
                for binding in ion_fan_bindings
                if binding.get("object_name") == action.get("component") or binding.get("object_category") == action.get("object_category")
            }
        )
        if actual_time > takt_time:
            alerts.append(f"Station {station['id']} exceeds takt by {round(actual_time - takt_time, 2)} seconds.")
        if ctq_actions and employee["skill_level"] == SkillLevel.novice.value:
            alerts.append(f"Station {station['id']} assigns CTQ work to novice operator {employee['name']}.")

        station_results.append(
            StationResult(
                id=station["id"],
                name=station.get("name", station["id"]),
                operator=employee["name"],
                skill_level=SkillLevel(employee["skill_level"]),
                efficiency_factor=efficiency,
                standard_time=standard_time,
                actual_time=actual_time,
                actions=[
                    {
                        "id": action["id"],
                        "description": action["description"],
                        "seconds": action["seconds"],
                        "station_id": action.get("station_id"),
                    }
                    for action in station_actions
                ],
                is_overloaded=actual_time > takt_time,
                required_gloves=required_gloves,
                ctq_actions=ctq_actions,
                ion_fan_required=bool(ion_fan_targets),
                ion_fan_targets=ion_fan_targets,
            )
        )

    station_count = len(station_results)
    balance_rate = 0.0
    if station_count and cycle_time:
        balance_rate = round(total_actual_time / (cycle_time * station_count), 2)
    bottleneck_station = max(station_results, key=lambda station: station.actual_time).id if station_results else "N/A"
    uph = int(3600 / cycle_time) if cycle_time else 0
    return LineBalanceResponse(
        bottleneck_station=bottleneck_station,
        cycle_time=round(cycle_time, 2),
        uph=uph,
        balance_rate=balance_rate,
        alerts=alerts,
        station_results=station_results,
    )
