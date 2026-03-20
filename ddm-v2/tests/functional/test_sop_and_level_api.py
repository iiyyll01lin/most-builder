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


@pytest.mark.functional
def test_sop_status_workflow_enforces_role_and_visibility_rules(client, engineer_headers, manager_headers):
    operator_login = client.post("/api/v1/auth/login", json={"username": "operator1", "password": "op123"})
    assert operator_login.status_code == 200
    operator_headers = {"Authorization": f"Bearer {operator_login.json()['access_token']}"}

    create = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-atlas", "version_no": "V9.9", "actions": []},
    )
    assert create.status_code == 201
    sop_id = create.json()["id"]

    operator_list_before_publish = client.get("/api/v1/sop/versions?project_id=proj-atlas", headers=operator_headers)
    assert operator_list_before_publish.status_code == 200
    assert all(version["status"] == "Published" for version in operator_list_before_publish.json())
    assert sop_id not in {version["id"] for version in operator_list_before_publish.json()}

    operator_get_draft = client.get(f"/api/v1/sop/versions/{sop_id}", headers=operator_headers)
    assert operator_get_draft.status_code == 403

    operator_review = client.put(
        f"/api/v1/sop/versions/{sop_id}/status",
        headers=operator_headers,
        json={"status": "Reviewed"},
    )
    assert operator_review.status_code == 403

    reviewed = client.put(
        f"/api/v1/sop/versions/{sop_id}/status",
        headers=engineer_headers,
        json={"status": "Reviewed"},
    )
    assert reviewed.status_code == 200
    reviewed_payload = reviewed.json()
    assert reviewed_payload["status"] == "Reviewed"
    assert reviewed_payload["reviewed_by"] == "usr-eng-1"
    assert reviewed_payload["reviewed_at"] is not None

    update_reviewed_actions = client.put(
        f"/api/v1/sop/versions/{sop_id}/actions",
        headers=engineer_headers,
        json=[{"description": "Should fail"}],
    )
    assert update_reviewed_actions.status_code == 400

    engineer_publish = client.put(
        f"/api/v1/sop/versions/{sop_id}/status",
        headers=engineer_headers,
        json={"status": "Published"},
    )
    assert engineer_publish.status_code == 403

    published = client.put(
        f"/api/v1/sop/versions/{sop_id}/status",
        headers=manager_headers,
        json={"status": "Published"},
    )
    assert published.status_code == 200
    published_payload = published.json()
    assert published_payload["status"] == "Published"
    assert published_payload["published_by"] == "usr-admin"
    assert published_payload["published_at"] is not None

    revert_to_draft = client.put(
        f"/api/v1/sop/versions/{sop_id}/status",
        headers=manager_headers,
        json={"status": "Draft"},
    )
    assert revert_to_draft.status_code == 400

    operator_get_published = client.get(f"/api/v1/sop/versions/{sop_id}", headers=operator_headers)
    assert operator_get_published.status_code == 200
    assert operator_get_published.json()["status"] == "Published"
