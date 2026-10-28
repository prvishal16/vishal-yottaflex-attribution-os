from decimal import Decimal

from yottaflex.domain.financials import (
    average_order_value,
    budget_utilization,
    conversion_rate,
    cost_coverage,
    cost_per_conversion,
    recognized_revenue,
    roas,
    roi,
)


def test_roi_and_roas_require_complete_positive_spend() -> None:
    assert roi(Decimal("250.00"), Decimal("100.00"), "COMPLETE") == roi(
        Decimal("250.00"), Decimal("100.00"), "COMPLETE"
    )
    result = roi(Decimal("250.00"), Decimal("100.00"), "COMPLETE")
    assert result.available
    assert result.value == Decimal("150.00")
    assert roas(Decimal("250.00"), Decimal("100.00"), "COMPLETE").value == Decimal("2.50")


def test_roi_is_unavailable_for_missing_or_partial_coverage() -> None:
    assert roi(Decimal("250.00"), Decimal("100.00"), "MISSING").available is False
    assert roi(Decimal("250.00"), Decimal("100.00"), "PARTIAL").status == "INCOMPLETE_COST_COVERAGE"
    assert roas(Decimal("250.00"), Decimal("100.00"), "PARTIAL").value is None


def test_roi_is_unavailable_without_paid_basis_or_spend() -> None:
    assert roi(Decimal("250.00"), Decimal("0.00"), "NO_COST_BASIS").status == "NO_PAID_SPEND"
    assert roi(Decimal("250.00"), Decimal("0.00"), "COMPLETE").status == "ZERO_SPEND"


def test_cost_coverage_distinguishes_unknown_from_zero() -> None:
    assert cost_coverage(Decimal("1000"), 0, 0) == "MISSING"
    assert cost_coverage(Decimal("1000"), 12, 0) == "COMPLETE"
    assert cost_coverage(Decimal("1000"), 12, 1) == "PARTIAL"
    assert cost_coverage(Decimal("0"), 0, 0) == "NO_COST_BASIS"


def test_cost_coverage_requires_every_campaign_month() -> None:
    assert (
        cost_coverage(Decimal("1000"), 12, 0, expected_periods=12, compatible_periods=12)
        == "COMPLETE"
    )
    assert (
        cost_coverage(Decimal("1000"), 11, 0, expected_periods=12, compatible_periods=11)
        == "PARTIAL"
    )


def test_cost_metrics_are_null_when_coverage_is_not_complete() -> None:
    assert cost_per_conversion(Decimal("100"), 2, "PARTIAL") is None
    assert cost_per_conversion(Decimal("100"), 2, "MISSING") is None
    assert cost_per_conversion(Decimal("100"), 2, "COMPLETE") == Decimal("50.00")


def test_average_order_value_and_conversion_rate() -> None:
    assert average_order_value(Decimal("1000"), 4) == Decimal("250.00")
    assert average_order_value(Decimal("1000"), 0) is None
    assert conversion_rate(25, 100) == Decimal("25.00")
    assert conversion_rate(25, 0) is None


def test_budget_utilization_uses_budget_only_as_a_reference() -> None:
    assert budget_utilization(Decimal("250"), Decimal("1000")) == Decimal("25.00")
    assert budget_utilization(Decimal("250"), Decimal("0")) is None


def test_recognized_revenue_handles_refunds_and_non_revenue_states() -> None:
    assert recognized_revenue(Decimal("100"), Decimal("0"), "PAID") == Decimal("100.00")
    assert recognized_revenue(Decimal("100"), Decimal("40"), "PARTIALLY_REFUNDED") == Decimal("60.00")
    assert recognized_revenue(Decimal("100"), Decimal("100"), "PARTIALLY_REFUNDED") == Decimal("0.00")
    assert recognized_revenue(Decimal("100"), Decimal("0"), "CANCELLED") == Decimal("0.00")
    assert recognized_revenue(Decimal("100"), Decimal("0"), "REFUNDED") == Decimal("0.00")
