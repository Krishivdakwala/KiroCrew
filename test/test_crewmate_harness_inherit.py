"""What a crewmate with no pin of its own runs on, and where that comes from.

Resolution, for a crewmate's own chat and the workers it opens:

1. the crewmate's pin ``agents.<name>.acp_backend`` (refuses when it cannot start, H17);
2. an explicitly stored ``agent.member_acp_backend`` (legacy, keeps working);
3. ``agent.acp_backend`` (Settings -> Agent Harness), Kiro CLI reading as KAS;
4. KAS, with a logged reason (H3) and a bell note, when crewmates cannot run on 3.

The answer is the loaded ``agent.member_acp_backend`` (``_read_backend_choice``), so
every reader of the crewmate backend gets the same one; the governance gate and the
enterprise KAS floor still decide what is selectable.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from kiro_crew import acp_backends
from kiro_crew.agent_sdk import backends as registry
from kiro_crew.config import loader_builders
from kiro_crew.config.loader_builders import _build_agent_config

#: Every harness the tests choose between, Kiro CLI (``""``) included.
SELECTABLE = {"", "kas", "claude", "codex", "goose", "opencode", "strands", "pi", "deepseek"}


@pytest.fixture(autouse=True)
def _registry(_floor_monkeypatch):
    """A fixed selectable set, and a fresh once-per-process log for each test."""
    _floor_monkeypatch.setattr(registry, "_baseline", set(SELECTABLE))
    _floor_monkeypatch.setattr(registry, "_selectable", set(SELECTABLE))
    _floor_monkeypatch.setattr(loader_builders, "_member_fallback_logged", set())


def _member(agent: dict) -> str:
    return _build_agent_config(agent).member_acp_backend


class TestResolver:
    def test_crewmates_follow_a_settings_harness_they_can_run_on(self):
        from kiro_crew.agent_sdk.backends import crewmate_inherited_backend

        for harness in ("claude", "kas"):
            assert crewmate_inherited_backend(harness) == (harness, False)

    def test_kiro_cli_reads_as_kas_and_is_not_a_fallback(self):
        from kiro_crew.agent_sdk.backends import crewmate_inherited_backend

        assert crewmate_inherited_backend(acp_backends.ACP_BACKEND_KIRO) == ("kas", False)

    @pytest.mark.parametrize(
        "harness",
        [
            "goose",
            "opencode",
            "strands",
            "copilot",
            # A crewmate chat could run here, but its workers could not carry their
            # kit (``worker_kit_backend_refusal``), so inheriting it would refuse
            # every worker the crewmate opens.
            "codex",
            "pi",
            "deepseek",
        ],
    )
    def test_a_harness_crewmates_cannot_run_on_falls_back_to_kas(self, harness):
        from kiro_crew.agent_sdk.backends import crewmate_inherited_backend

        assert crewmate_inherited_backend(harness) == ("kas", True)


class TestLoadedField:
    def test_nothing_set_is_kas(self):
        assert _member({}) == "kas"

    @pytest.mark.parametrize("unset", [None, ""])
    def test_an_unset_member_field_follows_the_settings_harness(self, unset):
        agent = {"acp_backend": "claude"}
        if unset is not None:
            agent["member_acp_backend"] = unset
        assert _member(agent) == "claude"

    def test_a_kiro_cli_settings_harness_gives_crewmates_kas(self):
        assert _member({"acp_backend": "kiro"}) == "kas"

    def test_a_kiro_cli_settings_harness_on_the_bundle_route_gives_crewmates_kas(self):
        cfg = _build_agent_config({"acp_backend": "kiro", "kas_bundle": True})
        assert cfg.acp_backend == acp_backends.ACP_BACKEND_KIRO
        assert cfg.member_acp_backend == "kas"

    @pytest.mark.parametrize(
        "harness", ["claude", "kas", "kiro", "codex", "pi", "deepseek", "goose"]
    )
    def test_an_inherited_harness_never_refuses_a_crewmates_worker(self, harness):
        from kiro_crew.config.loader import KiroCrewConfig
        from kiro_crew.mate_worker import crewmate_worker_backend, worker_kit_backend_refusal

        cfg = KiroCrewConfig()
        cfg.agent = _build_agent_config({"acp_backend": harness})
        assert worker_kit_backend_refusal(crewmate_worker_backend(cfg)) is None

    def test_an_explicit_legacy_value_wins_over_the_settings_harness(self):
        assert _member({"acp_backend": "claude", "member_acp_backend": "codex"}) == "codex"
        assert _member({"acp_backend": "claude", "member_acp_backend": "kas"}) == "kas"

    def test_a_legacy_kiro_value_still_reads_as_kas(self):
        assert _member({"acp_backend": "claude", "member_acp_backend": "kiro"}) == "kas"

    def test_a_legacy_value_crewmates_could_not_inherit_still_works(self):
        # goose is outside the inheritable set, but an explicit pick keeps working.
        assert _member({"acp_backend": "claude", "member_acp_backend": "goose"}) == "goose"

    def test_an_unrunnable_settings_harness_falls_back_with_a_logged_reason(self, caplog):
        with caplog.at_level(logging.WARNING, logger=loader_builders.logger.name):
            assert _member({"acp_backend": "goose"}) == "kas"
            assert _member({"acp_backend": "goose"}) == "kas"
        lines = [
            r.getMessage() for r in caplog.records if "crewmates cannot run on" in r.getMessage()
        ]
        assert len(lines) == 1
        assert "'goose'" in lines[0] and "'kas'" in lines[0]

    def test_a_policy_denied_settings_harness_lands_crewmates_on_kas(self, _floor_monkeypatch):
        # Governance narrows the registry: claude is gone, so the Settings harness
        # takes the floor (Kiro CLI) and crewmates read that as KAS.
        _floor_monkeypatch.setattr(registry, "_selectable", {"", "kas"})
        cfg = _build_agent_config({"acp_backend": "claude"})
        assert cfg.acp_backend == acp_backends.ACP_BACKEND_KIRO
        assert cfg.member_acp_backend == "kas"

    def test_a_policy_denied_legacy_value_still_degrades_at_the_gate(self, _floor_monkeypatch):
        _floor_monkeypatch.setattr(registry, "_selectable", {"", "kas"})
        assert _member({"acp_backend": "kas", "member_acp_backend": "claude"}) != "claude"

    def test_a_denied_kas_takes_the_floor_without_a_fallback_line(self, _floor_monkeypatch, caplog):
        _floor_monkeypatch.setattr(registry, "_selectable", {"", "goose"})
        with caplog.at_level(logging.WARNING, logger=loader_builders.logger.name):
            member = _member({"acp_backend": "claude"})
        assert member == acp_backends.ACP_BACKEND_KIRO


def _cfg(main: str, member: str, *, pin: str = "") -> SimpleNamespace:
    from kiro_crew.config.loader import KiroCrewAgentConfig

    return SimpleNamespace(
        agent=SimpleNamespace(acp_backend=main, member_acp_backend=member, kas_bundle=False),
        agents={
            "atlas": KiroCrewAgentConfig(
                member_id="atlas-0123456789ab", kiro_agent="atlas", acp_backend=pin
            )
        },
    )


@pytest.fixture
def declared(_floor_monkeypatch):
    """Whether config.json holds ``agent.member_acp_backend``; False by default."""
    state = {"value": False}
    _floor_monkeypatch.setattr(
        "kiro_crew.config.loader_document.member_acp_backend_declared", lambda: state["value"]
    )
    return state


class TestSource:
    def test_settings(self, declared):
        from kiro_crew.crewmate_harness import SOURCE_SETTINGS, inherited_harness_source

        got = inherited_harness_source(_cfg("claude", "claude"))
        assert (got.harness, got.source, got.settings_harness) == (
            "claude",
            SOURCE_SETTINGS,
            "claude",
        )

    def test_kiro_cli_is_settings_not_fallback(self, declared):
        from kiro_crew.crewmate_harness import SOURCE_SETTINGS, inherited_harness_source

        got = inherited_harness_source(_cfg(acp_backends.ACP_BACKEND_KIRO, "kas"))
        assert (got.harness, got.source, got.settings_harness) == ("kas", SOURCE_SETTINGS, "kiro")

    def test_legacy(self, declared):
        from kiro_crew.crewmate_harness import SOURCE_LEGACY, inherited_harness_source

        declared["value"] = True
        got = inherited_harness_source(_cfg("goose", "codex"))
        assert (got.harness, got.source) == ("codex", SOURCE_LEGACY)

    def test_fallback(self, declared):
        from kiro_crew.crewmate_harness import SOURCE_FALLBACK, inherited_harness_source

        got = inherited_harness_source(_cfg("goose", "kas"))
        assert (got.harness, got.source, got.settings_harness) == ("kas", SOURCE_FALLBACK, "goose")

    def test_a_pin_wins(self, declared):
        from kiro_crew.crewmate_harness import SOURCE_PIN, crewmate_harness_source

        got = crewmate_harness_source(_cfg("goose", "kas", pin="claude"), "atlas")
        assert (got.harness, got.source) == ("claude", SOURCE_PIN)

    def test_an_unstartable_pin_reads_empty_and_still_refuses_at_start(
        self, declared, _floor_monkeypatch
    ):
        from kiro_crew.crewmate_harness import (
            SOURCE_PIN,
            CrewmateHarnessUnavailable,
            crewmate_backend_pin,
            crewmate_harness_source,
        )

        cfg = _cfg("claude", "claude", pin="no-such-harness")
        got = crewmate_harness_source(cfg, "atlas")
        assert (got.harness, got.source) == ("", SOURCE_PIN)
        with pytest.raises(CrewmateHarnessUnavailable):
            crewmate_backend_pin(cfg, "dashboard:member-atlas-0123456789ab")

    def test_the_worker_backend_agrees_with_the_readout(self, declared):
        from kiro_crew.crewmate_harness import inherited_harness_source
        from kiro_crew.mate_worker import crewmate_worker_backend

        cfg = _cfg("claude", "claude")
        assert acp_backends.backend_to_stored(crewmate_worker_backend(cfg)) == (
            inherited_harness_source(cfg).harness
        )


class _State:
    def __init__(self) -> None:
        self.notes: list[tuple] = []

    def notify(self, kind, title, body, *, url=None, channel=None):
        self.notes.append((kind, title, body, url, channel))


class TestAlarm:
    @pytest.fixture(autouse=True)
    def _fresh(self, _floor_monkeypatch):
        from kiro_crew import crewmate_harness_notice

        _floor_monkeypatch.setattr(crewmate_harness_notice, "_announced", set())

    def test_a_fallback_rings_the_bell_once_naming_both_harnesses(self, declared):
        from kiro_crew import crewmate_harness_notice

        state = _State()
        assert asyncio.run(crewmate_harness_notice.deliver(state, _cfg("goose", "kas")))
        assert not asyncio.run(crewmate_harness_notice.deliver(state, _cfg("goose", "kas")))
        assert len(state.notes) == 1
        _kind, title, body, url, channel = state.notes[0]
        assert "Goose" in title or "goose" in title.lower()
        assert "Kiro" in title or "KAS" in title
        assert url == crewmate_harness_notice.NOTE_URL
        assert channel == crewmate_harness_notice.NOTE_CHANNEL
        assert "cannot run on" in body

    def test_no_bell_when_crewmates_follow_the_settings_harness(self, declared):
        from kiro_crew import crewmate_harness_notice

        state = _State()
        assert not asyncio.run(crewmate_harness_notice.deliver(state, _cfg("claude", "claude")))
        assert not asyncio.run(
            crewmate_harness_notice.deliver(state, _cfg(acp_backends.ACP_BACKEND_KIRO, "kas"))
        )
        assert state.notes == []

    def test_no_bell_when_the_legacy_setting_decides(self, declared):
        from kiro_crew import crewmate_harness_notice

        declared["value"] = True
        state = _State()
        assert not asyncio.run(crewmate_harness_notice.deliver(state, _cfg("goose", "kas")))

    def test_moving_away_and_back_rings_again(self, declared):
        from kiro_crew import crewmate_harness_notice

        state = _State()
        asyncio.run(crewmate_harness_notice.deliver(state, _cfg("goose", "kas")))
        asyncio.run(crewmate_harness_notice.deliver(state, _cfg("claude", "claude")))
        asyncio.run(crewmate_harness_notice.deliver(state, _cfg("goose", "kas")))
        assert len(state.notes) == 2

    def test_a_broken_bell_never_raises(self, declared):
        from kiro_crew import crewmate_harness_notice

        class _Broken:
            def notify(self, *a, **k):
                raise RuntimeError("bell down")

        assert not asyncio.run(crewmate_harness_notice.deliver(_Broken(), _cfg("goose", "kas")))
        # Not delivered, so still owed: the next delivery rings the bell.
        state = _State()
        assert asyncio.run(crewmate_harness_notice.deliver(state, _cfg("goose", "kas")))
        assert len(state.notes) == 1


class TestPanelReadout:
    def test_the_agent_harness_panel_reports_the_crewmate_harness(
        self, declared, _floor_monkeypatch
    ):
        from kiro_crew.dashboard.handlers import acp_backend_status

        _floor_monkeypatch.setattr(
            "kiro_crew.config.loader.KiroCrewConfig.load",
            staticmethod(lambda *a, **k: _cfg("goose", "kas")),
        )
        assert acp_backend_status._crewmate_harness() == {
            "harness": "kas",
            "source": "fallback",
            "settings_harness": "goose",
        }

    def test_a_failed_read_leaves_the_readout_out(self, _floor_monkeypatch):
        from kiro_crew.dashboard.handlers import acp_backend_status

        def _boom(*a, **k):
            raise OSError("unreadable")

        _floor_monkeypatch.setattr(
            "kiro_crew.config.loader.KiroCrewConfig.load", staticmethod(_boom)
        )
        assert acp_backend_status._crewmate_harness() is None
