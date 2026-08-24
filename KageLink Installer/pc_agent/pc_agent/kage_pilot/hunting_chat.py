from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Hashable, Mapping

from pc_agent.chat_reader import find_new_lines, normalize_text
from pc_agent.kage_pilot.chat_victory_v03g import AllChatControlsReader

AMBUSH_RE = re.compile(
    r"^\s*(?P<clan>[A-Za-z][A-Za-z-]*),\s*(?P<name>.+?)\s+"
    r"dashes\s+from\s+above\s+the\s+trees\s+as\s+they\s+prepare\s+their\s+ambush\.\s*$",
    re.IGNORECASE,
)
KO_RE = re.compile(
    r"\bhas\s+been\s+knocked(?:\s*-\s*|\s+)out\b|"
    r"\bhas\s+been\s+knocked\s+unconscious\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class HuntingChatEvent:
    kind: str
    text: str
    clan: str = ""
    name: str = ""
    source: str = ""


class HuntingChatWatcher:
    """Read all chat controls and emit only new exact forest events."""

    def __init__(self, game_title: str, chat_class: str, *, reader=None) -> None:
        self.reader = reader or AllChatControlsReader(game_title, chat_class)
        self._previous: dict[Hashable, str] = {}
        self._ko_counts: dict[Hashable, Counter[str]] = {}
        self._primed = False

    @staticmethod
    def _line_key(line: str) -> str:
        return " ".join(str(line or "").casefold().split())

    @classmethod
    def _ko_lines(cls, text: str) -> list[str]:
        return [line.strip() for line in str(text or "").splitlines() if KO_RE.search(line)]

    @classmethod
    def _counts(cls, text: str) -> Counter[str]:
        return Counter(cls._line_key(line) for line in cls._ko_lines(text))

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
        self._ko_counts = {source: self._counts(text) for source, text in snapshots.items()}
        self._primed = True
        print(f"HUNTING_CHAT_PRIMED sources={len(snapshots)}", flush=True)

    def poll(self) -> list[HuntingChatEvent]:
        snapshots = self._snapshots()
        if not self._primed:
            self.prime()
            return []
        if not snapshots:
            return []

        events: list[HuntingChatEvent] = []
        for source, current in snapshots.items():
            previous = self._previous.get(source)
            if previous is None:
                # A newly created control may expose old history; baseline it first.
                self._previous[source] = current
                self._ko_counts[source] = self._counts(current)
                continue
            if current == previous:
                continue

            lines, resynchronized = find_new_lines(previous, current)
            # Spawn authority fails closed on resync because returned text may be history.
            if not resynchronized:
                for line in lines:
                    text = str(line or "").strip()
                    match = AMBUSH_RE.match(text)
                    if match:
                        events.append(
                            HuntingChatEvent(
                                kind="spawn",
                                text=text,
                                clan=match.group("clan").strip(),
                                name=match.group("name").strip(),
                                source=str(source),
                            )
                        )

            ko_candidate: str | None = None
            for line in lines:
                text = str(line or "").strip()
                if KO_RE.search(text):
                    ko_candidate = text

            previous_counts = self._ko_counts.get(source, self._counts(previous))
            current_ko = self._ko_lines(current)
            current_counts = Counter(self._line_key(line) for line in current_ko)
            if ko_candidate is None and resynchronized:
                running: Counter[str] = Counter()
                for line in current_ko:
                    key = self._line_key(line)
                    running[key] += 1
                    if running[key] > previous_counts.get(key, 0):
                        ko_candidate = line
                        break

            self._previous[source] = current
            self._ko_counts[source] = current_counts
            if ko_candidate is not None:
                events.append(HuntingChatEvent("ko", ko_candidate, source=str(source)))
        return events


__all__ = ["AMBUSH_RE", "KO_RE", "HuntingChatEvent", "HuntingChatWatcher"]
