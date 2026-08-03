from __future__ import annotations

import base64
import csv
import hashlib
import json
import math
import os
import re
import threading
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Optional


PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{4,}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    printable = sum(1 for value in data if value in (9, 10, 13) or 32 <= value <= 126)
    return printable / len(data)


def extract_strings(data: bytes, minimum_length: int = 4) -> list[str]:
    if minimum_length != 4:
        pattern = re.compile(rb"[\x20-\x7e]{%d,}" % minimum_length)
    else:
        pattern = PRINTABLE_RE
    return [match.decode("ascii", errors="replace") for match in pattern.findall(data)]


def payload_fingerprint(data: bytes, length: int = 12) -> str:
    return hashlib.sha256(data).hexdigest()[:length]


def normalized_difference(left: bytes, right: bytes) -> float:
    if not left and not right:
        return 0.0
    longest = max(len(left), len(right))
    overlap = min(len(left), len(right))
    differences = sum(1 for index in range(overlap) if left[index] != right[index])
    differences += longest - overlap
    return differences / longest


def changed_offsets(left: bytes, right: bytes, limit: int = 256) -> list[int]:
    overlap = min(len(left), len(right), limit)
    changed = [index for index in range(overlap) if left[index] != right[index]]
    if len(left) != len(right) and overlap < limit:
        changed.extend(range(overlap, min(max(len(left), len(right)), limit)))
    return changed


def format_hex_ascii(data: bytes, changed: Optional[set[int]] = None, width: int = 16) -> str:
    changed = changed or set()
    rows: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hex_cells: list[str] = []
        ascii_cells: list[str] = []
        for index, value in enumerate(chunk, start=offset):
            cell = f"{value:02X}"
            hex_cells.append(f"[{cell}]" if index in changed else f" {cell} ")
            character = chr(value) if 32 <= value <= 126 else "."
            ascii_cells.append(character)
        hex_text = "".join(hex_cells)
        ascii_text = "".join(ascii_cells)
        rows.append(f"{offset:08X}  {hex_text:<64}  |{ascii_text}|")
    return "\n".join(rows)


@dataclass(slots=True)
class Endpoint:
    pid: int
    process_name: str
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    status: str = "ESTABLISHED"

    @property
    def label(self) -> str:
        return (
            f"PID {self.pid} · {self.local_ip}:{self.local_port} "
            f"↔ {self.remote_ip}:{self.remote_port}"
        )


@dataclass(slots=True)
class PacketRecord:
    timestamp: float
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int
    sequence: Optional[int]
    acknowledgment: Optional[int]
    payload: bytes
    direction: str
    frame_number: Optional[int] = None
    stream_id: Optional[int] = None
    entropy: float = field(init=False)
    printable: float = field(init=False)
    fingerprint: str = field(init=False)
    strings: list[str] = field(init=False)
    novelty: float = 1.0
    changed_offsets: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.entropy = shannon_entropy(self.payload)
        self.printable = printable_ratio(self.payload)
        self.fingerprint = payload_fingerprint(self.payload)
        self.strings = extract_strings(self.payload)

    @property
    def length(self) -> int:
        return len(self.payload)

    def to_json_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp, timezone.utc).isoformat(),
            "frame_number": self.frame_number,
            "stream_id": self.stream_id,
            "direction": self.direction,
            "source_ip": self.source_ip,
            "source_port": self.source_port,
            "destination_ip": self.destination_ip,
            "destination_port": self.destination_port,
            "sequence": self.sequence,
            "acknowledgment": self.acknowledgment,
            "length": self.length,
            "entropy": round(self.entropy, 6),
            "printable_ratio": round(self.printable, 6),
            "fingerprint": self.fingerprint,
            "novelty": round(self.novelty, 6),
            "changed_offsets": self.changed_offsets,
            "strings": self.strings,
            "payload_hex": self.payload.hex(),
            "payload_base64": base64.b64encode(self.payload).decode("ascii"),
        }


@dataclass(slots=True)
class MarkerRecord:
    timestamp: float
    label: str
    note: str = ""

    def to_json_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp, timezone.utc).isoformat(),
            "label": self.label,
            "note": self.note,
        }


