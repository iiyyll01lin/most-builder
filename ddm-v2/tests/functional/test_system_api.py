from __future__ import annotations

import pytest


@pytest.mark.functional
def test_root_serves_full_validation_ui(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Phase 1 - Full Stack Demo" in response.text
    assert "/static/legacy_ui/app.jsx" in response.text
    assert "@babel/standalone" in response.text


@pytest.mark.functional
def test_control_console_route_remains_available(client):
    response = client.get("/control-console")
    assert response.status_code == 200
    assert "Release-Candidate Control Console" in response.text
    assert 'id="login-form"' in response.text


@pytest.mark.functional
def test_health_and_db_status_endpoints(client, manager_headers):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    status = client.get("/api/v1/db/status", headers=manager_headers)
    assert status.status_code == 200
    assert status.json()["file_exists"] is True
    assert status.json()["persistent_file"] == str(client.app.state.store.db_path)


@pytest.mark.functional
def test_db_save_and_load_report_active_store_path(client, manager_headers):
    save_response = client.post("/api/v1/db/save", headers=manager_headers)
    assert save_response.status_code == 200
    assert save_response.json()["path"] == str(client.app.state.store.db_path)

    load_response = client.post("/api/v1/db/load", headers=manager_headers)
    assert load_response.status_code == 200
    assert load_response.json()["path"] == str(client.app.state.store.db_path)


@pytest.mark.functional
def test_database_management_endpoints_enforce_manager_access_and_export_state(client, manager_headers, engineer_headers):
    export_denied = client.get("/api/v1/db/export", headers=engineer_headers)
    assert export_denied.status_code == 403

    save_denied = client.post("/api/v1/db/save", headers=engineer_headers)
    assert save_denied.status_code == 403

    load_denied = client.post("/api/v1/db/load", headers=engineer_headers)
    assert load_denied.status_code == 403

    export_response = client.get("/api/v1/db/export", headers=manager_headers)
    assert export_response.status_code == 200
    payload = export_response.json()
    assert "projects" in payload
    assert "users" in payload
    assert any(project["id"] == "proj-atlas" for project in payload["projects"])


@pytest.mark.functional
def test_db_reset_restores_default_state_and_audits_reset(client, manager_headers):
    create_response = client.post(
        "/api/v1/master/syntax",
        headers=manager_headers,
        json={"action_verb": "ResetTarget", "code_most": "I", "parameter_range": "I6", "tmu_value": 6},
    )
    assert create_response.status_code == 201

    reset_response = client.delete("/api/v1/db/reset", headers=manager_headers)
    assert reset_response.status_code == 200

    syntax_response = client.get("/api/v1/master/syntax", headers=manager_headers)
    assert syntax_response.status_code == 200
    assert all(item["action_verb"] != "ResetTarget" for item in syntax_response.json())

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200

    audit_response = client.get("/api/v1/audit/logs?entity_type=database", headers=manager_headers)
    assert audit_response.status_code == 200
    assert audit_response.json()[0]["action"] == "RESET"


@pytest.mark.functional
def test_audit_logs_are_scoped_to_the_current_user_for_non_managers(client, manager_headers, engineer_headers):
    manager_create = client.post(
        "/api/v1/master/syntax",
        headers=manager_headers,
        json={"action_verb": "ManagerOnly", "code_most": "I", "parameter_range": "I6", "tmu_value": 6},
    )
    assert manager_create.status_code == 201

    engineer_create = client.post(
        "/api/v1/master/syntax",
        headers=engineer_headers,
        json={"action_verb": "EngineerOnly", "code_most": "G", "parameter_range": "G1", "tmu_value": 3},
    )
    assert engineer_create.status_code == 201

    engineer_audit = client.get("/api/v1/audit/logs?entity_type=syntax", headers=engineer_headers)
    assert engineer_audit.status_code == 200
    descriptions = [entry["description"] for entry in engineer_audit.json()]
    assert any("EngineerOnly" in description for description in descriptions)
    assert all("ManagerOnly" not in description for description in descriptions)
