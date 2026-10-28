"""Generation of leads, opportunities, orders, costs and lifecycle history."""

from __future__ import annotations

import calendar
import math
import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from yottaflex.config import DATASET_END
from yottaflex.domain.lifecycle import is_valid_transition
from yottaflex.generation.context import GenerationContext
from yottaflex.util import iso, money, parse_iso

ORDER_STATUS_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("PAID", 0.88),
    ("PARTIALLY_REFUNDED", 0.05),
    ("REFUNDED", 0.04),
    ("CANCELLED", 0.03),
)

REGION_REVENUE_FACTOR: dict[str, float] = {
    "NORTH_AMERICA": 1.10,
    "EUROPE": 1.00,
    "APAC": 0.85,
    "LATAM": 0.72,
}

SEGMENT_REVENUE_FACTOR: dict[str, float] = {"SMB": 0.62, "MID_MARKET": 1.00, "ENTERPRISE": 2.35}


class EventWriter:
    """Append lifecycle events while enforcing the documented state machine."""

    def __init__(self, ctx: GenerationContext) -> None:
        self.ctx = ctx
        self.rows = ctx.tables.setdefault("lifecycle_events", [])

    def append(
        self,
        entity_type: str,
        entity_id: str,
        previous_state: str,
        new_state: str,
        occurred_at: datetime,
        reason: str,
        source: str,
    ) -> None:
        if not is_valid_transition(entity_type, previous_state, new_state):
            raise ValueError(
                f"Invalid lifecycle transition {entity_type} {previous_state!r}->{new_state!r}"
            )
        self.rows.append(
            {
                "event_id": self.ctx.new_id("event"),
                "entity_type": entity_type,
                "entity_id": entity_id,
                "previous_state": previous_state,
                "new_state": new_state,
                "occurred_at": iso(occurred_at),
                "reason": reason,
                "source": source,
            }
        )


def _weighted(rng: random.Random, options: tuple[tuple[Any, float], ...]) -> Any:
    return rng.choices([value for value, _ in options], weights=[weight for _, weight in options], k=1)[0]


def _select_converters(ctx: GenerationContext) -> list[str]:
    candidates: list[tuple[float, str]] = []
    for contact_id, stats in ctx.contact_touch_stats.items():
        if stats["count"] == 0 or stats["first_at"] is None:
            continue
        weight = 1.0 + 0.30 * stats["count"]
        if not stats["resolved_count"]:
            weight *= 0.85
        uniform = max(ctx.rng.random(), 1e-9)
        score = -math.log(uniform) / weight
        candidates.append((score, contact_id))
    candidates.sort()
    target = ctx.spec.opportunities
    if len(candidates) < target:  # pragma: no cover - profile sizing guard
        raise ValueError(
            f"Profile '{ctx.config.profile}' does not have enough contacts with touchpoints "
            f"to create {target} opportunities ({len(candidates)} available)."
        )
    selected = sorted(contact_id for _, contact_id in candidates[:target])

    # Ensure at least one conversion is consent-ineligible so that the unattributed
    # conversion path is exercised and visible in the delivered dataset.
    consent_eligible = [
        contact_id
        for contact_id in selected
        if ctx.contact_by_id[contact_id]["consent_status"] == "GRANTED"
    ]
    if len(consent_eligible) == len(selected):
        chosen = selected[ctx.rng.randrange(len(selected))]
        ctx.contact_by_id[chosen]["consent_status"] = "DENIED"
        touch_by_id = {row["touchpoint_id"]: row for row in ctx.tables["touchpoints"]}
        for touch_id in ctx.contact_touch_stats[chosen]["touch_ids"]:
            touch_by_id[touch_id]["consent_status"] = "DENIED"
    return selected


def _order_timestamp(ctx: GenerationContext, last_at: datetime) -> datetime:
    delay_days = ctx.rng.choices(
        [0, 1, 2, 3, 5, 7, 10, 14, 21],
        weights=[0.10, 0.14, 0.16, 0.14, 0.12, 0.10, 0.08, 0.06, 0.10],
        k=1,
    )[0]
    order_at = last_at + timedelta(
        days=delay_days, hours=ctx.rng.randint(1, 9), minutes=ctx.rng.randrange(60)
    )
    cap = datetime.combine(DATASET_END, time(22, 0))
    if order_at > cap:
        order_at = min(cap, last_at + timedelta(minutes=ctx.rng.randint(30, 90)))
    if order_at <= last_at:  # pragma: no cover - defensive
        order_at = last_at + timedelta(hours=1)
    return order_at