@dataclass(slots=True)
class EventAnalysis:
    marker: MarkerRecord
    event_start: float
    event_end: float
    baseline_start: float
    baseline_end: float
    inbound_packets: int
    outbound_packets: int
    inbound_bytes: int
    outbound_bytes: int
    top_lengths: list[tuple[int, int]]
    event_only_fingerprints: list[tuple[str, int]]
    top_strings: list[tuple[str, int]]
    changed_offset_counts: list[tuple[int, int]]

    def to_json_dict(self) -> dict:
        payload = asdict(self)
        payload["marker"] = self.marker.to_json_dict()
        return payload

    def render_text(self, locale: str = "pt-BR") -> str:
        english = locale == "en-US"
        none_word = "none" if english else "nenhum"
        length_text = ", ".join(f"{length} B × {count}" for length, count in self.top_lengths) or none_word
        fingerprint_text = ", ".join(
            f"{fingerprint} × {count}" for fingerprint, count in self.event_only_fingerprints
        ) or ("no event-only signatures" if english else "nenhuma assinatura exclusiva")
        strings_text = "\n".join(f"  • {value!r} × {count}" for value, count in self.top_strings)
        offsets_text = ", ".join(
            f"0x{offset:02X} × {count}" for offset, count in self.changed_offset_counts
        ) or ("no recurring offsets" if english else "nenhum offset recorrente")
        if english:
            return (
                f"MARKER: {self.marker.label}\n"
                f"Note: {self.marker.note or '—'}\n\n"
                f"Event window: {self.event_start:.3f} → {self.event_end:.3f}\n"
                f"Inbound: {self.inbound_packets} packets / {self.inbound_bytes} bytes\n"
                f"Outbound: {self.outbound_packets} packets / {self.outbound_bytes} bytes\n\n"
                f"Most frequent lengths: {length_text}\n"
                f"Event-only signatures: {fingerprint_text}\n"
                f"Recurring changed offsets: {offsets_text}\n\n"
                f"Extracted ASCII strings:\n{strings_text or '  none'}"
            )
        return (
            f"MARCADOR: {self.marker.label}\n"
            f"Nota: {self.marker.note or '—'}\n\n"
            f"Janela do evento: {self.event_start:.3f} → {self.event_end:.3f}\n"
            f"Entrada: {self.inbound_packets} pacotes / {self.inbound_bytes} bytes\n"
            f"Saída: {self.outbound_packets} pacotes / {self.outbound_bytes} bytes\n\n"
            f"Tamanhos mais frequentes: {length_text}\n"
            f"Assinaturas exclusivas do evento: {fingerprint_text}\n"
            f"Offsets alterados recorrentes: {offsets_text}\n\n"
            f"Strings ASCII encontradas:\n{strings_text or '  nenhuma'}"
        )


class PacketHistory:
    def __init__(self, max_packets: int = 20_000) -> None:
        self._packets: Deque[PacketRecord] = deque(maxlen=max_packets)
        self._last_by_direction: dict[str, PacketRecord] = {}
        self._last_same_length: dict[tuple[str, int], PacketRecord] = {}
        self._fingerprints: Counter[str] = Counter()
        self._lock = threading.RLock()

    def append(self, packet: PacketRecord) -> PacketRecord:
        with self._lock:
            previous = self._last_by_direction.get(packet.direction)
            if previous is not None:
                packet.novelty = normalized_difference(previous.payload, packet.payload)

            same_length = self._last_same_length.get((packet.direction, packet.length))
            if same_length is not None:
                packet.changed_offsets = changed_offsets(same_length.payload, packet.payload)

            self._last_by_direction[packet.direction] = packet
            self._last_same_length[(packet.direction, packet.length)] = packet
            self._fingerprints[packet.fingerprint] += 1
            self._packets.append(packet)
            return packet

    def snapshot(self) -> list[PacketRecord]:
        with self._lock:
            return list(self._packets)

    def packets_between(self, start: float, end: float) -> list[PacketRecord]:
        with self._lock:
            return [packet for packet in self._packets if start <= packet.timestamp <= end]

    def analyze_marker(
        self,
        marker: MarkerRecord,
        before_seconds: float = 0.75,
        after_seconds: float = 1.50,
        baseline_gap: float = 0.50,
        baseline_seconds: float = 2.00,
    ) -> EventAnalysis:
        event_start = marker.timestamp - before_seconds
        event_end = marker.timestamp + after_seconds
        baseline_end = event_start - baseline_gap
        baseline_start = baseline_end - baseline_seconds

        event_packets = self.packets_between(event_start, event_end)
        baseline_packets = self.packets_between(baseline_start, baseline_end)

        inbound = [packet for packet in event_packets if packet.direction == "IN"]
        outbound = [packet for packet in event_packets if packet.direction == "OUT"]

        pattern_packets = inbound or event_packets
        baseline_pattern_packets = [
            packet for packet in baseline_packets if packet.direction == "IN"
        ] or baseline_packets

        event_fingerprints = Counter(packet.fingerprint for packet in pattern_packets)
        baseline_fingerprints = Counter(packet.fingerprint for packet in baseline_pattern_packets)
        exclusive = [
            (fingerprint, count)
            for fingerprint, count in event_fingerprints.most_common()
            if baseline_fingerprints[fingerprint] == 0
        ][:8]

        lengths = Counter(packet.length for packet in pattern_packets).most_common(8)
        strings = Counter(
            string
            for packet in pattern_packets
            for string in packet.strings
            if len(string.strip()) >= 4
        ).most_common(12)
        offsets = Counter(
            offset
            for packet in pattern_packets
            for offset in packet.changed_offsets
        ).most_common(16)

        return EventAnalysis(
            marker=marker,
            event_start=event_start,
            event_end=event_end,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            inbound_packets=len(inbound),
            outbound_packets=len(outbound),
            inbound_bytes=sum(packet.length for packet in inbound),
            outbound_bytes=sum(packet.length for packet in outbound),
            top_lengths=lengths,
            event_only_fingerprints=exclusive,
            top_strings=strings,
            changed_offset_counts=offsets,
        )


