from __future__ import annotations

from dataclasses import dataclass


OOC_CHANNEL = "ooc"
IC_CHANNEL = "ic"
VALID_CHANNELS = {OOC_CHANNEL, IC_CHANNEL}


@dataclass(frozen=True, slots=True)
class ParsedChatMessage:
    channel: str
    text: str


class ChatChannelParser:
    """Separates Shinobi chat text into OOC lines and complete IC blocks.

    The IC grammar is intentionally strict and deterministic:
    - an IC roleplay block starts at ``(*`` and ends at the next ``*)``;
    - incomplete roleplay blocks remain buffered until their closing delimiter;
    - a plain chat block containing the literal case-sensitive marker ``Says:`` is IC.
    """

    def __init__(self, pending_text: str = "") -> None:
        self._buffer = _normalize(pending_text)

    @property
    def pending_text(self) -> str:
        return self._buffer

    def reset(self) -> None:
        self._buffer = ""

    def feed(self, incoming_text: str) -> list[ParsedChatMessage]:
        if not incoming_text:
            return []

        self._buffer += _normalize(incoming_text)
        parsed: list[ParsedChatMessage] = []

        while self._buffer:
            ic_start = self._buffer.find("(*")

            if ic_start < 0:
                plain, remainder = _plain_messages(
                    self._buffer,
                    final_boundary=False,
                )
                parsed.extend(plain)
                self._buffer = remainder
                break

            if ic_start > 0:
                plain, _ = _plain_messages(
                    self._buffer[:ic_start],
                    final_boundary=True,
                )
                parsed.extend(plain)
                self._buffer = self._buffer[ic_start:]

            ic_end = self._buffer.find("*)", 2)
            if ic_end < 0:
                break

            block_end = ic_end + 2
            block = self._buffer[:block_end].strip("\n")
            if block:
                parsed.append(ParsedChatMessage(channel=IC_CHANNEL, text=block))
            self._buffer = self._buffer[block_end:]

        return parsed


def drop_replayed_prefix(
    messages: list[ParsedChatMessage],
    recent_messages: list[tuple[str, str]],
) -> list[ParsedChatMessage]:
    """Drops only the prefix that is a replay of the stored incoming suffix.

    This is used after a true resynchronization, when BYOND replaced or
    truncated enough of the RichEdit content that text-level overlap could not
    be established. Comparing complete classified messages prevents the whole
    visible history from being inserted again.
    """

    if not messages or not recent_messages:
        return messages

    current = [(item.channel, item.text) for item in messages]
    maximum_overlap = min(len(current), len(recent_messages), 500)
    for overlap in range(maximum_overlap, 0, -1):
        if recent_messages[-overlap:] == current[:overlap]:
            return messages[overlap:]
    return messages


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\x00")


def _plain_messages(
    text: str,
    *,
    final_boundary: bool,
) -> tuple[list[ParsedChatMessage], str]:
    """Classifies non-``(* ... *)`` text without changing legacy OOC rules.

    The only additional IC rule is the literal case-sensitive marker ``Says:``.
    A line that ends exactly at that marker is kept pending until its first
    non-empty continuation line arrives, so fragmented ``Name Says:`` blocks
    remain a single IC message.
    """

    normalized = _normalize(text)
    if not normalized:
        return [], ""

    trailing_open = normalized.endswith("(")
    core = normalized[:-1] if trailing_open else normalized
    lines = core.split("\n") if core else []
    parsed: list[ParsedChatMessage] = []
    remainder = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if "Says:" not in line:
            parsed.append(ParsedChatMessage(channel=OOC_CHANNEL, text=line.strip()))
            index += 1
            continue

        _, after_marker = line.split("Says:", 1)
        if after_marker.strip() or final_boundary:
            parsed.append(ParsedChatMessage(channel=IC_CHANNEL, text=line.strip()))
            index += 1
            continue

        continuation = index + 1
        while continuation < len(lines) and not lines[continuation].strip():
            continuation += 1

        if continuation >= len(lines):
            remainder = "\n".join(lines[index:])
            break

        block = "\n".join(lines[index : continuation + 1]).strip("\n")
        parsed.append(ParsedChatMessage(channel=IC_CHANNEL, text=block))
        index = continuation + 1

    if trailing_open:
        remainder += "("
    return parsed, remainder


def _ooc_messages(text: str) -> list[ParsedChatMessage]:
    # Retained as a compatibility helper for callers/tests outside the parser.
    return [
        ParsedChatMessage(channel=OOC_CHANNEL, text=line.strip())
        for line in text.splitlines()
        if line.strip()
    ]


def unfinished_ic_suffix(text: str) -> str:
    """Returns a trailing IC block that started but has not closed yet."""

    normalized = _normalize(text)
    last_start = normalized.rfind("(*")
    last_end = normalized.rfind("*)")
    return normalized[last_start:] if last_start > last_end else ""


def find_new_text(previous: str, current: str) -> tuple[str, bool]:
    """Returns the exact newly appended text and whether a resync was needed.

    It preserves newlines so IC paragraphs can be reconstructed. When the game
    truncates the beginning of the RichEdit history, the longest line overlap
    between the old suffix and the new prefix is used.
    """

    previous = _normalize(previous)
    current = _normalize(current)

    if not current or current == previous:
        return "", False

    if not previous:
        return current, False

    if current.startswith(previous):
        return current[len(previous):], False

    previous_lines = previous.split("\n")
    current_lines = current.split("\n")
    maximum_overlap = min(len(previous_lines), len(current_lines), 2000)

    for overlap in range(maximum_overlap, 0, -1):
        if previous_lines[-overlap:] == current_lines[:overlap]:
            matched_prefix = "\n".join(current_lines[:overlap])
            return current[len(matched_prefix):], False

    return current, True
