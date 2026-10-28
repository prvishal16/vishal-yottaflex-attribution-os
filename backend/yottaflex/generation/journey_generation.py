"""Synthetic customer journeys: touchpoints, sessions and identity evidence."""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import Any

from yottaflex.config import (
    DATASET_END,
    DATASET_START,
    date_range,
)
from yottaflex.generation.context import GenerationContext
from yottaflex.util import iso, parse_iso

TOUCH_COUNT_WEIGHTS: tuple[float, ...] = (
    0.06,  # 0
    0.10,  # 1
    0.13,  # 2
    0.15,  # 3
    0.15,  # 4
    0.13,  # 5
    0.10,  # 6
    0.07,  # 7
    0.05,  # 8
    0.03,  # 9
    0.02,  # 10
    0.01,  # 11
)

JOURNEY_SPANS: tuple[tuple[tuple[int, int], float], ...] = (
    ((7, 30), 0.22),
    ((31, 90), 0.38),
    ((91, 180), 0.27),
    ((181, 300), 0.13),
)

TOUCH_TYPE_BY_CHANNEL: dict[str, tuple[tuple[str, float], ...]] = {
    "search": (("CLICK", 0.72), ("IMPRESSION", 0.28)),
    "social": (("IMPRESSION", 0.58), ("CLICK", 0.42)),
    "email": (("EMAIL_OPEN", 0.58), ("EMAIL_CLICK", 0.42)),
    "referral": (("CLICK", 1.0),),
    "display": (("IMPRESSION", 0.80), ("CLICK", 0.20)),
    "direct": (("CLICK", 1.0),),
    "event": (("OFFLINE_EVENT", 0.70), ("PHONE_CALL", 0.30)),
}

SOURCE_SYSTEM_BY_CHANNEL: dict[str, str] = {
    "search": "AD_SERVER",
    "social": "AD_SERVER",
    "display": "AD_SERVER",
    "email": "EMAIL_PLATFORM",
    "referral": "WEB_ANALYTICS",
    "direct": "WEB_ANALYTICS",
    "event": "EVENT_PLATFORM",
}

SESSION_SOURCE_BY_CHANNEL: dict[str, tuple[str, str]] = {
    "search": ("google", "cpc"),
    "social": ("linkedin", "paid_social"),
    "email": ("newsletter", "email"),
    "referral": ("partner_referral", "referral"),
    "display": ("ad_network", "display"),
    "direct": ("direct", "none"),
    "event": ("offline_event", "event"),
}

EVIDENCE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("EMAIL_CLICK_SSO", 0.42),
    ("AUTHENTICATED_LOGIN", 0.30),
    ("FORM_SUBMIT_MATCH", 0.22),
    ("CRM_IMPORT_MATCH", 0.06),
)

LANDING_PAGES: tuple[str, ...] = (
    "/pricing",
    "/product/overview",
    "/demo",
    "/solutions/marketing",
    "/solutions/analytics",
    "/resources/guide",
    "/events/register",
    "/",
)

DEVICE_TYPES: tuple[tuple[str, float], ...] = (("desktop", 0.55), ("mobile", 0.40), ("tablet", 0.05))


