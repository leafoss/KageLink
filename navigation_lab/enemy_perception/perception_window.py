from __future__ import annotations


class EnemyPerceptionWindow:
    """Live diagnostic window for the passive enemy perception laboratory."""

    VIEW_OPTIONS = (
        ("01_grid_overlay.png", "1 — Grade, referências e células"),
        ("02_background_composite.png", "2 — Referências de tile vazio"),
        ("03_difference_composite.png", "3 — Diferença atual × vazio"),
        ("04_mask_composite.png", "4 — Máscara binária"),
        ("05_components_overlay.png", "5 — Componentes detectados"),
        ("06_entities_overlay.png", "6 — Entidades extraídas"),
        ("07_tracking_overlay.png", "7 — Track IDs e distância"),
        ("08_hostility_overlay.png", "8 — Hostilidade"),
        ("00_raw_window.png", "0 — Captura bruta"),
    )

    def __init__(
        self,
        engine,
        capture,
        capture_interval: float = 0.20,
        title: str = "Kage Enemy Perception Lab",
    ) -> None:
        self.engine = engine
        self.capture = capture
        self.interval = max(0.05, float(capture_interval))
        self.title = title
        self.running = True
        self._last_images = None
        self._last_result = None

    def run(self) -> None:
        import os
        import tkinter as tk
        from pathlib import Path
        from tkinter import messagebox, ttk

        from PIL import Image, ImageTk

        root = tk.Tk()
        root.title(self.title)
        root.geometry("1400x860")
        root.minsize(980, 640)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(root, padding=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(
            toolbar,
            text="Visualização diagnóstica:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        labels = [label for _key, label in self.VIEW_OPTIONS]
        key_by_label = {label: key for key, label in self.VIEW_OPTIONS}
        view_var = tk.StringVar(value=labels[0])
        view_combo = ttk.Combobox(
            toolbar,
            textvariable=view_var,
            values=labels,
            state="readonly",
            width=42,
        )
        view_combo.grid(row=0, column=1, sticky="w")

        debug_enabled = bool(
            self.engine.recorder and self.engine.recorder.enabled
        )
        debug_path = Path(self.engine.recorder.session_root) if debug_enabled else None

        def open_debug_folder() -> None:
            if not debug_enabled or debug_path is None:
                messagebox.showwarning(
                    self.title,
                    "A gravação de debug está desligada para esta sessão.",
                )
                return
            debug_path.mkdir(parents=True, exist_ok=True)
            try:
                os.startfile(str(debug_path))
            except AttributeError:
                import subprocess

                subprocess.Popen(["explorer", str(debug_path)])
            except OSError as exc:
                messagebox.showerror(
                    self.title,
                    f"Não foi possível abrir a pasta:\n{debug_path}\n\n{exc}",
                )

        ttk.Button(
            toolbar,
            text="Abrir pasta de debug",
            command=open_debug_folder,
        ).grid(row=0, column=2, padx=(8, 0))

        image_frame = ttk.Frame(root, padding=(8, 0, 8, 0))
        image_frame.grid(row=1, column=0, sticky="nsew")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
        label = ttk.Label(image_frame, anchor="center")
        label.grid(row=0, column=0, sticky="nsew")

        status = tk.StringVar(value="Iniciando captura e percepção...")
        details = tk.StringVar(
            value=(
                f"Debug: {'LIGADO' if debug_enabled else 'DESLIGADO'}"
                + (f" | {debug_path}" if debug_path else "")
            )
        )
        ttk.Label(root, textvariable=status, anchor="w", padding=(8, 5)).grid(
            row=2, column=0, sticky="ew"
        )
        ttk.Label(
            root,
            textvariable=details,
            anchor="w",
            padding=(8, 3, 8, 8),
        ).grid(row=3, column=0, sticky="ew")

        def render_selected() -> None:
            if not self._last_images:
                return
            import cv2

            selected_key = key_by_label.get(
                view_var.get(),
                "01_grid_overlay.png",
            )
            image = self._last_images.get(selected_key)
            if image is None:
                image = self._last_images["01_grid_overlay.png"]
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            rendered = Image.fromarray(rgb)
            max_width = max(640, root.winfo_width() - 30)
            max_height = max(480, root.winfo_height() - 145)
            rendered.thumbnail(
                (max_width, max_height),
                Image.Resampling.NEAREST,
            )
            photo = ImageTk.PhotoImage(rendered)
            label.configure(image=photo)
            label.image = photo

        view_combo.bind("<<ComboboxSelected>>", lambda _event: render_selected())
        root.bind("<Configure>", lambda _event: render_selected())

        def tick() -> None:
            if not self.running:
                return
            try:
                frame, bounds = self.capture.capture()
                result, images = self.engine.process_frame(
                    frame,
                    {
                        "title": bounds.title,
                        "hwnd": bounds.hwnd,
                        "width": bounds.width,
                        "height": bounds.height,
                        "capture_backend": bounds.capture_backend,
                    },
                )
                self._last_result = result
                self._last_images = images
                render_selected()

                references = sum(
                    int(cell.background_reference_available)
                    for cell in result.cells
                )
                overlays = sum(
                    int(cell.metrics.overlay_detected)
                    for cell in result.cells
                )
                status.set(
                    f"frame={result.frame_index} | "
                    f"player={'SIM' if result.player.get('recognized') else 'NÃO'} | "
                    f"estável={'SIM' if result.frame_state.get('settled') else 'NÃO'} | "
                    f"referências={references}/{len(result.cells)} | "
                    f"sobreposições={overlays} | entidades={len(result.entities)} | "
                    f"processamento={result.processing_time_ms:.1f} ms"
                )
                frame_path = (
                    debug_path
                    / "frames"
                    / f"frame_{result.frame_index:06d}"
                    if debug_path
                    else None
                )
                details.set(
                    f"Visualização: {view_var.get()} | "
                    f"Debug: {'LIGADO' if debug_enabled else 'DESLIGADO'}"
                    + (f" | frame salvo em: {frame_path}" if frame_path else "")
                )
            except Exception as exc:
                status.set(f"ERRO DE PROCESSAMENTO: {type(exc).__name__}: {exc}")
                details.set(
                    "A captura pode continuar visível, mas este frame não foi processado. "
                    + (f"Verifique: {debug_path / 'errors.log'}" if debug_path else "")
                )
            root.after(int(self.interval * 1000), tick)

        def close() -> None:
            self.running = False
            if self.engine.recorder:
                self.engine.recorder.finalize(self.engine.tracker.tracks)
            self.capture.close()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", close)
        root.after(1, tick)
        root.mainloop()
