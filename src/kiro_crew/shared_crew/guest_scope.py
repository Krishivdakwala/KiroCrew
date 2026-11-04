"""What a Shared Crew guest may not do: the owner-only surface, pinned in one place.

A guest is a collaborator a membership boundary admitted (``collaborators``).
Inside the Crew a guest has the owner's abilities: ``is_owner_dashboard_request``
answers true for a guest, so every owner-gated in-Crew route (chat, mates,
approvals, artifacts, skills, ...) admits one. The routes below are the
exception. They manage the share itself or the host's ceiling, so a guest is
refused on them exactly as before. Matching is by request path, which keeps the
list reviewable as data and lets one test pin it.

Anything that is not listed is open to a guest. Add a route here when it
manages who may reach the Crew, the network path, ``config.json``, security
policy, a credential, the gateway process, or code and tools the host runs
outside an agent's approvals.
"""

from __future__ import annotations

import os
import posixpath
import re
import stat
from pathlib import Path
from typing import Any

__all__ = [
    "OWNER_ONLY_METHOD_PATHS",
    "OWNER_ONLY_PATH_PATTERNS",
    "OWNER_ONLY_PATH_PREFIXES",
    "OWNER_ONLY_WRITE_PATTERNS",
    "OWNER_ONLY_RAW_PREFIXES",
    "guest_acts_as_owner",
    "attachment_path",
    "guest_attachment_path",
    "guest_created_by",
    "guest_write_denial",
    "guest_job_tag",
    "guest_posture_refusal",
    "is_guest_session",
    "is_owner_only_path",
]

#: Matched on a path-segment boundary: ``/api/mcp`` covers ``/api/mcp/custom`` and
#: not ``/api/mcp-apps/call``.
OWNER_ONLY_PATH_PREFIXES: tuple[str, ...] = (
    # Who may reach the Crew, and over which network path.
    "/api/shared-crew/access",
    "/api/shared-crew/preview",
    "/api/shared-crew/tailscale",
    "/api/shared-crew/ssm",
    "/api/tailnet",
    "/api/tunnel",
    "/api/mobile-connect",
    "/api/instances",
    # config.json and security policy.
    "/api/config",
    "/api/dashboard/config",
    "/api/agent/config",
    "/api/security",
    "/api/governance",
    "/api/redaction",
    "/api/admin",
    "/api/sel",
    "/api/decisions/consent",
    "/api/decisions/provider",
    "/api/decisions/local-models",
    "/api/aws",
    "/api/computer-use",
    "/api/telemetry/collection",
    "/api/debug",
    "/api/logs",
    "/api/diagnostics",
    "/api/system",
    # Credentials, connection secrets and the channels that hold them.
    "/api/secrets",
    "/api/connections",
    "/api/kas-login",
    "/api/kas-bundle",
    "/api/sso-login",
    "/api/sso-ttl",
    "/api/token",
    "/api/auth",
    "/api/webhooks",
    "/api/channels",
    "/api/channel",
    "/api/channel-folders",
    "/api/session-environments",
    "/api/wakatime",
    "/api/onboarding",
    "/api/stt/ffmpeg",
    "/api/slack",
    "/api/telegram",
    "/api/discord",
    "/api/feishu",
    "/api/imessage",
    "/api/teams",
    "/api/messaging",
    "/api/webex",
    "/api/wecom",
    "/api/weixin",
    "/api/whatsapp",
    "/api/voice/config",
    "/api/notifications/push",
    "/api/cloud",
    "/api/usage",
    "/api/sessions/usage",
    "/api/deploy",
    "/api/publish-providers",
    "/api/remote-artifacts",
    "/api/send-message",
    "/api/delete-message",
    "/api/slack-profile",
    "/api/mediated-secret-request",
    "/api/mediated-secret-capability",
    "/api/app-store",
    "/api/mcp-gateway",
    "/api/skills/-/trust",
    "/api/mcp/oauth",
    # The gateway process and code the host runs outside an agent's approvals.
    "/api/restart",
    "/api/shutdown",
    "/api/update",
    "/api/terminal",
    "/api/ws/terminal",
    "/api/mcp",
    "/api/capability",
    "/api/mcp-apps",
    "/api/hooks",
    "/api/kiro-hooks",
    "/api/apps",
    "/api/browser",
    "/apps",
    "/api/themes/install",
    "/api/themes/install-zip",
    "/api/portability",
    "/api/worktree",
    "/api/project-scaffold",
    # The host filesystem outside the Crew's own stores. ``/api/file-raw`` is
    # reached by a guest only for chat attachments (``guest_reads_attachment``).
    "/api/directory-upload",
    "/api/browse-dirs",
    "/api/browse-files",
    "/api/path-complete",
    "/api/reveal",
    "/api/project/git",
    "/api/project/tree",
    "/api/knowledge/pick-folder",
    "/api/knowledge/remote-search",
    "/api/knowledge/import",
    "/api/knowledge/ingest",
    "/api/knowledge/sources",
    "/api/memory/stores",
    "/api/memory/backup",
    "/api/memory/backups",
    "/api/memory/restore",
    "/api/memory/import",
    "/api/memory/migrate",
    "/api/memory/enable-embeddings",
    "/api/memory/disable-embeddings",
    "/api/memory/embedding-model",
)

