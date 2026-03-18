from __future__ import annotations

import pytest


@pytest.mark.functional
def test_most_workspace_roundtrip_export_and_import(client, engineer_headers):
    save = client.put(
        "/api/v1/most/workspaces/proj-atlas",
        headers=engineer_headers,
        json={
            "sop_version_id": "sop-atlas-v1",
            "steps": [
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
                }
            ],
            "wi_components": [
                {"id": "wi-1", "name": "Fastener WI", "key_parts": "SCREW", "stepIds": ["step-1"]}
            ],
            "selected_step_ids": ["step-1"],
        },
    )
    assert save.status_code == 200
    saved = save.json()
    assert saved["actions"][0]["params"]["_most"]["most_code"] == "G"
    assert saved["wi_components"][0]["total_seconds"] > 0
    assert saved["mi_sentences"][0]["text"]

    exported = client.get("/api/v1/most/workspaces/proj-atlas/export?sop_version_id=sop-atlas-v1", headers=engineer_headers)
    assert exported.status_code == 200
    assert exported.json()["steps"][0]["index_string"] == "A1 B0 G3 A1 B0 P3 A1"
    assert exported.json()["mi_sentences"][0]["most_code"] == "G"

    imported = client.post(
        "/api/v1/most/workspaces/proj-atlas/import",
        headers=engineer_headers,
        json={
            "sop_version_id": "sop-atlas-v1",
            "steps": exported.json()["steps"],
            "wiComponents": exported.json()["wi_components"],
            "selected_step_ids": ["step-1"],
        },
    )
    assert imported.status_code == 200
    assert imported.json()["summary"]["step_count"] == 1


@pytest.mark.functional
def test_workspace_actions_can_be_saved_into_sop_with_trace_fields(client, engineer_headers):
    workspace = client.put(
        "/api/v1/most/workspaces/proj-orion",
        headers=engineer_headers,
        json={
            "steps": [
                {
                    "id": "step-ctl",
                    "action": "Inspect",
                    "primary_action": "Inspect",
                    "object": "Motherboard",
                    "object_category": "PCB",
                    "seq_type": "CONTROLLED",
                    "hand": "Right Hand",
                    "from_location": "Fixture",
                    "to_location": "Fixture",
                    "params": {"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
                    "frequency": 1,
                }
            ],
            "wi_components": [],
            "selected_step_ids": [],
        },
    )
    assert workspace.status_code == 200

    create = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-orion", "version_no": "V2.1", "actions": []},
    )
    sop_id = create.json()["id"]

    update = client.put(
        f"/api/v1/sop/versions/{sop_id}/actions",
        headers=engineer_headers,
        json=workspace.json()["actions"],
    )
    assert update.status_code == 200
    action = update.json()["actions"][0]
    assert action["params"]["_most"]["most_code"] == "I"
    assert action["params"]["_most"]["step_id"] == "step-ctl"