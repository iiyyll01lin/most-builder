from __future__ import annotations

import pytest

from ddm_v2.schemas import MOSTStep
from ddm_v2.services.most_service import calculate_workflow


@pytest.mark.regression
def test_reference_most_calculation_regression(regression_fixture):
    steps = [MOSTStep(**step) for step in regression_fixture["steps"]]
    result = calculate_workflow(steps)

    assert result.total_tmu == regression_fixture["expected"]["total_tmu"]
    assert result.total_seconds == regression_fixture["expected"]["total_seconds"]
    assert result.breakdown[0].index_string == regression_fixture["expected"]["first_index_string"]
    assert result.breakdown[1].auto_sentence == regression_fixture["expected"]["second_auto_sentence"]


@pytest.mark.regression
def test_return_a_cm_above_65_maps_to_a32_not_a24(regression_fixture):
    """Regression lock for B1 fix: return_a_cm=70 must produce A32, not A24.

    The third fixture step uses return_a_cm=70.0 without an explicit A3 param,
    so the index string final segment must be A32.
    """
    steps = [MOSTStep(**step) for step in regression_fixture["steps"]]
    result = calculate_workflow(steps)

    third_index = result.breakdown[2].index_string
    assert third_index == regression_fixture["expected"]["third_index_string"], (
        f"Expected {regression_fixture['expected']['third_index_string']!r}, got {third_index!r}. "
        "If this regresses, check _lookup_a_index threshold (must be 65 cm, not 120 cm)."
    )


# ---------------------------------------------------------------------------
# Phase 3 regression tests: Level System main/sub/cub integrity after
# the new 1P2M and skill-certification changes
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_level_system_main_sub_cub_graph_unaffected_by_simulation_changes():
    """Regression lock: build_precedence_graph must continue to correctly
    model main→sub→cub dependency chains after the simulation service
    received 1P2M and skill-certification updates.  A cycle is only expected
    if main_seq values deliberately form a loop."""
    from ddm_v2.services.level_service import build_precedence_graph

    entries = [
        {
            "action_id": "act-main-1", "description": "Main step A", "ct_seconds": 3.0,
            "difficulty_factor": 1.0, "adjusted_ct": 3.0, "effective_cub_ct": None,
            "main_seq": "1", "order_seq": None, "cub_group": None,
            "number_tag": None, "number_count": None, "machine_count": 1,
            "operator_count": 1, "status_label": None, "sort_order": 0,
        },
        {
            "action_id": "act-main-2", "description": "Main step B", "ct_seconds": 2.0,
            "difficulty_factor": 1.0, "adjusted_ct": 2.0, "effective_cub_ct": None,
            "main_seq": "2", "order_seq": None, "cub_group": "CG1",
            "number_tag": None, "number_count": None, "machine_count": 2,
            "operator_count": 1, "status_label": None, "sort_order": 1,
        },
        {
            "action_id": "act-cub-1", "description": "Cub step", "ct_seconds": 1.0,
            "difficulty_factor": 1.0, "adjusted_ct": 1.0, "effective_cub_ct": 0.5,
            "main_seq": "3", "order_seq": None, "cub_group": "CG1",
            "number_tag": None, "number_count": None, "machine_count": 2,
            "operator_count": 1, "status_label": None, "sort_order": 2,
        },
    ]
    graph = build_precedence_graph(entries)

    # No cycles expected in a valid sequential DAG
    assert graph["cycle_errors"] == []
    # Precedence edges: main-1 → main-2 → cub-1 (sorted by main_seq 1,2,3)
    from_ids = [e["from"] for e in graph["precedence_edges"]]
    to_ids = [e["to"] for e in graph["precedence_edges"]]
    assert "act-main-1" in from_ids
    assert "act-cub-1" in to_ids
    # Cub group must still include both act-main-2 and act-cub-1
    assert set(graph["cub_groups"]["CG1"]) == {"act-main-2", "act-cub-1"}


@pytest.mark.regression
def test_1p2m_does_not_break_existing_balance_rate_formula_without_machine_count():
    """When machine_count is absent (defaults to 1), run_line_balance must
    produce the identical result as the pre-1P2M implementation.  This
    regression ensures backward compatibility for station assignments that
    do not set machine_count."""
    from ddm_v2.services.simulation_service import run_line_balance

    result = run_line_balance(
        project_id="proj-atlas",
        takt_time=4.0,
        station_assignments=[
            # No machine_count key — must default to 1
            {"id": "ST-1", "name": "Station 1", "employee_id": "emp-eva", "sop_ids": ["sop-1"]},
            {"id": "ST-2", "name": "Station 2", "employee_id": "emp-li", "sop_ids": ["sop-1"]},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.2, "certifications": []},
            {"id": "emp-li", "name": "Li", "skill_level": "Novice", "efficiency_factor": 0.8, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-atlas",
                "actions": [
                    {"id": "act-1", "description": "Fasten screw", "seconds": 1.2, "station_id": "ST-1",
                     "object_category": "Fastener", "glove_type": None, "component": "Screw",
                     "is_ctq": True, "required_skill": None},
                    {"id": "act-2", "description": "Inspect board", "seconds": 4.8, "station_id": "ST-2",
                     "object_category": "PCB", "glove_type": None, "component": "Motherboard",
                     "is_ctq": True, "required_skill": None},
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[{"id": "ion-pcb", "object_category": "PCB", "object_name": "Motherboard", "note": "ESD"}],
    )
    # Identical expectations as the existing test_run_line_balance_calculates_cycle_time_and_alerts
    assert result.bottleneck_station == "ST-2"
    assert result.cycle_time == pytest.approx(6.0, abs=0.01)
    assert result.uph == 600
    assert any("CTQ work to novice operator" in alert for alert in result.alerts)
    # machine_effective_time should be None when machine_count==1
    st1 = next(s for s in result.station_results if s.id == "ST-1")
    assert st1.machine_count == 1
    assert st1.machine_effective_time is None

