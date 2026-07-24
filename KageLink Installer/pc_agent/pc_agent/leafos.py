from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pc_agent.history import HistoryStore


RAW_STATE_KEY = "leafos_raw_last_exported_id"
_RAW_BEGIN_PREFIX = "<!-- kagelink-raw-begin "
_RAW_END = "<!-- kagelink-raw-end -->"
_SAYS_SPEAKER = re.compile(r"^\s*(?P<speaker>[^\r\n]{1,160}?)\s+Says:")
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def extract_speaker(text: str) -> str | None:
    """Extracts only speakers exposed by the literal deterministic ``Says:`` form."""

    first_line = str(text or "").splitlines()[0] if text else ""
    match = _SAYS_SPEAKER.search(first_line)
    if not match:
        return None
    speaker = " ".join(match.group("speaker").split()).strip()
    return speaker or None


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _local_timestamp(value: str) -> datetime:
    return _parse_timestamp(value).astimezone()


def _safe_name(value: str) -> str:
    clean = _INVALID_FILENAME.sub("_", value).strip().rstrip(".")
    return clean[:120] or "unknown"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _relative_or_absolute(path: Path, vault: Path | None) -> str:
    if vault is not None:
        try:
            return str(path.resolve().relative_to(vault.resolve())).replace("\\", "/")
        except (OSError, ValueError):
            pass
    return str(path.resolve()).replace("\\", "/")


class LeafOSRawExporter:
    """Append-only exporter that consumes persisted KageLink history records."""

    def __init__(
        self,
        raw_output_path: Path | None,
        *,
        export_ic: bool = True,
        export_ooc: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self.raw_output_path = Path(raw_output_path) if raw_output_path else None
        self.export_ic = bool(export_ic)
        self.export_ooc = bool(export_ooc)
        self.logger = logger or logging.getLogger("kagelink")
        self._availability_error_logged = False

    def _require_raw_root(self) -> Path:
        if self.raw_output_path is None:
            raise FileNotFoundError("RAW output path is not configured")
        root = self.raw_output_path
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise NotADirectoryError(f"RAW output path is not a directory: {root}")
        return root

    def ensure_structure(self) -> Path:
        root = self._require_raw_root()
        (root / "IC").mkdir(parents=True, exist_ok=True)
        (root / "OOC").mkdir(parents=True, exist_ok=True)
        return root

    def _enabled_for(self, channel: str) -> bool:
        return (channel == "ic" and self.export_ic) or (
            channel == "ooc" and self.export_ooc
        )

    def _raw_path(self, record: dict[str, Any]) -> Path:
        root = self.ensure_structure()
        local = _local_timestamp(str(record["timestamp"]))
        channel_dir = "IC" if record.get("channel") == "ic" else "OOC"
        return root / channel_dir / f"{local:%Y-%m-%d}.md"

    @staticmethod
    def _marker(record_id: int) -> str:
        return f'{_RAW_BEGIN_PREFIX}{{"id":{int(record_id)},'

    def append_record(self, record: dict[str, Any]) -> Path:
        path = self._raw_path(record)
        record_id = int(record["id"])
        text = str(record.get("text", ""))
        speaker = extract_speaker(text)
        metadata = {
            "id": record_id,
            "timestamp": str(record["timestamp"]),
            "channel": str(record.get("channel", "ooc")),
            "speaker": speaker,
        }
        marker = self._marker(record_id)

        # The SQLite cursor is authoritative. This tail check closes the tiny
        # crash window between an append and the cursor update without using
        # message text as an identity key.
        if path.exists():
            with path.open("rb") as existing:
                size = path.stat().st_size
                existing.seek(max(0, size - 262144))
                tail = existing.read().decode("utf-8", errors="ignore")
            if marker in tail:
                return path

        begin = _RAW_BEGIN_PREFIX + json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
        ) + " -->"
        entry = f"{begin}\n{text}\n{_RAW_END}\n\n"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(entry)
        return path

    def sync(self, history: HistoryStore) -> dict[str, int]:
        """Exports only new history IDs; disabled channels are marked seen."""

        counts = {"ic": 0, "ooc": 0}
        try:
            self.ensure_structure()
            self._availability_error_logged = False
        except OSError as error:
            if not self._availability_error_logged:
                self.logger.error("[LeafOS ERROR] RAW directory unavailable: %s", error)
                self._availability_error_logged = True
            return counts

        try:
            last_seen = int(history.get_runtime_state(RAW_STATE_KEY, "0") or 0)
        except ValueError:
            last_seen = 0

        while True:
            records = history.incoming_after_id(last_seen, 2000)
            if not records:
                break

            for record in records:
                record_id = int(record["id"])
                channel = str(record.get("channel", "ooc"))
                try:
                    if self._enabled_for(channel):
                        self.append_record(record)
                        counts[channel] += 1
                        self.logger.info(
                            "[LeafOS] %s appended: id=%s",
                            channel.upper(),
                            record_id,
                        )
                    # Advancing through disabled channels intentionally prevents
                    # old traffic from being re-exported if a channel is enabled
                    # later or if raw_output_path is changed.
                    history.set_runtime_state(RAW_STATE_KEY, str(record_id))
                    last_seen = record_id
                except OSError as error:
                    self.logger.error("[LeafOS ERROR] RAW export failed: %s", error)
                    return counts

            if len(records) < 2000:
                break

        return counts


