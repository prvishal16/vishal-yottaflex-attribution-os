from yottaflex.domain.identity import (
    IdentityLink,
    build_session_resolution,
    is_supported_evidence,
    resolve_session_contact,
    resolve_touch_contact,
)


def link(
    link_id: str,
    contact_id: str,
    evidence_type: str = "AUTHENTICATED_LOGIN",
    evidence_ref: str = "AUTH-123",
    status: str = "VERIFIED",
    session_id: str = "SES-2026-000001",
) -> IdentityLink:
    return IdentityLink(
        link_id=link_id,
        session_id=session_id,
        contact_id=contact_id,
        evidence_type=evidence_type,
        evidence_ref=evidence_ref,
        status=status,
        rule_id="IDR-TEST",
    )


def test_supported_evidence_requires_verified_status_type_and_reference() -> None:
    assert is_supported_evidence("AUTHENTICATED_LOGIN", "AUTH-1", "VERIFIED")
    assert not is_supported_evidence("AUTHENTICATED_LOGIN", "", "VERIFIED")
    assert not is_supported_evidence("TEMPORAL_PROXIMITY", "SESSION-1", "VERIFIED")
    assert not is_supported_evidence("AUTHENTICATED_LOGIN", "AUTH-1", "PENDING")


def test_supported_link_resolves_the_session() -> None:
    result = resolve_session_contact([link("LNK-1", "CON-1")])
    assert result.contact_id == "CON-1"
    assert result.status == "SESSION_LINKED"


def test_unsupported_link_never_resolves() -> None:
    result = resolve_session_contact(
        [link("LNK-1", "CON-1", evidence_type="TEMPORAL_PROXIMITY", evidence_ref="")]
    )
    assert result.contact_id is None
    assert result.status == "UNRESOLVED"


def test_conflicting_supported_links_are_ambiguous() -> None:
    result = resolve_session_contact(
        [link("LNK-1", "CON-1"), link("LNK-2", "CON-2", evidence_type="EMAIL_CLICK_SSO")]
    )
    assert result.contact_id is None
    assert result.status == "AMBIGUOUS"


def test_duplicate_supported_links_to_same_contact_resolve() -> None:
    result = resolve_session_contact([link("LNK-2", "CON-1"), link("LNK-1", "CON-1")])
    assert result.contact_id == "CON-1"
    assert result.status == "SESSION_LINKED"


def test_build_session_resolution_groups_by_session() -> None:
    resolutions = build_session_resolution(
        [
            link("LNK-1", "CON-1", session_id="SES-1"),
            link("LNK-2", "CON-2", session_id="SES-2"),
        ]
    )
    assert set(resolutions) == {"SES-1", "SES-2"}
    assert resolutions["SES-1"].contact_id == "CON-1"


def test_direct_contact_beats_session_resolution() -> None:
    resolutions = build_session_resolution([link("LNK-1", "CON-1")])
    result = resolve_touch_contact("CON-DIRECT", "SES-2026-000001", resolutions)
    assert result.contact_id == "CON-DIRECT"
    assert result.status == "DIRECT"


def test_touch_with_no_contact_or_session_is_unresolved() -> None:
    result = resolve_touch_contact(None, None, {})
    assert result.contact_id is None
    assert result.status == "UNRESOLVED"
