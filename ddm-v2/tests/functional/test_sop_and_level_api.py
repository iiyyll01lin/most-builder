from __future__ import annotations

import pytest


@pytest.mark.functional
def test_sop_action_update_sync_level_and_generate_graph(client, engineer_headers):
    create = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-orion", "version_no": "V2.0", "actions": []},
    )
    assert create.status_code == 201
    sop_id = create.json()["id"]

    actions_payload = [
        {
            "seq_type": "GENERAL",
            "description": "Grab screw and place to chassis",
            "tmu": 18,
            "seconds": 0.65,
            "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
            "station_id": "ST-1",
            "component": "Screw",
            "tool": "Torque Driver",
            "is_ctq": True,
            "primary_action": "Grab",
            "hand": "Right Hand",
            "object_category": "Fastener",
            "glove_type": "Finger Cot",
            "frequency": 2,
        },
        {
            "seq_type": "CONTROLLED",
            "description": "Inspect motherboard in fixture",
            "tmu": 19,
            "seconds": 0.68,
            "params": {"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
            "station_id": "ST-2",
            "component": "Motherboard",
            "tool": "Scanner",
            "is_ctq": True,
            "primary_action": "Inspect",
            "hand": "Right Hand",
            "object_category": "PCB",
            "glove_type": "ESD Glove",
            "frequency": 1,
        },
    ]
    update = client.put(f"/api/v1/sop/versions/{sop_id}/actions", headers=engineer_headers, json=actions_payload)
    assert update.status_code == 200
    assert len(update.json()["actions"]) == 2

    sync = client.post("/api/v1/level-system/sync", headers=engineer_headers, json={"project_id": "proj-orion", "sop_version_id": sop_id})
    assert sync.status_code == 200
    assert sync.json()["total_entries"] == 2

    level_entries = client.get("/api/v1/level-system/proj-orion", headers=engineer_headers)
    assert level_entries.status_code == 200
    entries = level_entries.json()["entries"]
    assert len(entries) == 2

    save = client.post(
        "/api/v1/level-system/save",
        headers=engineer_headers,
        json={
            "project_id": "proj-orion",
            "entries": [
                {"action_id": entries[0]["action_id"], "difficulty_factor": 1.1, "main_seq": "1", "machine_count": 1, "operator_count": 1},
                {"action_id": entries[1]["action_id"], "difficulty_factor": 1.0, "main_seq": "2", "cub_group": "C1", "machine_count": 2, "operator_count": 1},
            ],
        },
    )
    assert save.status_code == 200

    graph = client.post("/api/v1/level-system/generate-graph?project_id=proj-orion", headers=engineer_headers)
    assert graph.status_code == 200
    graph_payload = graph.json()
    assert len(graph_payload["nodes"]) == 2
    assert graph_payload["precedence_edges"][0]["type"] == "main"


@pytest.mark.functional
def test_missing_legacy_level_validation_endpoint_is_fixed(client, engineer_headers):
    response = client.post(
        "/api/v1/most/validate-level",
        headers=engineer_headers,
        json={"level": 3, "index_string": "A6 B0 G1 A3 B0 P1 A6"},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
