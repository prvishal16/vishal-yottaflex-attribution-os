"""Lifecycle state machines.

The generator and validator share these transitions so that recorded history can
be reconciled with current entity status.
"""

from __future__ import annotations

ALLOWED_TRANSITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "CAMPAIGN": {
        "PLANNED": ("ACTIVE",),
        "ACTIVE": ("PAUSED", "COMPLETED"),
        "PAUSED": ("ACTIVE", "COMPLETED"),
        "COMPLETED": (),
    },
    "CONTACT": {
        "NEW": ("ENGAGED", "DORMANT"),
        "ENGAGED": ("QUALIFIED", "DORMANT"),
        "QUALIFIED": ("CUSTOMER", "DORMANT"),
        "CUSTOMER": ("DORMANT",),
        "DORMANT": (),
    },
    "LEAD": {
        "NEW": ("WORKING",),
        "WORKING": ("QUALIFIED", "DISQUALIFIED"),
        "QUALIFIED": ("CONVERTED", "DISQUALIFIED", "WORKING"),
        "CONVERTED": (),
        "DISQUALIFIED": (),
    },
    "OPPORTUNITY": {
        "OPEN": ("QUALIFIED", "CLOSED_LOST"),
        "QUALIFIED": ("PROPOSAL", "CLOSED_LOST"),
        "PROPOSAL": ("NEGOTIATION", "CLOSED_WON", "CLOSED_LOST"),
        "NEGOTIATION": ("CLOSED_WON", "CLOSED_LOST"),
        "CLOSED_WON": (),
        "CLOSED_LOST": (),
    },
    "ORDER": {
        "CREATED": ("PAID", "CANCELLED"),
        "PAID": ("PARTIALLY_REFUNDED", "REFUNDED"),
        "PARTIALLY_REFUNDED": ("REFUNDED",),
        "REFUNDED": (),
        "CANCELLED": (),
    },
}

ENTITY_TYPES: tuple[str, ...] = tuple(ALLOWED_TRANSITIONS)


def is_valid_initial_state(entity_type: str, state: str) -> bool:
    return state in ALLOWED_TRANSITIONS[entity_type]


def is_valid_transition(entity_type: str, previous_state: str, new_state: str) -> bool:
    if previous_state == "":
        return is_valid_initial_state(entity_type, new_state)
    return new_state in ALLOWED_TRANSITIONS[entity_type].get(previous_state, ())


def terminal_states(entity_type: str) -> tuple[str, ...]:
    return tuple(state for state, nexts in ALLOWED_TRANSITIONS[entity_type].items() if not nexts)
