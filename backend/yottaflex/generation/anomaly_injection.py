"""Controlled anomaly fixtures.

Fixtures are injected after a valid baseline is generated. Their expected
dispositions are written to a separate ground-truth artifact. Detection rules
never read these labels.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from yottaflex.config import (
    ANOMALY_RULE_VERSION,
    DATASET_END,
    RECOGNIZED_ORDER_STATUSES,
    split_for_timestamp,
)
from yottaflex.generation.context import GenerationContext
from yottaflex.generation.journey_generation import SOURCE_SYSTEM_BY_CHANNEL
from yottaflex.util import iso, parse_iso


def _recognized_orders(ctx: GenerationContext) -> list[dict[str, Any]]:
    return [
        order
        for order in ctx.tables["orders"]
        if order["status"] in RECOGNIZED_ORDER_STATUSES
        and Decimal(order["amount"]) - Decimal(order["refunded_amount"]) > 0
    ]


def _revenue_campaign_ids(ctx: GenerationContext) -> set[str]:
    orders = _recognized_orders(ctx)
    contacts = {order["contact_id"] for order in orders}
    campaign_ids: set[str] = set()
    for contact_id in contacts:
        stats = ctx.contact_touch_stats.get(contact_id)
        if stats:
            campaign_ids.update(stats["campaign_ids"])
    return campaign_ids


def _label(
    ctx: GenerationContext,
    issue_type: str,
    entity_type: str,
    record_ids: list[str],
    split: str,
    expected_disposition: str,
    notes: str,
    severity: str,
) -> None:
    prefix = {
        "DUPLICATE_REVENUE": "DUP",
        "POST_CONVERSION_TOUCH": "POST",
        "CURRENCY_MISMATCH": "CUR",
        "MISSING_CAMPAIGN_COST": "MISS",
        "UNSUPPORTED_IDENTITY_LINK": "IDL",
    }[issue_type]
    existing = sum(1 for label in ctx.anomaly_labels if label["issue_type"] == issue_type)
    ctx.anomaly_labels.append(
        {
            "scenario_id": f"GT-{prefix}-{existing + 1:04d}",
            "issue_type": issue_type,
            "severity": severity,
            "entity_type": entity_type,
            "record_ids": "|".join(record_ids),
            "split": split,
            "expected_disposition": expected_disposition,
            "notes": notes,
            "fixture_version": ANOMALY_RULE_VERSION,
        }
    )
    ctx.fixture_counts[issue_type] = ctx.fixture_counts.get(issue_type, 0) + 1


def inject_anomalies(ctx: GenerationContext) -> None:
    spec = ctx.spec
    recognized = _recognized_orders(ctx)
    used_order_ids: set[str] = set()

    # ------------------------------------------------------------------
    # 1. Duplicate revenue: duplicate the same source transaction key.
    # ------------------------------------------------------------------
    candidates = [
        row for row in sorted(recognized, key=lambda item: item["order_id"]) if row["status"] == "PAID"
    ]
    duplicates = ctx.rng.sample(candidates, k=min(spec.duplicate_orders, len(candidates)))
    for original in duplicates:
        used_order_ids.add(original["order_id"])
        duplicate = dict(original)
        duplicate["order_id"] = ctx.new_id("order")
        ingested = parse_iso(original["ingested_at"]) + timedelta(days=2, hours=3)
        duplicate["ingested_at"] = iso(ingested)
        ctx.tables["orders"].append(duplicate)
        ctx.tables["lifecycle_events"].append(
            {
                "event_id": ctx.new_id("event"),
                "entity_type": "ORDER",
                "entity_id": duplicate["order_id"],
                "previous_state": "",
                "new_state": "CREATED",
                "occurred_at": original["ordered_at"],
                "reason": "Duplicate order received from source system",
                "source": "COMMERCE",
            }
        )
        ctx.tables["lifecycle_events"].append(
            {
                "event_id": ctx.new_id("event"),
                "entity_type": "ORDER",
                "entity_id": duplicate["order_id"],
                "previous_state": "CREATED",
                "new_state": "PAID",
                "occurred_at": iso(ingested),
                "reason": "Duplicate payment record received",
                "source": "COMMERCE",
            }
        )
        _label(
            ctx,
            "DUPLICATE_REVENUE",
            "ORDER",
            [original["order_id"], duplicate["order_id"]],
            split_for_timestamp(parse_iso(original["ordered_at"])),
            "Preserve both source rows; count only the earliest ingested transaction in revenue totals.",
            "Duplicate order shares source_system_ref with the original and represents the same economic transaction.",
            "HIGH",
        )

    # ------------------------------------------------------------------
    # 2. Post-conversion touchpoint.
    # ------------------------------------------------------------------
    post_candidates = [
        order
        for order in candidates
        if order["order_id"] not in used_order_ids
        and parse_iso(order["ordered_at"]) <= datetime.combine(DATASET_END, time(19, 0)) - timedelta(days=12)
    ]
    selected_post = ctx.rng.sample(
        post_candidates, k=min(spec.post_conversion_touches, len(post_candidates))
    )
    for order in selected_post:
        used_order_ids.add(order["order_id"])
        order_at = parse_iso(order["ordered_at"])
        occurred_at = order_at + timedelta(days=ctx.rng.randint(2, 10), hours=ctx.rng.randint(1, 6))
        cap = datetime.combine(DATASET_END, time(20, 0))
        if occurred_at > cap:
            occurred_at = cap
        active_campaigns = ctx.campaigns_by_day.get(occurred_at.date(), [])
        if active_campaigns:
            campaign = ctx.rng.choice(active_campaigns)
        else:
            stats = ctx.contact_touch_stats[order["contact_id"]]
            campaign = ctx.campaign_by_id[stats["campaign_ids"][-1]]
        campaign_id = campaign["campaign_id"]
        channel = ctx.channel_by_id[campaign["primary_channel_id"]]
        touch_id = ctx.new_id("touch")
        ctx.tables["touchpoints"].append(
            {
                "touchpoint_id": touch_id,
                "contact_id": order["contact_id"],
                "session_id": None,
                "campaign_id": campaign_id,
                "channel_id": campaign["primary_channel_id"],
                "creative_id": None,
                "occurred_at": iso(occurred_at),
                "touch_type": "EMAIL_CLICK" if channel["channel_type"] == "email" else "CLICK",
                "source_system": SOURCE_SYSTEM_BY_CHANNEL[channel["channel_type"]],
                "identity_status": "DIRECT",
                "consent_status": "GRANTED",
                "is_offline": False,
                "created_at": iso(occurred_at + timedelta(minutes=ctx.rng.randint(2, 90))),
            }
        )
        _label(
            ctx,
            "POST_CONVERSION_TOUCH",
            "TOUCHPOINT",
            [touch_id],
            split_for_timestamp(order_at),
            "Exclude touchpoint from attribution for the earlier conversion; retain it as source evidence.",
            f"Touchpoint occurred after order {order['order_id']} for the same contact.",
            "MEDIUM",
        )

    # ------------------------------------------------------------------
    # 3. Currency mismatch: incompatible cost currency without an FX rate.
    # ------------------------------------------------------------------
    revenue_campaigns = _revenue_campaign_ids(ctx)
    cost_campaigns = {row["campaign_id"] for row in ctx.tables["cost_records"]}
    paid_budgeted = [
        campaign
        for campaign in ctx.tables["campaigns"]
        if campaign["campaign_id"] in revenue_campaigns
        and campaign["campaign_id"] in cost_campaigns
        and Decimal(campaign["budget_amount"]) > 0
    ]
    currency_campaigns = ctx.rng.sample(
        sorted(paid_budgeted, key=lambda row: row["campaign_id"]),
        k=min(spec.currency_mismatch_costs, len(paid_budgeted)),
    )
    currency_campaign_ids = {row["campaign_id"] for row in currency_campaigns}
    for campaign in currency_campaigns:
        start = parse_iso(campaign["start_at"])
        end = parse_iso(campaign["end_at"])
        cost_date = start + (end - start) * ctx.rng.uniform(0.2, 0.8)
        cost_id = ctx.new_id("cost")
        amount = Decimal(str(round(ctx.rng.uniform(250.0, 1800.0), 2)))
        ctx.tables["cost_records"].append(
            {
                "cost_id": cost_id,
                "campaign_id": campaign["campaign_id"],
                "channel_id": campaign["primary_channel_id"],
                "creative_id": "",
                "cost_date": cost_date.date().isoformat(),
                "amount": str(amount),
                "currency": "USD",
                "cost_category": "MEDIA",
                "source_ref": f"INV-{cost_id}",
                "period": cost_date.strftime("%Y-%m"),
            }
        )
        _label(
            ctx,
            "CURRENCY_MISMATCH",
            "COST_RECORD",
            [cost_id],
            split_for_timestamp(cost_date),
            "Quarantine this cost from EUR totals; no documented FX rate is available for conversion.",
            f"Cost currency USD differs from campaign currency {campaign['budget_currency']}.",
            "MEDIUM",
        )

    # ------------------------------------------------------------------
    # 4. Missing campaign cost records.
    # ------------------------------------------------------------------
    remaining = [
        campaign
        for campaign in paid_budgeted
        if campaign["campaign_id"] not in currency_campaign_ids
    ]
    missing_campaigns = ctx.rng.sample(
        sorted(remaining, key=lambda row: row["campaign_id"]),
        k=min(spec.missing_cost_campaigns, len(remaining)),
    )
    for campaign in missing_campaigns:
        campaign_id = campaign["campaign_id"]
        removed = [row for row in ctx.tables["cost_records"] if row["campaign_id"] == campaign_id]
        ctx.tables["cost_records"] = [
            row for row in ctx.tables["cost_records"] if row["campaign_id"] != campaign_id
        ]
        first_order = next(
            (
                order
                for order in sorted(recognized, key=lambda row: row["ordered_at"])
                if campaign_id in ctx.contact_touch_stats[order["contact_id"]]["campaign_ids"]
            ),
            None,
        )
        split = (
            split_for_timestamp(parse_iso(first_order["ordered_at"]))
            if first_order
            else split_for_timestamp(parse_iso(campaign["start_at"]))
        )
        _label(
            ctx,
            "MISSING_CAMPAIGN_COST",
            "CAMPAIGN",
            [campaign_id],
            split,
            "Report spend as unknown and ROI as unavailable; do not treat missing cost as zero.",
            f"Removed {len(removed)} synthetic cost records for a campaign with recorded revenue influence.",
            "HIGH",
        )

    # ------------------------------------------------------------------
    # 5. Anonymous session linked without sufficient identity evidence.
    # ------------------------------------------------------------------
    identity_candidates = [
        order
        for order in candidates
        if order["order_id"] not in used_order_ids
        and ctx.contact_touch_stats[order["contact_id"]]["count"] > 0
    ]
    selected_identity = ctx.rng.sample(
        identity_candidates, k=min(spec.unsupported_links, len(identity_candidates))
    )
    for order in selected_identity:
        stats = ctx.contact_touch_stats[order["contact_id"]]
        campaign_id = stats["campaign_ids"][0]
        campaign = ctx.campaign_by_id[campaign_id]
        channel = ctx.channel_by_id[campaign["primary_channel_id"]]
        campaign_start = parse_iso(campaign["start_at"])
        campaign_end = parse_iso(campaign["end_at"])
        order_at = parse_iso(order["ordered_at"])
        proposed = order_at - timedelta(days=ctx.rng.randint(5, 20), hours=ctx.rng.randint(1, 5))
        occurred_at = max(campaign_start + timedelta(hours=1), min(proposed, campaign_end - timedelta(hours=1)))
        session_id = ctx.new_id("session")
        anonymous_id = ctx.new_id("anon")
        ctx.tables.setdefault("sessions", []).append(
            {
                "session_id": session_id,
                "anonymous_id": anonymous_id,
                "started_at": iso(occurred_at - timedelta(minutes=ctx.rng.randint(1, 8))),
                "ended_at": iso(occurred_at + timedelta(minutes=ctx.rng.randint(3, 30))),
                "source": "partner_referral",
                "medium": "referral",
                "landing_page": "/pricing",
                "campaign_id": campaign_id,
                "device_type": "desktop",
            }
        )
        link_id = ctx.new_id("link")
        ctx.tables["identity_links"].append(
            {
                "link_id": link_id,
                "session_id": session_id,
                "contact_id": order["contact_id"],
                "evidence_type": "TEMPORAL_PROXIMITY",
                "evidence_ref": "",
                "linked_at": iso(occurred_at),
                "status": "VERIFIED",
                "rule_id": "IDR-TEMPORAL-001",
            }
        )
        touch_id = ctx.new_id("touch")
        ctx.tables["touchpoints"].append(
            {
                "touchpoint_id": touch_id,
                "contact_id": None,
                "session_id": session_id,
                "campaign_id": campaign_id,
                "channel_id": campaign["primary_channel_id"],
                "creative_id": None,
                "occurred_at": iso(occurred_at),
                "touch_type": "CLICK",
                "source_system": SOURCE_SYSTEM_BY_CHANNEL[channel["channel_type"]],
                "identity_status": "SESSION_LINKED",
                "consent_status": "GRANTED",
                "is_offline": False,
                "created_at": iso(occurred_at + timedelta(minutes=ctx.rng.randint(2, 60))),
            }
        )
        _label(
            ctx,
            "UNSUPPORTED_IDENTITY_LINK",
            "IDENTITY_LINK",
            [link_id, session_id],
            split_for_timestamp(occurred_at),
            "Reject the unsupported link for attribution; retain the link and session for audit.",
            "Link uses TEMPORAL_PROXIMITY without documentary evidence and must not resolve the session.",
            "HIGH",
        )