class RawRecordReader:
    """Reads the technical record envelope while leaving original text untouched."""

    def __init__(self, raw_output_path: Path | None) -> None:
        self.raw_output_path = Path(raw_output_path) if raw_output_path else None

    def _root(self) -> Path:
        if self.raw_output_path is None:
            raise FileNotFoundError("RAW output path is not configured")
        root = self.raw_output_path
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"RAW output path unavailable: {root}")
        return root

    def _files(self) -> Iterable[Path]:
        root = self._root()
        for channel in ("IC", "OOC"):
            folder = root / channel
            if folder.exists():
                yield from sorted(folder.glob("*.md"))

    @staticmethod
    def _parse_file(path: Path) -> list[dict[str, Any]]:
        content = path.read_text(encoding="utf-8-sig")
        records: list[dict[str, Any]] = []
        cursor = 0
        while True:
            begin_at = content.find(_RAW_BEGIN_PREFIX, cursor)
            if begin_at < 0:
                break
            meta_end = content.find(" -->", begin_at)
            if meta_end < 0:
                break
            payload = content[begin_at + len(_RAW_BEGIN_PREFIX) : meta_end]
            text_start = meta_end + len(" -->")
            if content.startswith("\n", text_start):
                text_start += 1
            end_at = content.find("\n" + _RAW_END, text_start)
            if end_at < 0:
                break
            try:
                meta = json.loads(payload)
            except json.JSONDecodeError:
                cursor = meta_end + 4
                continue
            if isinstance(meta, dict) and "id" in meta:
                record = dict(meta)
                record["id"] = int(record["id"])
                record["text"] = content[text_start:end_at]
                record["raw_file"] = path
                records.append(record)
            cursor = end_at + len("\n" + _RAW_END)
        return records

    def after_id(self, after_id: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in self._files():
            for record in self._parse_file(path):
                if int(record["id"]) > int(after_id):
                    result.append(record)
        result.sort(key=lambda item: int(item["id"]))
        return result


class LeafOSProcessor:
    """Deterministic RAW-to-Inbox processor; no LLM or narrative inference."""

    def __init__(
        self,
        vault_path: Path | None,
        raw_output_path: Path | None,
        *,
        session_idle_seconds: float = 900.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.vault_path = Path(vault_path) if vault_path else None
        self.raw_output_path = Path(raw_output_path) if raw_output_path else None
        self.session_idle_seconds = max(60.0, float(session_idle_seconds))
        self.logger = logger or logging.getLogger("kagelink")

    def _require_vault(self) -> Path:
        if self.vault_path is None:
            raise FileNotFoundError("LeafOS Vault path is not configured")
        vault = self.vault_path
        vault.mkdir(parents=True, exist_ok=True)
        if not vault.is_dir():
            raise NotADirectoryError(f"LeafOS Vault path is not a directory: {vault}")
        return vault

    def _paths(self) -> dict[str, Path]:
        vault = self._require_vault()
        paths = {
            "state": vault / "80 - Processor" / "processor_state.json",
            "sessions": vault / "80 - Processor" / "Sessions",
            "participants": vault / "80 - Processor" / "Participants",
            "inbox_sessions": vault / "70 - LeafOS Inbox" / "Sessions",
            "inbox_events": vault / "70 - LeafOS Inbox" / "Events",
            "new_characters": vault / "70 - LeafOS Inbox" / "New Characters",
        }
        for key, path in paths.items():
            if key != "state":
                path.mkdir(parents=True, exist_ok=True)
        paths["state"].parent.mkdir(parents=True, exist_ok=True)
        return paths

    @staticmethod
    def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return dict(default)
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            return value if isinstance(value, dict) else dict(default)
        except (OSError, json.JSONDecodeError):
            return dict(default)

    def _raw_reference(self, record: dict[str, Any]) -> str:
        path = Path(record["raw_file"])
        return _relative_or_absolute(path, self.vault_path)

    @staticmethod
    def _next_session_id(
        state: dict[str, Any],
        record: dict[str, Any],
    ) -> str:
        local = _local_timestamp(str(record["timestamp"]))
        day = f"{local:%Y-%m-%d}"
        counters = state.setdefault("session_counters", {})
        current = int(counters.get(day, 0)) + 1
        counters[day] = current
        return f"{day}_{current:03d}"

    def _new_session(
        self,
        state: dict[str, Any],
        record: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "session_id": self._next_session_id(state, record),
            "started_at": str(record["timestamp"]),
            "ended_at": str(record["timestamp"]),
            "participants": [],
            "message_count": 0,
            "message_ids": [],
            "raw_sources": [],
            "messages": [],
        }

    def _add_message(self, session: dict[str, Any], record: dict[str, Any]) -> None:
        speaker = record.get("speaker") or extract_speaker(str(record.get("text", "")))
        raw_reference = self._raw_reference(record)
        message = {
            "id": int(record["id"]),
            "timestamp": str(record["timestamp"]),
            "channel": str(record.get("channel", "ic")),
            "speaker": speaker,
            "text": str(record.get("text", "")),
            "raw_source": raw_reference,
        }
        session["messages"].append(message)
        session["message_ids"].append(int(record["id"]))
        session["message_count"] = len(session["messages"])
        session["ended_at"] = str(record["timestamp"])
        if speaker and speaker not in session["participants"]:
            session["participants"].append(speaker)
        if raw_reference not in session["raw_sources"]:
            session["raw_sources"].append(raw_reference)

    def _update_participants(
        self,
        paths: dict[str, Path],
        record: dict[str, Any],
        speaker: str | None,
    ) -> None:
        if not speaker:
            return
        index_path = paths["participants"] / "discovered.json"
        payload = self._load_json(index_path, {"participants": {}})
        participants = payload.setdefault("participants", {})
        existing = participants.get(speaker)
        is_new = not isinstance(existing, dict)
        if is_new:
            existing = {
                "first_seen": str(record["timestamp"]),
                "last_seen": str(record["timestamp"]),
                "message_count": 0,
            }
            participants[speaker] = existing
        existing["last_seen"] = str(record["timestamp"])
        existing["message_count"] = int(existing.get("message_count", 0)) + 1
        _atomic_json(index_path, payload)

        if is_new:
            candidate = {
                "name": speaker,
                "first_seen": str(record["timestamp"]),
                "source_message_id": int(record["id"]),
                "status": "detected_unreviewed",
            }
            _atomic_json(
                paths["new_characters"] / f"{_safe_name(speaker)}.json",
                candidate,
            )

    def _close_session(self, paths: dict[str, Path], session: dict[str, Any]) -> None:
        if not session.get("messages"):
            return
        session_id = str(session["session_id"])
        _atomic_json(paths["sessions"] / f"{_safe_name(session_id)}.json", session)

        inbox_payload = {
            "type": "session",
            "session_id": session_id,
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "participants": session.get("participants", []),
            "message_count": session.get("message_count", 0),
            "message_ids": session.get("message_ids", []),
            "raw_sources": session.get("raw_sources", []),
            "messages": session.get("messages", []),
            "status": "processor_ready",
        }
        _atomic_json(
            paths["inbox_sessions"] / f"{_safe_name(session_id)}.json",
            inbox_payload,
        )
        self.logger.info("[LeafOS Processor] Session closed: %s", session_id)

    def run_once(self, *, now: datetime | None = None) -> dict[str, int]:
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
        try:
            last_processed = max(0, int(state.get("last_processed_id", 0)))
        except (TypeError, ValueError):
            last_processed = 0

        reader = RawRecordReader(self.raw_output_path)
        records = reader.after_id(last_processed)
        session = state.get("open_session")
        if not isinstance(session, dict):
            session = None

        processed_ic = 0
        closed = 0
        cursor = last_processed
        for record in records:
            record_id = int(record["id"])
            cursor = max(cursor, record_id)
            if str(record.get("channel", "ooc")) != "ic":
                continue

            timestamp = _parse_timestamp(str(record["timestamp"]))
            if session and session.get("messages"):
                previous = _parse_timestamp(str(session["ended_at"]))
                if (timestamp - previous).total_seconds() >= self.session_idle_seconds:
                    self._close_session(paths, session)
                    closed += 1
                    session = None

            if session is None:
                session = self._new_session(state, record)
            self._add_message(session, record)
            speaker = record.get("speaker") or extract_speaker(str(record.get("text", "")))
            self._update_participants(paths, record, speaker)
            processed_ic += 1

        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        if session and session.get("messages"):
            last_message_at = _parse_timestamp(str(session["ended_at"]))
            if (current_time - last_message_at).total_seconds() >= self.session_idle_seconds:
                self._close_session(paths, session)
                closed += 1
                session = None

        state.update(
            {
                "last_processed_id": cursor,
                "last_run": current_time.isoformat(),
                "raw_source": str(self.raw_output_path or ""),
                "open_session": session,
            }
        )
        _atomic_json(paths["state"], state)
        return {"processed_ic": processed_ic, "closed_sessions": closed}