#: Matched as a plain string prefix (the file routes share a ``file-`` stem).
OWNER_ONLY_RAW_PREFIXES: tuple[str, ...] = ("/api/file-",)

#: Matched against the whole path.
OWNER_ONLY_PATH_PATTERNS: tuple[str, ...] = (
    # A schedule's script source and secret grants.
    r"/api/crons/[^/]+/(?:script|secrets)",
    # Publishing or syncing an artifact spends the owner's account and posts it publicly.
    r"/api/artifacts/[^/]+/(?:publish|sharing|pull-latest|upstream-status|overwrite-remote)(?:/.*)?",
    # A session's remote environment: browsing and writing its files.
    r"/api/chat/slots/[^/]+/environment/(?:browse|file)(?:/.*)?",
)

#: Matched against the whole path for every method but a read. A guest reads these
#: (the agent picker, the workspace list, a session's environment) and does not
#: change them: an agent spec writes machine-wide tool approvals and MCP
#: declarations into ``config.json``, a workspace adopts a host directory, and an
#: environment repoints where the session runs.
OWNER_ONLY_WRITE_PATTERNS: tuple[str, ...] = (
    r"/api/agents(?:/.*)?",
    r"/api/workspaces(?:/.*)?",
    r"/api/projects(?:/.*)?",
    r"/api/themes(?:/.*)?",
    r"/api/chat/slots/[^/]+/environment",
)

#: ``(method, path)`` pairs refused whatever the rest of the path's methods allow:
#: deleting every stored session cannot be undone.
OWNER_ONLY_METHOD_PATHS: tuple[tuple[str, str], ...] = (
    ("DELETE", "/api/sessions"),
    # The native file picker and the interactive screenshot start host desktop processes.
    ("POST", "/api/upload"),
    ("POST", "/api/screenshot"),
)

_PATTERNS = tuple(re.compile(p) for p in OWNER_ONLY_PATH_PATTERNS)
_WRITE_PATTERNS = tuple(re.compile(p) for p in OWNER_ONLY_WRITE_PATTERNS)
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def is_owner_only_path(path: str, method: str = "") -> bool:
    """Whether *path* (with *method*, when given) is a route a guest is refused on."""
    if any(seg in (".", "..") for seg in path.split("/")):
        # The router matches the path as sent, so a dot segment can stand in a
        # path variable where normalization would erase it.
        return True
    path = posixpath.normpath("/" + path.lstrip("/")) if path else "/"
    if (method.upper(), path) in OWNER_ONLY_METHOD_PATHS:
        return True
    if any(path.startswith(p) for p in OWNER_ONLY_RAW_PREFIXES):
        return True
    for prefix in OWNER_ONLY_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    if any(p.fullmatch(path) for p in _PATTERNS):
        return True
    return (
        bool(method)
        and method.upper() not in _READ_METHODS
        and any(p.fullmatch(path) for p in _WRITE_PATTERNS)
    )


#: Owner-only paths a guest's session still writes to: signing out and refreshing.
_GUEST_WRITE_EXEMPT_PATHS = frozenset({"/api/auth/logout", "/api/auth/refresh", "/api/logout"})


