from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from ddm_v2.schemas import LineBalanceResponse, SkillLevel, StationResult


def _simo_adjusted_standard_time(actions: list[dict]) -> float:
    """Compute SIMO-adjusted station standard time.

    Actions that share a ``simo_group_id`` and are marked ``is_simo`` are
    treated as simultaneous: only the bottleneck (max seconds) action in each
    group is counted.  Actions without a simo_group_id contribute normally.
    This prevents overcounting when both left-hand and right-hand operations
    are executed in parallel on the same station.
    """
    simo_groups: dict[str, float] = {}
    non_simo_total = 0.0
    for action in actions:
        simo_gid = action.get("simo_group_id")
        if action.get("is_simo") and simo_gid:
            seconds = float(action.get("seconds", 0))
            simo_groups[simo_gid] = max(simo_groups.get(simo_gid, 0.0), seconds)
        else:
            non_simo_total += float(action.get("seconds", 0))
    return non_simo_total + sum(simo_groups.values())


def run_line_balance(
    project_id: str,
    takt_time: float,
    station_assignments: list[dict],
    employees: list[dict],
    sop_versions: list[dict],
    glove_rules: list[dict],
    ion_fan_bindings: list[dict],
    progress_callback: Callable[[int, str], None] | None = None,
) -> LineBalanceResponse:
    def _emit(pct: int, msg: str) -> None:
        if progress_callback is not None:
            progress_callback(pct, msg)

    _emit(5, "Resolving SOP actions")
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

    _emit(15, "Building employee roster map")

    station_count_total = max(len(station_assignments), 1)
    for station_index, station in enumerate(station_assignments):
        _emit(15 + int(65 * station_index / station_count_total), f"Processing station {station.get('id', station_index + 1)}")
        employee_id = station.get("employee_id") or (default_employee.get("id") if default_employee else None)
        employee = employee_map.get(employee_id) if employee_id else None
        if employee is None:
            # Hard fault: an unresolvable employee assignment produces incorrect
            # cycle time and UPH values.  Surface the error immediately so the
            # IE/PE can fix the station assignment before re-running simulation.
            resolved_id = station.get("employee_id") or "(none)"
            raise ValueError(
                f"Station '{station['id']}' references employee '{resolved_id}' "
                "which does not exist in the employee roster. "
                "Assign a valid employee to this station before running line balance."
            )

        station_actions = [action for action in all_actions if action.get("station_id") == station["id"]]
        standard_time = round(_simo_adjusted_standard_time(station_actions), 2)
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
    _emit(85, "Computing balance metrics")
    if station_count and cycle_time:
        balance_rate = round(total_actual_time / (cycle_time * station_count), 2)
    bottleneck_station = max(station_results, key=lambda station: station.actual_time).id if station_results else "N/A"
    uph = int(3600 / cycle_time) if cycle_time else 0
    _emit(95, "Finalizing results")
    return LineBalanceResponse(
        bottleneck_station=bottleneck_station,
        cycle_time=round(cycle_time, 2),
        uph=uph,
        balance_rate=balance_rate,
        alerts=alerts,
        station_results=station_results,
    )

