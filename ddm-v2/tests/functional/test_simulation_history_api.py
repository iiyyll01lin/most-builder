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


@pytest.mark.functional
def test_simulation_history_limit_clamps_results(client, engineer_headers, manager_headers):
    """The limit parameter must be clamped between 1 and 200."""
    sop_id = _create_simulatable_sop(client, engineer_headers)

    # Create 3 simulation results
    for _ in range(3):
        client.post(
            "/api/v1/simulation/line-balance",
            headers=engineer_headers,
            json={
                "project_id": "proj-atlas",
                "takt_time": 4.0,
                "stations": [{"id": "ST-1", "employee_id": "emp-eva", "sop_ids": [sop_id]}],
            },
        )

    # limit=1 should return at most 1 result
    resp_one = client.get("/api/v1/simulation/history?limit=1", headers=engineer_headers)
    assert resp_one.status_code == 200
    assert len(resp_one.json()["results"]) == 1
    assert resp_one.json()["total"] == 3

    # limit=0 is invalid; clamped to 1 — should not return an empty list
    resp_zero = client.get("/api/v1/simulation/history?limit=0", headers=engineer_headers)
    assert resp_zero.status_code == 200
    assert len(resp_zero.json()["results"]) >= 1

    # limit=999 is clamped to 200; all results should still be included
    resp_large = client.get("/api/v1/simulation/history?limit=999", headers=engineer_headers)
    assert resp_large.status_code == 200
    assert resp_large.json()["total"] == len(resp_large.json()["results"])


@pytest.mark.functional
def test_reassign_action_between_stations(client, engineer_headers, manager_headers):
    """Moving an action to another station must persist and be rejected for wrong source."""
    sop_id = _create_simulatable_sop(client, engineer_headers)

    # Get the action id we just created
    sop = client.get(f"/api/v1/sop/versions/{sop_id}", headers=engineer_headers)
    action_id = sop.json()["actions"][0]["id"]

    # Reassign from ST-1 to ST-2
    resp = client.post(
        "/api/v1/simulation/reassign-action",
        headers=engineer_headers,
        json={"action_id": action_id, "from_station_id": "ST-1", "to_station_id": "ST-2"},
    )
    assert resp.status_code == 200
    assert resp.json()["action"]["station_id"] == "ST-2"

    # Attempting to reassign from the old station (ST-1) must now fail
    resp_wrong = client.post(
        "/api/v1/simulation/reassign-action",
        headers=engineer_headers,
        json={"action_id": action_id, "from_station_id": "ST-1", "to_station_id": "ST-3"},
    )
    assert resp_wrong.status_code == 400

    # Attempting to reassign a non-existent action must return 404
    resp_missing = client.post(
        "/api/v1/simulation/reassign-action",
        headers=engineer_headers,
        json={"action_id": "act-ghost", "from_station_id": "ST-1", "to_station_id": "ST-2"},
    )
    assert resp_missing.status_code == 404


# ---------------------------------------------------------------------------
# Phase 2 hardening: takt_time and missing-employee guard
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_simulation_rejects_zero_takt_time(client, engineer_headers):
    """A takt_time of 0 is physically meaningless; the API must reject it with
    a 422 Unprocessable Entity so the PE knows to provide a valid cycle target."""
    response = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": "proj-atlas",
            "takt_time": 0,
            "stations": [{"id": "ST-1", "employee_id": "emp-eva", "sop_ids": []}],
        },
    )
    assert response.status_code == 422


@pytest.mark.functional
def test_simulation_rejects_negative_takt_time(client, engineer_headers):
    """Negative takt time is semantically impossible and must be rejected."""
    response = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": "proj-atlas",
            "takt_time": -1.0,
            "stations": [{"id": "ST-1", "employee_id": "emp-eva", "sop_ids": []}],
        },
    )
    assert response.status_code == 422


@pytest.mark.functional
def test_simulation_returns_422_for_unknown_employee_in_station(client, engineer_headers):
    """If a station assignment uses an employee_id that not in the roster, the
    API must return 422 with a clear, actionable error message rather than
    silently dropping the station and producing wrong cycle time/UPH data."""
    response = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": "proj-atlas",
            "takt_time": 4.0,
            "stations": [
                {"id": "ST-1", "employee_id": "emp-does-not-exist", "sop_ids": []},
            ],
        },
    )
    assert response.status_code == 422
    assert "emp-does-not-exist" in response.json()["detail"]
