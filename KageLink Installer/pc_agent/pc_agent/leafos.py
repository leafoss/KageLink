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
