"""Identity resolution rules.

A session may resolve to a contact only through a verified link whose evidence
type is explicitly allowed. Temporal proximity is never sufficient.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from yottaflex.config import ALLOWED_IDENTITY_EVIDENCE


@dataclass(frozen=True)
class IdentityLink:
    link_id: str
    session_id: str
    contact_id: str
    evidence_type: str
    evidence_ref: str
    status: str
    rule_id: str


@dataclass(frozen=True)
class ResolutionOutcome:
    contact_id: str | None
    status: str
    rule_id: str
    evidence: str
    reason: str


def is_supported_evidence(evidence_type: str, evidence_ref: str, status: str) -> bool:
    return (
        status.upper() == "VERIFIED"
        and evidence_type in ALLOWED_IDENTITY_EVIDENCE
        and bool(evidence_ref.strip())
    )


def resolve_session_contact(links: Iterable[IdentityLink]) -> ResolutionOutcome:
    """Resolve one session from all of its link records.

    Multiple distinct supported contacts make the session ambiguous and therefore
    unresolved; the platform must not guess.
    """

    supported = [link for link in links if is_supported_evidence(link.evidence_type, link.evidence_ref, link.status)]
    if not supported:
        return ResolutionOutcome(
            contact_id=None,
            status="UNRESOLVED",
            rule_id="IDR-NO-EVIDENCE",
            evidence="",
            reason="No verified identity link with supported evidence.",
        )
    contacts = {link.contact_id for link in supported}
    if len(contacts) > 1:
        return ResolutionOutcome(
            contact_id=None,
            status="AMBIGUOUS",
            rule_id="IDR-AMBIGUOUS",
            evidence="|".join(sorted(link.link_id for link in supported)),
            reason="Conflicting supported identity links.",
        )
    link = sorted(supported, key=lambda item: (item.link_id,))[0]
    return ResolutionOutcome(
        contact_id=link.contact_id,
        status="SESSION_LINKED",
        rule_id=link.rule_id,
        evidence=link.evidence_ref,
        reason=f"Resolved through {link.evidence_type}.",
    )


def build_session_resolution(links: Iterable[IdentityLink]) -> dict[str, ResolutionOutcome]:
    grouped: dict[str, list[IdentityLink]] = {}
    for link in links:
        grouped.setdefault(link.session_id, []).append(link)
    return {session_id: resolve_session_contact(rows) for session_id, rows in grouped.items()}


def resolve_touch_contact(
    direct_contact_id: str | None,
    session_id: str | None,
    session_resolution: Mapping[str, ResolutionOutcome],
) -> ResolutionOutcome:
    if direct_contact_id:
        return ResolutionOutcome(
            contact_id=direct_contact_id,
            status="DIRECT",
            rule_id="IDR-DIRECT-CONTACT",
            evidence=direct_contact_id,
            reason="Touchpoint carries a direct contact identifier.",
        )
    if session_id and session_id in session_resolution:
        outcome = session_resolution[session_id]
        if outcome.contact_id:
            return outcome
        return outcome
    return ResolutionOutcome(
        contact_id=None,
        status="UNRESOLVED",
        rule_id="IDR-NO-SESSION",
        evidence="",
        reason="No contact identifier and no resolvable session link.",
    )
