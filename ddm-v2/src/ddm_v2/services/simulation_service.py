from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy

from ddm_v2.schemas import BalanceReport, LineBalanceResponse, SkillLevel, StationResult


def check_skill_certification(
    action: dict,
    employee: dict,
) -> str | None:
    """Return an alert string if the action requires a skill certification that
    the assigned employee does not hold; return None when no mismatch is found.

    Certification matching rules:
    - ``action["required_skill"]`` names the required skill/FATP code.
    - ``employee["certifications"]`` is the list of codes the operator holds.
    - If the employee is Expert or Proficient **and** the certifications list is
      empty, they are assumed to be universally qualified (backward-compat for
      existing employee records that predate the certifications field).
    - Novice operators are NEVER assumed to be universally qualified.
    """
    required = action.get("required_skill")
    if not required:
        return None
    certs: list[str] = employee.get("certifications") or []
    skill_level: str = employee.get("skill_level", "")
    # Backward-compat: non-novice with no certifications recorded → assume qualified.
    if not certs and skill_level != SkillLevel.novice.value:
        return None
    if required in certs:
        return None
    return (
        f"Action '{action.get('description', action.get('id', '?'))}' requires "
        f"skill '{required}', but operator '{employee.get('name', '?')}' does not "
        "hold this certification."
    )


