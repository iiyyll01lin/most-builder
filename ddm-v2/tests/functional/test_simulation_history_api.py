from __future__ import annotations

import pytest


def _create_simulatable_sop(client, engineer_headers):
    create = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-atlas", "version_no": "V3.0", "actions": []},
    )
    assert create.status_code == 201
    sop_id = create.json()["id"]

    update = client.put(
        f"/api/v1/sop/versions/{sop_id}/actions",
        headers=engineer_headers,
        json=[
            {
                "seq_type": "GENERAL",
                "description": "Grab screw",
                "tmu": 18,
                "seconds": 0.65,
                "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                "station_id": "ST-1",
                "component": "Motherboard",
                "tool": "Torque Driver",
                "is_ctq": True,
                "primary_action": "Grab",
                "hand": "Right Hand",
                "object_category": "PCB",
                "glove_type": "ESD Glove",
                "frequency": 1,
            }
        ],
    )
    assert update.status_code == 200
    return sop_id


@pytest.mark.functional
def test_simulation_history_delete_and_clear_are_audited(client, engineer_headers, manager_headers):
    sop_id = _create_simulatable_sop(client, engineer_headers)

    simulate = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": "proj-atlas",
            "takt_time": 4.0,
            "stations": [
                {"id": "ST-1", "employee_id": "emp-eva", "sop_ids": [sop_id]},
            ],
        },
    )
    assert simulate.status_code == 200

    history = client.get("/api/v1/simulation/history?project_id=proj-atlas", headers=engineer_headers)
    assert history.status_code == 200
    assert history.json()["total"] == 1
    sim_id = history.json()["results"][0]["id"]

    denied_delete = client.delete(f"/api/v1/simulation/history/{sim_id}", headers=engineer_headers)
    assert denied_delete.status_code == 403

    delete_response = client.delete(f"/api/v1/simulation/history/{sim_id}", headers=manager_headers)
    assert delete_response.status_code == 204

    empty_history = client.get("/api/v1/simulation/history?project_id=proj-atlas", headers=engineer_headers)
    assert empty_history.status_code == 200
    assert empty_history.json()["total"] == 0

    simulate_again = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": "proj-atlas",
            "takt_time": 4.0,
            "stations": [
                {"id": "ST-1", "employee_id": "emp-eva", "sop_ids": [sop_id]},
            ],
        },
    )
    assert simulate_again.status_code == 200

    clear_response = client.delete("/api/v1/simulation/history", headers=manager_headers)
    assert clear_response.status_code == 204

    audit_response = client.get("/api/v1/audit/logs?entity_type=simulation-result", headers=manager_headers)
    assert audit_response.status_code == 200
    actions = {entry["action"] for entry in audit_response.json()}
    assert {"CREATE", "DELETE"}.issubset(actions)