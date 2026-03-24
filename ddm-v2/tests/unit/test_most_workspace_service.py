from __future__ import annotations

import pytest

from ddm_v2.services.most_workspace_service import build_workspace_snapshot


@pytest.mark.unit
def test_build_workspace_snapshot_includes_most_trace_and_component_totals():
    snapshot = build_workspace_snapshot(
        project_id="proj-atlas",
        sop_version_id="sop-atlas-v1",
        raw_steps=[
            {
                "id": "step-1",
                "action": "Grab",
                "primary_action": "Grab",
                "object": "Screw",
                "object_category": "Fastener",
                "seq_type": "GENERAL",
                "hand": "Right Hand",
                "from_location": "Component Bin",
                "to_location": "Chassis",
                "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                "frequency": 2,
                "is_ctq": True,
            },
            {
                "id": "step-2",
                "action": "Inspect",
                "primary_action": "Inspect",
                "object": "Motherboard",
                "object_category": "PCB",
                "seq_type": "CONTROLLED",
                "hand": "Right Hand",
                "from_location": "Fixture",
                "to_location": "Fixture",
                "params": {"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
            },
        ],
        raw_wi_components=[
            {"id": "wi-1", "name": "DIMM WI", "stepIds": ["step-1", "step-2"], "key_parts": "DIMM"}
        ],
        selected_step_ids=["step-1"],
        workspace_id="mostws-1",
    )

    assert snapshot["summary"]["step_count"] == 2
    assert snapshot["summary"]["component_count"] == 1
    assert snapshot["actions"][0]["params"]["_most"]["most_code"] == "G"
    assert snapshot["actions"][0]["params"]["_most"]["index_string"] == "A1 B0 G3 A1 B0 P3 A1"
    assert snapshot["wi_components"][0]["total_tmu"] == sum(step["tmu"] for step in snapshot["steps"])
    assert snapshot["wi_components"][0]["step_count"] == 2
