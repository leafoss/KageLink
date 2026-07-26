from __future__ import annotations

import asyncio
import contextlib
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends
from pydantic import BaseModel, Field

import app as legacy
from pc_agent.chat_channels import ChatChannelParser, drop_replayed_prefix, find_new_text, unfinished_ic_suffix
from pc_agent.leafos_lifecycle import LifecycleLeafOSProcessor
from pc_agent.primary_character import get_primary_character, resolve_primary_character


class FinalizeSessionRequest(BaseModel):
    reason: str = Field(default="manual", min_length=1, max_length=80)
    restart_monitor: bool = True


def _build_lifecycle_processor() -> LifecycleLeafOSProcessor | None:
    config = legacy.config
    if (
        not config.leafos_enabled
        or not config.leafos_export_ic
        or config.leafos_vault_path is None
        or config.leafos_raw_output_path is None
    ):
        return None
    return LifecycleLeafOSProcessor(
        config.leafos_vault_path,
        config.leafos_raw_output_path,
        session_idle_seconds=config.leafos_session_idle_seconds,
        logger=legacy.logging.getLogger("kagelink"),
        primary_character_provider=lambda: get_primary_character(legacy.history),
        primary_character_resolver=lambda session: resolve_primary_character(
            legacy.history,
            session.get("started_at"),
        ),
        require_primary_character=True,
    )


# Replace only the Processor implementation. Chat, GAME, STATS and tunnel remain
# the original KageLink runtime and keep their existing isolation contracts.
legacy.leafos_processor = _build_lifecycle_processor()


async def _flush_chat_once() -> int:
    """Perform one deterministic final chat read before a session is closed."""

    stored_snapshot, stored_pending = await asyncio.to_thread(legacy.history.monitor_state)
    if stored_snapshot is None:
        stored = await asyncio.to_thread(legacy.history.recent_incoming_texts, 800)
        previous_text = "\n".join(stored)
        stored_pending = unfinished_ic_suffix(previous_text)
    else:
        previous_text = stored_snapshot

    parser = ChatChannelParser(stored_pending)
    current = await asyncio.to_thread(legacy.reader.read_current)
    if current is None:
        if legacy.leafos_exporter is not None:
            await asyncio.to_thread(legacy.leafos_exporter.sync, legacy.history)
        return 0

    addition, resynchronized = find_new_text(previous_text, current)
    if resynchronized:
        parser.reset()

    parsed_messages = parser.feed(addition)
    if resynchronized and parsed_messages:
        recent_records = await asyncio.to_thread(
            legacy.history.recent_incoming_records,
            500,
        )
        parsed_messages = drop_replayed_prefix(parsed_messages, recent_records)

    for parsed in parsed_messages:
        record = await asyncio.to_thread(
            legacy.history.add,
            "incoming",
            parsed.text,
            resynchronized,
            parsed.channel,
        )
        legacy.runtime_status.last_chat_update = time.time()
        await legacy.manager.broadcast({"type": "message", "message": record})

    await asyncio.to_thread(
        legacy.history.save_monitor_state,
        current,
        parser.pending_text,
    )

    if legacy.leafos_exporter is not None:
        await asyncio.to_thread(legacy.leafos_exporter.sync, legacy.history)

    return len(parsed_messages)


async def finalize_leafos_session(
    reason: str,
    *,
    restart_monitor: bool,
    closed_cleanly: bool = True,
) -> dict[str, Any]:
    processor = legacy.leafos_processor
    if processor is None:
        return {
            "enabled": False,
            "closed": False,
            "session_id": None,
            "reason": reason,
            "flushed_messages": 0,
        }

    current_task = legacy.monitor_task
    if current_task is not None and not current_task.done():
        current_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await current_task
        legacy.monitor_task = None

    flushed = 0
    try:
        flushed = await _flush_chat_once()
        result = await asyncio.to_thread(
            processor.finalize_open_session,
            reason,
            closed_cleanly=closed_cleanly,
            now=datetime.now(timezone.utc),
            consume_pending=True,
        )
        result["enabled"] = True
        result["flushed_messages"] = flushed
        return result
    finally:
        if restart_monitor and legacy.monitor_task is None:
            legacy.monitor_task = asyncio.create_task(
                legacy.monitor_chat_loop(),
                name="shinobi-chat-monitor",
            )


