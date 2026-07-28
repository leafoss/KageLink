from __future__ import annotations

from collections import Counter
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import re
from typing import Hashable, Mapping

import win32gui

from pc_agent.chat_reader import ChatReader, find_new_lines, normalize_text
from pc_agent.windows import find_controls


WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
SMTO_ABORTIFHUNG = 0x0002
_VICTORY_RE = re.compile(r"\bhas\s+been\s+knocked(?:\s*-\s*|\s+)out\b", re.IGNORECASE)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
_user32.SendMessageTimeoutW.restype = wintypes.LPARAM


@dataclass(frozen=True, slots=True)
class VictorySignal:
    text: str
    source: str = "chat"
    resynchronized: bool = False


class AllChatControlsReader:
    """Read every visible chat-class control owned by the Shinobi process.

    The original ChatReader intentionally selects the largest visible RichEdit for normal
    KageLink history. Combat victory is safety-critical and may be printed in another visible
    RichEdit, so this reader snapshots all viable controls while keeping the original reader as
    a fallback when control enumeration is temporarily unavailable.
    """

    def __init__(self, game_title: str, chat_class: str) -> None:
        self.game_title = game_title
        self.chat_class = chat_class
        self._fallback = ChatReader(game_title, chat_class)

    @staticmethod
    def _send_timeout(hwnd: int, message: int, wparam: int, lparam: int) -> int:
        result = ctypes.c_size_t(0)
        ok = _user32.SendMessageTimeoutW(
            int(hwnd),
            int(message),
            int(wparam),
            int(lparam),
            SMTO_ABORTIFHUNG,
            800,
            ctypes.byref(result),
        )
        return int(result.value) if ok else 0

    @classmethod
    def _read_hwnd(cls, hwnd: int) -> str:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return ""
        length = cls._send_timeout(hwnd, WM_GETTEXTLENGTH, 0, 0)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = cls._send_timeout(hwnd, WM_GETTEXT, length + 1, ctypes.addressof(buffer))
        return normalize_text(buffer.value) if copied > 0 else ""

    def read_all_current(self) -> dict[Hashable, str]:
        _, controls = find_controls(self.game_title, self.chat_class)
        snapshots: dict[Hashable, str] = {}
        for candidate in controls:
            if not candidate.visible or candidate.width <= 20 or candidate.height <= 20:
                continue
            text = self._read_hwnd(candidate.hwnd)
            if text:
                snapshots[int(candidate.hwnd)] = text

        if snapshots:
            return snapshots

        fallback = self._fallback.read_current() or ""
        return {"selected": fallback} if fallback else {}


class RobustChatVictoryWatcher:
    """Detect only newly produced KO phrases across all chat controls.

    Normal appends use exact line overlap. If BYOND truncates or rewrites a RichEdit history,
    the watcher compares per-line occurrence counts against the previous snapshot. A temporary
    empty read is ignored rather than replacing the baseline, preventing both missed KOs and
    old-history false positives on the next successful read.
    """

    def __init__(self, game_title: str, chat_class: str, *, reader=None) -> None:
        self.reader = reader or AllChatControlsReader(game_title, chat_class)
        self._previous: dict[Hashable, str] = {}
        self._victory_counts: dict[Hashable, Counter[str]] = {}
        self._primed = False
        self.last_source_count = 0
        self.last_resynchronized_sources = 0

    @staticmethod
    def is_victory_text(text: str) -> bool:
        return bool(_VICTORY_RE.search(str(text or "")))

    @staticmethod
    def _line_key(line: str) -> str:
        return " ".join(str(line or "").casefold().split())

    @classmethod
    def _victory_lines(cls, text: str) -> list[str]:
        return [line.strip() for line in str(text or "").splitlines() if cls.is_victory_text(line)]

    @classmethod
    def _counts(cls, text: str) -> Counter[str]:
        return Counter(cls._line_key(line) for line in cls._victory_lines(text))

    def _snapshots(self) -> dict[Hashable, str]:
        read_all = getattr(self.reader, "read_all_current", None)
        if callable(read_all):
            raw = read_all() or {}
            if isinstance(raw, Mapping):
                return {
                    source: normalize_text(str(text or ""))
                    for source, text in raw.items()
                    if str(text or "")
                }
        read_one = getattr(self.reader, "read_current", None)
        text = read_one() if callable(read_one) else ""
        return {"selected": normalize_text(str(text or ""))} if text else {}

    def prime(self) -> None:
        snapshots = self._snapshots()
        self._previous = dict(snapshots)
        self._victory_counts = {source: self._counts(text) for source, text in snapshots.items()}
        self.last_source_count = len(snapshots)
        self.last_resynchronized_sources = 0
        self._primed = True

    def poll(self) -> VictorySignal | None:
        snapshots = self._snapshots()
        if not self._primed:
            self._previous = dict(snapshots)
            self._victory_counts = {source: self._counts(text) for source, text in snapshots.items()}
            self.last_source_count = len(snapshots)
            self._primed = True
            return None

        # A failed/empty Win32 read must not erase the good baseline.
        if not snapshots:
            self.last_source_count = 0
            self.last_resynchronized_sources = 0
            return None

        signal: VictorySignal | None = None
        resync_count = 0

        for source, current in snapshots.items():
            previous = self._previous.get(source)
            if previous is None:
                # Newly created controls may expose old history. Baseline them first.
                self._previous[source] = current
                self._victory_counts[source] = self._counts(current)
                continue
            if current == previous:
                continue

            new_lines, resynchronized = find_new_lines(previous, current)
            if resynchronized:
                resync_count += 1

            candidate: str | None = None
            for line in new_lines:
                if self.is_victory_text(line):
                    candidate = line.strip()

            previous_counts = self._victory_counts.get(source, self._counts(previous))
            current_victories = self._victory_lines(current)
            current_counts = Counter(self._line_key(line) for line in current_victories)

            # On a rewritten/truncated history, exact overlap may be unavailable. A larger
            # occurrence count is still authoritative evidence that a new KO line appeared.
            if candidate is None and resynchronized:
                running: Counter[str] = Counter()
                for line in current_victories:
                    key = self._line_key(line)
                    running[key] += 1
                    if running[key] > previous_counts.get(key, 0):
                        candidate = line

            self._previous[source] = current
            self._victory_counts[source] = current_counts

            if signal is None and candidate is not None:
                signal = VictorySignal(
                    text=candidate,
                    source=str(source),
                    resynchronized=bool(resynchronized),
                )

        self.last_source_count = len(snapshots)
        self.last_resynchronized_sources = resync_count
        return signal


__all__ = [
    "AllChatControlsReader",
    "RobustChatVictoryWatcher",
    "VictorySignal",
]