def _revenue_amount(ctx: GenerationContext, contact: dict[str, Any]) -> Decimal:
    base = ctx.rng.lognormvariate(7.65, 0.72)
    amount = base * SEGMENT_REVENUE_FACTOR[contact["segment"]] * REGION_REVENUE_FACTOR[contact["region"]]
    amount = min(max(amount, 49.0), 120_000.0)
    return money(amount)


def generate_transactions(ctx: GenerationContext) -> None:
    """Create conversion opportunities and their commercial records."""

    events = EventWriter(ctx)
    touch_by_id = {row["touchpoint_id"]: row for row in ctx.tables["touchpoints"]}
    ctx.metadata["touch_by_id"] = touch_by_id

    selected = _select_converters(ctx)
    leads = ctx.tables.setdefault("leads", [])
    opportunities = ctx.tables.setdefault("opportunities", [])
    orders = ctx.tables.setdefault("orders", [])
    conversion_by_contact: dict[str, dict[str, Any]] = ctx.metadata.setdefault(
        "conversion_by_contact", {}
    )

    for contact_id in selected:
        contact = ctx.contact_by_id[contact_id]
        stats = ctx.contact_touch_stats[contact_id]
        first_touch = touch_by_id[stats["first_touch_id"]]
        first_at: datetime = stats["first_at"]
        last_at: datetime = stats["last_at"]
        order_at = _order_timestamp(ctx, last_at)
        window_seconds = max((order_at - first_at).total_seconds(), 3600.0)
        lead_at = first_at + timedelta(seconds=window_seconds * ctx.rng.uniform(0.06, 0.22))
        opp_at = first_at + timedelta(seconds=window_seconds * ctx.rng.uniform(0.35, 0.68))
        if lead_at >= opp_at:  # pragma: no cover - defensive
            lead_at = first_at
            opp_at = first_at + timedelta(minutes=5)
        qualified_at = lead_at + (opp_at - lead_at) * 0.55
        amount = _revenue_amount(ctx, contact)

        recent_opportunity = (DATASET_END - opp_at.date()).days <= 45
        outcome_roll = ctx.rng.random()
        if recent_opportunity and outcome_roll < 0.20:
            outcome = "OPEN"
        elif outcome_roll < 0.57:
            outcome = "WON"
        else:
            outcome = "LOST"

        if outcome == "OPEN":
            stage = _weighted(
                ctx.rng,
                (("OPEN", 0.25), ("QUALIFIED", 0.30), ("PROPOSAL", 0.25), ("NEGOTIATION", 0.20)),
            )
            closed_at = None
            expected_value = amount
        else:
            if outcome == "WON":
                stage = "CLOSED_WON"
                closed_at = order_at - timedelta(
                    minutes=ctx.rng.randint(30, max(31, int((order_at - opp_at).total_seconds() // 120)))
                )
                if closed_at <= opp_at:
                    closed_at = opp_at + timedelta(minutes=10)
                expected_value = amount
            else:
                stage = "CLOSED_LOST"
                closed_at = min(
                    datetime.combine(DATASET_END, time(21, 0)),
                    opp_at + timedelta(days=ctx.rng.randint(5, 45), hours=ctx.rng.randint(1, 8)),
                )
                expected_value = money(float(amount) * ctx.rng.uniform(0.7, 1.3))

        lead_id = ctx.new_id("lead")
        source_channel = ctx.channel_by_id[first_touch["channel_id"]]["name"]
        source_session_id = first_touch["session_id"]
        lead_status = "CONVERTED"
        leads.append(
            {
                "lead_id": lead_id,
                "contact_id": contact_id,
                "created_at": iso(lead_at),
                "source": source_channel,
                "status": lead_status,
                "qualified_at": iso(qualified_at),
                "source_session_id": source_session_id,
            }
        )
        events.append("LEAD", lead_id, "", "NEW", lead_at, "Lead captured", "MARKETING_AUTOMATION")
        events.append(
            "LEAD",
            lead_id,
            "NEW",
            "WORKING",
            lead_at + (qualified_at - lead_at) * 0.35,
            "Lead assigned to sales development",
            "CRM",
        )
        events.append(
            "LEAD", lead_id, "WORKING", "QUALIFIED", qualified_at, "Qualification criteria met", "CRM"
        )
        if lead_status == "CONVERTED":
            events.append(
                "LEAD", lead_id, "QUALIFIED", "CONVERTED", opp_at, "Converted to opportunity", "CRM"
            )

        opportunity_id = ctx.new_id("opportunity")
        opportunities.append(
            {
                "opportunity_id": opportunity_id,
                "lead_id": lead_id,
                "contact_id": contact_id,
                "created_at": iso(opp_at),
                "stage": stage,
                "expected_value": str(expected_value),
                "currency": "EUR",
                "closed_at": iso(closed_at) if closed_at else "",
                "outcome": outcome,
                "owner_team": contact["region"].title().replace("_", " "),
            }
        )
        _write_opportunity_events(events, opportunity_id, opp_at, closed_at, stage, outcome)

        order_id: str | None = None
        if outcome == "WON":
            status = _weighted(ctx.rng, ORDER_STATUS_WEIGHTS)
            refunded = Decimal("0.00")
            if status == "PARTIALLY_REFUNDED":
                refunded = money(amount * Decimal(str(ctx.rng.uniform(0.05, 0.45))))
            elif status == "REFUNDED":
                refunded = amount
            order_id = ctx.new_id("order")
            ingested_at = order_at + timedelta(hours=ctx.rng.randint(1, 12), minutes=ctx.rng.randrange(60))
            orders.append(
                {
                    "order_id": order_id,
                    "opportunity_id": opportunity_id,
                    "contact_id": contact_id,
                    "ordered_at": iso(order_at),
                    "status": status,
                    "amount": str(amount),
                    "refunded_amount": str(refunded),
                    "currency": "EUR",
                    "source_system_ref": f"TXN-{order_id.split('-')[-1]}-{ctx.rng.randrange(1000, 9999)}",
                    "ingested_at": iso(ingested_at),
                }
            )
            _write_order_events(events, order_id, order_at, ingested_at, status, ctx.rng)

        conversion_by_contact[contact_id] = {
            "lead_id": lead_id,
            "opportunity_id": opportunity_id,
            "order_id": order_id,
            "outcome": outcome,
            "lead_created_at": lead_at,
            "opportunity_created_at": opp_at,
            "order_at": order_at if order_id else None,
            "amount": amount,
        }
        contact["lifecycle_status"] = "CUSTOMER" if outcome == "WON" else "QUALIFIED"

    _generate_secondary_leads(ctx, events, touch_by_id, selected)
    _generate_campaign_lifecycle(ctx, events)
    _generate_contact_lifecycle(ctx, events)
    _generate_cost_records(ctx)


def _write_opportunity_events(
    events: EventWriter,
    opportunity_id: str,
    created_at: datetime,
    closed_at: datetime | None,
    stage: str,
    outcome: str,
) -> None:
    events.append("OPPORTUNITY", opportunity_id, "", "OPEN", created_at, "Opportunity created", "CRM")
    chain = ["QUALIFIED", "PROPOSAL", "NEGOTIATION"]
    stages_to_write = {"OPEN": 0, "QUALIFIED": 1, "PROPOSAL": 2, "NEGOTIATION": 3}.get(stage, 3)
    end = closed_at if closed_at is not None else created_at + timedelta(days=20)
    total_seconds = max((end - created_at).total_seconds(), 600.0)
    previous = "OPEN"
    for index in range(stages_to_write):
        next_stage = chain[index]
        timestamp = created_at + timedelta(seconds=total_seconds * ((index + 1) / (stages_to_write + 2)))
        if timestamp >= end:
            timestamp = end - timedelta(minutes=1)
        events.append(
            "OPPORTUNITY",
            opportunity_id,
            previous,
            next_stage,
            timestamp,
            f"Stage advanced to {next_stage.title()}",
            "CRM",
        )
        previous = next_stage
    if closed_at is not None:
        events.append(
            "OPPORTUNITY",
            opportunity_id,
            previous,
            stage,
            closed_at,
            "Closed won" if outcome == "WON" else "Closed lost",
            "CRM",
        )


def _write_order_events(
    events: EventWriter,
    order_id: str,
    ordered_at: datetime,
    ingested_at: datetime,
    status: str,
    rng: random.Random,
) -> None:
    events.append("ORDER", order_id, "", "CREATED", ordered_at, "Order placed", "COMMERCE")
    if status == "CANCELLED":
        cancelled_at = ordered_at + timedelta(hours=rng.randint(1, 48))
        if cancelled_at > ingested_at:
            cancelled_at = ingested_at
        events.append("ORDER", order_id, "CREATED", "CANCELLED", cancelled_at, "Order cancelled", "COMMERCE")
        return
    events.append("ORDER", order_id, "CREATED", "PAID", ingested_at, "Payment captured", "COMMERCE")
    if status in ("REFUNDED", "PARTIALLY_REFUNDED"):
        refund_at = min(
            datetime.combine(DATASET_END, time(21, 0)),
            ingested_at + timedelta(days=rng.randint(1, 14), hours=rng.randint(1, 6)),
        )
        if refund_at <= ingested_at:
            refund_at = ingested_at + timedelta(minutes=30)
        events.append(
            "ORDER",
            order_id,
            "PAID",
            status,
            refund_at,
            "Refund processed" if status == "REFUNDED" else "Partial refund processed",
            "COMMERCE",
        )


def _generate_secondary_leads(
    ctx: GenerationContext,
    events: EventWriter,
    touch_by_id: dict[str, dict[str, Any]],
    selected: list[str],
) -> None:
    selected_set = set(selected)
    leads = ctx.tables["leads"]
    for contact_id, stats in sorted(ctx.contact_touch_stats.items()):
        if contact_id in selected_set or stats["count"] == 0:
            continue
        if ctx.rng.random() >= 0.08:
            continue
        first_touch = touch_by_id[stats["first_touch_id"]]
        lead_at: datetime = stats["first_at"] + timedelta(
            days=ctx.rng.randint(0, 7), hours=ctx.rng.randint(1, 8)
        )
        lead_at = min(lead_at, datetime.combine(DATASET_END, time(20, 0)))
        status = _weighted(
            ctx.rng,
            (("NEW", 0.38), ("WORKING", 0.28), ("QUALIFIED", 0.20), ("DISQUALIFIED", 0.14)),
        )
        qualified_at = None
        if status in ("QUALIFIED", "DISQUALIFIED"):
            qualified_at = min(
                datetime.combine(DATASET_END, time(21, 0)),
                lead_at + timedelta(days=ctx.rng.randint(1, 10)),
            )
        lead_id = ctx.new_id("lead")
        leads.append(
            {
                "lead_id": lead_id,
                "contact_id": contact_id,
                "created_at": iso(lead_at),
                "source": ctx.channel_by_id[first_touch["channel_id"]]["name"],
                "status": status,
                "qualified_at": iso(qualified_at) if qualified_at else "",
                "source_session_id": first_touch["session_id"],
            }
        )
        events.append("LEAD", lead_id, "", "NEW", lead_at, "Lead captured", "MARKETING_AUTOMATION")
        working_at = lead_at + timedelta(hours=ctx.rng.randint(2, 24))
        if status != "NEW":
            events.append("LEAD", lead_id, "NEW", "WORKING", working_at, "Lead worked", "CRM")
        if status == "QUALIFIED" and qualified_at is not None:
            events.append(
                "LEAD", lead_id, "WORKING", "QUALIFIED", qualified_at, "Qualification criteria met", "CRM"
            )
        if status == "DISQUALIFIED" and qualified_at is not None:
            events.append(
                "LEAD", lead_id, "WORKING", "DISQUALIFIED", qualified_at, "Disqualified by sales", "CRM"
            )


def _generate_campaign_lifecycle(ctx: GenerationContext, events: EventWriter) -> None:
    for campaign in ctx.tables["campaigns"]:
        created = parse_iso(campaign["created_at"])
        start = parse_iso(campaign["start_at"])
        end = parse_iso(campaign["end_at"])
        events.append(
            "CAMPAIGN", campaign["campaign_id"], "", "PLANNED", created, "Campaign created", "MARKETING_OPS"
        )
        events.append(
            "CAMPAIGN",
            campaign["campaign_id"],
            "PLANNED",
            "ACTIVE",
            start,
            "Campaign launched",
            "MARKETING_OPS",
        )
        if campaign["status"] == "PAUSED":
            pause_at = start + (end - start) * ctx.rng.uniform(0.3, 0.8)
            events.append(
                "CAMPAIGN",
                campaign["campaign_id"],
                "ACTIVE",
                "PAUSED",
                pause_at,
                "Campaign paused by operator",
                "MARKETING_OPS",
            )
        elif campaign["status"] == "COMPLETED":
            events.append(
                "CAMPAIGN",
                campaign["campaign_id"],
                "ACTIVE",
                "COMPLETED",
                end,
                "Campaign completed",
                "MARKETING_OPS",
            )


def _generate_contact_lifecycle(ctx: GenerationContext, events: EventWriter) -> None:
    conversions = ctx.metadata.get("conversion_by_contact", {})
    for contact in ctx.tables["contacts"]:
        contact_id = contact["contact_id"]
        created = parse_iso(contact["created_at"])
        events.append("CONTACT", contact_id, "", "NEW", created, "Contact created", "WEB")
        stats = ctx.contact_touch_stats[contact_id]
        conversion = conversions.get(contact_id)
        if conversion:
            events.append(
                "CONTACT",
                contact_id,
                "NEW",
                "ENGAGED",
                stats["first_at"],
                "First marketing interaction",
                "WEB",
            )
            lead_at = conversion["lead_created_at"]
            if lead_at > stats["first_at"]:
                events.append(
                    "CONTACT",
                    contact_id,
                    "ENGAGED",
                    "QUALIFIED",
                    lead_at,
                    "Lead qualified",
                    "CRM",
                )
            if conversion["outcome"] == "WON":
                order_at = conversion["order_at"]
                events.append(
                    "CONTACT",
                    contact_id,
                    "QUALIFIED",
                    "CUSTOMER",
                    order_at,
                    "First paid order",
                    "COMMERCE",
                )
        elif stats["count"] > 0 and ctx.rng.random() < 0.16:
            events.append(
                "CONTACT",
                contact_id,
                "NEW",
                "ENGAGED",
                stats["first_at"],
                "Marketing engagement observed",
                "WEB",
            )
            contact["lifecycle_status"] = "ENGAGED"
            if ctx.rng.random() < 0.20:
                dormant_at = min(
                    datetime.combine(DATASET_END, time(21, 0)),
                    stats["last_at"] + timedelta(days=ctx.rng.randint(30, 120)),
                )
                if dormant_at > stats["last_at"]:
                    events.append(
                        "CONTACT",
                        contact_id,
                        "ENGAGED",
                        "DORMANT",
                        dormant_at,
                        "No activity in trailing period",
                        "WAREHOUSE",
                    )
                    contact["lifecycle_status"] = "DORMANT"


def _month_end(day: datetime) -> datetime:
    last_day = calendar.monthrange(day.year, day.month)[1]
    return datetime(day.year, day.month, last_day, 18, 0)


def _generate_cost_records(ctx: GenerationContext) -> None:
    costs = ctx.tables.setdefault("cost_records", [])
    for campaign in ctx.tables["campaigns"]:
        budget = Decimal(campaign["budget_amount"])
        if budget <= 0:
            continue
        start = parse_iso(campaign["start_at"])
        end = parse_iso(campaign["end_at"])
        months: list[tuple[datetime, datetime]] = []
        cursor = datetime(start.year, start.month, 1)
        while cursor <= end:
            end_of_month = _month_end(cursor)
            period_end = min(end_of_month, end)
            period_start = max(cursor, start)
            if period_end >= period_start:
                months.append((period_start, period_end))
            if cursor.month == 12:
                cursor = datetime(cursor.year + 1, 1, 1)
            else:
                cursor = datetime(cursor.year, cursor.month + 1, 1)
        if not months:
            continue
        weights = [ctx.rng.uniform(0.78, 1.22) for _ in months]
        total_weight = sum(weights)
        spend_factor = ctx.rng.uniform(0.68, 1.24)
        total_spend = money(budget * Decimal(str(spend_factor)))
        allocated = Decimal("0.00")
        for index, ((period_start, period_end), weight) in enumerate(zip(months, weights, strict=True)):
            if index == len(months) - 1:
                amount = total_spend - allocated
            else:
                amount = money(total_spend * Decimal(str(weight)) / Decimal(str(total_weight)))
                allocated += amount
            if amount <= 0:
                continue
            cost_id = ctx.new_id("cost")
            cost_date = period_start + (period_end - period_start) / 2
            costs.append(
                {
                    "cost_id": cost_id,
                    "campaign_id": campaign["campaign_id"],
                    "channel_id": campaign["primary_channel_id"],
                    "creative_id": "",
                    "cost_date": cost_date.date().isoformat(),
                    "amount": str(amount),
                    "currency": campaign["budget_currency"],
                    "cost_category": _weighted(
                        ctx.rng, (("MEDIA", 0.85), ("PLATFORM_FEE", 0.10), ("CREATIVE", 0.05))
                    ),
                    "source_ref": f"INV-{cost_id}",
                    "period": period_start.strftime("%Y-%m"),
                }
            )
