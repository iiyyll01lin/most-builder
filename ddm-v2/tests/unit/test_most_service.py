from __future__ import annotations

import pytest

from ddm_v2.schemas import MOSTStep, OperatorTime
from ddm_v2.services.most_service import calculate_workflow, generate_index_string


@pytest.mark.unit
def test_general_sequence_calculation_uses_sum_and_frequency():
    result = calculate_workflow(
        [
            MOSTStep(
                action="Grab",
                object="Screw",
                object_category="Fastener",
                seq_type="GENERAL",
                params={"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                frequency=2,
            )
        ]
    )

    assert result.total_tmu == 18
    assert result.total_seconds == 0.65
    assert result.breakdown[0].index_string == "A1 B0 G3 A1 B0 P3 A1"


@pytest.mark.unit
def test_collaborative_step_uses_max_operator_time_for_effective_time():
    result = calculate_workflow(
        [
            MOSTStep(
                action="Place",
                object="Motherboard",
                object_category="PCB",
                seq_type="CONTROLLED",
                params={"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
                is_collaborative=True,
                operator_count=2,
                operators=[OperatorTime(employee_id="emp-eva", individual_tmu=18), OperatorTime(employee_id="emp-noah", individual_tmu=24)],
            )
        ]
    )

    assert result.total_tmu == 19
    assert result.collaborative_effective_tmu == 24
    assert result.breakdown[0].effective_tmu == 24


@pytest.mark.unit
def test_generate_index_string_returns_controlled_sequence_shape():
    index_string = generate_index_string({"A1": 1, "B1": 0, "G": 3, "M": 10, "X": 0, "I": 6, "A3": 3}, "CONTROLLED")
    assert index_string == "A1 B0 G3 M10 X0 I6 A3"
