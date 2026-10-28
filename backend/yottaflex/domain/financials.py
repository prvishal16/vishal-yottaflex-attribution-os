"""Financial formulas and coverage rules.

Campaign budget is not spend. Missing cost is unknown, never zero. ROI and ROAS
are only reported when the spend basis is complete and positive.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class RatioResult:
    value: Decimal | None
    available: bool
    status: str


def _ratio(numerator: Decimal, denominator: Decimal, quant: str = "0.01") -> Decimal:
    return (numerator / denominator).quantize(Decimal(quant), rounding=ROUND_HALF_UP)


def roi(attributed_revenue: Decimal, spend: Decimal, coverage: str) -> RatioResult:
    if coverage == "MISSING":
        return RatioResult(None, False, "MISSING_COST")
    if coverage == "PARTIAL":
        return RatioResult(None, False, "INCOMPLETE_COST_COVERAGE")
    if coverage == "NO_COST_BASIS":
        return RatioResult(None, False, "NO_PAID_SPEND")
    if spend <= 0:
        return RatioResult(None, False, "ZERO_SPEND")
    return RatioResult(_ratio((attributed_revenue - spend) * HUNDRED, spend), True, "AVAILABLE")


def roas(attributed_revenue: Decimal, spend: Decimal, coverage: str) -> RatioResult:
    if coverage in ("MISSING", "PARTIAL"):
        return RatioResult(None, False, "INCOMPLETE_COST_COVERAGE")
    if coverage == "NO_COST_BASIS":
        return RatioResult(None, False, "NO_PAID_SPEND")
    if spend <= 0:
        return RatioResult(None, False, "ZERO_SPEND")
    return RatioResult(_ratio(attributed_revenue, spend), True, "AVAILABLE")


def cost_coverage(
    budget: Decimal,
    compatible_cost_count: int,
    incompatible_cost_count: int,
    expected_periods: int | None = None,
    compatible_periods: int | None = None,
) -> str:
    if budget <= 0:
        return "NO_COST_BASIS"
    if compatible_cost_count == 0:
        return "MISSING"
    if incompatible_cost_count > 0:
        return "PARTIAL"
    if (
        expected_periods is not None
        and compatible_periods is not None
        and compatible_periods < expected_periods
    ):
        return "PARTIAL"
    return "COMPLETE"


def budget_utilization(spend: Decimal, budget: Decimal) -> Decimal | None:
    if budget <= 0:
        return None
    return _ratio(spend * HUNDRED, budget)


def cost_per_conversion(spend: Decimal, conversions: int, coverage: str) -> Decimal | None:
    if conversions <= 0 or coverage != "COMPLETE":
        return None
    return _ratio(spend, Decimal(conversions))


def average_order_value(attributed_revenue: Decimal, conversions: int) -> Decimal | None:
    if conversions <= 0:
        return None
    return _ratio(attributed_revenue, Decimal(conversions))


def conversion_rate(conversions: int, opportunities: int) -> Decimal | None:
    if opportunities <= 0:
        return None
    return _ratio(Decimal(conversions) * HUNDRED, Decimal(opportunities))


def recognized_revenue(amount: Decimal, refunded_amount: Decimal, status: str) -> Decimal:
    if status == "PAID":
        return amount
    if status == "PARTIALLY_REFUNDED":
        return max(Decimal("0.00"), amount - refunded_amount)
    return Decimal("0.00")
