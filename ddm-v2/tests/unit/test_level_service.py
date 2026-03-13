from __future__ import annotations

import pytest

from ddm_v2.services.level_service import build_precedence_graph, validate_level_tags


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