def guest_write_denial(request: Any) -> Any:
    """A 403 when a guest writes to an owner-only route, else ``None``.

    Run before the handler, so a listed route is closed even when its handler
    never asks the owner gate. Reads are left to their handlers: the dashboard
    polls several listed routes and meets their own refusals.
    """
    method = str(getattr(request, "method", "") or "").upper()
    if method in _READ_METHODS or not is_guest_session(request):
        return None
    path = str(getattr(request, "path", "") or "")
    if path.rstrip("/") in _GUEST_WRITE_EXEMPT_PATHS or not is_owner_only_path(path, method):
        return None
    from aiohttp import web

    return web.json_response(
        {"error": "owner authorization required", "code": "owner_only"}, status=403
    )


#: Postures and actions that auto-approve later tool calls without the owner.
_UNATTENDED_POSTURES = frozenset({"yolo", "trust", "trust_reads", "trust_command", "trust_base"})


def guest_posture_refusal(request: Any, posture: object) -> Any:
    """A 403 when a guest asks for an approval posture that outlasts their click.

    A guest approves or rejects each tool call. Turning on trust, trust-reads or
    YOLO would auto-approve later calls (YOLO for every session) and keep doing so
    after the guest is revoked, so those stay the host owner's.
    """
    if not isinstance(posture, str) or posture not in _UNATTENDED_POSTURES:
        return None
    if not is_guest_session(request):
        return None
    from aiohttp import web

    return web.json_response(
        {"error": "this approval mode is owner-only", "code": "owner_only"}, status=403
    )


def guest_job_tag(principal_id: str) -> str:
    """The ``created_by`` a schedule a guest created carries, so a revoke can find it."""
    return f"guest:{principal_id}"


def guest_created_by(request: Any) -> str:
    """The ``created_by`` stamp for a schedule *request* creates: a guest's, else ``""``."""
    if not is_guest_session(request):
        return ""
    from kiro_crew.shared_crew.identity import viewer_principal

    return guest_job_tag(viewer_principal(request).id)


def is_guest_session(request: Any) -> bool:
    """Whether *request* is a guest's own dashboard session, on any route.

    A guest is a person a membership boundary admitted: an empty (present) app
    claim, the dashboard-user claim, no internal secret, and a verified
    collaborator actor. Never with the Shared Crew preview off.
    """
    if request.get("internal_auth") is True or request.get("app", None) != "":
        return False
    if request.get("is_dashboard_user") is not True or not request.get("user"):
        return False
    from kiro_crew.shared_crew.collaborators import is_collaborator_actor
    from kiro_crew.shared_crew.identity import actor_of

    return is_collaborator_actor(actor_of(request))


def guest_acts_as_owner(request: Any) -> bool:
    """Whether *request* is a guest on a route a guest may use as the owner would."""
    return is_guest_session(request) and not is_owner_only_path(
        str(getattr(request, "path", "") or ""), str(getattr(request, "method", "") or "")
    )


def attachment_path(raw: str) -> str:
    """The resolved path of *raw* when it is a file directly inside a chat attachment store, else ``""``.

    The stores are the upload directory and a session's ``<stem>.attachments``
    directory under the data home's ``sessions/``. The path is resolved first, so
    ``..`` and a symlink that leave a store resolve to their real parent and are
    refused; only a direct child of a store qualifies. A file with a second hard
    link is refused too: a link planted in a store would otherwise name a file
    outside it. The caller opens the returned path, not *raw*, so a link swapped in
    after this check meets the no-follow open. Blocking (``realpath``, ``lstat``).
    """
    if not raw or "\x00" in raw:
        return ""
    from kiro_crew.chat_attachments import ATTACHMENTS_DIR_SUFFIX
    from kiro_crew.config.paths import config_dir
    from kiro_crew.dashboard.handlers.files import _upload_dir

    try:
        resolved = Path(os.path.realpath(os.path.expanduser(raw)))
        parent = resolved.parent
        uploads = Path(os.path.realpath(_upload_dir()))
        sessions = Path(os.path.realpath(config_dir() / "sessions"))
        in_store = parent == uploads or (
            parent.name.endswith(ATTACHMENTS_DIR_SUFFIX) and parent.parent == sessions
        )
        if not in_store:
            return ""
        info = os.lstat(resolved)
    except (OSError, ValueError):
        return ""
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        return ""
    return str(resolved)


async def guest_attachment_path(request: Any, raw: str) -> str:
    """The path a guest may read through ``/api/file-raw``: a chat attachment only, else ``""``."""
    import asyncio

    if not is_guest_session(request):
        return ""
    return await asyncio.to_thread(attachment_path, raw)
