from observer_core import (
    MarkerRecord,
    PacketHistory,
    PacketRecord,
    changed_offsets,
    extract_strings,
    normalized_difference,
    printable_ratio,
    shannon_entropy,
)


def packet(timestamp: float, payload: bytes, direction: str = "IN") -> PacketRecord:
    return PacketRecord(
        timestamp=timestamp,
        source_ip="203.0.113.10" if direction == "IN" else "192.0.2.5",
        source_port=12345 if direction == "IN" else 54321,
        destination_ip="192.0.2.5" if direction == "IN" else "203.0.113.10",
        destination_port=54321 if direction == "IN" else 12345,
        sequence=1,
        acknowledgment=1,
        payload=payload,
        direction=direction,
    )


def test_payload_metrics_are_deterministic() -> None:
    payload = b"MOVE enemy 12 34"
    assert printable_ratio(payload) == 1.0
    assert shannon_entropy(payload) > 2.0
    assert extract_strings(payload) == ["MOVE enemy 12 34"]


def test_changed_offsets_and_difference() -> None:
    assert changed_offsets(b"\x01\x02\x03", b"\x01\x09\x03") == [1]
    assert normalized_difference(b"abc", b"axc") == 1 / 3


def test_history_compares_same_length_payloads() -> None:
    history = PacketHistory()
    first = history.append(packet(1.0, b"\x01\x02\x03"))
    second = history.append(packet(2.0, b"\x01\x09\x03"))
    assert first.changed_offsets == []
    assert second.changed_offsets == [1]
    assert second.novelty == 1 / 3


def test_event_analysis_finds_event_only_signature() -> None:
    history = PacketHistory()
    history.append(packet(1.0, b"idle"))
    history.append(packet(2.0, b"idle"))
    history.append(packet(4.2, b"enemy-visible"))
    history.append(packet(4.4, b"enemy-visible"))
    marker = MarkerRecord(timestamp=4.0, label="ENEMY_APPEARED")
    analysis = history.analyze_marker(marker, before_seconds=0.1, after_seconds=0.6)
    assert analysis.inbound_packets == 2
    assert analysis.event_only_fingerprints
    assert analysis.top_strings[0][0] == "enemy-visible"


def test_event_analysis_prefers_inbound_patterns() -> None:
    history = PacketHistory()
    history.append(packet(1.0, b"idle-in", "IN"))
    history.append(packet(1.1, b"command-out", "OUT"))
    history.append(packet(4.1, b"enemy-in", "IN"))
    history.append(packet(4.2, b"command-out-new", "OUT"))
    marker = MarkerRecord(timestamp=4.0, label="ENEMY_APPEARED")
    analysis = history.analyze_marker(marker, before_seconds=0.1, after_seconds=0.4)
    assert analysis.inbound_packets == 1
    assert analysis.outbound_packets == 1
    assert analysis.top_strings[0][0] == "enemy-in"
