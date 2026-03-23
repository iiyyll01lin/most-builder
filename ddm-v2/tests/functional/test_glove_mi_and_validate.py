"""Functional tests for glove-check, MI naming, validate-level, and project endpoints."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Glove check
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_glove_check_returns_specific_rule_before_wildcard(client, engineer_headers):
    """A specific object_category rule must win over the wildcard '*' rule."""
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "Motherboard", "object_category": "PCB", "action": "Place"},
    )
    assert response.status_code == 200
    body = response.json()
    # Seed has glv-pcb (PCB → ESD Glove) which should beat glv-default (* → General Glove)
    assert body["glove_type"] == "ESD Glove"
    assert body["matched_rule_id"] == "glv-pcb"


@pytest.mark.functional
def test_glove_check_wildcard_fallback_for_unknown_category(client, engineer_headers):
    """An object category with no specific rule falls back to the wildcard rule."""
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "Cable", "object_category": "Cable", "action": "Route"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["glove_type"] == "General Glove"
    assert body["matched_rule_id"] == "glv-default"


@pytest.mark.functional
def test_glove_check_action_specific_rule_beats_category_wildcard(client, engineer_headers):
    """A rule matching both category AND action should beat a category-only rule."""
    # Seed: glv-fastener matches category=Fastener + action=Fasten → Finger Cot
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "Screw", "object_category": "Fastener", "action": "Fasten"},
    )
    assert response.status_code == 200
    assert response.json()["glove_type"] == "Finger Cot"


# ---------------------------------------------------------------------------
# MI naming validation
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_mi_naming_validate_rejects_missing_required_fields(client, engineer_headers):
    response = client.post(
        "/api/v1/mi-naming/validate",
        headers=engineer_headers,
        json={"fields": {"project": "K860G6", "line": ""}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is False
    # "line" is empty and required; "station" and "seconds" are also missing
    assert len(body["errors"]) >= 2


@pytest.mark.functional
def test_mi_naming_validate_succeeds_with_all_fields(client, engineer_headers):
    response = client.post(
        "/api/v1/mi-naming/validate",
        headers=engineer_headers,
        json={"fields": {"project": "K860G6", "line": "L1", "station": "ST-01", "seconds": "3.5"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is True
    assert body["errors"] == []
    assert body["suggested_name"] is not None


# ---------------------------------------------------------------------------
# validate-level endpoint
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_validate_level_endpoint_detects_sub_before_main(client, engineer_headers):
    response = client.post(
        "/api/v1/level-system/validate",
        headers=engineer_headers,
        json={"nodes": [{"action_id": "a1", "tag": "sub-1"}, {"action_id": "a2", "tag": "main-1"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is False
    assert body["errors"]


@pytest.mark.functional
def test_validate_level_endpoint_accepts_valid_tag_sequence(client, engineer_headers):
    response = client.post(
        "/api/v1/level-system/validate",
        headers=engineer_headers,
        json={"nodes": [{"action_id": "a1", "tag": "MAIN-1"}, {"action_id": "a2", "tag": "MAIN-2"}]},
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is True


@pytest.mark.functional
def test_validate_level_endpoint_detects_duplicate_main_seq(client, engineer_headers):
    response = client.post(
        "/api/v1/level-system/validate",
        headers=engineer_headers,
        json={
            "nodes": [
                {"action_id": "a1", "tag": "MAIN-1"},
                {"action_id": "a2", "tag": "MAIN-2"},
                {"action_id": "a3", "tag": "MAIN-1"},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is False
    assert any("duplicate" in e.lower() for e in body["errors"])


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_project_list_returns_seeded_projects(client, engineer_headers):
    response = client.get("/api/v1/projects", headers=engineer_headers)
    assert response.status_code == 200
    projects = response.json()
    project_ids = {p["id"] for p in projects}
    assert "proj-atlas" in project_ids
    assert "proj-orion" in project_ids


@pytest.mark.functional
def test_project_detail_returns_correct_project(client, engineer_headers):
    response = client.get("/api/v1/projects/proj-atlas", headers=engineer_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "K860G6-BASY"


@pytest.mark.functional
def test_project_detail_returns_404_for_unknown_project(client, engineer_headers):
    response = client.get("/api/v1/projects/proj-does-not-exist", headers=engineer_headers)
    assert response.status_code == 404
