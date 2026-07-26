from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pc_agent.leafos import LeafOSProcessor, RawRecordReader, _atomic_json, _safe_name


PrimaryCharacterProvider = Callable[[], str]
PrimaryCharacterResolver = Callable[[dict[str, Any]], str]


class LifecycleLeafOSProcessor(LeafOSProcessor):
    """LeafOS processor with explicit, auditable session lifecycle controls.

    The original Processor remains responsible for deterministic RAW ingestion and
    idle/gap splitting. This subclass adds explicit close reasons, crash recovery,
    primary-character stamping, and a fail-safe block that prevents creation of a
    new ambiguous session while no primary character is configured.
    """

    def __init__(
        self,
        vault_path: Path | None,
        raw_output_path: Path | None,
        *,
        session_idle_seconds: float = 900.0,
        logger=None,
        primary_character_provider: PrimaryCharacterProvider | None = None,
        primary_character_resolver: PrimaryCharacterResolver | None = None,
        require_primary_character: bool = True,
    ) -> None:
        super().__init__(
            vault_path,
            raw_output_path,
            session_idle_seconds=session_idle_seconds,
            logger=logger,
        )
        self.primary_character_provider = primary_character_provider
        self.primary_character_resolver = primary_character_resolver
        self.require_primary_character = bool(require_primary_character)
        self._lifecycle_lock = threading.RLock()
        self._forced_close_reason: str | None = None
        self._forced_closed_cleanly = True

    def _current_primary_character(self) -> str:
        provider = self.primary_character_provider
        if provider is None:
            return ""
        try:
            return str(provider() or "").strip()
        except Exception:
            self.logger.exception("[LeafOS Processor ERROR] Could not read primary character")
            return ""

    def _resolve_session_character(self, session: dict[str, Any]) -> str:
        existing = str(session.get("primary_character", "") or "").strip()
        if existing:
            return existing
        resolver = self.primary_character_resolver
        if resolver is not None:
            try:
                resolved = str(resolver(session) or "").strip()
                if resolved:
                    return resolved
            except Exception:
                self.logger.exception(
                    "[LeafOS Processor ERROR] Could not resolve primary character for session %s",
                    session.get("session_id", ""),
                )
        return self._current_primary_character()

    def _new_session(self, state: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        session = super()._new_session(state, record)
        session["primary_character"] = self._current_primary_character()
        return session

    def _close_session(self, paths: dict[str, Path], session: dict[str, Any]) -> None:
        if not session.get("messages"):
            return

        session_id = str(session["session_id"])
        payload = dict(session)
        payload["primary_character"] = self._resolve_session_character(payload)
        payload["closed_at"] = datetime.now(timezone.utc).isoformat()
        payload["close_reason"] = self._forced_close_reason or "idle_timeout"
        payload["closed_cleanly"] = bool(self._forced_closed_cleanly)

        _atomic_json(paths["sessions"] / f"{_safe_name(session_id)}.json", payload)

        inbox_payload = {
            "type": "session",
            "session_id": session_id,
            "started_at": payload.get("started_at"),
            "ended_at": payload.get("ended_at"),
            "closed_at": payload.get("closed_at"),
            "close_reason": payload.get("close_reason"),
            "closed_cleanly": payload.get("closed_cleanly"),
            "primary_character": payload.get("primary_character", ""),
            "participants": payload.get("participants", []),
            "message_count": payload.get("message_count", 0),
            "message_ids": payload.get("message_ids", []),
            "raw_sources": payload.get("raw_sources", []),
            "messages": payload.get("messages", []),
            "status": "processor_ready",
        }
        _atomic_json(
            paths["inbox_sessions"] / f"{_safe_name(session_id)}.json",
            inbox_payload,
        )
        self.logger.info(
            "[LeafOS Processor] Session closed: %s reason=%s clean=%s character=%s",
            session_id,
            payload["close_reason"],
            payload["closed_cleanly"],
            payload.get("primary_character") or "(unset)",
        )

    def _state_payload(self) -> tuple[dict[str, Path], dict[str, Any]]:
        paths = self._paths()
        state = self._load_json(
            paths["state"],
            {
                "last_processed_id": 0,
                "last_run": "",
                "raw_source": "",
                "open_session": None,
                "session_counters": {},
            },
        )
        return paths, state

    def evidence_id_floor(self) -> int:
        """Return the highest numeric message ID already present in LeafOS state/RAW.

        This is used only to keep a newly created local SQLite database from
        restarting message IDs below an existing Vault cursor.
        """

        with self._lifecycle_lock:
            _paths, state = self._state_payload()
            try:
                floor = max(0, int(state.get("last_processed_id", 0) or 0))
            except (TypeError, ValueError):
                floor = 0
            try:
                records = RawRecordReader(self.raw_output_path).after_id(0)
            except (OSError, FileNotFoundError):
                records = []
            for record in records:
                try:
                    floor = max(floor, int(record.get("id", 0) or 0))
                except (TypeError, ValueError):
                    continue
            return floor

    def has_open_session(self) -> bool:
        with self._lifecycle_lock:
            _paths, state = self._state_payload()
            session = state.get("open_session")
            return isinstance(session, dict) and bool(session.get("messages"))

    def lifecycle_status(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            _paths, state = self._state_payload()
            session = state.get("open_session")
            if not isinstance(session, dict) or not session.get("messages"):
                return {
                    "open": False,
                    "primary_character": self._current_primary_character(),
                    "blocked_no_primary_character": bool(
                        self.require_primary_character and not self._current_primary_character()
                    ),
                }
            return {
                "open": True,
                "session_id": str(session.get("session_id", "")),
                "started_at": session.get("started_at"),
                "ended_at": session.get("ended_at"),
                "message_count": int(session.get("message_count", 0) or 0),
                "primary_character": self._resolve_session_character(session),
                "blocked_no_primary_character": False,
            }

    def run_once(self, *, now: datetime | None = None) -> dict[str, int]:
        with self._lifecycle_lock:
            paths, state = self._state_payload()
            session = state.get("open_session")
            has_open = isinstance(session, dict) and bool(session.get("messages"))
            if (
                self.require_primary_character
                and not has_open
                and not self._current_primary_character()
            ):
                current_time = now or datetime.now(timezone.utc)
                if current_time.tzinfo is None:
                    current_time = current_time.replace(tzinfo=timezone.utc)
                state["last_run"] = current_time.isoformat()
                state["blocked_reason"] = "primary_character_required"
                _atomic_json(paths["state"], state)
                return {
                    "processed_ic": 0,
                    "closed_sessions": 0,
                    "blocked_no_primary_character": 1,
                }
            if state.pop("blocked_reason", None) is not None:
                _atomic_json(paths["state"], state)
            return super().run_once(now=now)

    def finalize_open_session(
        self,
        close_reason: str,
        *,
        closed_cleanly: bool = True,
        now: datetime | None = None,
        consume_pending: bool = True,
    ) -> dict[str, Any]:
        """Consume pending RAW and explicitly close the current session."""

        with self._lifecycle_lock:
            current_time = now or datetime.now(timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)

            processed_result: dict[str, int] = {
                "processed_ic": 0,
                "closed_sessions": 0,
            }
            if consume_pending:
                processed_result = self.run_once(now=current_time)

            paths, state = self._state_payload()
            session = state.get("open_session")
            if not isinstance(session, dict) or not session.get("messages"):
                return {
                    "closed": False,
                    "session_id": None,
                    "close_reason": str(close_reason),
                    "closed_cleanly": bool(closed_cleanly),
                    "processed": processed_result,
                }

            session_id = str(session.get("session_id", ""))
            self._forced_close_reason = str(close_reason or "manual")
            self._forced_closed_cleanly = bool(closed_cleanly)
            try:
                self._close_session(paths, session)
            finally:
                self._forced_close_reason = None
                self._forced_closed_cleanly = True

            state["open_session"] = None
            state["last_run"] = current_time.isoformat()
            _atomic_json(paths["state"], state)
            return {
                "closed": True,
                "session_id": session_id,
                "close_reason": str(close_reason),
                "closed_cleanly": bool(closed_cleanly),
                "processed": processed_result,
            }

    def recover_unclean_session(self, *, now: datetime | None = None) -> dict[str, Any]:
        if not self.has_open_session():
            return {
                "closed": False,
                "session_id": None,
                "close_reason": "unclean_shutdown_recovery",
                "closed_cleanly": False,
            }
        return self.finalize_open_session(
            "unclean_shutdown_recovery",
            closed_cleanly=False,
            now=now,
            consume_pending=True,
        )
