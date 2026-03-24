from __future__ import annotations

import pytest

from ddm_v2.services.level_service import build_level_entries, build_precedence_graph, validate_level_tags


@pytest.mark.unit
def test_validate_level_tags_rejects_sub_before_main():
    errors = validate_level_tags(["sub-1", "main-1"])
    assert errors
    assert "sub tag cannot appear before main tag" in errors[0]


@pytest.mark.unit
def test_build_precedence_graph_groups_cub_and_number_constraints():
    graph = build_precedence_graph(
        [
            {"action_id": "act-1", "description": "A", "ct_seconds": 1.2, "difficulty_factor": 1.0, "adjusted_ct": 1.2, "effective_cub_ct": None, "main_seq": "1", "order_seq": None, "cub_group": "C1", "number_tag": "NB1", "number_count": 2, "machine_count": 1, "operator_count": 1, "status_label": None},
            {"action_id": "act-2", "description": "B", "ct_seconds": 0.8, "difficulty_factor": 1.0, "adjusted_ct": 0.8, "effective_cub_ct": 0.4, "main_seq": "2", "order_seq": None, "cub_group": "C1", "number_tag": None, "number_count": None, "machine_count": 2, "operator_count": 1, "status_label": None},
        ]
    )

    assert graph["precedence_edges"] == [{"from": "act-1", "to": "act-2", "type": "main"}]
    assert graph["cub_groups"]["C1"] == ["act-1", "act-2"]
    assert graph["number_constraints"]["NB1"]["limit"] == 2


@pytest.mark.unit
def test_build_level_entries_calculates_effective_cub_ct_and_preserves_sort_order():
    entries = build_level_entries(
        "proj-atlas",
        [
            {"id": "act-1", "description": "First", "seconds": 1.5, "frequency": 1},
            {"id": "act-2", "description": "Second", "seconds": 2.4, "frequency": 1},
        ],
        existing_entries=[
            {"action_id": "act-1", "difficulty_factor": 1.2, "cub_group": "C1", "machine_count": 2, "operator_count": 1, "sort_order": 1},
            {"action_id": "act-2", "difficulty_factor": 1.0, "sort_order": 0},
        ],
    )

    assert [entry["action_id"] for entry in entries] == ["act-2", "act-1"]
    reordered = {entry["action_id"]: entry for entry in entries}
    assert reordered["act-1"]["adjusted_ct"] == 1.8
    assert reordered["act-1"]["effective_cub_ct"] == 0.9
    assert reordered["act-2"]["row_no"] == 1


@pytest.mark.unit
def test_validate_level_tags_rejects_duplicate_main_seq():
    """Regression: duplicate main tags with the same sequence value must be flagged."""
    errors = validate_level_tags(["MAIN-1", "MAIN-2", "MAIN-1"])
    assert errors
    assert any("duplicate" in e.lower() for e in errors)


@pytest.mark.unit
def test_validate_level_tags_accepts_distinct_main_seqs():
    errors = validate_level_tags(["MAIN-1", "MAIN-2", "MAIN-3"])
    assert errors == []


@pytest.mark.unit
def test_validate_level_tags_skips_empty_tags():
    """Empty/blank tags must be ignored without error."""
    errors = validate_level_tags(["", "MAIN-1", "", "MAIN-2"])
    assert errors == []


@pytest.mark.unit
def test_build_level_entries_preserves_existing_fields_for_unknown_actions():
    """Actions not in existing_entries should use all defaults without error."""
    entries = build_level_entries(
        "proj-x",
        [{"id": "act-new", "description": "New", "seconds": 1.0, "frequency": 1}],
        existing_entries=[],
    )
    assert entries[0]["difficulty_factor"] == 1.0
    assert entries[0]["adjusted_ct"] == 1.0
    assert entries[0]["effective_cub_ct"] is None
    assert entries[0]["machine_count"] == 1
    assert entries[0]["operator_count"] == 1


# ---------------------------------------------------------------------------
# Phase 2 hardening tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_precedence_graph_sorts_main_seq_numerically_not_lexicographically():
    """Regression for string-sort bug: main_seq '10' must come after '9', not
    between '1' and '2' as it would under lexicographic ordering.  A wrong
    ordering here directly corrupts the production SOP sequence on the floor."""
    entries = [
        {
            "action_id": f"act-{i}", "description": f"Step {i}", "ct_seconds": 1.0,
            "difficulty_factor": 1.0, "adjusted_ct": 1.0, "effective_cub_ct": None,
            "main_seq": str(i), "order_seq": None, "cub_group": None,
            "number_tag": None, "number_count": None,
            "machine_count": 1, "operator_count": 1, "status_label": None,
        }
        for i in [1, 2, 10, 11, 3]
    ]
    graph = build_precedence_graph(entries)
    edge_sequence = [e["from"] for e in graph["precedence_edges"]]
    # Expected order: 1 -> 2 -> 3 -> 10 -> 11
    assert edge_sequence == ["act-1", "act-2", "act-3", "act-10"]


@pytest.mark.unit
def test_build_precedence_graph_reports_no_cycles_for_valid_dag():
    """A strictly sequential main_seq=1,2,3 produces an acyclic graph."""
    entries = [
        {
            "action_id": k, "description": k, "ct_seconds": 1.0,
            "difficulty_factor": 1.0, "adjusted_ct": 1.0, "effective_cub_ct": None,
            "main_seq": v, "order_seq": None, "cub_group": None,
            "number_tag": None, "number_count": None,
            "machine_count": 1, "operator_count": 1, "status_label": None,
        }
        for k, v in [("a", "1"), ("b", "2"), ("c", "3")]
    ]
    graph = build_precedence_graph(entries)
    assert graph["cycle_errors"] == []


@pytest.mark.unit
def test_validate_level_tags_does_not_flag_maintenance_as_main_tag():
    """'maintenance' must NOT be treated as a 'main' tag.  If treated as main,
    subsequent 'sub' tags would incorrectly pass validation."""
    errors = validate_level_tags(["maintenance", "sub-1"])
    # 'sub-1' before any real MAIN tag should be an error
    assert any("sub tag cannot appear before main tag" in e for e in errors)


@pytest.mark.unit
def test_validate_level_tags_correctly_identifies_main_dash_prefix():
    """'main-1' is a valid main tag; 'sub-1' after it must not raise an error."""
    errors = validate_level_tags(["main-1", "sub-1"])
    assert errors == []
