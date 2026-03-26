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


# ---------------------------------------------------------------------------
# Phase 3 business-logic hardening tests (IE/PE domain rules)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ion_fan_required_for_lcd_via_object_category():
    """When an action's object_category matches an ion_fan_binding category,
    ion_fan_required must be True for that station.
    Domain rule: LCD (高單價物料 category) mandates ion fan activation."""
    result = run_line_balance(
        project_id="proj-x",
        takt_time=10.0,
        station_assignments=[
            {"id": "ST-1", "name": "LCD Station", "employee_id": "emp-eva", "sop_ids": []},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.0, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-x",
                "actions": [
                    {
                        "id": "act-1",
                        "description": "Place LCD",
                        "seconds": 2.0,
                        "station_id": "ST-1",
                        "object_category": "高單價物料",
                        "component": "LCD",
                        "glove_type": None,
                        "is_ctq": False,
                    }
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[
            {"id": "ion-lcd", "object_category": "高單價物料", "object_name": "LCD", "note": "ESD"},
        ],
    )
    st = result.station_results[0]
    assert st.ion_fan_required is True
    assert "LCD" in st.ion_fan_targets


@pytest.mark.unit
def test_ion_fan_required_for_dimm_via_object_name():
    """DIMM (RAM) must trigger ion_fan_required via exact object_name match."""
    result = run_line_balance(
        project_id="proj-x",
        takt_time=10.0,
        station_assignments=[
            {"id": "ST-1", "name": "DIMM Station", "employee_id": "emp-eva", "sop_ids": []},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.0, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-x",
                "actions": [
                    {
                        "id": "act-1",
                        "description": "Insert DIMM",
                        "seconds": 1.5,
                        "station_id": "ST-1",
                        "object_category": "記憶體",
                        "component": "DIMM",
                        "glove_type": None,
                        "is_ctq": True,
                    }
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[
            {"id": "ion-dimm", "object_category": "記憶體", "object_name": "DIMM", "note": "ESD"},
        ],
    )
    st = result.station_results[0]
    assert st.ion_fan_required is True
    assert "DIMM" in st.ion_fan_targets


@pytest.mark.unit
def test_ion_fan_not_required_for_non_esd_parts():
    """Chassis (機殼) has no ion fan binding; ion_fan_required must be False."""
    result = run_line_balance(
        project_id="proj-x",
        takt_time=10.0,
        station_assignments=[
            {"id": "ST-1", "name": "Chassis Station", "employee_id": "emp-eva", "sop_ids": []},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.0, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-x",
                "actions": [
                    {
                        "id": "act-1",
                        "description": "Place Chassis",
                        "seconds": 3.0,
                        "station_id": "ST-1",
                        "object_category": "機殼",
                        "component": "Chassis",
                        "glove_type": None,
                        "is_ctq": False,
                    }
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[
            {"id": "ion-lcd", "object_category": "高單價物料", "object_name": "LCD", "note": "ESD"},
        ],
    )
    st = result.station_results[0]
    assert st.ion_fan_required is False
    assert st.ion_fan_targets == []


@pytest.mark.unit
def test_glove_assignment_for_mlb_returns_half_finger_gloves():
    """MLB (主板/MLB category) must produce '兩只半指手套' via glove rule lookup."""
    result = run_line_balance(
        project_id="proj-x",
        takt_time=10.0,
        station_assignments=[
            {"id": "ST-1", "name": "MLB Station", "employee_id": "emp-eva", "sop_ids": []},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.0, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-x",
                "actions": [
                    {
                        "id": "act-1",
                        "description": "Install MLB",
                        "seconds": 3.0,
                        "station_id": "ST-1",
                        "object_category": "主板/MLB",
                        "component": "MLB",
                        "glove_type": None,
                        "is_ctq": True,
                    }
                ],
            }
        ],
        glove_rules=[
            {"id": "glv-mlb", "object_category": "主板/MLB", "action": "*", "glove_type": "兩只半指手套"},
            {"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"},
        ],
        ion_fan_bindings=[],
    )
    st = result.station_results[0]
    assert "兩只半指手套" in st.required_gloves


@pytest.mark.unit
def test_skill_certification_alert_for_uncertified_operator():
    """When an action requires skill 'FATP01' (screw driving) and the operator
    lacks that certification, a skill-mismatch alert must appear in both
    station skill_alerts and the top-level alerts list."""
    from ddm_v2.services.simulation_service import check_skill_certification

    action = {"id": "act-1", "description": "Tighten screw", "required_skill": "FATP01"}
    employee_without_cert = {"id": "emp-li", "name": "Li", "skill_level": "Novice", "certifications": []}
    employee_with_cert = {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "certifications": ["FATP01"]}

    assert check_skill_certification(action, employee_without_cert) is not None
    assert "FATP01" in check_skill_certification(action, employee_without_cert)
    assert check_skill_certification(action, employee_with_cert) is None


@pytest.mark.unit
def test_skill_certification_no_alert_for_action_without_required_skill():
    """Actions with no required_skill should never produce a skill alert."""
    from ddm_v2.services.simulation_service import check_skill_certification

    action_no_skill = {"id": "act-2", "description": "Move part", "required_skill": None}
    employee = {"id": "emp-li", "name": "Li", "skill_level": "Novice", "certifications": []}
    assert check_skill_certification(action_no_skill, employee) is None


@pytest.mark.unit
def test_skill_certification_backward_compat_non_novice_empty_certs():
    """Non-novice employees with an empty certifications list are assumed to be
    universally qualified (backward compatibility for pre-certification records).
    A novice with empty certifications is NOT assumed qualified."""
    from ddm_v2.services.simulation_service import check_skill_certification

    action = {"id": "act-1", "description": "Tighten screw", "required_skill": "FATP01"}
    expert_no_certs = {"id": "emp-x", "name": "X", "skill_level": "Expert", "certifications": []}
    novice_no_certs = {"id": "emp-y", "name": "Y", "skill_level": "Novice", "certifications": []}

    assert check_skill_certification(action, expert_no_certs) is None
    assert check_skill_certification(action, novice_no_certs) is not None


@pytest.mark.unit
def test_skill_cert_alert_in_run_line_balance():
    """End-to-end: run_line_balance must propagate skill_alerts to station results
    and to the top-level alerts when an operator lacks a required certification."""
    result = run_line_balance(
        project_id="proj-x",
        takt_time=10.0,
        station_assignments=[
            {"id": "ST-1", "name": "Screw Station", "employee_id": "emp-li", "sop_ids": []},
        ],
        employees=[
            {"id": "emp-li", "name": "Li", "skill_level": "Novice", "efficiency_factor": 0.8, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-x",
                "actions": [
                    {
                        "id": "act-1",
                        "description": "Tighten torque screw",
                        "seconds": 1.0,
                        "station_id": "ST-1",
                        "object_category": "Fastener",
                        "component": "Screw",
                        "glove_type": None,
                        "is_ctq": True,
                        "required_skill": "FATP01",
                    }
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[],
    )
    assert result.station_results[0].skill_alerts
    assert any("FATP01" in alert for alert in result.station_results[0].skill_alerts)
    assert any("FATP01" in alert for alert in result.alerts)


@pytest.mark.unit
def test_1p2m_machine_count_reduces_bottleneck_contribution():
    """1 Person 2 Machines (machine_count=2) must halve the operator's bottleneck
    contribution.  Without this, the cycle_time would be distorted upward and UPH
    would be incorrectly halved.

    Setup:
    - ST-1 (1P2M, machine_count=2): standard_time=8s, efficiency=1.0 → actual=8s
      machine_effective_time = 8 / 2 = 4s  ← used for bottleneck
    - ST-2 (1P1M): standard_time=5s, efficiency=1.0 → actual=5s
    Expected: cycle_time = max(4, 5) = 5s  (ST-2 is bottleneck, not ST-1)
    """
    result = run_line_balance(
        project_id="proj-x",
        takt_time=10.0,
        station_assignments=[
            {"id": "ST-1", "name": "1P2M Station", "employee_id": "emp-eva", "sop_ids": [], "machine_count": 2},
            {"id": "ST-2", "name": "Normal Station", "employee_id": "emp-noah", "sop_ids": [], "machine_count": 1},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.0, "certifications": []},
            {"id": "emp-noah", "name": "Noah", "skill_level": "Proficient", "efficiency_factor": 1.0, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-x",
                "actions": [
                    {"id": "act-1", "description": "Machine op", "seconds": 8.0, "station_id": "ST-1",
                     "object_category": "PCB", "component": "Board", "glove_type": None, "is_ctq": False},
                    {"id": "act-2", "description": "Manual op", "seconds": 5.0, "station_id": "ST-2",
                     "object_category": "PCB", "component": "Board", "glove_type": None, "is_ctq": False},
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[],
    )
    # Machine effective time for ST-1 = 8/2 = 4.0; ST-2 = 5.0
    assert result.cycle_time == pytest.approx(5.0, abs=0.01)
    assert result.bottleneck_station == "ST-2"
    # ST-1 machine_effective_time should be 4.0
    st1 = next(s for s in result.station_results if s.id == "ST-1")
    assert st1.machine_count == 2
    assert st1.machine_effective_time == pytest.approx(4.0, abs=0.01)


@pytest.mark.unit
def test_1p2m_balance_rate_not_distorted():
    """Balance rate with 1P2M must account for machine parallelism.
    If both stations have machine_effective_time=3.0 and cycle_time=3.0,
    balance_rate = 1.0 (perfect balance)."""
    result = run_line_balance(
        project_id="proj-x",
        takt_time=10.0,
        station_assignments=[
            {"id": "ST-1", "name": "1P2M", "employee_id": "emp-eva", "sop_ids": [], "machine_count": 2},
            {"id": "ST-2", "name": "1P1M", "employee_id": "emp-noah", "sop_ids": [], "machine_count": 1},
        ],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.0, "certifications": []},
            {"id": "emp-noah", "name": "Noah", "skill_level": "Proficient", "efficiency_factor": 1.0, "certifications": []},
        ],
        sop_versions=[
            {
                "id": "sop-1",
                "project_id": "proj-x",
                "actions": [
                    {"id": "act-1", "description": "Machine op", "seconds": 6.0, "station_id": "ST-1",
                     "object_category": "Base", "component": "Part", "glove_type": None, "is_ctq": False},
                    {"id": "act-2", "description": "Manual op", "seconds": 3.0, "station_id": "ST-2",
                     "object_category": "Base", "component": "Part", "glove_type": None, "is_ctq": False},
                ],
            }
        ],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[],
    )
    # ST-1: actual=6s, machine_effective=3s.  ST-2: actual=3s.
    # cycle_time = max(3, 3) = 3.  total_actual = 3+3 = 6.  balance_rate = 6/(3*2) = 1.0
    assert result.cycle_time == pytest.approx(3.0, abs=0.01)
    assert result.balance_rate == pytest.approx(1.0, abs=0.01)


@pytest.mark.unit
def test_ion_fan_o1_lookup_with_large_action_count():
    """Ion fan lookup must complete without timeout or O(n²) degradation
    even when station has many actions (>5000 smoke test).
    With the O(1) pre-indexed lookup, this should complete in < 2 seconds."""
    import time

    large_actions = [
        {
            "id": f"act-{i}",
            "description": f"Step {i}",
            "seconds": 0.01,
            "station_id": "ST-1",
            "object_category": "機殼",  # no ion fan binding → fast path
            "component": f"Part-{i}",
            "glove_type": None,
            "is_ctq": False,
        }
        for i in range(5001)
    ]
    start = time.monotonic()
    result = run_line_balance(
        project_id="proj-x",
        takt_time=9999.0,
        station_assignments=[{"id": "ST-1", "name": "Big Station", "employee_id": "emp-eva", "sop_ids": []}],
        employees=[
            {"id": "emp-eva", "name": "Eva", "skill_level": "Expert", "efficiency_factor": 1.0, "certifications": []},
        ],
        sop_versions=[{"id": "sop-big", "project_id": "proj-x", "actions": large_actions}],
        glove_rules=[{"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"}],
        ion_fan_bindings=[
            {"id": "ion-lcd", "object_category": "高單價物料", "object_name": "LCD", "note": "ESD"},
            {"id": "ion-dimm", "object_category": "記憶體", "object_name": "DIMM", "note": "ESD"},
            {"id": "ion-cpu", "object_category": "處理器", "object_name": "CPU", "note": "ESD"},
        ],
    )
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"Ion fan O(1) lookup took {elapsed:.2f}s — possible O(n²) regression"
    assert result.station_results[0].ion_fan_required is False  # no LCD/DIMM/CPU actions
