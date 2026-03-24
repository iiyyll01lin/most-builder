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


@pytest.mark.unit
def test_controlled_sequence_with_dynamic_x_time_keeps_other_indices_in_total():
    result = calculate_workflow(
        [
            MOSTStep(
                action="Inspect",
                object="Motherboard",
                object_category="PCB",
                seq_type="CONTROLLED",
                params={"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1, "X_time_seconds": 0.36},
            )
        ]
    )

    assert result.total_tmu == 29
    assert result.total_seconds == 1.04


@pytest.mark.unit
def test_simo_and_collaborative_summaries_are_reported_together():
    result = calculate_workflow(
        [
            MOSTStep(
                action="Grab",
                object="Screw",
                object_category="Fastener",
                seq_type="GENERAL",
                hand="Left Hand",
                is_simo=True,
                simo_group_id="sg-1",
                params={"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
            ),
            MOSTStep(
                action="Place",
                object="Motherboard",
                object_category="PCB",
                seq_type="CONTROLLED",
                hand="Right Hand",
                is_simo=True,
                simo_group_id="sg-1",
                is_collaborative=True,
                operator_count=2,
                operators=[OperatorTime(employee_id="emp-eva", individual_tmu=15), OperatorTime(employee_id="emp-noah", individual_tmu=24)],
                params={"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
            ),
        ]
    )

    assert result.total_tmu == 28
    assert result.simo_max_tmu == 19
    assert result.simo_seconds == 0.68
    # With simo_group_id="sg-1": group contains 9 + 19; effective = max = 19.
    assert result.simo_adjusted_total_tmu == 19
    assert result.simo_adjusted_total_seconds == 0.68
    assert result.collaborative_effective_tmu == 33
    assert result.collaborative_effective_seconds == 1.19


@pytest.mark.unit
def test_lookup_a_index_max_is_65cm_not_120cm():
    """Regression: boundary between A24 and A32 must be 65 cm (per MiniMOST spec).

    Previously the code used 120 cm, causing distances between 65.1–120 cm to
    return index 24 instead of the correct 32.
    """
    # 65 cm is the last distance that maps to index 24
    index_at_65 = generate_index_string({}, "GENERAL", return_a_cm=65.0)
    assert index_at_65.endswith("A24"), f"A3 at 65 cm should be A24, got: {index_at_65}"

    # 65.1 cm crosses the boundary and must map to index 32
    index_at_65_1 = generate_index_string({}, "GENERAL", return_a_cm=65.1)
    assert index_at_65_1.endswith("A32"), f"A3 at 65.1 cm should be A32, got: {index_at_65_1}"

    # The previously-wrong upper bound: 120 cm must also map to A32
    index_at_120 = generate_index_string({}, "GENERAL", return_a_cm=120.0)
    assert index_at_120.endswith("A32"), f"A3 at 120 cm should be A32, got: {index_at_120}"


@pytest.mark.unit
def test_generate_index_string_default_a3_uses_return_a_cm():
    """When A3 is not in params, it is inferred from return_a_cm."""
    # 15 cm → index 6
    s = generate_index_string({"A1": 1, "B1": 0, "G": 1, "A2": 1, "B2": 0, "P": 1}, "GENERAL", return_a_cm=15.0)
    assert s == "A1 B0 G1 A1 B0 P1 A6"


@pytest.mark.unit
def test_generate_index_string_explicit_a3_overrides_return_a_cm():
    """An explicit A3 in params must not be overridden by return_a_cm."""
    s = generate_index_string({"A1": 1, "B1": 0, "G": 1, "A2": 1, "B2": 0, "P": 1, "A3": 3}, "GENERAL", return_a_cm=200.0)
    assert s == "A1 B0 G1 A1 B0 P1 A3"


@pytest.mark.unit
def test_calculate_workflow_empty_steps_returns_zero_totals():
    result = calculate_workflow([])
    assert result.total_tmu == 0
    assert result.total_seconds == 0.0
    assert result.breakdown == []
    assert result.simo_max_tmu is None
    assert result.collaborative_effective_tmu is None
    assert result.simo_adjusted_total_tmu is None


# ---------------------------------------------------------------------------
# Phase 2 hardening tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_simo_adjusted_total_tmu_uses_max_within_simo_group():
    """simo_adjusted_total_tmu must equal max(group TMUs) when a simo_group_id
    is supplied — not the sum of both hands."""
    result = calculate_workflow(
        [
            MOSTStep(
                action="Grab",
                object="Screw",
                seq_type="GENERAL",
                hand="Left Hand",
                is_simo=True,
                simo_group_id="sg-A",
                params={"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},  # 9 TMU
            ),
            MOSTStep(
                action="Place",
                object="Motherboard",
                seq_type="CONTROLLED",
                hand="Right Hand",
                is_simo=True,
                simo_group_id="sg-A",
                params={"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},  # 19 TMU
                operator_count=1,
            ),
        ]
    )

    # total_tmu stays as raw sum (backward compat)
    assert result.total_tmu == 28
    # SIMO-adjusted: both are in group sg-A → effective = max(9, 19) = 19
    assert result.simo_adjusted_total_tmu == 19
    assert result.simo_adjusted_total_seconds == pytest.approx(0.68, abs=0.01)


@pytest.mark.unit
def test_simo_adjusted_total_tmu_handles_two_independent_simo_groups():
    """Two separate simo_group_ids each contribute their max to the adjusted total."""
    result = calculate_workflow(
        [
            MOSTStep(action="Grab", object="A", seq_type="GENERAL", hand="Left Hand",
                     is_simo=True, simo_group_id="sg-1",
                     params={"A1": 1, "B1": 0, "G": 1, "A2": 1, "B2": 0, "P": 1, "A3": 0}),  # 4 TMU
            MOSTStep(action="Place", object="B", seq_type="GENERAL", hand="Right Hand",
                     is_simo=True, simo_group_id="sg-1",
                     params={"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1}),  # 9 TMU
            MOSTStep(action="Grab", object="C", seq_type="GENERAL", hand="Left Hand",
                     is_simo=True, simo_group_id="sg-2",
                     params={"A1": 1, "B1": 0, "G": 1, "A2": 0, "B2": 0, "P": 1, "A3": 0}),  # 3 TMU
            MOSTStep(action="Place", object="D", seq_type="GENERAL", hand="Right Hand",
                     is_simo=True, simo_group_id="sg-2",
                     params={"A1": 1, "B1": 0, "G": 1, "A2": 1, "B2": 0, "P": 1, "A3": 1}),  # 5 TMU
        ]
    )

    assert result.total_tmu == 21  # 4+9+3+5
    # sg-1: max(4,9)=9; sg-2: max(3,5)=5 → adjusted = 14
    assert result.simo_adjusted_total_tmu == 14


@pytest.mark.unit
def test_simo_without_group_id_does_not_produce_adjusted_total():
    """Legacy SIMO steps (no simo_group_id) cannot be correctly adjusted;
    simo_adjusted_total_tmu must be None to prevent silently outputting
    wrong data to the IE/PE."""
    result = calculate_workflow(
        [
            MOSTStep(action="Grab", object="A", seq_type="GENERAL", is_simo=True,
                     params={"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1}),
        ]
    )
    assert result.simo_adjusted_total_tmu is None


@pytest.mark.unit
def test_collaborative_step_rejects_operator_count_less_than_two():
    """A collaborative step with operator_count=1 must raise ValueError with a
    domain-specific message so an IE knows exactly what to fix."""
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError) as exc_info:
        MOSTStep(
            action="Fasten",
            object="Motherboard",
            seq_type="GENERAL",
            is_collaborative=True,
            operator_count=1,  # invalid: collaborative requires >= 2
            params={"A1": 1, "B1": 0, "G": 1, "A2": 1, "B2": 0, "P": 1, "A3": 1},
        )
    assert "operator_count >= 2" in str(exc_info.value)


@pytest.mark.unit
def test_collaborative_step_rejects_single_operator_in_operators_list():
    """A collaborative step that lists exactly 1 operator TMU must fail
    validation — it means the PE forgot to add the second operator."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        MOSTStep(
            action="Place",
            object="Board",
            seq_type="CONTROLLED",
            is_collaborative=True,
            operator_count=2,
            operators=[OperatorTime(employee_id="emp-eva", individual_tmu=18)],
            params={"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
        )
    assert "at least 2 are required" in str(exc_info.value)


@pytest.mark.unit
def test_collaborative_step_with_empty_operators_is_allowed_in_flight():
    """operator_count=2, operators=[] should be accepted (in-progress data entry).
    The PE has declared intent but not yet filled in operator TMUs."""
    step = MOSTStep(
        action="Place",
        object="Board",
        seq_type="CONTROLLED",
        is_collaborative=True,
        operator_count=2,
        operators=[],
        params={"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
    )
    assert step.is_collaborative is True
    assert step.operators == []