class SessionWriter:
    CSV_FIELDS = [
        "timestamp_iso",
        "direction",
        "source",
        "destination",
        "length",
        "entropy",
        "printable_ratio",
        "fingerprint",
        "novelty",
        "changed_offsets",
        "strings",
    ]

    def __init__(self, root: Path, endpoint: Endpoint, interface: str, tshark_path: str) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = root / timestamp
        self.path.mkdir(parents=True, exist_ok=False)
        self.endpoint = endpoint
        self.interface = interface
        self.tshark_path = tshark_path
        self._packet_file = (self.path / "packets.jsonl").open("a", encoding="utf-8", buffering=1)
        self._marker_file = (self.path / "markers.jsonl").open("a", encoding="utf-8", buffering=1)
        self._analysis_file = (self.path / "event_analysis.jsonl").open("a", encoding="utf-8", buffering=1)
        self._csv_handle = (self.path / "packets.csv").open("a", newline="", encoding="utf-8-sig", buffering=1)
        self._csv = csv.DictWriter(self._csv_handle, fieldnames=self.CSV_FIELDS)
        self._csv.writeheader()
        self._lock = threading.RLock()
        self._write_session_metadata()

    def _write_session_metadata(self) -> None:
        metadata = {
            "created_at": utc_now().isoformat(),
            "mode": "passive_read_only",
            "endpoint": asdict(self.endpoint),
            "interface": self.interface,
            "tshark_path": self.tshark_path,
            "format_version": 1,
            "notes": [
                "Payloads are raw TCP segment payloads, not guaranteed application messages.",
                "The protocol may be fragmented, compressed, encoded, or encrypted.",
            ],
        }
        (self.path / "session.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def write_packet(self, packet: PacketRecord) -> None:
        payload = packet.to_json_dict()
        with self._lock:
            self._packet_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._csv.writerow(
                {
                    "timestamp_iso": payload["timestamp_iso"],
                    "direction": packet.direction,
                    "source": f"{packet.source_ip}:{packet.source_port}",
                    "destination": f"{packet.destination_ip}:{packet.destination_port}",
                    "length": packet.length,
                    "entropy": f"{packet.entropy:.3f}",
                    "printable_ratio": f"{packet.printable:.3f}",
                    "fingerprint": packet.fingerprint,
                    "novelty": f"{packet.novelty:.3f}",
                    "changed_offsets": " ".join(f"0x{offset:X}" for offset in packet.changed_offsets),
                    "strings": " | ".join(packet.strings),
                }
            )

    def write_marker(self, marker: MarkerRecord) -> None:
        with self._lock:
            self._marker_file.write(json.dumps(marker.to_json_dict(), ensure_ascii=False) + "\n")

    def write_analysis(self, analysis: EventAnalysis) -> None:
        with self._lock:
            self._analysis_file.write(json.dumps(analysis.to_json_dict(), ensure_ascii=False) + "\n")

    def close(self) -> None:
        with self._lock:
            for handle in (self._packet_file, self._marker_file, self._analysis_file, self._csv_handle):
                try:
                    handle.flush()
                    handle.close()
                except Exception:
                    pass


def default_session_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "KageLink PC Agent" / "data" / "dream_daemon_observer"
    return Path(__file__).resolve().parent / "dream_daemon_observer_data"
