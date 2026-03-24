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

    exported = client.get("/api/v1/most/workspaces/proj-atlas/export?sop_version_id=sop-atlas-v1", headers=engineer_headers)
    assert exported.status_code == 200
    assert exported.json()["steps"][0]["index_string"] == "A1 B0 G3 A1 B0 P3 A1"

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
def test_workspace_get_returns_empty_workspace_for_new_project(client, engineer_headers):
    """A GET before any save must return a valid empty workspace structure."""
    response = client.get("/api/v1/most/workspaces/proj-orion", headers=engineer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["steps"] == []
    assert body["wi_components"] == []
    assert body["project_id"] == "proj-orion"
    assert body["summary"]["total_tmu"] == 0


@pytest.mark.functional
def test_workspace_get_returns_404_for_unknown_project(client, engineer_headers):
    """A workspace GET for a non-existent project must return 404."""
    response = client.get("/api/v1/most/workspaces/proj-not-real", headers=engineer_headers)
    assert response.status_code == 404


@pytest.mark.functional
def test_workspace_save_requires_engineer_or_manager(client):
    """Operators must not be able to save workspaces."""
    login = client.post("/api/v1/auth/login", json={"username": "operator1", "password": "op123"})
    op_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.put(
        "/api/v1/most/workspaces/proj-atlas",
        headers=op_headers,
        json={"steps": [], "wi_components": [], "selected_step_ids": []},
    )
    assert response.status_code == 403


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


@pytest.mark.functional
def test_level_save_propagates_into_matching_most_workspace(client, engineer_headers):
    create_sop = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-orion", "version_no": "V5", "actions": []},
    )
    assert create_sop.status_code == 201
    sop_id = create_sop.json()["id"]

    update_actions = client.put(
        f"/api/v1/sop/versions/{sop_id}/actions",
        headers=engineer_headers,
        json=[
            {
                "id": "sync-act-1",
                "seq_type": "GENERAL",
                "description": "Install bracket",
                "tmu": 20,
                "seconds": 0.72,
                "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                "station_id": "ST-01",
            }
        ],
    )
    assert update_actions.status_code == 200

    workspace_save = client.put(
        "/api/v1/most/workspaces/proj-orion",
        headers=engineer_headers,
        json={
            "sop_version_id": sop_id,
            "steps": [
                {
                    "id": "sync-act-1",
                    "action_id": "sync-act-1",
                    "action": "Install",
                    "primary_action": "Install",
                    "object": "Bracket",
                    "object_category": "Component",
                    "seq_type": "GENERAL",
                    "hand": "Right Hand",
                    "from_location": "Bin",
                    "to_location": "Fixture",
                    "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                    "frequency": 1,
                }
            ],
            "wi_components": [],
            "selected_step_ids": ["sync-act-1"],
        },
    )
    assert workspace_save.status_code == 200

    sync_level = client.post(
        "/api/v1/level-system/sync",
        headers=engineer_headers,
        json={"project_id": "proj-orion", "sop_version_id": sop_id},
    )
    assert sync_level.status_code == 200

    save_level = client.post(
        "/api/v1/level-system/save",
        headers=engineer_headers,
        json={
            "project_id": "proj-orion",
            "sop_version_id": sop_id,
            "entries": [
                {
                    "action_id": "sync-act-1",
                    "difficulty_factor": 1.2,
                    "main_seq": "3",
                    "operator_count": 1,
                    "machine_count": 1,
                }
            ],
        },
    )
    assert save_level.status_code == 200

    workspace = client.get(f"/api/v1/most/workspaces/proj-orion?sop_version_id={sop_id}", headers=engineer_headers)
    assert workspace.status_code == 200
    action = workspace.json()["actions"][0]
    assert action["level_tag"] == "MAIN-3"
    assert action["params"]["_level"]["difficulty_factor"] == 1.2
