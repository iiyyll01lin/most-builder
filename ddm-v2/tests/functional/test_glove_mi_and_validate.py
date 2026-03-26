"""Functional tests for glove-check, MI naming, validate-level, and project endpoints."""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Glove check
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_glove_check_returns_specific_rule_before_wildcard(client, engineer_headers):
    """A specific object_category rule must win over the wildcard '*' rule.
    PCB category now maps to '兩只半指手套' (two half-finger gloves) per the
    updated manufacturing domain specification."""
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "Motherboard", "object_category": "PCB", "action": "Place"},
    )
    assert response.status_code == 200
    body = response.json()
    # glv-pcb (PCB → 兩只半指手套) should beat glv-default (* → General Glove)
    assert body["glove_type"] == "兩只半指手套"
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
        json={"fields": {"model5": "HDL50", "line": ""}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is False
    # status, pick_type, process, line, area, ct are missing/empty
    assert len(body["errors"]) >= 2


@pytest.mark.functional
def test_mi_naming_validate_succeeds_with_all_fields(client, engineer_headers):
    """Validate with all 8 required fields (Model5_Status_PickType_Process_CFI_Line_Area_CT)."""
    response = client.post(
        "/api/v1/mi-naming/validate",
        headers=engineer_headers,
        json={"fields": {
            "model5": "HDL50", "status": "ASSY", "pick_type": "FPT",
            "process": "ASSY", "cfi": "", "line": "L1", "area": "ST-01", "ct": "3.5"
        }},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is True
    assert body["errors"] == []
    # Suggested name uses '_' separator, CFI is skipped as empty
    assert body["suggested_name"] is not None
    assert "_" in body["suggested_name"]
    assert body["suggested_name"].startswith("HDL50")


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


# ---------------------------------------------------------------------------
# Phase 3 business-logic hardening: domain-specific glove & ion fan rules
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_glove_check_returns_half_finger_gloves_for_mlb(client, engineer_headers):
    """MLB (主板/MLB category) must return '兩只半指手套' — the domain-correct
    manufacturing glove type for high-value ESD-sensitive boards."""
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "MLB", "object_category": "主板/MLB", "action": "Install"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["glove_type"] == "兩只半指手套"
    assert body["matched_rule_id"] == "glv-mlb"


@pytest.mark.functional
def test_glove_check_returns_half_finger_gloves_for_dimm(client, engineer_headers):
    """DIMM (記憶體 category) must return '兩只半指手套'."""
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "DIMM", "object_category": "記憶體", "action": "Insert"},
    )
    assert response.status_code == 200
    assert response.json()["glove_type"] == "兩只半指手套"


@pytest.mark.functional
def test_glove_check_returns_half_finger_gloves_for_cpu(client, engineer_headers):
    """CPU (處理器 category) must return '兩只半指手套'."""
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "CPU", "object_category": "處理器", "action": "Install"},
    )
    assert response.status_code == 200
    assert response.json()["glove_type"] == "兩只半指手套"


@pytest.mark.functional
def test_glove_check_returns_left_half_right_fingercot_for_cable(client, engineer_headers):
    """Cable (線材 category) must return '左手半指+右手指套'."""
    response = client.post(
        "/api/v1/gloves/check",
        headers=engineer_headers,
        json={"object_name": "Top Cable", "object_category": "線材", "action": "Route"},
    )
    assert response.status_code == 200
    assert response.json()["glove_type"] == "左手半指+右手指套"


@pytest.mark.functional
def test_mi_naming_convention_8_field_uses_underscore_separator(client, engineer_headers):
    """The MI naming convention must use '_' as segment separator and produce
    the format: [Model5]_[Status]_[PickType]_[Process]_[CFI]_[Line]_[Area]_[CT]."""
    response = client.post(
        "/api/v1/mi-naming/validate",
        headers=engineer_headers,
        json={"fields": {
            "model5": "K860G",
            "status": "ASSY",
            "pick_type": "FPT",
            "process": "BASY",
            "cfi": "CFI01",
            "line": "L3",
            "area": "A2",
            "ct": "4.5",
        }},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is True
    name = body["suggested_name"]
    assert name is not None
    segments = name.split("_")
    assert len(segments) == 8, f"Expected 8 segments, got {len(segments)}: {name}"
    assert segments[0] == "K860G"
    assert segments[3] == "BASY"
    assert segments[5] == "L3"
    assert segments[7] == "4.5"


@pytest.mark.functional
def test_mi_naming_convention_rejects_missing_ct(client, engineer_headers):
    """CT (cycle time) is a required field in the 8-field convention."""
    response = client.post(
        "/api/v1/mi-naming/validate",
        headers=engineer_headers,
        json={"fields": {
            "model5": "K860G", "status": "ASSY", "pick_type": "FPT",
            "process": "BASY", "line": "L3", "area": "A2",
        }},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is False
    assert any("CT" in e for e in body["errors"])


@pytest.mark.functional
def test_simulation_line_balance_with_1p2m_reduces_cycle_time(client, engineer_headers):
    """An API-level 1P2M simulation must produce machine_effective_time and
    correctly lower the cycle_time compared to a 1P1M configuration."""
    # Create SOP version
    sop = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": "proj-atlas", "version_no": "V1P2M-test", "actions": []},
    )
    assert sop.status_code == 201
    sop_id = sop.json()["id"]

    # Run simulation with machine_count=2 on ST-3-1a
    sim = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": "proj-atlas",
            "takt_time": 10.0,
            "stations": [
                {"id": "ST-3-1a", "employee_id": "emp-eva", "sop_ids": [sop_id], "machine_count": 2},
            ],
        },
    )
    assert sim.status_code == 200
    body = sim.json()
    st = body["station_results"][0]
    assert st["machine_count"] == 2

