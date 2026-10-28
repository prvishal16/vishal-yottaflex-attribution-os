"""Generation of independent reference data and master entities.

Records are generated in dependency order. Every foreign key is selected from
previously generated parent records; child identifiers are never invented.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from yottaflex.config import (
    DATASET_END,
    DATASET_START,
    GENERATOR_VERSION,
    REPORTING_CURRENCY,
    ProfileSpec,
)
from yottaflex.util import iso, money

CHANNELS: tuple[dict[str, Any], ...] = (
    {
        "channel_id": "CHN-000001",
        "name": "Paid Search",
        "category": "paid",
        "channel_type": "search",
        "is_paid": True,
    },
    {
        "channel_id": "CHN-000002",
        "name": "Paid Social",
        "category": "paid",
        "channel_type": "social",
        "is_paid": True,
    },
    {
        "channel_id": "CHN-000003",
        "name": "Email",
        "category": "owned",
        "channel_type": "email",
        "is_paid": False,
    },
    {
        "channel_id": "CHN-000004",
        "name": "Organic Search",
        "category": "organic",
        "channel_type": "search",
        "is_paid": False,
    },
    {
        "channel_id": "CHN-000005",
        "name": "Referral",
        "category": "earned",
        "channel_type": "referral",
        "is_paid": False,
    },
    {
        "channel_id": "CHN-000006",
        "name": "Display",
        "category": "paid",
        "channel_type": "display",
        "is_paid": True,
    },
    {
        "channel_id": "CHN-000007",
        "name": "Direct",
        "category": "direct",
        "channel_type": "direct",
        "is_paid": False,
    },
    {
        "channel_id": "CHN-000008",
        "name": "Offline Events",
        "category": "offline",
        "channel_type": "event",
        "is_paid": True,
    },
)

CHANNEL_MIX: tuple[tuple[str, float], ...] = (
    ("CHN-000001", 0.22),
    ("CHN-000002", 0.18),
    ("CHN-000003", 0.20),
    ("CHN-000004", 0.11),
    ("CHN-000005", 0.08),
    ("CHN-000006", 0.10),
    ("CHN-000007", 0.06),
    ("CHN-000008", 0.05),
)

AUDIENCES: tuple[dict[str, Any], ...] = (
    ("Enterprise Prospects", "FIRMOGRAPHIC", "Companies with 1,000+ employees in target industries."),
    ("Mid-Market Growth", "FIRMOGRAPHIC", "Companies with 100-999 employees and growth signals."),
    ("SMB Self-Serve", "FIRMOGRAPHIC", "Small businesses evaluating self-serve plans."),
    ("North America Buyers", "GEOGRAPHY", "Synthetic regional segment for North America."),
    ("Europe Decision Makers", "GEOGRAPHY", "Synthetic regional segment for Europe."),
    ("APAC Expansion", "GEOGRAPHY", "Synthetic regional segment for Asia-Pacific."),
    ("High Intent Visitors", "BEHAVIORAL", "Visitors with repeated pricing or demo page activity."),
    ("Cart Abandoners", "BEHAVIORAL", "Synthetic users who abandoned an evaluation request."),
    ("New Subscribers", "LIFECYCLE", "Contacts created in the last 60 days."),
    ("Returning Customers", "LIFECYCLE", "Existing customers eligible for expansion offers."),
    ("Lapsed Customers", "LIFECYCLE", "Customers without activity for 180 days."),
    ("Event Attendees", "ENGAGEMENT", "Synthetic registrants of online and offline events."),
)

CAMPAIGN_TYPES: tuple[tuple[str, float], ...] = (
    ("ACQUISITION", 0.40),
    ("NURTURE", 0.22),
    ("RETENTION", 0.14),
    ("BRAND", 0.12),
    ("PRODUCT_LAUNCH", 0.12),
)

OBJECTIVES: tuple[tuple[str, float], ...] = (
    ("LEAD_GENERATION", 0.45),
    ("REVENUE", 0.30),
    ("AWARENESS", 0.15),
    ("RETENTION", 0.10),
)

CREATIVE_TYPES: dict[str, tuple[tuple[str, float], ...]] = {
    "search": (("TEXT_AD", 0.7), ("LANDING_PAGE", 0.3)),
    "social": (("IMAGE_AD", 0.45), ("VIDEO_AD", 0.40), ("LANDING_PAGE", 0.15)),
    "email": (("EMAIL", 0.85), ("LANDING_PAGE", 0.15)),
    "referral": (("TEXT_AD", 0.6), ("LANDING_PAGE", 0.4)),
    "display": (("IMAGE_AD", 0.55), ("VIDEO_AD", 0.30), ("LANDING_PAGE", 0.15)),
    "direct": (("LANDING_PAGE", 1.0),),
    "event": (("EVENT", 0.7), ("LANDING_PAGE", 0.3)),
}

REGIONS: tuple[tuple[str, float], ...] = (
    ("NORTH_AMERICA", 0.36),
    ("EUROPE", 0.30),
    ("APAC", 0.20),
    ("LATAM", 0.14),
)

COUNTRIES: dict[str, tuple[str, ...]] = {
    "NORTH_AMERICA": ("US", "CA"),
    "EUROPE": ("DE", "FR", "NL", "ES", "SE"),
    "APAC": ("IN", "SG", "AU", "JP"),
    "LATAM": ("BR", "MX", "CO", "CL"),
}

SEGMENTS: tuple[tuple[str, float], ...] = (
    ("SMB", 0.55),
    ("MID_MARKET", 0.33),
    ("ENTERPRISE", 0.12),
)

ACQUISITION_CHANNEL_WEIGHTS: tuple[tuple[str, float], ...] = CHANNEL_MIX


def weighted_choice(rng: random.Random, options: tuple[tuple[Any, float], ...]) -> Any:
    values = [item for item, _ in options]
    weights = [weight for _, weight in options]
    return rng.choices(values, weights=weights, k=1)[0]


def business_time(rng: random.Random, day: date) -> datetime:
    hour = rng.choices(range(6, 23), weights=[1, 1, 2, 4, 6, 7, 7, 6, 6, 5, 4, 4, 3, 3, 2, 1, 1], k=1)[0]
    minute = rng.randrange(0, 60)
    second = rng.randrange(0, 60)
    return datetime.combine(day, time(hour, minute, second))


def generate_audiences() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (name, category, definition) in enumerate(AUDIENCES, start=1):
        rows.append(
            {
                "audience_id": f"AUD-{index:06d}",
                "name": name,
                "category": category,
                "definition": definition,
                "effective_from": "2025-01-01",
                "effective_to": "2026-12-31",
                "status": "ACTIVE",
            }
        )
    return rows


def generate_campaigns(
    rng: random.Random, spec: ProfileSpec, channels: list[dict[str, Any]], audiences: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    campaigns: list[dict[str, Any]] = []
    campaign_channels: list[dict[str, Any]] = []
    campaign_audiences: list[dict[str, Any]] = []
    creatives: list[dict[str, Any]] = []

    channel_by_id = {channel["channel_id"]: channel for channel in channels}
    secondary_pool = ["CHN-000003", "CHN-000005", "CHN-000007"]

    start_min = date(2025, 8, 15)
    start_max = date(2026, 8, 31)
    span_days = (start_max - start_min).days
    as_of = date(2026, 10, 1)

    for index in range(spec.campaigns):
        campaign_id = f"CMP-2026-{index + 1:06d}"
        offset_days = 0 if spec.campaigns == 1 else round(index * span_days / (spec.campaigns - 1))
        start_day = start_min + timedelta(days=offset_days)
        jitter = rng.randint(-2, 2)
        start_day = max(start_min, min(start_max, start_day + timedelta(days=jitter)))
        duration = rng.choices(
            [rng.randint(30, 60), rng.randint(61, 120), rng.randint(121, 240)],
            weights=[0.15, 0.45, 0.40],
            k=1,
        )[0]
        end_day = min(DATASET_END, start_day + timedelta(days=duration))
        start_at = datetime.combine(start_day, time(8, 0))
        end_at = datetime.combine(end_day, time(21, 0))
        created_at = start_at - timedelta(days=rng.randint(7, 35), hours=rng.randint(0, 6))
        status = (
            ("PAUSED" if rng.random() < 0.04 else "COMPLETED")
            if end_at.date() < as_of
            else "ACTIVE"  # pragma: no cover - all generated campaigns end before the as-of date
        )
        updated_at = end_at if status != "ACTIVE" else start_at + timedelta(days=1)

        primary_channel_id = weighted_choice(rng, CHANNEL_MIX)
        is_paid = bool(channel_by_id[primary_channel_id]["is_paid"])
        if is_paid:
            budget = money(rng.lognormvariate(9.4, 0.7))
            budget = max(Decimal("2500.00"), min(Decimal("180000.00"), budget))
        else:
            budget = Decimal("0.00")
        audience_id = audiences[rng.randrange(len(audiences))]["audience_id"]
        campaign_type = weighted_choice(rng, CAMPAIGN_TYPES)
        objective = weighted_choice(rng, OBJECTIVES)
        season = {
            9: "Autumn",
            10: "Autumn",
            11: "Holiday",
            12: "Holiday",
            1: "New Year",
            2: "Winter",
            3: "Spring",
            4: "Spring",
            5: "Summer",
            6: "Summer",
            7: "Mid-Year",
            8: "Late Summer",
        }[start_day.month]
        channel_name = channel_by_id[primary_channel_id]["name"]
        name = f"{season} {campaign_type.title().replace('_', ' ')} - {channel_name} {index + 1:03d}"

        campaigns.append(
            {
                "campaign_id": campaign_id,
                "name": name,
                "campaign_type": campaign_type,
                "objective": objective,
                "start_at": iso(start_at),
                "end_at": iso(end_at),
                "status": status,
                "budget_amount": str(budget),
                "budget_currency": REPORTING_CURRENCY,
                "primary_channel_id": primary_channel_id,
                "target_audience_id": audience_id,
                "created_at": iso(created_at),
                "updated_at": iso(updated_at),
            }
        )

        campaign_channels.append(
            {"campaign_id": campaign_id, "channel_id": primary_channel_id, "is_primary": True}
        )
        secondary_count = rng.choices([0, 1], weights=[0.62, 0.38], k=1)[0]
        candidates = [channel for channel in secondary_pool if channel != primary_channel_id]
        rng.shuffle(candidates)
        for secondary in candidates[:secondary_count]:
            campaign_channels.append(
                {"campaign_id": campaign_id, "channel_id": secondary, "is_primary": False}
            )

        campaign_audiences.append({"campaign_id": campaign_id, "audience_id": audience_id})
        if rng.random() < 0.35:
            other = audiences[rng.randrange(len(audiences))]["audience_id"]
            if other != audience_id:
                campaign_audiences.append({"campaign_id": campaign_id, "audience_id": other})

        creative_count = rng.choices([1, 2, 3], weights=[0.25, 0.5, 0.25], k=1)[0]
        channel_type = channel_by_id[primary_channel_id]["channel_type"]
        for creative_number in range(creative_count):
            creative_type = weighted_choice(rng, CREATIVE_TYPES[channel_type])
            creative_start = start_at + timedelta(days=rng.randint(0, 5))
            creative_end = end_at
            creatives.append(
                {
                    "creative_id": f"CRE-{len(creatives) + 1:06d}",
                    "campaign_id": campaign_id,
                    "channel_id": primary_channel_id,
                    "name": f"{name} / {creative_type.title().replace('_', ' ')} {creative_number + 1}",
                    "creative_type": creative_type,
                    "start_at": iso(creative_start),
                    "end_at": iso(creative_end),
                    "status": "ACTIVE",
                    "created_at": iso(creative_start - timedelta(days=rng.randint(1, 5))),
                }
            )

    return campaigns, campaign_channels, campaign_audiences, creatives


def generate_contacts(
    rng: random.Random, spec: ProfileSpec, channels: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    start = date(2025, 9, 1)
    end = date(2026, 7, 31)
    span = (end - start).days
    channel_ids = [channel["channel_id"] for channel in channels]
    channel_weights = [dict(CHANNEL_MIX)[channel_id] for channel_id in channel_ids]

    for index in range(spec.contacts):
        contact_id = f"CON-2026-{index + 1:06d}"
        # Triangular distribution concentrates contact creation in the middle of the period.
        offset = int(rng.triangular(0, span, span * 0.55))
        created_day = start + timedelta(days=offset)
        created_at = business_time(rng, created_day)
        region = weighted_choice(rng, REGIONS)
        country = rng.choice(COUNTRIES[region])
        segment = weighted_choice(rng, SEGMENTS)
        consent_roll = rng.random()
        if consent_roll < 0.86:
            consent = "GRANTED"
        elif consent_roll < 0.94:
            consent = "DENIED"
        else:
            consent = "UNKNOWN"
        acquisition_channel_id = rng.choices(channel_ids, weights=channel_weights, k=1)[0]
        contacts.append(
            {
                "contact_id": contact_id,
                "created_at": iso(created_at),
                "region": region,
                "country": country,
                "segment": segment,
                "consent_status": consent,
                "lifecycle_status": "NEW",
                "acquisition_channel_id": acquisition_channel_id,
            }
        )
    return contacts


def generation_metadata() -> dict[str, str]:
    return {
        "generator_version": GENERATOR_VERSION,
        "dataset_start": DATASET_START.isoformat(),
        "dataset_end": DATASET_END.isoformat(),
    }
