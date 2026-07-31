from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from ..simulator import SimulationResult, SimulationSnapshot, SimulatorEngine
from .ascii_renderer import render_ascii


class DebugWindow:
    """Desktop debug window for the independent simulator.

    The UI intentionally uses only the Python standard library so the first PR 24
    milestone is easy to run from PowerShell. Real capture panels are reserved for
    the Windows/BYOND validation phase and do not silently pretend to be active.
    """

    def __init__(self, engine: SimulatorEngine, language: str = "pt-BR", step_delay: float = 0.08) -> None:
        self.engine = engine
        self.language = language
        self.step_delay = step_delay
        self.root = tk.Tk()
        self.root.title("Kage Navigation Lab — PR 24")
        self.root.geometry("1280x800")
        self.root.minsize(960, 640)
        self._queue: queue.Queue[SimulationSnapshot | SimulationResult] = queue.Queue()
        self._build()

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=1)
        header = ttk.Frame(self.root, padding=8)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.status_var = tk.StringVar(value="Simulator | IDLE")
        ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(header, text="Start / Iniciar", command=self._start).pack(side="right")

        map_frame = ttk.LabelFrame(self.root, text="Local map / Mapa local", padding=8)
        map_frame.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(8, 4), pady=(0, 8))
        map_frame.rowconfigure(0, weight=1)
        map_frame.columnconfigure(0, weight=1)
        self.map_text = tk.Text(map_frame, font=("Consolas", 16), wrap="none", state="disabled")
        self.map_text.grid(sticky="nsew")

        telemetry = ttk.LabelFrame(self.root, text="Telemetry / Telemetria", padding=8)
        telemetry.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=(0, 4))
        telemetry.rowconfigure(0, weight=1)
        telemetry.columnconfigure(0, weight=1)
        self.telemetry_text = tk.Text(telemetry, font=("Consolas", 10), wrap="word", state="disabled")
        self.telemetry_text.grid(sticky="nsew")

        events = ttk.LabelFrame(self.root, text="Decisions and events / Decisões e eventos", padding=8)
        events.grid(row=2, column=1, sticky="nsew", padx=(4, 8), pady=(4, 8))
        events.rowconfigure(0, weight=1)
        events.columnconfigure(0, weight=1)
        self.events_text = tk.Text(events, font=("Consolas", 9), wrap="word", state="disabled")
        self.events_text.grid(sticky="nsew")
        self.root.after(40, self._poll)

    def _start(self) -> None:
        if any(thread.name == "navigation-simulator" and thread.is_alive() for thread in threading.enumerate()):
            return
        thread = threading.Thread(target=self._run, name="navigation-simulator", daemon=True)
        thread.start()

    def _run(self) -> None:
        result = self.engine.run(on_snapshot=self._publish)
        self._queue.put(result)

    def _publish(self, snapshot: SimulationSnapshot) -> None:
        self._queue.put(snapshot)
        time.sleep(self.step_delay)

    def _poll(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                if isinstance(item, SimulationSnapshot):
                    self._render_snapshot(item)
                else:
                    self.status_var.set(f"Simulator | {item.outcome.upper()} | steps={item.steps}")
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _render_snapshot(self, snapshot: SimulationSnapshot) -> None:
        self.status_var.set(f"Simulator | {snapshot.state.value} | step={snapshot.step}")
        self._set_text(self.map_text, render_ascii(self.engine.grid, snapshot.actual_position, snapshot.goal, snapshot.path))
        decision = snapshot.decision
        telemetry = "\n".join([
            f"Mode / Modo: simulator",
            f"State / Estado: {snapshot.state.value}",
            f"Region / Região: {snapshot.pose.region_id}",
            f"Estimated pose / Posição estimada: ({snapshot.pose.x:.1f}, {snapshot.pose.y:.1f})",
            f"Actual pose / Posição real: ({snapshot.actual_position.x}, {snapshot.actual_position.y})",
            f"Destination / Destino: ({snapshot.goal.x}, {snapshot.goal.y})",
            f"Localization confidence / Confiança: {snapshot.pose.confidence:.0%}",
            f"Route confidence / Confiança rota: {decision.route_confidence:.0%}",
            f"Action / Ação: {decision.action}",
            f"Reason / Motivo: {decision.reason}",
            f"Recoveries / Recuperações: {snapshot.recoveries}",
        ])
        self._set_text(self.telemetry_text, telemetry)
        lines = [f"[{snapshot.step:03}] {decision.action}: {decision.reason}"]
        lines.extend(f"  - {event}" for event in snapshot.events)
        self.events_text.configure(state="normal")
        self.events_text.insert("end", "\n".join(lines) + "\n")
        self.events_text.see("end")
        self.events_text.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()