def _simo_adjusted_standard_time(actions: list[dict]) -> float:
    """Compute SIMO-adjusted station standard time — O(n) single-pass algorithm.

    Actions that share a ``simo_group_id`` and are marked ``is_simo`` are
    grouped by their ID in a single pass using a ``defaultdict(list)``.  For
    each group, only the bottleneck (max seconds) action is counted towards the
    station total — this is the SIMO rule: parallel left/right-hand motions
    take as long as the slower hand, not the sum of both.
    Actions without a ``simo_group_id`` contribute their full duration normally.
    """
    # Single-pass grouping: O(n) — no nested loops.
    simo_groups: defaultdict[str, list[float]] = defaultdict(list)
    non_simo_total = 0.0
    for action in actions:
        simo_gid = action.get("simo_group_id")
        if action.get("is_simo") and simo_gid:
            simo_groups[simo_gid].append(float(action.get("seconds", 0)))
        else:
            non_simo_total += float(action.get("seconds", 0))
    # For each SIMO group take only the bottleneck (max) hand time.
    simo_total = sum(max(times) for times in simo_groups.values())
    return non_simo_total + simo_total


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

    # Pre-build O(1) ion-fan lookup indexes to handle >5000 actions without O(n²) penalty.
    # Index by exact object_name and by object_category for fast per-action lookup.
    _ion_by_name: dict[str, str] = {}
    _ion_by_category: dict[str, str] = {}
    for _b in ion_fan_bindings:
        _name = (_b.get("object_name") or "").strip().lower()
        _cat = (_b.get("object_category") or "").strip().lower()
        if _name:
            _ion_by_name[_name] = _b.get("object_name", "")
        if _cat:
            _ion_by_category[_cat] = _b.get("object_name") or _b.get("object_category", "")

    # Pre-sort glove rules by specificity once (avoids re-sorting O(n_rules) per action).
    _sorted_glove_rules = sorted(
        glove_rules,
        key=lambda r: (
            (1 if r.get("object_category") == "*" else 0)
            + (1 if r.get("action") in ("*", None) else 0)
        ),
    )

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

        # 1 Person 2 Machines (1P2M): the station may declare machine_count > 1.
        # The operator's wall-clock load is standard_time / machine_count because the
        # machine runs in parallel; however each machine still contributes to CT.
        machine_count: int = max(int(station.get("machine_count") or 1), 1)

        station_actions = [action for action in all_actions if action.get("station_id") == station["id"]]
        standard_time = round(_simo_adjusted_standard_time(station_actions), 2)
        efficiency = float(employee.get("efficiency_factor", 1.0)) or 1.0
        actual_time = round(standard_time / efficiency, 2)
        # For 1P2M, the operator's effective cycle contribution is divided by machine_count.
        machine_effective_time: float | None = None
        if machine_count > 1:
            machine_effective_time = round(actual_time / machine_count, 2)
        # Bottleneck uses machine_effective_time when applicable; fallback to actual_time.
        bottleneck_contribution = machine_effective_time if machine_effective_time is not None else actual_time
        cycle_time = max(cycle_time, bottleneck_contribution)
        total_actual_time += bottleneck_contribution

        required_gloves = sorted(
            {
                action.get("glove_type")
                or next(
                    (
                        rule["glove_type"]
                        for rule in _sorted_glove_rules
                        if rule["object_category"] in {action.get("object_category"), "*"}
                    ),
                    "General Glove",
                )
                for action in station_actions
            }
        )
        ctq_actions = sorted([action["id"] for action in station_actions if action.get("is_ctq")])

        # O(1) ion-fan lookup using pre-built indexes.
        ion_fan_targets: set[str] = set()
        for action in station_actions:
            comp = (action.get("component") or "").strip().lower()
            cat = (action.get("object_category") or "").strip().lower()
            if comp and comp in _ion_by_name:
                ion_fan_targets.add(_ion_by_name[comp])
            elif cat and cat in _ion_by_category:
                ion_fan_targets.add(_ion_by_category[cat])

        if bottleneck_contribution > takt_time:
            alerts.append(f"Station {station['id']} exceeds takt by {round(bottleneck_contribution - takt_time, 2)} seconds.")
        if ctq_actions and employee["skill_level"] == SkillLevel.novice.value:
            alerts.append(f"Station {station['id']} assigns CTQ work to novice operator {employee['name']}.")

        # Skill certification check: alert when an action declares a required_skill
        # that is not in the assigned employee's certifications.
        station_skill_alerts: list[str] = []
        for action in station_actions:
            cert_alert = check_skill_certification(action, employee)
            if cert_alert:
                station_skill_alerts.append(cert_alert)
                if cert_alert not in alerts:
                    alerts.append(f"Station {station['id']}: {cert_alert}")

        station_results.append(
            StationResult(
                id=station["id"],
                name=station.get("name", station["id"]),
                operator=employee["name"],
                skill_level=SkillLevel(employee["skill_level"]),
                efficiency_factor=efficiency,
                standard_time=standard_time,
                actual_time=actual_time,
                machine_count=machine_count,
                machine_effective_time=machine_effective_time,
                actions=[
                    {
                        "id": action["id"],
                        "description": action["description"],
                        "seconds": action["seconds"],
                        "station_id": action.get("station_id"),
                    }
                    for action in station_actions
                ],
                is_overloaded=bottleneck_contribution > takt_time,
                required_gloves=required_gloves,
                ctq_actions=ctq_actions,
                ion_fan_required=bool(ion_fan_targets),
                ion_fan_targets=sorted(ion_fan_targets),
                skill_alerts=station_skill_alerts,
            )
        )

    station_count = len(station_results)
    balance_rate = 0.0
    _emit(85, "Computing balance metrics")
    if station_count and cycle_time:
        balance_rate = round(total_actual_time / (cycle_time * station_count), 2)
    bottleneck_station = max(station_results, key=lambda s: s.machine_effective_time if s.machine_effective_time is not None else s.actual_time).id if station_results else "N/A"
    uph = int(3600 / cycle_time) if cycle_time else 0

    # Line Balance Efficiency KPIs (IE/PE summary).
    # Efficiency = ΣCT / (n × CT_max) × 100  — same as balance_rate expressed as %.
    # Loss = 100 - Efficiency; a loss > 15% signals redistribution opportunity.
    balance_efficiency_pct = round(balance_rate * 100, 1)
    balance_loss_pct = round(100.0 - balance_efficiency_pct, 1)
    balance_report = BalanceReport(
        balance_efficiency_pct=balance_efficiency_pct,
        balance_loss_pct=balance_loss_pct,
        bottleneck_station_id=bottleneck_station,
    )

    _emit(95, "Finalizing results")
    return LineBalanceResponse(
        bottleneck_station=bottleneck_station,
        cycle_time=round(cycle_time, 2),
        uph=uph,
        balance_rate=balance_rate,
        alerts=alerts,
        station_results=station_results,
        balance_report=balance_report,
    )

