"""Functional tests for the BFF (Backend-For-Frontend) aggregator endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.functional
def test_bff_dashboard_returns_all_sections(client, engineer_headers):
    """GET /bff/dashboard/{project_id} must return project, sop_versions, workspace,
    level_system, and precedence_graph sections in a single response."""
    response = client.get("/api/v1/bff/dashboard/proj-atlas", headers=engineer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["project"]["id"] == "proj-atlas"
    assert isinstance(body["sop_versions"], list)
    assert "workspace" in body
    assert body["workspace"]["project_id"] == "proj-atlas"
    assert "level_system" in body
    assert "total_count" in body["level_system"]
    assert "precedence_graph" in body  # may be None for empty project


@pytest.mark.functional
def test_bff_dashboard_returns_404_for_unknown_project(client, engineer_headers):
    """BFF dashboard for a non-existent project must return 404 with structured error."""
    response = client.get("/api/v1/bff/dashboard/proj-does-not-exist", headers=engineer_headers)
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "NOT_FOUND"
    assert "message" in body


@pytest.mark.functional
def test_bff_dashboard_requires_authentication(client):
    """Unauthenticated requests to the BFF endpoint must be rejected."""
    response = client.get("/api/v1/bff/dashboard/proj-atlas")
    assert response.status_code in (401, 403)


@pytest.mark.functional
def test_bff_dashboard_sop_summaries_omit_full_action_list(client, engineer_headers):
    """SOP summaries in the BFF response must include action_count but NOT the full actions list,
    to keep the response payload lean."""
    create = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={
            "project_id": "proj-atlas",
            "version_no": "V-BFF-1",
            "actions": [
                {
                    "seq_type": "GENERAL",
                    "description": "Test action",
                    "tmu": 10,
                    "seconds": 0.36,
                    "params": {},
                    "station_id": "ST-1",
                }
            ],
        },
    )
    assert create.status_code == 201

    response = client.get("/api/v1/bff/dashboard/proj-atlas", headers=engineer_headers)
    assert response.status_code == 200
    body = response.json()
    bff_sop = next((s for s in body["sop_versions"] if s["version_no"] == "V-BFF-1"), None)
    assert bff_sop is not None
    assert bff_sop["action_count"] == 1
    assert "actions" not in bff_sop, "Full action list must not be embedded in BFF sop summary"


@pytest.mark.functional
def test_bff_dashboard_respects_sop_version_id_query_param(client, engineer_headers):
    """When sop_version_id is specified, the BFF must use that version's data."""
    create = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-atlas", "version_no": "V-BFF-2", "actions": []},
    )
    assert create.status_code == 201
    sop_id = create.json()["id"]

    response = client.get(
        f"/api/v1/bff/dashboard/proj-atlas?sop_version_id={sop_id}",
        headers=engineer_headers,
    )
    assert response.status_code == 200
    assert response.json()["active_sop_version_id"] == sop_id


@pytest.mark.functional
def test_master_list_syntax_returns_x_total_count_header(client, engineer_headers):
    """GET /master/syntax without pagination params must still expose X-Total-Count header."""
    response = client.get("/api/v1/master/syntax", headers=engineer_headers)
    assert response.status_code == 200
    assert "x-total-count" in response.headers
    assert int(response.headers["x-total-count"]) >= 0
    assert isinstance(response.json(), list)  # backward-compat: still a bare list


@pytest.mark.functional
def test_master_list_syntax_paginated_returns_envelope(client, engineer_headers):
    """GET /master/syntax?page=1&size=5 must return a PaginatedResponse envelope."""
    response = client.get("/api/v1/master/syntax?page=1&size=5", headers=engineer_headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert body["page"] == 1
    assert body["size"] == 5
    assert "pages" in body
    assert len(body["items"]) <= 5


@pytest.mark.functional
def test_audit_logs_paginated_returns_envelope(client, manager_headers):
    """GET /audit/logs?page=1&size=10 must return a PaginatedResponse envelope."""
    response = client.get("/api/v1/audit/logs?page=1&size=10", headers=manager_headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert body["page"] == 1
    assert body["size"] == 10


@pytest.mark.functional
def test_audit_logs_legacy_returns_bare_list_with_header(client, manager_headers):
    """GET /audit/logs without page param must return a bare list (backward compat)
    and include X-Total-Count header."""
    response = client.get("/api/v1/audit/logs", headers=manager_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert "x-total-count" in response.headers


@pytest.mark.functional
def test_structured_error_response_for_404(client, engineer_headers):
    """404 errors must now return {error_code, message} instead of {detail}."""
    response = client.get("/api/v1/most/workspaces/proj-nonexistent", headers=engineer_headers)
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "NOT_FOUND"
    assert "message" in body


@pytest.mark.functional
def test_structured_error_response_for_validation_failure(client, engineer_headers):
    """422 validation errors must return {error_code: VALIDATION_ERROR, message, detail}."""
    response = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={"project_id": "proj-atlas", "takt_time": -1, "stations": []},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert isinstance(body["detail"], list)
    assert any("takt_time" in err.get("field", "") for err in body["detail"])