def prepare_campaign_index(ctx: GenerationContext) -> None:
    """Build date/channel indexes so campaign selection is referentially safe."""

    campaign_channel_map: dict[str, list[dict[str, Any]]] = {}
    for row in ctx.tables["campaign_channels"]:
        campaign_channel_map.setdefault(row["campaign_id"], []).append(row)
    for rows in campaign_channel_map.values():
        rows.sort(key=lambda row: (not _as_bool(row["is_primary"]), row["channel_id"]))

    for campaign in ctx.tables["campaigns"]:
        ctx.campaign_by_id[campaign["campaign_id"]] = campaign
    for channel in ctx.tables["channels"]:
        ctx.channel_by_id[channel["channel_id"]] = channel
    for contact in ctx.tables["contacts"]:
        ctx.contact_by_id[contact["contact_id"]] = contact

    for creative in ctx.tables["creatives"]:
        key = (creative["campaign_id"], creative["channel_id"])
        ctx.creatives_by_campaign_channel.setdefault(key, []).append(creative)

    days = date_range(date(2025, 8, 15), date(2026, 9, 30))
    for day in days:
        active: list[dict[str, Any]] = []
        for campaign in ctx.tables["campaigns"]:
            start = parse_iso(campaign["start_at"]).date()
            end = parse_iso(campaign["end_at"]).date()
            if start <= day <= end:
                active.append(campaign)
        if not active:
            continue
        ctx.campaigns_by_day[day] = active
        for campaign in active:
            for bridge in campaign_channel_map.get(campaign["campaign_id"], []):
                ctx.campaigns_by_day_channel.setdefault((day, bridge["channel_id"]), []).append(campaign)

    ctx.metadata["campaign_channel_map"] = campaign_channel_map


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def _weighted(rng: random.Random, options: tuple[tuple[Any, float], ...]) -> Any:
    return rng.choices([value for value, _ in options], weights=[weight for _, weight in options], k=1)[0]


def _touch_counts(ctx: GenerationContext) -> list[int]:
    contacts = ctx.tables["contacts"]
    counts = [rng_choices(rng=ctx.rng, options=TOUCH_COUNT_WEIGHTS) for _ in contacts]
    # Anomaly fixtures add touchpoints later; keep the final dataset at the
    # published profile size by reserving room for those fixture rows.
    fixture_touches = ctx.spec.post_conversion_touches + ctx.spec.unsupported_links
    target = max(1, ctx.spec.touchpoints - fixture_touches)
    delta = target - sum(counts)
    if delta > 0:
        for _ in range(delta):
            candidate = ctx.rng.randrange(len(counts))
            if counts[candidate] < 15:
                counts[candidate] += 1
    elif delta < 0:
        removable = [index for index, count in enumerate(counts) if count > 0]
        for _ in range(-delta):
            index = removable[ctx.rng.randrange(len(removable))]
            if counts[index] > 1:
                counts[index] -= 1
            else:
                counts[index] = 0
                removable.remove(index)
    return counts


def rng_choices(rng: random.Random, options: tuple[float, ...]) -> int:
    return rng.choices(range(len(options)), weights=list(options), k=1)[0]


