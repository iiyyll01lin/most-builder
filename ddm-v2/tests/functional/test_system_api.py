from __future__ import annotations

import pytest


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
