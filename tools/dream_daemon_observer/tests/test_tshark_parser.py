from dream_daemon_observer import TsharkCapture, TsharkInterface
from observer_core import Endpoint


def test_tshark_row_is_classified_as_inbound() -> None:
    endpoint = Endpoint(
        pid=1,
        process_name="dreamseeker.exe",
        local_ip="192.0.2.10",
        local_port=50000,
        remote_ip="203.0.113.20",
        remote_port=12345,
    )
    capture = TsharkCapture(
        tshark_path="tshark",
        interface=TsharkInterface("1", "Ethernet"),
        endpoint=endpoint,
        on_packet=lambda _packet: None,
        on_error=lambda _message: None,
        on_stopped=lambda _code: None,
    )
    row = (
        "7\t1720000000.250000\t203.0.113.20\t\t12345\t"
        "192.0.2.10\t\t50000\t100\t200\t4\t1\t01:02:03:04"
    )
    packet = capture._parse_line(row)
    assert packet is not None
    assert packet.direction == "IN"
    assert packet.payload == b"\x01\x02\x03\x04"
    assert packet.frame_number == 7
