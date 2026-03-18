from __future__ import annotations

import pytest


@pytest.mark.regression
def test_workspace_export_retains_index_string_and_trace(client, engineer_headers):
    save = client.put(
        "/api/v1/most/workspaces/proj-atlas",
        headers=engineer_headers,
        json={
            "steps": [
                {
                    "id": "step-reg-1",
                    "action": "Grab",
                    "primary_action": "Grab",
                    "object": "Screw",
                    "object_category": "Fastener",
                    "seq_type": "GENERAL",
                    "hand": "Right Hand",
                    "from_location": "Component Bin",
                    "to_location": "Chassis",
                    "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                }
            ],
            "wi_components": [],
            "selected_step_ids": [],
        },
    )
    assert save.status_code == 200

    exported = client.get("/api/v1/most/workspaces/proj-atlas/export", headers=engineer_headers)
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["steps"][0]["index_string"] == "A1 B0 G3 A1 B0 P3 A1"
    assert payload["actions"][0]["params"]["_most"]["most_code"] == "G"
    assert payload["mi_sentences"][0]["index_string"] == "A1 B0 G3 A1 B0 P3 A1"