from __future__ import annotations

import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from capture_runtime import (
    TsharkCapture,
    TsharkInterface,
    discover_endpoints,
    find_dumpcap,
    find_tshark,
    list_tshark_interfaces,
)
from observer_core import (
    Endpoint,
    MarkerRecord,
    PacketHistory,
    PacketRecord,
    SessionWriter,
    default_session_root,
    format_hex_ascii,
)

APP_TITLE = "KageLink · Dream Daemon Observer"
MAX_ROWS = 5_000

TEXT = {
    "pt-BR": {
        "process": "Processo",
        "refresh": "Atualizar conexões",
        "connection": "Conexão",
        "interface": "Interface",
        "start": "Iniciar captura",
        "stop": "Parar",
        "folder": "Abrir sessão",
        "top": "Sempre visível",
        "out": "Mostrar saída",
        "pause": "Pausar tabela",
        "markers": "Marcadores",
        "note": "Nota opcional",
        "enemy": "Inimigo apareceu",
        "enemy_move": "Inimigo se moveu",
        "player_move": "Jogador se moveu",
        "attack": "Golpe / ataque",
        "map": "Mapa mudou",
        "custom": "Personalizado",
        "details": "Pacote selecionado",
        "analysis": "Correlação do evento",
        "ready": "Abra o jogo e atualize as conexões.",
        "no_endpoint": "Nenhuma conexão TCP ativa do Dream Seeker foi encontrada.",
        "no_tshark": "TShark não encontrado. Instale Wireshark com TShark e Npcap.",
        "choose_endpoint": "Selecione uma conexão do Dream Seeker.",
        "choose_interface": "Selecione a interface Ethernet ou Wi-Fi ativa.",
        "capturing": "Captura passiva iniciada.",
        "stopped": "Captura encerrada.",
        "custom_title": "Marcador personalizado",
        "custom_question": "Digite o nome curto do evento:",
        "wait": "Marcador registrado. Aguardando os pacotes posteriores…",
        "passive": "Somente leitura: não injeta, não altera pacotes e não envia comandos ao jogo.",
        "language": "Idioma",
    },
    "en-US": {
        "process": "Process",
        "refresh": "Refresh connections",
        "connection": "Connection",
        "interface": "Interface",
        "start": "Start capture",
        "stop": "Stop",
        "folder": "Open session",
        "top": "Always on top",
        "out": "Show outbound",
        "pause": "Pause table",
        "markers": "Markers",
        "note": "Optional note",
        "enemy": "Enemy appeared",
        "enemy_move": "Enemy moved",
        "player_move": "Player moved",
        "attack": "Skill / attack",
        "map": "Map changed",
        "custom": "Custom",
        "details": "Selected packet",
        "analysis": "Event correlation",
        "ready": "Open the game and refresh connections.",
        "no_endpoint": "No active Dream Seeker TCP connection was found.",
        "no_tshark": "TShark not found. Install Wireshark with TShark and Npcap.",
        "choose_endpoint": "Select a Dream Seeker connection.",
        "choose_interface": "Select the active Ethernet or Wi-Fi interface.",
        "capturing": "Passive capture started.",
        "stopped": "Capture stopped.",
        "custom_title": "Custom marker",
        "custom_question": "Enter a short event name:",
        "wait": "Marker recorded. Waiting for following packets…",
        "passive": "Read-only: does not inject, modify packets, or send game commands.",
        "language": "Language",
    },
}


class ObserverApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1280x780")
        root.minsize(980, 640)

        self.language = tk.StringVar(value="pt-BR")
        self.process_name = tk.StringVar(value="dreamseeker.exe")
        self.endpoint_value = tk.StringVar()
        self.interface_value = tk.StringVar()
        self.note = tk.StringVar()
        self.status = tk.StringVar()
        self.session_text = tk.StringVar(value="—")
        self.topmost = tk.BooleanVar(value=True)
        self.show_outbound = tk.BooleanVar(value=False)
        self.pause_table = tk.BooleanVar(value=False)

        self.tshark_path = find_tshark()
        self.dumpcap_path = find_dumpcap(self.tshark_path)
        self.endpoints: list[Endpoint] = []
        self.interfaces: list[TsharkInterface] = []
        self.capture: Optional[TsharkCapture] = None
        self.writer: Optional[SessionWriter] = None
        self.session_path: Optional[Path] = None
        self.history = PacketHistory()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.rows: dict[str, PacketRecord] = {}
        self.counts = {"all": 0, "in": 0, "out": 0, "bytes": 0, "markers": 0}
        self.closing = False

        self._build()
        self._translate()
        self._set_topmost()
        self._load_interfaces()
        self.refresh_connections()
        root.after(75, self._drain)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<F12>", lambda _event: self.close())

    def tr(self, key: str) -> str:
        return TEXT[self.language.get()][key]

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        controls = ttk.Frame(outer)
        controls.pack(fill="x")
        self.process_label = ttk.Label(controls)
        self.process_label.pack(side="left")
        ttk.Entry(controls, textvariable=self.process_name, width=18).pack(side="left", padx=5)
        self.refresh_button = ttk.Button(controls, command=self.refresh_connections)
        self.refresh_button.pack(side="left", padx=(0, 10))
        self.endpoint_label = ttk.Label(controls)
        self.endpoint_label.pack(side="left")
        self.endpoint_combo = ttk.Combobox(controls, textvariable=self.endpoint_value, state="readonly", width=45)
        self.endpoint_combo.pack(side="left", fill="x", expand=True, padx=5)

        second = ttk.Frame(outer)
        second.pack(fill="x", pady=(6, 0))
        self.interface_label = ttk.Label(second)
        self.interface_label.pack(side="left")
        self.interface_combo = ttk.Combobox(second, textvariable=self.interface_value, state="readonly", width=50)
        self.interface_combo.pack(side="left", fill="x", expand=True, padx=5)
        self.start_button = ttk.Button(second, command=self.start_capture)
        self.start_button.pack(side="left", padx=3)
        self.stop_button = ttk.Button(second, command=self.stop_capture, state="disabled")
        self.stop_button.pack(side="left", padx=3)
        self.folder_button = ttk.Button(second, command=self.open_folder, state="disabled")
        self.folder_button.pack(side="left", padx=3)

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=6)
        self.top_check = ttk.Checkbutton(options, variable=self.topmost, command=self._set_topmost)
        self.top_check.pack(side="left")
        self.out_check = ttk.Checkbutton(options, variable=self.show_outbound)
        self.out_check.pack(side="left", padx=10)
        self.pause_check = ttk.Checkbutton(options, variable=self.pause_table)
        self.pause_check.pack(side="left")
        self.language_label = ttk.Label(options)
        self.language_label.pack(side="right", padx=(5, 0))
        language_combo = ttk.Combobox(options, textvariable=self.language, values=("pt-BR", "en-US"), state="readonly", width=8)
        language_combo.pack(side="right")
        language_combo.bind("<<ComboboxSelected>>", lambda _event: self._translate())

        self.stats_label = ttk.Label(outer, font=("Segoe UI", 10, "bold"))
        self.stats_label.pack(fill="x", pady=(0, 5))

        self.marker_box = ttk.LabelFrame(outer, padding=6)
        self.marker_box.pack(fill="x")
        self.marker_buttons: list[tuple[ttk.Button, str, str]] = []
        for key, marker in (
            ("enemy", "ENEMY_APPEARED"),
            ("enemy_move", "ENEMY_MOVED"),
            ("player_move", "PLAYER_MOVED"),
            ("attack", "ATTACK_OR_SKILL"),
            ("map", "MAP_CHANGED"),
        ):
            button = ttk.Button(self.marker_box, command=lambda value=marker: self.add_marker(value))
            button.pack(side="left", padx=(0, 4))
            self.marker_buttons.append((button, key, marker))
        self.custom_button = ttk.Button(self.marker_box, command=self.custom_marker)
        self.custom_button.pack(side="left", padx=(0, 10))
        self.note_label = ttk.Label(self.marker_box)
        self.note_label.pack(side="left")
        ttk.Entry(self.marker_box, textvariable=self.note).pack(side="left", fill="x", expand=True, padx=5)

        pane = ttk.Panedwindow(outer, orient="vertical")
        pane.pack(fill="both", expand=True, pady=(6, 0))
        table_frame = ttk.Frame(pane)
        pane.add(table_frame, weight=3)
        columns = ("frame", "time", "dir", "length", "entropy", "ascii", "change", "fingerprint", "text")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        widths = (65, 105, 55, 65, 70, 65, 70, 105, 430)
        for name, width in zip(columns, widths):
            self.table.heading(name, text=name)
            self.table.column(name, width=width, stretch=name == "text")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self.show_packet)

        lower = ttk.Panedwindow(pane, orient="horizontal")
        pane.add(lower, weight=2)
        self.details_box = ttk.LabelFrame(lower, padding=4)
        self.analysis_box = ttk.LabelFrame(lower, padding=4)
        lower.add(self.details_box, weight=3)
        lower.add(self.analysis_box, weight=2)
        self.details = tk.Text(self.details_box, wrap="none", font=("Consolas", 10), state="disabled")
        self.details.pack(fill="both", expand=True)
        self.analysis = tk.Text(self.analysis_box, wrap="word", font=("Segoe UI", 10), state="disabled")
        self.analysis.pack(fill="both", expand=True)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(5, 0))
        self.passive_label = ttk.Label(footer)
        self.passive_label.pack(side="left")
        ttk.Label(footer, textvariable=self.session_text).pack(side="right")
        ttk.Label(outer, textvariable=self.status, anchor="w").pack(fill="x")

    def _translate(self) -> None:
        self.process_label.configure(text=self.tr("process"))
        self.refresh_button.configure(text=self.tr("refresh"))
        self.endpoint_label.configure(text=self.tr("connection"))
        self.interface_label.configure(text=self.tr("interface"))
        self.start_button.configure(text=self.tr("start"))
        self.stop_button.configure(text=self.tr("stop"))
        self.folder_button.configure(text=self.tr("folder"))
        self.top_check.configure(text=self.tr("top"))
        self.out_check.configure(text=self.tr("out"))
        self.pause_check.configure(text=self.tr("pause"))
        self.language_label.configure(text=self.tr("language"))
        self.marker_box.configure(text=self.tr("markers"))
        self.note_label.configure(text=self.tr("note"))
        for button, key, _marker in self.marker_buttons:
            button.configure(text=self.tr(key))
        self.custom_button.configure(text=self.tr("custom"))
        self.details_box.configure(text=self.tr("details"))
        self.analysis_box.configure(text=self.tr("analysis"))
        self.passive_label.configure(text=self.tr("passive"))
        if not self.capture or not self.capture.running:
            self.status.set(self.tr("ready"))
        self._update_stats()

    def _set_topmost(self) -> None:
        self.root.attributes("-topmost", bool(self.topmost.get()))

    def _load_interfaces(self) -> None:
        if not self.tshark_path:
            self.status.set(self.tr("no_tshark"))
            return
        try:
            self.interfaces = list_tshark_interfaces(self.tshark_path)
        except Exception as exc:
            self.status.set(str(exc))
            return
        values = [f"{item.identifier}. {item.label}" for item in self.interfaces]
        self.interface_combo["values"] = values
        if values:
            index = next((i for i, value in enumerate(values) if "loopback" not in value.lower()), 0)
            self.interface_combo.current(index)

    def refresh_connections(self) -> None:
        try:
            self.endpoints = discover_endpoints(self.process_name.get())
        except Exception as exc:
            self.status.set(str(exc))
            return
        values = [item.label for item in self.endpoints]
        self.endpoint_combo["values"] = values
        if values:
            self.endpoint_combo.current(0)
            self.status.set(f"{len(values)} TCP connection(s)")
        else:
            self.endpoint_value.set("")
            self.status.set(self.tr("no_endpoint"))

    def _selected_endpoint(self) -> Optional[Endpoint]:
        index = self.endpoint_combo.current()
        return self.endpoints[index] if 0 <= index < len(self.endpoints) else None

    def _selected_interface(self) -> Optional[TsharkInterface]:
        index = self.interface_combo.current()
        return self.interfaces[index] if 0 <= index < len(self.interfaces) else None

    def start_capture(self) -> None:
        if not self.tshark_path:
            messagebox.showerror(APP_TITLE, self.tr("no_tshark"), parent=self.root)
            return
        endpoint = self._selected_endpoint()
        interface = self._selected_interface()
        if endpoint is None:
            messagebox.showwarning(APP_TITLE, self.tr("choose_endpoint"), parent=self.root)
            return
        if interface is None:
            messagebox.showwarning(APP_TITLE, self.tr("choose_interface"), parent=self.root)
            return
        self.writer = SessionWriter(default_session_root(), endpoint, interface.label, self.tshark_path)
        self.session_path = self.writer.path
        self.session_text.set(str(self.session_path))
        self.folder_button.configure(state="normal")
        self.capture = TsharkCapture(
            self.tshark_path,
            interface,
            endpoint,
            lambda packet: self.events.put(("packet", packet)),
            lambda error: self.events.put(("error", error)),
            lambda code: self.events.put(("stopped", code)),
            self.dumpcap_path,
            self.session_path / "capture.pcapng",
        )
        self.capture.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.refresh_button.configure(state="disabled")
        self.status.set(self.tr("capturing"))

    def stop_capture(self) -> None:
        if self.capture:
            self.capture.stop()
        self._capture_stopped()

    def _capture_stopped(self) -> None:
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.refresh_button.configure(state="normal")
        self.status.set(self.tr("stopped"))
        if self.writer:
            self.writer.close()
            self.writer = None

    def open_folder(self) -> None:
        if not self.session_path:
            return
        if os.name == "nt":
            os.startfile(self.session_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(self.session_path)])
        else:
            subprocess.Popen(["xdg-open", str(self.session_path)])

    def custom_marker(self) -> None:
        value = simpledialog.askstring(self.tr("custom_title"), self.tr("custom_question"), parent=self.root)
        if value:
            self.add_marker(value.strip().upper().replace(" ", "_"))

    def add_marker(self, label: str) -> None:
        if not self.capture or not self.capture.running:
            messagebox.showwarning(APP_TITLE, self.tr("start"), parent=self.root)
            return
        marker = MarkerRecord(time.time(), label, self.note.get().strip())
        self.note.set("")
        self.counts["markers"] += 1
        self._update_stats()
        if self.writer:
            self.writer.write_marker(marker)
        self._set_text(self.analysis, self.tr("wait"))
        self.root.after(1700, lambda: self._analyze(marker))

    def _analyze(self, marker: MarkerRecord) -> None:
        result = self.history.analyze_marker(marker)
        if self.writer:
            self.writer.write_analysis(result)
        self._set_text(self.analysis, result.render_text(self.language.get()))

    def _drain(self) -> None:
        if self.closing:
            return
        for _ in range(300):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "packet":
                self._packet(value)  # type: ignore[arg-type]
            elif kind == "error":
                self.status.set(str(value))
            elif kind == "stopped":
                self._capture_stopped()
        self.root.after(75, self._drain)

    def _packet(self, packet: PacketRecord) -> None:
        packet = self.history.append(packet)
        if self.writer:
            self.writer.write_packet(packet)
        self.counts["all"] += 1
        self.counts["bytes"] += packet.length
        if packet.direction == "IN":
            self.counts["in"] += 1
        elif packet.direction == "OUT":
            self.counts["out"] += 1
        self._update_stats()
        if self.pause_table.get() or packet.direction == "OTHER":
            return
        if packet.direction == "OUT" and not self.show_outbound.get():
            return
        local = time.strftime("%H:%M:%S", time.localtime(packet.timestamp))
        milliseconds = int(packet.timestamp % 1 * 1000)
        item = self.table.insert(
            "",
            "end",
            values=(
                packet.frame_number or self.counts["all"],
                f"{local}.{milliseconds:03d}",
                packet.direction,
                packet.length,
                f"{packet.entropy:.2f}",
                f"{packet.printable * 100:.0f}%",
                f"{packet.novelty * 100:.0f}%",
                packet.fingerprint,
                " | ".join(packet.strings)[:300],
            ),
        )
        self.rows[item] = packet
        children = self.table.get_children()
        if len(children) > MAX_ROWS:
            for old in children[:250]:
                self.rows.pop(old, None)
                self.table.delete(old)
        self.table.yview_moveto(1.0)

    def _update_stats(self) -> None:
        if self.language.get() == "en-US":
            text = (
                f"Packets: {self.counts['all']:,}   Inbound: {self.counts['in']:,}   "
                f"Outbound: {self.counts['out']:,}   Bytes: {self.counts['bytes']:,}   "
                f"Markers: {self.counts['markers']:,}"
            )
        else:
            text = (
                f"Pacotes: {self.counts['all']:,}   Entrada: {self.counts['in']:,}   "
                f"Saída: {self.counts['out']:,}   Bytes: {self.counts['bytes']:,}   "
                f"Marcadores: {self.counts['markers']:,}"
            )
        self.stats_label.configure(text=text)

    def show_packet(self, _event: object = None) -> None:
        selected = self.table.selection()
        if not selected or selected[0] not in self.rows:
            return
        packet = self.rows[selected[0]]
        header = (
            f"{packet.source_ip}:{packet.source_port} → {packet.destination_ip}:{packet.destination_port}\n"
            f"direction={packet.direction} length={packet.length} seq={packet.sequence} "
            f"ack={packet.acknowledgment} stream={packet.stream_id}\n"
            f"entropy={packet.entropy:.3f} printable={packet.printable * 100:.1f}% "
            f"change={packet.novelty * 100:.1f}% fingerprint={packet.fingerprint}\n"
            f"changed_offsets={','.join(hex(value) for value in packet.changed_offsets) or '—'}\n"
            f"strings={' | '.join(packet.strings) or '—'}\n\n"
        )
        self._set_text(self.details, header + format_hex_ascii(packet.payload, set(packet.changed_offsets)))

    @staticmethod
    def _set_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        if self.capture:
            self.capture.stop()
        if self.writer:
            self.writer.close()
        self.root.destroy()
