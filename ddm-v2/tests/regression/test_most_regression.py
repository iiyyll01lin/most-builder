from __future__ import annotations

import pytest

from ddm_v2.schemas import MOSTStep
from ddm_v2.services.most_service import calculate_workflow


@pytest.mark.regression
def test_reference_most_calculation_regression(regression_fixture):
    steps = [MOSTStep(**step) for step in regression_fixture["steps"]]
    result = calculate_workflow(steps)

    assert result.total_tmu == regression_fixture["expected"]["total_tmu"]
    assert result.total_seconds == regression_fixture["expected"]["total_seconds"]
    assert result.breakdown[0].index_string == regression_fixture["expected"]["first_index_string"]
    assert result.breakdown[1].auto_sentence == regression_fixture["expected"]["second_auto_sentence"]


@pytest.mark.regression
def test_return_a_cm_above_65_maps_to_a32_not_a24(regression_fixture):
    """Regression lock for B1 fix: return_a_cm=70 must produce A32, not A24.

    The third fixture step uses return_a_cm=70.0 without an explicit A3 param,
    so the index string final segment must be A32.
    """
    steps = [MOSTStep(**step) for step in regression_fixture["steps"]]
    result = calculate_workflow(steps)

    third_index = result.breakdown[2].index_string
    assert third_index == regression_fixture["expected"]["third_index_string"], (
        f"Expected {regression_fixture['expected']['third_index_string']!r}, got {third_index!r}. "
        "If this regresses, check _lookup_a_index threshold (must be 65 cm, not 120 cm)."
    )
