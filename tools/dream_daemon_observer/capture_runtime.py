from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import psutil

from observer_core import Endpoint, PacketRecord


@dataclass(slots=True)
class TsharkInterface:
    identifier: str
    label: str


def find_tshark() -> Optional[str]:
    candidates = [
        shutil.which("tshark"),
        os.environ.get("TSHARK_PATH"),
        r"C:\Program Files\Wireshark\tshark.exe",
        r"C:\Program Files (x86)\Wireshark\tshark.exe",
    ]
    return next((str(Path(path)) for path in candidates if path and Path(path).is_file()), None)


def find_dumpcap(tshark_path: Optional[str]) -> Optional[str]:
    candidates = [
        shutil.which("dumpcap"),
        str(Path(tshark_path).with_name("dumpcap.exe")) if tshark_path else None,
        r"C:\Program Files\Wireshark\dumpcap.exe",
        r"C:\Program Files (x86)\Wireshark\dumpcap.exe",
    ]
    return next((str(Path(path)) for path in candidates if path and Path(path).is_file()), None)


def list_tshark_interfaces(tshark_path: str) -> list[TsharkInterface]:
    completed = subprocess.run(
        [tshark_path, "-D"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "TShark -D failed")
    interfaces: list[TsharkInterface] = []
    for line in completed.stdout.splitlines():
        if "." not in line:
            continue
        identifier, label = line.strip().split(".", 1)
        interfaces.append(TsharkInterface(identifier.strip(), label.strip()))
    return interfaces


def discover_endpoints(process_name: str) -> list[Endpoint]:
    target = process_name.lower().strip().removesuffix(".exe")
    processes: dict[int, str] = {}
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = str(process.info.get("name") or "")
            if name.lower().removesuffix(".exe") == target:
                processes[int(process.info["pid"])] = name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    endpoints: list[Endpoint] = []
    for pid, name in processes.items():
        try:
            connections = psutil.Process(pid).net_connections(kind="tcp")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            connections = [item for item in psutil.net_connections(kind="tcp") if item.pid == pid]
        for connection in connections:
            if not connection.laddr or not connection.raddr:
                continue
            if str(connection.status) not in {"ESTABLISHED", str(psutil.CONN_ESTABLISHED)}:
                continue
            endpoints.append(
                Endpoint(
                    pid=pid,
                    process_name=name,
                    local_ip=str(connection.laddr.ip),
                    local_port=int(connection.laddr.port),
                    remote_ip=str(connection.raddr.ip),
                    remote_port=int(connection.raddr.port),
                    status=str(connection.status),
                )
            )
    unique = {
        (item.pid, item.local_ip, item.local_port, item.remote_ip, item.remote_port): item
        for item in endpoints
    }
    return sorted(unique.values(), key=lambda item: (item.pid, item.remote_ip, item.remote_port))


class TsharkCapture:
    def __init__(
        self,
        tshark_path: str,
        interface: TsharkInterface,
        endpoint: Endpoint,
        on_packet: Callable[[PacketRecord], None],
        on_error: Callable[[str], None],
        on_stopped: Callable[[int], None],
        dumpcap_path: Optional[str] = None,
        pcap_path: Optional[Path] = None,
    ) -> None:
        self.tshark_path = tshark_path
        self.interface = interface
        self.endpoint = endpoint
        self.on_packet = on_packet
        self.on_error = on_error
        self.on_stopped = on_stopped
        self.dumpcap_path = dumpcap_path
        self.pcap_path = pcap_path
        self._process: Optional[subprocess.Popen[str]] = None
        self._dumpcap: Optional[subprocess.Popen[str]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dream-daemon-capture")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for process in (self._process, self._dumpcap):
            if process is None or process.poll() is not None:
                continue
            try:
                process.terminate()
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
            except OSError:
                pass

    def _popen_options(self) -> dict:
        if os.name != "nt":
            return {}
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": startup, "creationflags": subprocess.CREATE_NO_WINDOW}

    def _run(self) -> None:
        capture_filter = f"host {self.endpoint.remote_ip} and tcp port {self.endpoint.remote_port}"
        options = self._popen_options()
        if self.dumpcap_path and self.pcap_path:
            try:
                self._dumpcap = subprocess.Popen(
                    [
                        self.dumpcap_path,
                        "-q",
                        "-i",
                        self.interface.identifier,
                        "-f",
                        capture_filter,
                        "-s",
                        "0",
                        "-w",
                        str(self.pcap_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **options,
                )
            except OSError as exc:
                self.on_error(f"PCAP recorder unavailable: {exc}")

        fields = [
            "frame.number",
            "frame.time_epoch",
            "ip.src",
            "ipv6.src",
            "tcp.srcport",
            "ip.dst",
            "ipv6.dst",
            "tcp.dstport",
            "tcp.seq",
            "tcp.ack",
            "tcp.len",
            "tcp.stream",
            "tcp.payload",
        ]
        command = [
            self.tshark_path,
            "-l",
            "-n",
            "-i",
            self.interface.identifier,
            "-f",
            capture_filter,
            "-Y",
            "tcp.payload",
            "-T",
            "fields",
            "-E",
            "separator=\t",
            "-E",
            "occurrence=f",
        ]
        for field in fields:
            command.extend(["-e", field])

        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **options,
            )
        except OSError as exc:
            self.on_error(str(exc))
            self.on_stopped(-1)
            return

        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                if self._stop.is_set():
                    break
                try:
                    packet = self._parse_line(line.rstrip("\r\n"))
                    if packet is not None:
                        self.on_packet(packet)
                except Exception as exc:
                    self.on_error(f"Unable to parse TShark row: {exc}")
        finally:
            code = self._process.poll()
            if code is None:
                code = self._process.wait()
            stderr = self._process.stderr.read().strip() if self._process.stderr else ""
            if not self._stop.is_set() and code != 0 and stderr:
                self.on_error(stderr)
            if self._dumpcap and self._dumpcap.poll() is None:
                try:
                    self._dumpcap.terminate()
                    self._dumpcap.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        self._dumpcap.kill()
                    except OSError:
                        pass
            self._process = None
            self.on_stopped(code)

    def _parse_line(self, line: str) -> Optional[PacketRecord]:
        values = line.split("\t")
        values.extend([""] * (13 - len(values)))
        (
            frame,
            timestamp,
            ipv4_source,
            ipv6_source,
            source_port,
            ipv4_destination,
            ipv6_destination,
            destination_port,
            sequence,
            acknowledgment,
            _length,
            stream,
            payload_hex,
        ) = values[:13]
        payload_hex = payload_hex.replace(":", "").replace(" ", "")
        if not payload_hex:
            return None
        source_ip = ipv4_source or ipv6_source
        destination_ip = ipv4_destination or ipv6_destination
        source_port_number = int(source_port)
        destination_port_number = int(destination_port)
        if (
            source_ip == self.endpoint.remote_ip
            and source_port_number == self.endpoint.remote_port
            and destination_port_number == self.endpoint.local_port
        ):
            direction = "IN"
        elif (
            destination_ip == self.endpoint.remote_ip
            and destination_port_number == self.endpoint.remote_port
            and source_port_number == self.endpoint.local_port
        ):
            direction = "OUT"
        else:
            direction = "OTHER"
        return PacketRecord(
            timestamp=float(timestamp),
            source_ip=source_ip,
            source_port=source_port_number,
            destination_ip=destination_ip,
            destination_port=destination_port_number,
            sequence=int(sequence) if sequence else None,
            acknowledgment=int(acknowledgment) if acknowledgment else None,
            payload=bytes.fromhex(payload_hex),
            direction=direction,
            frame_number=int(frame) if frame else None,
            stream_id=int(stream) if stream else None,
        )