def _choose_campaign(
    ctx: GenerationContext,
    day: date,
    preferred_channel_id: str,
    previous_campaign_id: str | None,
    prefer_channel: bool,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    if prefer_channel and ctx.rng.random() < 0.72:
        candidates = list(ctx.campaigns_by_day_channel.get((day, preferred_channel_id), []))
    if not candidates:
        candidates = list(ctx.campaigns_by_day.get(day, []))
    if not candidates:  # defensive guard: clamp to a campaign that starts nearest the day
        candidates = [ctx.tables["campaigns"][0]]
    if previous_campaign_id and len(candidates) > 1:
        filtered = [row for row in candidates if row["campaign_id"] != previous_campaign_id]
        if filtered:
            candidates = filtered
    weights = [
        1.35 if ctx.channel_by_id[row["primary_channel_id"]]["is_paid"] else 1.0 for row in candidates
    ]
    return ctx.rng.choices(candidates, weights=weights, k=1)[0]


def _clamp_to_campaign(
    ctx: GenerationContext, campaign: dict[str, Any], candidate: datetime
) -> datetime:
    start = parse_iso(campaign["start_at"])
    end = parse_iso(campaign["end_at"])
    if candidate < start:
        return start + timedelta(minutes=ctx.rng.randint(5, 90))
    if candidate > end:
        return end - timedelta(minutes=ctx.rng.randint(5, 90))
    return candidate


def _pick_creative(
    ctx: GenerationContext, campaign_id: str, channel_id: str, occurred_at: datetime
) -> str | None:
    candidates = ctx.creatives_by_campaign_channel.get((campaign_id, channel_id), [])
    effective = [
        row
        for row in candidates
        if parse_iso(row["start_at"]) <= occurred_at <= parse_iso(row["end_at"])
    ]
    if not effective:
        effective = candidates
    if not effective:
        return None
    return effective[ctx.rng.randrange(len(effective))]["creative_id"]


def _create_session(
    ctx: GenerationContext,
    campaign: dict[str, Any],
    channel: dict[str, Any],
    occurred_at: datetime,
    anonymous: bool,
    create_link: bool,
) -> tuple[str, bool]:
    session_id = ctx.new_id("session")
    anonymous_id = ctx.new_id("anon")
    source, medium = SESSION_SOURCE_BY_CHANNEL[channel["channel_type"]]
    device = _weighted(ctx.rng, DEVICE_TYPES)
    started_at = occurred_at - timedelta(minutes=ctx.rng.randint(1, 15))
    ended_at = occurred_at + timedelta(minutes=ctx.rng.randint(2, 40))
    ctx.tables.setdefault("sessions", []).append(
        {
            "session_id": session_id,
            "anonymous_id": anonymous_id,
            "started_at": iso(started_at),
            "ended_at": iso(ended_at),
            "source": source,
            "medium": medium,
            "landing_page": ctx.rng.choice(LANDING_PAGES),
            "campaign_id": campaign["campaign_id"],
            "device_type": device,
        }
    )
    linked = False
    if anonymous and create_link:
        evidence_type = _weighted(ctx.rng, EVIDENCE_WEIGHTS)
        rule_id = {
            "EMAIL_CLICK_SSO": "IDR-EMAIL-CLICK-001",
            "AUTHENTICATED_LOGIN": "IDR-LOGIN-001",
            "FORM_SUBMIT_MATCH": "IDR-FORM-MATCH-001",
            "CRM_IMPORT_MATCH": "IDR-CRM-MATCH-001",
        }[evidence_type]
        ctx.tables.setdefault("identity_links", []).append(
            {
                "link_id": ctx.new_id("link"),
                "session_id": session_id,
                "contact_id": ctx.metadata["_current_contact_id"],
                "evidence_type": evidence_type,
                "evidence_ref": f"EV-{session_id}",
                "linked_at": iso(started_at + timedelta(minutes=ctx.rng.randint(0, 25))),
                "status": "VERIFIED",
                "rule_id": rule_id,
            }
        )
        linked = True
    return session_id, linked


def generate_touchpoints(ctx: GenerationContext) -> None:
    """Generate touchpoints for every contact, then attach sessions and evidence."""

    prepare_campaign_index(ctx)
    contacts = ctx.tables["contacts"]
    counts = _touch_counts(ctx)
    touches: list[dict[str, Any]] = []

    for contact, desired_count in zip(contacts, counts, strict=True):
        contact_id = contact["contact_id"]
        ctx.metadata["_current_contact_id"] = contact_id
        created_at = parse_iso(contact["created_at"])
        stats: dict[str, Any] = {
            "contact_id": contact_id,
            "count": desired_count,
            "first_at": None,
            "last_at": None,
            "first_touch_id": None,
            "last_touch_id": None,
            "resolved_count": 0,
            "unresolved_count": 0,
            "campaign_ids": [],
            "touch_ids": [],
        }
        if desired_count == 0:
            ctx.contact_touch_stats[contact_id] = stats
            continue

        span_range = _weighted(ctx.rng, JOURNEY_SPANS)
        span_days = ctx.rng.randint(span_range[0], span_range[1])
        horizon = min(created_at.date() + timedelta(days=span_days), date(2026, 9, 29))
        available_days = max(0, (horizon - created_at.date()).days)
        offsets = [ctx.rng.randint(0, available_days) for _ in range(desired_count)]
        offsets[0] = ctx.rng.randint(0, min(2, available_days))
        offsets.sort()

        anonymous_prefix = 0
        roll = ctx.rng.random()
        if roll < 0.30:
            anonymous_prefix = 1
        elif roll < 0.38:
            anonymous_prefix = 2
        anonymous_prefix = min(anonymous_prefix, desired_count)

        previous_campaign_id: str | None = None
        contact_touches: list[dict[str, Any]] = []
        for position, offset in enumerate(offsets):
            day = created_at.date() + timedelta(days=offset)
            occurred_at = _business_datetime(ctx.rng, day)
            if occurred_at < created_at:
                occurred_at = created_at + timedelta(minutes=ctx.rng.randint(1, 60))
            prefer_channel = position == 0 or ctx.rng.random() < 0.30
            campaign = _choose_campaign(
                ctx,
                day,
                contact["acquisition_channel_id"],
                previous_campaign_id,
                prefer_channel,
            )
            occurred_at = _clamp_to_campaign(ctx, campaign, occurred_at)
            if position == 0:
                occurred_at = max(occurred_at, created_at)

            channel_rows = ctx.metadata["campaign_channel_map"].get(campaign["campaign_id"], [])
            primary_channel_id = campaign["primary_channel_id"]
            if len(channel_rows) > 1 and ctx.rng.random() < 0.06:
                channel_id = channel_rows[1]["channel_id"]
            else:
                channel_id = primary_channel_id
            channel = ctx.channel_by_id[channel_id]
            touch_type = _weighted(ctx.rng, TOUCH_TYPE_BY_CHANNEL[channel["channel_type"]])
            is_offline = channel["channel_type"] == "event" or touch_type == "PHONE_CALL"
            creative_id = _pick_creative(ctx, campaign["campaign_id"], channel_id, occurred_at)

            anonymous = position < anonymous_prefix
            session_id: str | None = None
            identity_status = "DIRECT"
            resolved = True
            if anonymous:
                linked = ctx.rng.random() < 0.84
                session_id, linked = _create_session(
                    ctx, campaign, channel, occurred_at, anonymous=True, create_link=linked
                )
                identity_status = "SESSION_LINKED" if linked else "UNRESOLVED"
                resolved = linked
            elif ctx.rng.random() < 0.30:
                session_id, _ = _create_session(
                    ctx, campaign, channel, occurred_at, anonymous=False, create_link=False
                )

            touch_id = ctx.new_id("touch")
            row = {
                "touchpoint_id": touch_id,
                "contact_id": None if anonymous else contact_id,
                "session_id": session_id,
                "campaign_id": campaign["campaign_id"],
                "channel_id": channel_id,
                "creative_id": creative_id,
                "occurred_at": iso(occurred_at),
                "touch_type": touch_type,
                "source_system": SOURCE_SYSTEM_BY_CHANNEL[channel["channel_type"]],
                "identity_status": identity_status,
                "consent_status": contact["consent_status"],
                "is_offline": is_offline,
                "created_at": iso(occurred_at + timedelta(minutes=ctx.rng.randint(1, 120))),
            }
            touches.append(row)
            contact_touches.append(row)
            stats["campaign_ids"].append(campaign["campaign_id"])
            stats["touch_ids"].append(touch_id)
            if resolved:
                stats["resolved_count"] += 1
            else:
                stats["unresolved_count"] += 1
            previous_campaign_id = campaign["campaign_id"]

        contact_touches.sort(key=lambda row: (row["occurred_at"], row["touchpoint_id"]))
        stats["first_at"] = parse_iso(contact_touches[0]["occurred_at"])
        stats["last_at"] = parse_iso(contact_touches[-1]["occurred_at"])
        stats["first_touch_id"] = contact_touches[0]["touchpoint_id"]
        stats["last_touch_id"] = contact_touches[-1]["touchpoint_id"]
        ctx.contact_touch_stats[contact_id] = stats

    ctx.tables["touchpoints"] = touches
    ctx.tables.setdefault("sessions", [])
    ctx.tables.setdefault("identity_links", [])


def _business_datetime(rng: random.Random, day: date) -> datetime:
    hour_weights = (1, 1, 2, 4, 6, 7, 7, 6, 6, 5, 4, 4, 3, 3, 2, 1, 1)
    hour = rng.choices(range(6, 23), weights=hour_weights, k=1)[0]
    return datetime.combine(day, time(hour, rng.randrange(60), rng.randrange(60)))


def dataset_day_bounds() -> tuple[date, date]:
    return DATASET_START, DATASET_END
