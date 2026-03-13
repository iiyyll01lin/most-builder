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
