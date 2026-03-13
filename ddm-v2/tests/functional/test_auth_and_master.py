from __future__ import annotations

import pytest


@pytest.mark.functional
def test_login_success_and_profile(client):
    login = client.post("/api/v1/auth/login", json={"username": "engineer1", "password": "eng123"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["username"] == "engineer1"


@pytest.mark.functional
def test_operator_cannot_create_syntax(client):
    login = client.post("/api/v1/auth/login", json={"username": "operator1", "password": "op123"})
    token = login.json()["access_token"]
    response = client.post(
        "/api/v1/master/syntax",
        headers={"Authorization": f"Bearer {token}"},
        json={"action_verb": "Align", "code_most": "I", "parameter_range": "I6", "tmu_value": 6},
    )
    assert response.status_code == 403


@pytest.mark.functional
def test_manager_can_crud_syntax_and_audit(client, manager_headers):
    create_response = client.post(
        "/api/v1/master/syntax",
        headers=manager_headers,
        json={"action_verb": "Align", "code_most": "I", "parameter_range": "I6", "tmu_value": 6},
    )
    assert create_response.status_code == 201
    created = create_response.json()

    update_response = client.put(
        f"/api/v1/master/syntax/{created['id']}",
        headers=manager_headers,
        json={"action_verb": "Align", "code_most": "I", "parameter_range": "I10", "tmu_value": 10},
    )
    assert update_response.status_code == 200
    assert update_response.json()["parameter_range"] == "I10"

    delete_response = client.delete(f"/api/v1/master/syntax/{created['id']}", headers=manager_headers)
    assert delete_response.status_code == 204

    audit_response = client.get("/api/v1/audit/logs?entity_type=syntax", headers=manager_headers)
    assert audit_response.status_code == 200
    assert len(audit_response.json()) >= 3
