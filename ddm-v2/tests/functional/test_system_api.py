from __future__ import annotations

import pytest


@pytest.mark.functional
def test_root_serves_full_validation_ui(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Phase 1 - Full Stack Demo" in response.text
    assert "/static/frontend-build/app.js" in response.text
    assert "@babel/standalone" not in response.text


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
def test_frontend_build_assets_are_served(client):
    shell = client.get("/")
    assert "/static/frontend-build/app.js" in shell.text


@pytest.mark.functional
def test_db_save_and_load_report_active_store_path(client, manager_headers):
    save_response = client.post("/api/v1/db/save", headers=manager_headers)
    assert save_response.status_code == 200
    assert save_response.json()["path"] == str(client.app.state.store.db_path)

    load_response = client.post("/api/v1/db/load", headers=manager_headers)
    assert load_response.status_code == 200
    assert load_response.json()["path"] == str(client.app.state.store.db_path)
