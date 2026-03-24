from __future__ import annotations

import pytest

from ddm_v2.services.simulation_service import run_line_balance


@pytest.mark.unit
def test_run_line_balance_calculates_cycle_time_and_alerts():
    result = run_line_balance(
        project_id="proj-atlas",
        takt_time=4.0,
        station_assignments=[
            {"id": "ST-1", "name": "Station 1", "employee_id": "emp-eva", "sop_ids": ["sop-1"]},
            {"id": "ST-2", "name": "Station 2", "employee_id": "emp-li", "sop_ids": ["sop-1"]},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.2},
            {"id": "emp-li", "name": "Li", "skill_level": "Novice", "efficiency_factor": 0.8},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-atlas",
                "actions": [
                    {"id": "act-1", "description": "Fasten screw", "seconds": 1.2, "station_id": "ST-1", "object_category": "Fastener", "glove_type": None, "component": "Screw", "is_ctq": True},
                    {"id": "act-2", "description": "Inspect board", "seconds": 4.8, "station_id": "ST-2", "object_category": "PCB", "glove_type": None, "component": "Motherboard", "is_ctq": True},
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[{"id": "ion-pcb", "object_category": "PCB", "object_name": "Motherboard", "note": "ESD critical handling"}],
    )

    assert result.bottleneck_station == "ST-2"
    assert result.cycle_time == 6.0
    assert result.uph == 600
    assert any("CTQ work to novice operator" in alert for alert in result.alerts)


@pytest.mark.unit
def test_run_line_balance_filters_to_selected_sop_ids_and_defaults_operator_when_missing():
    result = run_line_balance(
        project_id="proj-atlas",
        takt_time=3.0,
        station_assignments=[
            {"id": "ST-1", "name": "Station 1", "employee_id": None, "sop_ids": ["sop-keep"]},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.2},
            {"id": "emp-li", "name": "Li", "skill_level": "Novice", "efficiency_factor": 0.8},
        ],
        sop_versions=[
            {
                "id": "sop-keep",
                "project_id": "proj-atlas",
                "actions": [
                    {"id": "act-1", "description": "Keep action", "seconds": 1.2, "station_id": "ST-1", "object_category": "Fastener", "glove_type": None, "component": "Screw", "is_ctq": False},
                ],
            },
            {
                "id": "sop-ignore",
                "project_id": "proj-atlas",
                "actions": [
                    {"id": "act-2", "description": "Ignored action", "seconds": 9.0, "station_id": "ST-1", "object_category": "PCB", "glove_type": None, "component": "Motherboard", "is_ctq": False},
                ],
            },
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[],
    )

    assert result.station_results[0].operator == "Eva"
    assert result.station_results[0].standard_time == 1.2
    assert result.station_results[0].actual_time == 1.0


# ---------------------------------------------------------------------------
# Phase 2 hardening tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_line_balance_raises_on_unknown_employee_id():
    """If a station references an employee_id that doesn't exist in the roster,
    the service must raise ValueError immediately.  Silently dropping the station
    would produce incorrect cycle_time and UPH values for the IE/PE."""
    with pytest.raises(ValueError) as exc_info:
        run_line_balance(
            project_id="proj-test",
            takt_time=5.0,
            station_assignments=[
                {"id": "ST-X", "name": "Ghost Station", "employee_id": "emp-ghost", "sop_ids": []},
            ],
            employees=[
                {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.2},
            ],
            sop_versions=[],
            glove_rules=[],
            ion_fan_bindings=[],
        )
    assert "emp-ghost" in str(exc_info.value)


@pytest.mark.unit
def test_simo_adjusted_standard_time_deduplicates_simo_group():
    """SIMO-paired actions in the same station must count only their max seconds,
    not the sum of both hands.  Overcounting inflates the station cycle time
    and leads to incorrect line balance recommendations."""
    from ddm_v2.services.simulation_service import _simo_adjusted_standard_time

    actions = [
        {"id": "a1", "description": "LH grab", "seconds": 0.50, "station_id": "ST-1",
         "is_simo": True, "simo_group_id": "sg-1"},
        {"id": "a2", "description": "RH inspect", "seconds": 1.20, "station_id": "ST-1",
         "is_simo": True, "simo_group_id": "sg-1"},
        {"id": "a3", "description": "Individual", "seconds": 0.80, "station_id": "ST-1",
         "is_simo": False, "simo_group_id": None},
    ]
    adjusted = _simo_adjusted_standard_time(actions)
    # sg-1: max(0.50, 1.20) = 1.20; individual: 0.80 → total = 2.00
    assert adjusted == pytest.approx(2.00, abs=0.01)


@pytest.mark.unit
def test_simo_adjusted_standard_time_skips_actions_without_group_id():
    """Actions marked is_simo=True but without simo_group_id cannot be
    deduplicated; they are counted individually (safe degradation)."""
    from ddm_v2.services.simulation_service import _simo_adjusted_standard_time

    actions = [
        {"id": "a1", "seconds": 1.0, "is_simo": True, "simo_group_id": None},
        {"id": "a2", "seconds": 2.0, "is_simo": True, "simo_group_id": None},
    ]
    # No deduplication possible → sum = 3.0
    assert _simo_adjusted_standard_time(actions) == pytest.approx(3.0, abs=0.01)
