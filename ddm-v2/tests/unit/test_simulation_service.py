from __future__ import annotations

import pytest

from ddm_v2.services.simulation_service import run_line_balance


@pytest.mark.unit
def test_run_line_balance_calculates_cycle_time_and_alerts():
    result = run_line_balance(
        project_id="proj-atlas",
        takt_time=4.0,
        station_assignments=[
            {"id": "ST-1", "name": "Station 1", "employee_id": "emp-eva"},
            {"id": "ST-2", "name": "Station 2", "employee_id": "emp-li"},
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
