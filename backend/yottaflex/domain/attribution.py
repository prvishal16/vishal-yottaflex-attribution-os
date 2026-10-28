"""Deterministic attribution eligibility and credit allocation.

This module is the single source of truth for eligibility and model formulas.
Both the pipeline and the journey-explanation API call these functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from yottaflex.config import MODELS

ELIGIBLE = "ELIGIBLE"
CONVERSION_REASON_NO_TOUCHES = "NO_ELIGIBLE_TOUCHPOINTS:NO_TOUCHPOINTS_IN_SCOPE"
POST_CONVERSION = "POST_CONVERSION"
OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
CONSENT_DENIED = "CONSENT_DENIED"
NO_CAMPAIGN = "NO_CAMPAIGN"

EXCLUSION_LABELS: dict[str, str] = {
    ELIGIBLE: "Eligible for attribution",
    POST_CONVERSION: "Occurred after the conversion timestamp",
    OUTSIDE_WINDOW: "Occurred before the attribution lookback window",
    IDENTITY_UNRESOLVED: "No supported identity link to the converting contact",
    CONSENT_DENIED: "Consent is not granted for marketing attribution",
    NO_CAMPAIGN: "Touchpoint has no valid campaign association",
}

EXCLUDED_COUNT_FIELDS: dict[str, str] = {
    POST_CONVERSION: "excluded_post_conversion",
    OUTSIDE_WINDOW: "excluded_outside_window",
    IDENTITY_UNRESOLVED: "excluded_identity_unresolved",
    CONSENT_DENIED: "excluded_consent",
    NO_CAMPAIGN: "excluded_no_campaign",
}

MICRO = Decimal("0.000001")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Conversion:
    order_id: str
    opportunity_id: str
    contact_id: str
    ordered_at: datetime
    revenue: Decimal
    currency: str


@dataclass(frozen=True)
class TouchCandidate:
    touchpoint_id: str
    campaign_id: str
    channel_id: str
    occurred_at: datetime
    consent_status: str
    resolved_contact_id: str | None
    resolution_status: str
    resolution_rule_id: str
    identity_status: str


@dataclass(frozen=True)
class TouchClassification:
    touch: TouchCandidate
    outcome: str
    reason: str


@dataclass(frozen=True)
class Allocation:
    touchpoint_id: str
    campaign_id: str
    channel_id: str
    credit_fraction: Decimal
    attributed_revenue: Decimal


def classify_touch(
    touch: TouchCandidate,
    conversion: Conversion,
    lookback_days: int,
    contact_consent_status: str = "GRANTED",
) -> TouchClassification:
    """Classify one candidate touch for one conversion.

    Ordering of checks is part of the published rule set and determines which
    exclusion reason is reported when several conditions fail at once.
    """

    if touch.occurred_at > conversion.ordered_at:
        return TouchClassification(touch, POST_CONVERSION, EXCLUSION_LABELS[POST_CONVERSION])
    window_start = conversion.ordered_at - timedelta(days=lookback_days)
    if touch.occurred_at < window_start:
        return TouchClassification(touch, OUTSIDE_WINDOW, EXCLUSION_LABELS[OUTSIDE_WINDOW])
    if not touch.resolved_contact_id or touch.resolved_contact_id != conversion.contact_id:
        return TouchClassification(touch, IDENTITY_UNRESOLVED, EXCLUSION_LABELS[IDENTITY_UNRESOLVED])
    if touch.consent_status != "GRANTED" or contact_consent_status != "GRANTED":
        return TouchClassification(touch, CONSENT_DENIED, EXCLUSION_LABELS[CONSENT_DENIED])
    if not touch.campaign_id or not touch.channel_id:
        return TouchClassification(touch, NO_CAMPAIGN, EXCLUSION_LABELS[NO_CAMPAIGN])
    return TouchClassification(touch, ELIGIBLE, EXCLUSION_LABELS[ELIGIBLE])


def sort_eligible_touches(touches: list[TouchCandidate]) -> list[TouchCandidate]:
    """Stable tie-break: occurred_at ascending, then touchpoint_id ascending."""

    return sorted(touches, key=lambda touch: (touch.occurred_at, touch.touchpoint_id))


def allocate_credit(
    conversion: Conversion,
    eligible_touches: list[TouchCandidate],
    model: str,
) -> list[Allocation]:
    if model not in MODELS:
        raise ValueError(f"Unsupported attribution model: {model}")
    ordered = sort_eligible_touches(eligible_touches)
    if not ordered:
        return []
    if model == "first_touch":
        chosen = ordered[0]
        return [_allocation(chosen, Decimal("1.000000"), conversion.revenue)]
    if model == "last_touch":
        chosen = ordered[-1]
        return [_allocation(chosen, Decimal("1.000000"), conversion.revenue)]

    count = len(ordered)
    base_fraction = (Decimal(1) / Decimal(count)).quantize(MICRO, rounding=ROUND_DOWN)
    allocations: list[Allocation] = []
    allocated_revenue = Decimal("0.00")
    for index, touch in enumerate(ordered):
        if index == count - 1:
            fraction = Decimal(1) - base_fraction * (count - 1)
            revenue = conversion.revenue - allocated_revenue
        else:
            fraction = base_fraction
            revenue = (conversion.revenue * fraction).quantize(CENT, rounding=ROUND_HALF_UP)
            allocated_revenue += revenue
        allocations.append(_allocation(touch, fraction.quantize(MICRO), revenue))
    return allocations


def _allocation(touch: TouchCandidate, fraction: Decimal, revenue: Decimal) -> Allocation:
    return Allocation(
        touchpoint_id=touch.touchpoint_id,
        campaign_id=touch.campaign_id,
        channel_id=touch.channel_id,
        credit_fraction=fraction,
        attributed_revenue=revenue.quantize(CENT, rounding=ROUND_HALF_UP),
    )


def exclusion_counts(classifications: list[TouchClassification]) -> dict[str, int]:
    counts = {field: 0 for field in EXCLUDED_COUNT_FIELDS.values()}
    for classification in classifications:
        field = EXCLUDED_COUNT_FIELDS.get(classification.outcome)
        if field:
            counts[field] += 1
    return counts


def reconciliation_difference(conversion_revenue: Decimal, allocations: list[Allocation]) -> Decimal:
    return (conversion_revenue - sum((row.attributed_revenue for row in allocations), Decimal("0.00"))).quantize(CENT)
