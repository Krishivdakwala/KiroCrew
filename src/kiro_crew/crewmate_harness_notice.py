"""The dashboard alarm that says crewmates cannot follow the Settings harness.

A crewmate with no pin of its own and no stored ``agent.member_acp_backend`` runs on
``agent.acp_backend`` (Settings -> Agent Harness). When that harness is one crewmates
cannot run on, the loader runs them on KAS instead and logs why
(``config.loader_builders._note_member_fallback``, harness-parity H3). The log is for
the operator; this note is for the person, in the bell, and it opens the Agent
Harness panel, which shows the same fact beside the picker.

Sent at gateway start and on every config change that touches either harness field,
once per Settings harness per process: the bell is not refilled on each reload, and
a person who moves to a harness crewmates can follow and back is told again.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

NOTE_KIND = "agent"
NOTE_CHANNEL = "system.agent"
NOTE_URL = "/settings/agent"

#: The Settings harnesses already announced in this process.
_announced: set[str] = set()
_lock = threading.Lock()


def fallback_note(config: Any) -> dict[str, str] | None:
    """The note when crewmates fall back and it was not yet sent, else ``None``. Blocking."""
    from kiro_crew.crewmate_harness import SOURCE_FALLBACK, harness_label, inherited_harness_source

    source = inherited_harness_source(config)
    with _lock:
        if source.source != SOURCE_FALLBACK:
            _announced.clear()
            return None
        if source.settings_harness in _announced:
            return None
        _announced.add(source.settings_harness)
    chosen = harness_label(source.settings_harness)
    used = harness_label(source.harness)
    return {
        "title": f"Mates run on {used}, not {chosen}",
        "body": (
            f"Your Agent Harness is {chosen}, which mates cannot run on. Mate "
            f"chats and the workers they open run on {used} instead. To choose "
            "another harness for a mate, set one in its settings."
        ),
        "url": NOTE_URL,
        "harness": source.settings_harness,
    }


def _forget(settings_harness: str) -> None:
    """Drop *settings_harness* from the announced set after a failed delivery."""
    with _lock:
        _announced.discard(settings_harness)


async def deliver(state: Any, config: Any | None = None) -> bool:
    """Send the note to *state*'s bell when it is owed. Returns whether it went out.

    *config* is the config now in force; ``None`` loads it. Never raises: a missing
    alarm leaves the log line and the Agent Harness panel, which say the same.
    """
    try:
        if config is None:
            from kiro_crew.config.loader import KiroCrewConfig

            config = await asyncio.to_thread(KiroCrewConfig.load)
        note = await asyncio.to_thread(fallback_note, config)
        if note is None:
            return False
    except Exception:  # noqa: BLE001 - the alarm must not take a config apply down
        logger.warning("could not work out the crewmate harness fallback notice", exc_info=True)
        return False
    try:
        state.notify(NOTE_KIND, note["title"], note["body"], url=note["url"], channel=NOTE_CHANNEL)
    except Exception:  # noqa: BLE001 - the alarm must not take a config apply down
        # Not delivered, so not announced: the next config change or start tries again.
        _forget(note["harness"])
        logger.warning("could not deliver the crewmate harness fallback notice", exc_info=True)
        return False
    return True


#: Strong reference to the boot delivery: the loop holds tasks weakly.
_TASK: "asyncio.Task[bool] | None" = None


def schedule(state: Any) -> "asyncio.Task[bool]":
    """Run :func:`deliver` once in the background, at gateway start. Call on the loop."""
    global _TASK
    _TASK = asyncio.create_task(deliver(state), name="crewmate-harness-fallback-notice")
    return _TASK
