from __future__ import annotations


class EnemyPerceptionWindow:
    """Responsive live diagnostic window for the passive perception laboratory."""

    LIVE_VIEW_KEY = "__live_decision__"
    VIEW_OPTIONS = (
        (LIVE_VIEW_KEY, "9 — Visão ao vivo: decisões e Track IDs"),
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

    @staticmethod
    def _enum_value(value) -> str:
        return str(getattr(value, "value", value))

    def _build_live_decision(self):
        """Build a clean combined view without the per-cell text wall.

        The saved specialist images remain unchanged. This view is intended for
        the operator: known backgrounds are quiet borders, residual differences
        are explicit, and every tracked entity is visible on the default page.
        """

        import cv2
        import numpy as np

        if not self._last_images or self._last_result is None:
            return None

        result = self._last_result
        raw = self._last_images.get("00_raw_window.png")
        if raw is None:
            raw = self._last_images.get("01_grid_overlay.png")
        if raw is None:
            return None
        image = raw.copy()
        height, width = image.shape[:2]

        cutoff = int(result.playfield.get("cutoff_y_px", height))
        if cutoff < height:
            shade = image.copy()
            cv2.rectangle(shade, (0, cutoff), (width - 1, height - 1), (25, 25, 25), -1)
            cv2.addWeighted(shade, 0.65, image, 0.35, 0.0, image)
            cv2.line(image, (0, cutoff), (width - 1, cutoff), (0, 0, 255), 2)

        player_screen = result.player.get("screen_cell")
        player_cell = None
        for cell in result.cells:
            x0, y0, x1, y1 = cell.pixel_bounds
            if not cell.inside_playfield:
                color = (55, 55, 55)
            elif not cell.inside_processing_roi:
                color = (75, 75, 75)
            elif cell.semantic_candidate_created:
                color = (255, 0, 255)
            elif cell.residual_candidate_created:
                color = (0, 165, 255)
            elif cell.background_match_level == "strong":
                color = (0, 145, 0)
            elif cell.background_match_level == "usable":
                color = (0, 205, 255)
            elif cell.background_match_level == "weak":
                color = (0, 255, 255)
            else:
                color = (115, 115, 115)

            thickness = 2 if (
                cell.semantic_candidate_created or cell.residual_candidate_created
            ) else 1
            cv2.rectangle(image, (x0, y0), (x1 - 1, y1 - 1), color, thickness)

            if player_screen is not None and tuple(cell.screen_cell) == tuple(player_screen):
                player_cell = cell

            if cell.semantic_candidate_created:
                label = f"NPC {cell.terrain_confidence:.0%}"
                cv2.putText(
                    image,
                    label,
                    (x0 + 2, max(14, y0 + 13)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.38,
                    (255, 0, 255),
                    1,
                    cv2.LINE_AA,
                )
            elif cell.residual_candidate_created:
                label = f"DIFF {cell.metrics.changed_pixel_ratio:.0%}"
                cv2.putText(
                    image,
                    label,
                    (x0 + 2, max(14, y0 + 13)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.38,
                    (0, 165, 255),
                    1,
                    cv2.LINE_AA,
                )
            elif (
                cell.inside_processing_roi
                and cell.background_match_level in {"weak", "none"}
                and not (
                    player_screen is not None
                    and tuple(cell.screen_cell) == tuple(player_screen)
                )
            ):
                label = (
                    f"BG {cell.background_match_level.upper()}"
                    if cell.background_match_level != "none"
                    else "NO BG"
                )
                cv2.putText(
                    image,
                    label,
                    (x0 + 2, max(14, y0 + 13)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.30,
                    color,
                    1,
                    cv2.LINE_AA,
                )

        if player_cell is not None:
            x0, y0, x1, y1 = player_cell.pixel_bounds
            center_x = (x0 + x1) // 2
            center_y = (y0 + y1) // 2
            tile_size = int(result.calibration.get("tile_size_px", max(1, x1 - x0)))
            radius_px = int(result.roi.get("interest_radius_cells", 4)) * tile_size
            points = np.array(
                [
                    [center_x, center_y - radius_px],
                    [center_x + radius_px, center_y],
                    [center_x, center_y + radius_px],
                    [center_x - radius_px, center_y],
                ],
                np.int32,
            )
            cv2.polylines(image, [points], True, (255, 180, 0), 2)
            cv2.rectangle(image, (x0, y0), (x1 - 1, y1 - 1), (255, 180, 0), 2)
            source = str(result.player.get("source", "unknown")).upper()
            cv2.putText(
                image,
                f"PLAYER {source}",
                (max(0, x0 - 75), max(18, y0 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (255, 180, 0),
                1,
                cv2.LINE_AA,
            )

        for entity in result.entities:
            x0, y0, x1, y1 = entity.region.bounding_box_px
            hostility = self._enum_value(entity.hostility_state)
            if entity.attack_recommended or hostility in {
                "hostile_confirmed",
                "attack_recommended",
            }:
                color = (0, 0, 255)
            elif hostility in {"hostile_probable", "approaching_entity"}:
                color = (0, 100, 255)
            elif "semantic_npc" in entity.candidate_sources:
                color = (255, 0, 255)
            else:
                color = (0, 165, 255)

            cv2.rectangle(image, (x0, y0), (x1, y1), color, 2)
            source = (
                "NPC"
                if "semantic_npc" in entity.candidate_sources
                else "RESIDUAL"
            )
            first_line = f"{entity.track_id} D={entity.distance_to_player} {source}"
            second_line = f"{hostility} score={entity.hostility_score}"
            cv2.putText(
                image,
                first_line,
                (x0, max(18, y0 - 16)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                color,
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                second_line,
                (x0, max(32, y0 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                color,
                1,
                cv2.LINE_AA,
            )

        counters = result.counters
        banner = (
            f"FRAME {result.frame_index} | "
            f"SEM {counters.get('semantic_candidates', 0)} | "
            f"RES {counters.get('residual_candidates', 0)} | "
            f"TRACKS {len(result.entities)} | "
            f"{result.processing_time_ms:.0f} ms"
        )
        cv2.rectangle(image, (7, 7), (min(width - 8, 620), 34), (20, 20, 20), -1)
        cv2.putText(
            image,
            banner,
            (14, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (235, 235, 235),
            1,
            cv2.LINE_AA,
        )
        return image

    def run(self) -> None:
        import os
        import queue
        import threading
        import time
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
            width=45,
        )
        view_combo.grid(row=0, column=1, sticky="w")

        debug_enabled = bool(self.engine.recorder and self.engine.recorder.enabled)
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

        status = tk.StringVar(value="Iniciando worker de captura e percepção...")
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

            selected_key = key_by_label.get(view_var.get(), self.LIVE_VIEW_KEY)
            if selected_key == self.LIVE_VIEW_KEY:
                image = self._build_live_decision()
            else:
                image = self._last_images.get(selected_key)
            if image is None:
                image = self._last_images.get("01_grid_overlay.png")
            if image is None:
                return

            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            rendered = Image.fromarray(rgb)
            max_width = max(640, root.winfo_width() - 30)
            max_height = max(480, root.winfo_height() - 145)
            rendered.thumbnail((max_width, max_height), Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(rendered)
            label.configure(image=photo)
            label.image = photo

        view_combo.bind("<<ComboboxSelected>>", lambda _event: render_selected())
        root.bind("<Configure>", lambda _event: render_selected())

        result_queue: queue.Queue = queue.Queue(maxsize=2)
        stop_event = threading.Event()

        def publish(payload) -> None:
            try:
                result_queue.put_nowait(payload)
            except queue.Full:
                try:
                    result_queue.get_nowait()
                except queue.Empty:
                    pass
                result_queue.put_nowait(payload)

        def worker_loop() -> None:
            while not stop_event.is_set():
                started = time.perf_counter()
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
                    publish(("result", result, images))
                except Exception as exc:
                    publish(("error", type(exc).__name__, str(exc)))
                elapsed = time.perf_counter() - started
                remaining = self.interval - elapsed
                if remaining > 0:
                    stop_event.wait(remaining)

        worker = threading.Thread(
            target=worker_loop,
            name="enemy-perception-worker",
            daemon=True,
        )
        worker.start()

        def poll_results() -> None:
            if not self.running:
                return
            latest = None
            while True:
                try:
                    latest = result_queue.get_nowait()
                except queue.Empty:
                    break

            if latest is not None:
                if latest[0] == "error":
                    _kind, error_type, error_message = latest
                    status.set(f"ERRO DE PROCESSAMENTO: {error_type}: {error_message}")
                    details.set(
                        "O worker continuará tentando o próximo frame. "
                        + (
                            f"Verifique: {debug_path / 'errors.log'}"
                            if debug_path
                            else ""
                        )
                    )
                else:
                    _kind, result, images = latest
                    self._last_result = result
                    self._last_images = images
                    render_selected()

                    counters = result.counters
                    references = (
                        int(counters.get("background_matches_strong", 0))
                        + int(counters.get("background_matches_usable", 0))
                    )
                    status.set(
                        f"frame={result.frame_index} | "
                        f"player={'SIM' if result.player.get('recognized') else 'NÃO'} "
                        f"({result.player.get('source', 'unknown')}) | "
                        f"estável={'SIM' if result.frame_state.get('settled') else 'NÃO'} | "
                        f"BG={references} | "
                        f"semânticos={counters.get('semantic_candidates', 0)} | "
                        f"residuais={counters.get('residual_candidates', 0)} | "
                        f"tracks={len(result.entities)} | "
                        f"processamento={result.processing_time_ms:.1f} ms"
                    )
                    frame_path = (
                        debug_path / "frames" / f"frame_{result.frame_index:06d}"
                        if debug_path
                        else None
                    )
                    details.set(
                        f"Visualização: {view_var.get()} | "
                        "Processamento executado em thread separada; a janela deve "
                        "continuar responsiva."
                        + (f" | frame salvo em: {frame_path}" if frame_path else "")
                    )
            root.after(50, poll_results)

        def close() -> None:
            self.running = False
            stop_event.set()
            status.set("Encerrando worker e finalizando o debug...")
            worker.join(timeout=8.0)
            if self.engine.recorder:
                self.engine.recorder.finalize(self.engine.tracker.tracks)
            self.capture.close()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", close)
        root.after(50, poll_results)
        root.mainloop()
