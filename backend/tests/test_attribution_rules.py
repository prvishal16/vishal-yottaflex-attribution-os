from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from yottaflex.domain.attribution import (
    CONSENT_DENIED,
    ELIGIBLE,
    IDENTITY_UNRESOLVED,
    NO_CAMPAIGN,
    OUTSIDE_WINDOW,
    POST_CONVERSION,
    Conversion,
    TouchCandidate,
    allocate_credit,
    classify_touch,
    exclusion_counts,
    reconciliation_difference,
    sort_eligible_touches,
)

ORDERED_AT = datetime(2026, 3, 15, 12, 0, 0)
CONVERSION = Conversion(
    order_id="ORD-2026-000001",
    opportunity_id="OPP-2026-000001",
    contact_id="CON-2026-000001",
    ordered_at=ORDERED_AT,
    revenue=Decimal("100.00"),
    currency="EUR",
)


def touch(
    touchpoint_id: str,
    minutes: int,
    *,
    contact_id: str | None = "CON-2026-000001",
    consent: str = "GRANTED",
    campaign: str = "CMP-2026-000001",
    channel: str = "CHN-000001",
) -> TouchCandidate:
    return TouchCandidate(
        touchpoint_id=touchpoint_id,
        campaign_id=campaign,
        channel_id=channel,
        occurred_at=ORDERED_AT + timedelta(minutes=minutes),
        consent_status=consent,
        resolved_contact_id=contact_id,
        resolution_status="DIRECT" if contact_id else "UNRESOLVED",
        resolution_rule_id="IDR-DIRECT-CONTACT",
        identity_status="DIRECT",
    )


def test_eligible_touch_is_within_window_and_consented() -> None:
    result = classify_touch(touch("TOUCH-1", -60), CONVERSION, 90)
    assert result.outcome == ELIGIBLE


def test_post_conversion_takes_priority_over_window() -> None:
    result = classify_touch(touch("TOUCH-1", 1), CONVERSION, 90)
    assert result.outcome == POST_CONVERSION


def test_touch_outside_lookback_is_excluded() -> None:
    result = classify_touch(touch("TOUCH-1", -(90 * 24 * 60 + 1)), CONVERSION, 90)
    assert result.outcome == OUTSIDE_WINDOW


def test_unresolved_identity_is_excluded() -> None:
    result = classify_touch(touch("TOUCH-1", -60, contact_id=None), CONVERSION, 90)
    assert result.outcome == IDENTITY_UNRESOLVED


def test_mismatched_identity_is_excluded() -> None:
    result = classify_touch(touch("TOUCH-1", -60, contact_id="CON-2026-999999"), CONVERSION, 90)
    assert result.outcome == IDENTITY_UNRESOLVED


def test_touch_consent_denied_is_excluded() -> None:
    result = classify_touch(touch("TOUCH-1", -60, consent="DENIED"), CONVERSION, 90)
    assert result.outcome == CONSENT_DENIED


def test_contact_consent_denied_is_excluded() -> None:
    result = classify_touch(
        touch("TOUCH-1", -60), CONVERSION, 90, contact_consent_status="DENIED"
    )
    assert result.outcome == CONSENT_DENIED


def test_missing_campaign_is_excluded() -> None:
    result = classify_touch(touch("TOUCH-1", -60, campaign=""), CONVERSION, 90)
    assert result.outcome == NO_CAMPAIGN


def test_first_touch_uses_earliest_and_last_touch_uses_latest() -> None:
    touches = [touch("TOUCH-B", -10), touch("TOUCH-A", -100), touch("TOUCH-C", -50)]
    first = allocate_credit(CONVERSION, touches, "first_touch")
    last = allocate_credit(CONVERSION, touches, "last_touch")
    assert first[0].touchpoint_id == "TOUCH-A"
    assert first[0].attributed_revenue == Decimal("100.00")
    assert last[0].touchpoint_id == "TOUCH-B"
    assert last[0].attributed_revenue == Decimal("100.00")


def test_ties_break_on_touchpoint_id() -> None:
    same = ORDERED_AT - timedelta(minutes=5)
    first = touch("TOUCH-000002", -5)
    second = touch("TOUCH-000001", -5)
    ordered = sort_eligible_touches([first, second])
    assert [item.touchpoint_id for item in ordered] == ["TOUCH-000001", "TOUCH-000002"]
    assert first.occurred_at == same


def test_linear_allocation_is_cent_exact_and_sums_to_one() -> None:
    touches = [touch(f"TOUCH-{index}", -index) for index in (1, 2, 3)]
    allocations = allocate_credit(CONVERSION, touches, "linear")
    assert [row.attributed_revenue for row in allocations] == [
        Decimal("33.33"),
        Decimal("33.33"),
        Decimal("33.34"),
    ]
    assert sum((row.credit_fraction for row in allocations), Decimal("0")) == Decimal("1.000000")
    assert reconciliation_difference(CONVERSION.revenue, allocations) == Decimal("0.00")


def test_linear_allocation_handles_seven_way_split() -> None:
    touches = [touch(f"TOUCH-{index}", -index) for index in range(1, 8)]
    allocations = allocate_credit(CONVERSION, touches, "linear")
    assert sum((row.attributed_revenue for row in allocations), Decimal("0")) == Decimal("100.00")
    assert len(allocations) == 7
    assert allocations[0].credit_fraction == Decimal("0.142857")
    assert allocations[-1].credit_fraction == Decimal("0.142858")


def test_no_eligible_touches_produces_no_allocations() -> None:
    assert allocate_credit(CONVERSION, [], "linear") == []


def test_unsupported_model_is_rejected() -> None:
    with pytest.raises(ValueError):
        allocate_credit(CONVERSION, [touch("TOUCH-1", -1)], "position_based")


def test_exclusion_counts_group_by_reason() -> None:
    classifications = [
        classify_touch(touch("TOUCH-1", -10), CONVERSION, 90),
        classify_touch(touch("TOUCH-2", 10), CONVERSION, 90),
        classify_touch(touch("TOUCH-3", -(91 * 24 * 60)), CONVERSION, 90),
        classify_touch(touch("TOUCH-4", -10, consent="DENIED"), CONVERSION, 90),
        classify_touch(touch("TOUCH-5", -10, contact_id=None), CONVERSION, 90),
    ]
    counts = exclusion_counts(classifications)
    assert counts == {
        "excluded_post_conversion": 1,
        "excluded_outside_window": 1,
        "excluded_identity_unresolved": 1,
        "excluded_consent": 1,
        "excluded_no_campaign": 0,
    }