def _count_json_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def leafos_status_payload() -> dict[str, Any]:
    config = legacy.config
    processor = legacy.leafos_processor
    if processor is None or config.leafos_vault_path is None:
        return {
            "enabled": False,
            "primary_character": get_primary_character(legacy.history),
            "session": {"open": False},
            "closed_sessions": 0,
            "interpretations": 0,
            "pending_review_sessions": 0,
        }

    vault = Path(config.leafos_vault_path)
    interpretations = vault / "70 - LeafOS Inbox" / "Interpretations"
    sessions = vault / "80 - Processor" / "Sessions"
    pending_review = 0
    if interpretations.exists():
        from pc_agent.leafos_memory import LeafOSMemoryReviewer

        try:
            pending_review = len(LeafOSMemoryReviewer(vault).list_sessions())
        except Exception:
            pending_review = -1

    return {
        "enabled": True,
        "primary_character": get_primary_character(legacy.history),
        "session": processor.lifecycle_status(),
        "closed_sessions": _count_json_files(sessions),
        "interpretations": _count_json_files(interpretations),
        "pending_review_sessions": pending_review,
    }


@legacy.app.get(
    "/api/leafos/status",
    dependencies=[Depends(legacy.security.require_authorization)],
)
async def get_leafos_status() -> dict[str, Any]:
    return leafos_status_payload()


@legacy.app.post(
    "/api/leafos/finalize-session",
    dependencies=[Depends(legacy.security.require_authorization)],
)
async def post_finalize_leafos_session(request: FinalizeSessionRequest) -> dict[str, Any]:
    return await finalize_leafos_session(
        request.reason,
        restart_monitor=request.restart_monitor,
        closed_cleanly=True,
    )


async def _game_close_watcher() -> None:
    was_online = False
    missing_since: float | None = None
    while True:
        try:
            online = bool(legacy.runtime_status.game_online)
            if online:
                was_online = True
                missing_since = None
            elif was_online:
                if missing_since is None:
                    missing_since = time.monotonic()
                elif time.monotonic() - missing_since >= 10.0:
                    processor = legacy.leafos_processor
                    if processor is not None and processor.has_open_session():
                        await finalize_leafos_session(
                            "game_closed",
                            restart_monitor=True,
                            closed_cleanly=True,
                        )
                    was_online = False
                    missing_since = None
        except asyncio.CancelledError:
            raise
        except Exception:
            legacy.logging.getLogger("kagelink").exception(
                "[LeafOS Lifecycle ERROR] Game-close watcher failed"
            )
        await asyncio.sleep(1.0)


_original_lifespan = legacy.lifespan


@asynccontextmanager
async def unified_lifespan(fastapi_app):
    processor = legacy.leafos_processor
    if processor is not None:
        try:
            if legacy.leafos_exporter is not None:
                await asyncio.to_thread(legacy.leafos_exporter.sync, legacy.history)
            if processor.has_open_session():
                await asyncio.to_thread(
                    processor.recover_unclean_session,
                    now=datetime.now(timezone.utc),
                )
        except Exception:
            legacy.logging.getLogger("kagelink").exception(
                "[LeafOS Lifecycle ERROR] Could not recover previous open session"
            )

    async with _original_lifespan(fastapi_app):
        watcher = asyncio.create_task(_game_close_watcher(), name="leafos-game-close-watcher")
        try:
            yield
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher


legacy.app.router.lifespan_context = unified_lifespan

app = legacy.app
runtime_status = legacy.runtime_status
