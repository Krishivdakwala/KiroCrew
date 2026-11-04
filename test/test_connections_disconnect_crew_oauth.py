"""Disconnect when Kiro Crew holds the sign-in (``connections.crew_oauth``).

Reuses the handler harness of ``test_connections_disconnect.py``: every side
effect but the decision under test is neutralized there.
"""

from __future__ import annotations

import pytest
from test_connections_disconnect import _SLUG, _client, _entry, _provider_url, _wire


@pytest.mark.asyncio
async def test_a_failed_crew_held_cleanup_is_a_coded_failure_not_a_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Crew-held sign-in that could not be removed must not read as disconnected."""
    from kiro_crew.connections import crew_oauth

    purged: list[str] = []
    audits: list[dict] = []
    _wire(
        monkeypatch,
        removed=[],
        surviving=[],
        inventory=[_entry(_SLUG, _provider_url())],
        purged=purged,
        audits=audits,
    )

    async def _vault_broken(_slug: str) -> dict:
        raise OSError("vault unreadable")

    monkeypatch.setattr(crew_oauth, "manages", lambda _slug: True)
    monkeypatch.setattr(crew_oauth, "disconnect", _vault_broken)
    client = await _client()
    try:
        resp = await client.post("/api/connections/disconnect", json={"slug": _SLUG})
        body = await resp.json()
    finally:
        await client.close()

    assert resp.status == 502
    assert body["code"] == "crew_cleanup_failed" and body["entryRemoved"] is True
    assert purged == [_SLUG], "the rest of Disconnect still ran"
    assert [a["outcome"] for a in audits if a.get("operation") == "connections_disconnect"] == [
        "partial"
    ]


@pytest.mark.asyncio
async def test_a_crew_held_grant_another_entry_still_uses_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The census that keeps the native grant keeps Crew's: no revoke, no dropped bridge."""
    from kiro_crew.connections import crew_oauth, crew_oauth_proxy

    _wire(
        monkeypatch,
        removed=[],
        surviving=[],
        inventory=[_entry(_SLUG, _provider_url()), _entry("notion-work", _provider_url())],
        purged=[],
        revoked=[],
    )
    called: list[str] = []

    async def _disconnect(slug: str) -> dict:
        called.append("disconnect")
        return {"removed": True, "revoked": True}

    monkeypatch.setattr(crew_oauth, "manages", lambda _slug: True)
    monkeypatch.setattr(crew_oauth, "disconnect", _disconnect)
    monkeypatch.setattr(crew_oauth_proxy, "drop_slug", lambda slug: called.append("drop"))
    client = await _client()
    try:
        resp = await client.post("/api/connections/disconnect", json={"slug": _SLUG})
        body = await resp.json()
    finally:
        await client.close()

    assert resp.status == 200
    assert body["grantSharedWith"] == ["notion-work"]
    assert body["crewGrantKept"] is True and body["upstreamRevoked"] is False
    assert called == [], "a grant another entry still uses was revoked or cut"
