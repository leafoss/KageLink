from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from ..storage import JsonRepository
from .engine import MappingObserverEngine, MappingSnapshot
from .window_capture import WindowBounds, WindowsClientCapture


class MappingObserverDebugWindow:
    def __init__(
        self,
        engine: MappingObserverEngine,
        capture: WindowsClientCapture,
        repository: JsonRepository,
        fps: float = 10.0,
        language: str = "pt-BR",
    ) -> None:
        self.engine = engine
        self.capture = capture
        self.repository = repository
        self.fps = max(1.0, min(30.0, fps))
        self.language = language
        self.root = tk.Tk()
        self.root.title("Kage Mapping Lab — PR 24")
        self.root.geometry("1480x900")
        self.root.minsize(1100, 720)
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stop = threading.Event()
        self._running = False
        self._raw_photo: Any | None = None
        self._processed_photo: Any | None = None
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(40, self._poll)

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        header = ttk.Frame(self.root, padding=8)
        header.grid(row=0, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="Observer / Observador | PAUSED")
        ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(header, text="Start / Iniciar", command=self._start).pack(side="right", padx=4)
        ttk.Button(header, text="Pause / Pausar", command=self._pause).pack(side="right", padx=4)
        ttk.Button(header, text="Save / Salvar", command=self._save).pack(side="right", padx=4)
        ttk.Button(header, text="Reset map / Zerar mapa", command=self._reset).pack(side="right", padx=4)

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        visual = ttk.Frame(body)
        visual.columnconfigure(0, weight=1)
        visual.columnconfigure(1, weight=1)
        visual.rowconfigure(0, weight=1)
        original_frame = ttk.LabelFrame(visual, text="Original game client / Cliente original", padding=6)
        original_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        original_frame.columnconfigure(0, weight=1)
        original_frame.rowconfigure(0, weight=1)
        self.raw_label = ttk.Label(original_frame, anchor="center")
        self.raw_label.grid(sticky="nsew")
        processed_frame = ttk.LabelFrame(visual, text="Motion + 64 px grid / Movimento + grade 64 px", padding=6)
        processed_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        processed_frame.columnconfigure(0, weight=1)
        processed_frame.rowconfigure(0, weight=1)
        self.processed_label = ttk.Label(processed_frame, anchor="center")
        self.processed_label.grid(sticky="nsew")
        body.add(visual, weight=3)

        details = ttk.Frame(body)
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=3)
        details.rowconfigure(1, weight=2)
        details.rowconfigure(2, weight=2)
        map_frame = ttk.LabelFrame(details, text="Relative tile map / Mapa relativo", padding=6)
        map_frame.grid(row=0, column=0, sticky="nsew")
        map_frame.columnconfigure(0, weight=1)
        map_frame.rowconfigure(0, weight=1)
        self.map_text = tk.Text(map_frame, font=("Consolas", 13), wrap="none", state="disabled")
        self.map_text.grid(sticky="nsew")
        telemetry_frame = ttk.LabelFrame(details, text="Telemetry / Telemetria", padding=6)
        telemetry_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        telemetry_frame.columnconfigure(0, weight=1)
        telemetry_frame.rowconfigure(0, weight=1)
        self.telemetry_text = tk.Text(telemetry_frame, font=("Consolas", 10), wrap="word", state="disabled")
        self.telemetry_text.grid(sticky="nsew")
        events_frame = ttk.LabelFrame(details, text="Events / Eventos", padding=6)
        events_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        events_frame.columnconfigure(0, weight=1)
        events_frame.rowconfigure(0, weight=1)
        self.events_text = tk.Text(events_frame, font=("Consolas", 9), wrap="word", state="disabled")
        self.events_text.grid(sticky="nsew")
        body.add(details, weight=2)

    def _start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop.clear()
        self.status_var.set("Observer / Observador | RUNNING")
        threading.Thread(target=self._capture_loop, name="mapping-observer", daemon=True).start()

    def _pause(self) -> None:
        self._running = False
        self._stop.set()
        self.status_var.set("Observer / Observador | PAUSED")

    def _capture_loop(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                frame, bounds = self.capture.capture()
                snapshot = self.engine.process_frame(frame)
                self._queue.put(("snapshot", (snapshot, bounds)))
            except Exception as exc:
                self._queue.put(("error", str(exc)))
                time.sleep(min(1.0, interval * 4))
            remaining = interval - (time.perf_counter() - started)
            if remaining > 0:
                time.sleep(remaining)

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "snapshot":
                    snapshot, bounds = payload
                    self._render(snapshot, bounds)
                else:
                    self.status_var.set(f"Observer / Observador | WAITING | {payload}")
                    self._append_event(f"ERROR: {payload}")
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def _render(self, snapshot: MappingSnapshot, bounds: WindowBounds) -> None:
        self._raw_photo = self._photo(snapshot.raw_frame, self.raw_label)
        self._processed_photo = self._photo(snapshot.processed_frame, self.processed_label)
        self.raw_label.configure(image=self._raw_photo)
        self.processed_label.configure(image=self._processed_photo)
        self._set_text(self.map_text, snapshot.map_ascii)
        motion = snapshot.motion
        odometry = snapshot.odometry
        position = self.engine.odometry.position
        telemetry = "\n".join([
            f"Window / Janela: {bounds.title}",
            f"Client / Cliente: {bounds.width}x{bounds.height} at {bounds.left},{bounds.top}",
            f"Foreground / Em foco: {bounds.foreground}",
            f"Frame: {snapshot.frame_index}",
            f"Region / Região: {self.engine.region_map.region_id}",
            f"Camera mode / Modo câmera: {self.engine.odometry.camera_mode}",
            f"Tile / Célula: {self.engine.region_map.tile_size_px}x{self.engine.region_map.tile_size_px} px",
            f"Screen shift / Movimento tela: ({motion.screen_dx_px:+.2f}, {motion.screen_dy_px:+.2f}) px",
            f"Correlation / Correlação: {motion.response:.2%} [{motion.reason}]",
            f"Residual / Resíduo: ({self.engine.odometry.residual_x_px:+.2f}, {self.engine.odometry.residual_y_px:+.2f}) px",
            f"Map cell / Célula mapa: ({position.x}, {position.y})",
            f"Accepted / Aceito: {bool(odometry and odometry.accepted)}",
        ])
        self._set_text(self.telemetry_text, telemetry)
        if odometry and odometry.traversed:
            self._append_event(
                f"frame={snapshot.frame_index} tile=({position.x},{position.y}) "
                f"step=({odometry.tile_dx:+d},{odometry.tile_dy:+d}) confidence={motion.response:.2f}"
            )
        self.status_var.set(f"Observer | RUNNING | tile=({position.x},{position.y}) | confidence={motion.response:.0%}")

    def _photo(self, bgr_frame: Any, widget: ttk.Label) -> Any:
        import cv2
        from PIL import Image, ImageTk

        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        image.thumbnail((max(420, widget.winfo_width()), max(300, widget.winfo_height())), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _append_event(self, value: str) -> None:
        self.events_text.configure(state="normal")
        self.events_text.insert("end", value + "\n")
        self.events_text.see("end")
        self.events_text.configure(state="disabled")

    def _save(self) -> None:
        path = self.repository.save_mapping_state(self.engine.region_map.region_id, self.engine.export_state())
        self._append_event(f"saved={path}")
        messagebox.showinfo("Kage Mapping Lab", f"Map saved / Mapa salvo:\n{path}")

    def _reset(self) -> None:
        if messagebox.askyesno("Kage Mapping Lab", "Reset the current relative map? / Zerar o mapa relativo atual?"):
            self.engine.reset()
            self._append_event("map reset / mapa zerado")

    def _close(self) -> None:
        self._pause()
        try:
            self._save_without_dialog()
        finally:
            self.capture.close()
            self.root.destroy()

    def _save_without_dialog(self) -> Path:
        path = self.repository.save_mapping_state(self.engine.region_map.region_id, self.engine.export_state())
        self._append_event(f"autosaved={path}")
        return path

    def run(self) -> None:
        self.root.mainloop()
