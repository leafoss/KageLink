from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from ..storage import JsonRepository
from .grid_calibration import GridCalibration
from .window_capture import WindowsClientCapture


class _GridCaptureHotkey:
    """Passive F8 listener used only to request a frozen calibration frame."""

    def __init__(self, callback: Any) -> None:
        self.callback = callback
        self._listener: Any | None = None
        self._pressed = False

    def start(self) -> None:
        if self._listener is not None:
            return
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise RuntimeError("Missing dependency 'pynput'. Run setup_navigation.ps1 again.") from exc

        def on_press(key: Any) -> None:
            if key == keyboard.Key.f8 and not self._pressed:
                self._pressed = True
                self.callback()

        def on_release(key: Any) -> None:
            if key == keyboard.Key.f8:
                self._pressed = False

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        self._pressed = False
        if listener is not None:
            listener.stop()


class GridCalibrationWindow:
    """Frozen-frame square-grid editor designed for fullscreen game calibration."""

    def __init__(
        self,
        capture: WindowsClientCapture,
        repository: JsonRepository,
        region_id: str,
        language: str = "pt-BR",
    ) -> None:
        self.capture = capture
        self.repository = repository
        self.region_id = region_id
        self.language = language
        self.root = tk.Tk()
        self.root.title("Kage Grid Calibration Lab — PR 24")
        self.root.geometry("1420x880")
        self.root.minsize(1050, 680)
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._capture_lock = threading.Lock()
        self._raw_frame: Any | None = None
        self._photo: Any | None = None
        self._display_scale = 1.0
        self._display_left = 0.0
        self._display_top = 0.0
        self._display_width = 0
        self._display_height = 0
        self._hotkey = _GridCaptureHotkey(self._request_hotkey_capture)

        calibration = self._load_initial_calibration()
        self.tile_size_var = tk.IntVar(value=calibration.tile_size_px)
        self.offset_x_var = tk.IntVar(value=calibration.offset_x_px)
        self.offset_y_var = tk.IntVar(value=calibration.offset_y_px)
        self.thickness_var = tk.IntVar(value=calibration.line_thickness)
        self.opacity_var = tk.DoubleVar(value=calibration.line_opacity)
        self.status_var = tk.StringVar(
            value="Pressione F8 dentro do jogo para congelar uma captura / Press F8 in game to freeze a frame"
        )
        self.stats_var = tk.StringVar(value="Aguardando captura / Waiting for capture")

        self._build()
        self._bind_variables()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(50, self._poll)
        self.root.after(250, self._initial_capture)
        self._hotkey.start()

    def _load_initial_calibration(self) -> GridCalibration:
        if self.repository.has_grid_calibration(self.region_id):
            return GridCalibration.from_dict(self.repository.load_grid_calibration(self.region_id))
        return GridCalibration()

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=10)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Ajuste o tamanho e o alinhamento das células quadradas sobre uma captura congelada do jogo.",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Minimizar para o jogo", command=self.root.iconify).grid(row=0, column=1, padx=4)
        ttk.Button(header, text="Capturar agora", command=self._capture_now).grid(row=0, column=2, padx=4)
        ttk.Button(header, text="Salvar calibração", command=self._save).grid(row=0, column=3, padx=4)

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        preview_frame = ttk.LabelFrame(body, text="Captura congelada + grid / Frozen capture + grid", padding=6)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(preview_frame, background="#111111", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._redraw())
        self.canvas.bind("<Button-1>", self._anchor_from_click)
        body.add(preview_frame, weight=4)

        controls = ttk.Frame(body, padding=(10, 0, 0, 0))
        controls.columnconfigure(0, weight=1)
        body.add(controls, weight=2)

        instructions = ttk.LabelFrame(controls, text="Fluxo fullscreen", padding=10)
        instructions.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            instructions,
            text=(
                "1. Minimize esta janela.\n"
                "2. Dentro do jogo, pressione F8.\n"
                "3. Volte com Alt+Tab.\n"
                "4. Ajuste o grid sobre a imagem congelada.\n"
                "5. Clique em um cruzamento real para ancorar o grid."
            ),
            justify="left",
        ).grid(sticky="w")

        settings = ttk.LabelFrame(controls, text="Dimensões do grid", padding=10)
        settings.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        settings.columnconfigure(1, weight=1)

        self._add_scale(settings, 0, "Tamanho da célula", self.tile_size_var, 8, 256, "px")
        self.offset_x_scale = self._add_scale(settings, 1, "Offset horizontal", self.offset_x_var, 0, 63, "px")
        self.offset_y_scale = self._add_scale(settings, 2, "Offset vertical", self.offset_y_var, 0, 63, "px")
        self._add_scale(settings, 3, "Espessura da linha", self.thickness_var, 1, 6, "px")

        ttk.Label(settings, text="Opacidade").grid(row=4, column=0, sticky="w", pady=(8, 0))
        opacity = ttk.Scale(settings, from_=0.10, to=1.0, variable=self.opacity_var, orient="horizontal")
        opacity.grid(row=4, column=1, sticky="ew", padx=8, pady=(8, 0))
        self.opacity_value = ttk.Label(settings, width=8)
        self.opacity_value.grid(row=4, column=2, sticky="e", pady=(8, 0))

        actions = ttk.LabelFrame(controls, text="Alinhamento", padding=10)
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Centralizar cruzamento", command=self._center_grid).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(actions, text="Restaurar 64×64", command=self._reset_defaults).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Label(
            actions,
            text="Clique na imagem sobre um canto/cruzamento de células para alinhar os offsets X e Y.",
            wraplength=360,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        telemetry = ttk.LabelFrame(controls, text="Resultado", padding=10)
        telemetry.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        controls.rowconfigure(3, weight=1)
        ttk.Label(telemetry, textvariable=self.stats_var, justify="left", wraplength=380).grid(sticky="nw")

        status = ttk.Label(self.root, textvariable=self.status_var, padding=(10, 6), anchor="w")
        status.grid(row=2, column=0, sticky="ew")

    def _add_scale(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.IntVar,
        minimum: int,
        maximum: int,
        suffix: str,
    ) -> tk.Scale:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(8 if row else 0, 0))
        scale = tk.Scale(
            parent,
            from_=minimum,
            to=maximum,
            orient="horizontal",
            variable=variable,
            showvalue=False,
            resolution=1,
            highlightthickness=0,
        )
        scale.grid(row=row, column=1, sticky="ew", padx=8, pady=(8 if row else 0, 0))
        value_label = ttk.Label(parent, textvariable=variable, width=5)
        value_label.grid(row=row, column=2, sticky="e", pady=(8 if row else 0, 0))
        ttk.Label(parent, text=suffix).grid(row=row, column=3, sticky="w", pady=(8 if row else 0, 0))
        return scale

    def _bind_variables(self) -> None:
        for variable in (
            self.tile_size_var,
            self.offset_x_var,
            self.offset_y_var,
            self.thickness_var,
            self.opacity_var,
        ):
            variable.trace_add("write", self._settings_changed)

    def _settings_changed(self, *_args: Any) -> None:
        size = max(8, min(256, int(self.tile_size_var.get())))
        maximum = max(0, size - 1)
        self.offset_x_scale.configure(to=maximum)
        self.offset_y_scale.configure(to=maximum)
        if self.offset_x_var.get() > maximum:
            self.offset_x_var.set(self.offset_x_var.get() % size)
        if self.offset_y_var.get() > maximum:
            self.offset_y_var.set(self.offset_y_var.get() % size)
        self.opacity_value.configure(text=f"{self.opacity_var.get():.0%}")
        self._redraw()

    def _calibration(self) -> GridCalibration:
        return GridCalibration(
            tile_size_px=int(self.tile_size_var.get()),
            offset_x_px=int(self.offset_x_var.get()),
            offset_y_px=int(self.offset_y_var.get()),
            line_thickness=int(self.thickness_var.get()),
            line_opacity=float(self.opacity_var.get()),
        )

    def _initial_capture(self) -> None:
        self._capture_async(require_foreground=False, source="startup")

    def _capture_now(self) -> None:
        self._capture_async(require_foreground=False, source="button")

    def _request_hotkey_capture(self) -> None:
        self._capture_async(require_foreground=True, source="F8")

    def _capture_async(self, require_foreground: bool, source: str) -> None:
        if not self._capture_lock.acquire(blocking=False):
            return

        def worker() -> None:
            try:
                frame, bounds = self.capture.capture()
                if require_foreground and not bounds.foreground:
                    self._queue.put(("status", "F8 ignorado: o jogo não estava em primeiro plano."))
                    return
                self._queue.put(("frame", (frame, bounds, source)))
            except Exception as exc:
                self._queue.put(("error", str(exc)))
            finally:
                self._capture_lock.release()

        threading.Thread(target=worker, name="grid-calibration-capture", daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "frame":
                    frame, bounds, source = payload
                    self._raw_frame = frame
                    self.status_var.set(
                        f"Captura congelada ({source}): {bounds.width}×{bounds.height} — ajuste e salve a calibração."
                    )
                    self._redraw()
                elif kind == "status":
                    self.status_var.set(str(payload))
                else:
                    self.status_var.set(f"Erro de captura: {payload}")
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _redraw(self) -> None:
        frame = self._raw_frame
        if frame is None or not hasattr(self, "canvas"):
            return
        try:
            import cv2
            from PIL import Image, ImageTk

            calibration = self._calibration()
            rendered = calibration.draw(frame)
            rgb = cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            canvas_width = max(1, self.canvas.winfo_width())
            canvas_height = max(1, self.canvas.winfo_height())
            scale = min(canvas_width / image.width, canvas_height / image.height)
            display_width = max(1, int(image.width * scale))
            display_height = max(1, int(image.height * scale))
            image = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(image)
            self._display_scale = scale
            self._display_width = display_width
            self._display_height = display_height
            self._display_left = (canvas_width - display_width) / 2
            self._display_top = (canvas_height - display_height) / 2
            self.canvas.delete("all")
            self.canvas.create_image(canvas_width / 2, canvas_height / 2, image=self._photo, anchor="center")
            height, width = frame.shape[:2]
            columns = max(1, len(calibration.vertical_lines(width)) - 1)
            rows = max(1, len(calibration.horizontal_lines(height)) - 1)
            self.stats_var.set(
                "\n".join(
                    [
                        f"Imagem: {width}×{height} px",
                        f"Célula quadrada: {calibration.tile_size_px}×{calibration.tile_size_px} px",
                        f"Offset: X={calibration.offset_x_px} px | Y={calibration.offset_y_px} px",
                        f"Linhas: {len(calibration.vertical_lines(width))} verticais | {len(calibration.horizontal_lines(height))} horizontais",
                        f"Área aproximada visível: {columns}×{rows} células completas",
                        f"Espessura: {calibration.line_thickness} px | Opacidade: {calibration.line_opacity:.0%}",
                    ]
                )
            )
        except Exception as exc:
            self.status_var.set(f"Erro ao desenhar grid: {exc}")

    def _anchor_from_click(self, event: tk.Event[Any]) -> None:
        if self._raw_frame is None or self._display_scale <= 0:
            return
        local_x = event.x - self._display_left
        local_y = event.y - self._display_top
        if not (0 <= local_x < self._display_width and 0 <= local_y < self._display_height):
            return
        source_x = int(round(local_x / self._display_scale))
        source_y = int(round(local_y / self._display_scale))
        size = int(self.tile_size_var.get())
        self.offset_x_var.set(source_x % size)
        self.offset_y_var.set(source_y % size)
        self.status_var.set(
            f"Grid ancorado no ponto da captura ({source_x}, {source_y}); offsets atualizados."
        )

    def _center_grid(self) -> None:
        if self._raw_frame is None:
            return
        height, width = self._raw_frame.shape[:2]
        calibration = self._calibration()
        calibration.center_on(width, height)
        self.offset_x_var.set(calibration.offset_x_px)
        self.offset_y_var.set(calibration.offset_y_px)

    def _reset_defaults(self) -> None:
        self.tile_size_var.set(64)
        self.offset_x_var.set(0)
        self.offset_y_var.set(0)
        self.thickness_var.set(1)
        self.opacity_var.set(0.75)

    def _save(self) -> None:
        try:
            calibration = self._calibration()
            path = self.repository.save_grid_calibration(self.region_id, calibration.to_dict())
            self.status_var.set(f"Calibração salva: {path}")
            messagebox.showinfo(
                "Kage Grid Calibration Lab",
                "Calibração salva e será carregada automaticamente pelo Mapping Lab.\n\n"
                f"Célula: {calibration.tile_size_px}×{calibration.tile_size_px} px\n"
                f"Offset: ({calibration.offset_x_px}, {calibration.offset_y_px})",
            )
        except Exception as exc:
            messagebox.showerror("Kage Grid Calibration Lab", str(exc))

    def _close(self) -> None:
        self._hotkey.stop()
        self.capture.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
