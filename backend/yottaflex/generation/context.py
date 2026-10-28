"""Mutable generation context shared by the generator modules."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from yottaflex.config import RunConfig
from yottaflex.util import IdSequence


@dataclass
class GenerationContext:
    config: RunConfig
    rng: random.Random
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sequences: dict[str, IdSequence] = field(default_factory=dict)
    campaign_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    channel_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    contact_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    campaigns_by_day: dict[date, list[dict[str, Any]]] = field(default_factory=dict)
    campaigns_by_day_channel: dict[tuple[date, str], list[dict[str, Any]]] = field(default_factory=dict)
    creatives_by_campaign_channel: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    contact_touch_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    anomaly_labels: list[dict[str, Any]] = field(default_factory=list)
    fixture_counts: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        defaults = {
            "touch": ("TOUCH", 2026, 6),
            "session": ("SES", 2026, 6),
            "link": ("LNK", 2026, 6),
            "lead": ("LEAD", 2026, 6),
            "opportunity": ("OPP", 2026, 6),
            "order": ("ORD", 2026, 6),
            "cost": ("COST", 2026, 6),
            "event": ("EVT", 2026, 6),
            "attribution": ("ATTR", 2026, 6),
            "conversion_result": ("CONV", 2026, 6),
            "issue": ("ISS", 2026, 6),
            "anon": ("ANON", None, 8),
        }
        for key, (prefix, year, width) in defaults.items():
            self.sequences.setdefault(key, IdSequence(prefix, year=year, width=width))

    def new_id(self, kind: str) -> str:
        return self.sequences[kind].next()

    @property
    def spec(self):  # noqa: ANN201 - lazy import cycle avoidance is unnecessary here
        return self.config.spec
