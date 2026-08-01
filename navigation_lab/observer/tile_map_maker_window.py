from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from ..storage import JsonRepository
from .grid_calibration import GridCalibration
from .tile_knowledge import TILE_CLASS_LABELS_PT_BR, TileClass, TileKnowledgeBase
from .tile_map_engine import ClassifiedGridCell, SemanticTileMapEngine, TileScanResult
from .window_capture import WindowsClientCapture


class _TileScanHotkey:
    """Passive F8 listener that requests one full calibrated tile scan."""

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


class TileMapMakerWindow:
    """Human-in-the-loop semantic classifier for every calibrated screen tile."""

    def __init__(
        self,
        capture: WindowsClientCapture,
        repository: JsonRepository,
        region_id: str,
        calibration: GridCalibration,
        similarity_threshold: float = 0.92,
        language: str = "pt-BR",
    ) -> None:
        self.capture = capture
        self.repository = repository
        self.region_id = region_id
        self.calibration = calibration
        self.language = language
        self.knowledge = self._load_knowledge(similarity_threshold)
        self.engine = SemanticTileMapEngine(
            calibration=calibration,
            knowledge=self.knowledge,
            similarity_threshold=similarity_threshold,
        )

        self.root = tk.Tk()
        self.root.title("Kage Semantic Tile MapMaker — PR 24")
        self.root.geometry("1540x920")
        self.root.minsize(1120, 720)
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._capture_lock = threading.Lock()
        self._hotkey = _TileScanHotkey(self._request_hotkey_scan)
        self._scan: TileScanResult | None = None
        self._selected: ClassifiedGridCell | None = None
        self._photo: Any | None = None
        self._crop_photo: Any | None = None
        self._display_scale = 1.0
        self._display_left = 0.0
        self._display_top = 0.0
        self._display_width = 0
        self._display_height = 0

        self.threshold_var = tk.DoubleVar(value=float(similarity_threshold))
        self.status_var = tk.StringVar(
            value="Minimize, return to the game and press F8 / Minimize, volte ao jogo e pressione F8"
        )
        self.stats_var = tk.StringVar(value="Nenhuma captura analisada")
        self.selected_var = tk.StringVar(value="Selecione uma célula desconhecida")

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(50, self._poll)
        self._hotkey.start()

    def _load_knowledge(self, threshold: float) -> TileKnowledgeBase:
        if self.repository.has_tile_knowledge(self.region_id):
            knowledge = TileKnowledgeBase.from_dict(self.repository.load_tile_knowledge(self.region_id))
            knowledge.similarity_threshold = float(threshold)
            return knowledge
        return TileKnowledgeBase(similarity_threshold=float(threshold))

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Cada célula do grid vira um crop visual e recebe uma classe semântica.",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Minimizar para o jogo", command=self.root.iconify).grid(row=0, column=1, padx=4)
        ttk.Button(header, text="Capturar e analisar", command=self._scan_now).grid(row=0, column=2, padx=4)
        ttk.Button(header, text="Salvar conhecimento", command=self._save_knowledge_dialog).grid(
            row=0, column=3, padx=4
        )

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        preview = ttk.LabelFrame(body, text="Janela do jogo + classificação / Game window + classification", padding=6)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(preview, background="#111111", highlightthickness=0)
        self.canvas.grid(sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._redraw())
        self.canvas.bind("<Button-1>", self._select_from_canvas)
        body.add(preview, weight=4)

        right = ttk.Frame(body, padding=(8, 0, 0, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.rowconfigure(3, weight=1)
        body.add(right, weight=2)

        threshold_frame = ttk.LabelFrame(right, text="Reconhecimento", padding=8)
        threshold_frame.grid(row=0, column=0, sticky="ew")
        threshold_frame.columnconfigure(1, weight=1)
        ttk.Label(threshold_frame, text="Similaridade mínima").grid(row=0, column=0, sticky="w")
        threshold = ttk.Scale(
            threshold_frame,
            from_=0.70,
            to=0.995,
            variable=self.threshold_var,
            orient="horizontal",
            command=lambda _value: self._threshold_changed(),
        )
        threshold.grid(row=0, column=1, sticky="ew", padx=8)
        self.threshold_label = ttk.Label(threshold_frame, width=7)
        self.threshold_label.grid(row=0, column=2, sticky="e")
        ttk.Label(
            threshold_frame,
            text="Maior = mais perguntas e menos classificações automáticas incorretas.",
            wraplength=360,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._threshold_changed(rescan=False)

        unknown_frame = ttk.LabelFrame(right, text="Fila de células desconhecidas", padding=8)
        unknown_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        unknown_frame.columnconfigure(0, weight=1)
        unknown_frame.rowconfigure(0, weight=1)
        self.unknown_list = tk.Listbox(unknown_frame, exportselection=False, font=("Consolas", 10))
        self.unknown_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(unknown_frame, orient="vertical", command=self.unknown_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.unknown_list.configure(yscrollcommand=scrollbar.set)
        self.unknown_list.bind("<<ListboxSelect>>", self._select_from_unknown_list)

        selected_frame = ttk.LabelFrame(right, text="Célula selecionada", padding=8)
        selected_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        selected_frame.columnconfigure(0, weight=1)
        self.crop_label = ttk.Label(selected_frame, anchor="center")
        self.crop_label.grid(row=0, column=0, sticky="ew")
        ttk.Label(selected_frame, textvariable=self.selected_var, justify="left", wraplength=370).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        teaching = ttk.LabelFrame(right, text="Ensinar classificação", padding=8)
        teaching.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        teaching.columnconfigure(0, weight=1)
        teaching.columnconfigure(1, weight=1)
        categories = [
            TileClass.WALKABLE,
            TileClass.WALL,
            TileClass.WALKABLE_WITH_JUTSU,
            TileClass.BLOCKING_OBJECT,
            TileClass.NPC,
            TileClass.TRANSITION,
            TileClass.DANGER,
            TileClass.IGNORE_DYNAMIC,
        ]
        for index, category in enumerate(categories):
            ttk.Button(
                teaching,
                text=TILE_CLASS_LABELS_PT_BR[category],
                command=lambda selected=category: self._teach(selected),
            ).grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 4) if index % 2 == 0 else (4, 0),
                pady=3,
            )
        ttk.Label(
            teaching,
            text=(
                "Parede = terreno estrutural. Bloqueia caminho = objeto físico ocupando a célula. "
                "NPC = entidade viva/móvel; não torna o terreno inferior uma parede permanente. "
                "Ignorar/dinâmico = jogador, efeito ou animação que não deve virar exemplo de terreno."
            ),
            justify="left",
            wraplength=370,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        stats = ttk.LabelFrame(right, text="Resumo", padding=8)
        stats.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(stats, textvariable=self.stats_var, justify="left", wraplength=380).grid(sticky="w")

        ttk.Label(self.root, textvariable=self.status_var, padding=(8, 5), anchor="w").grid(
            row=2, column=0, sticky="ew"
        )

    def _request_hotkey_scan(self) -> None:
        self._capture_async(require_foreground=True, source="F8")

    def _scan_now(self) -> None:
        self._capture_async(require_foreground=False, source="button")

    def _capture_async(self, require_foreground: bool, source: str) -> None:
        if not self._capture_lock.acquire(blocking=False):
            return

        def worker() -> None:
            try:
                frame, bounds = self.capture.capture()
                if require_foreground and not bounds.foreground:
                    self._queue.put(("status", "F8 ignorado: o jogo não estava em primeiro plano."))
                    return
                result = self.engine.scan(frame)
                self._queue.put(("scan", (result, bounds, source)))
            except Exception as exc:
                self._queue.put(("error", str(exc)))
            finally:
                self._capture_lock.release()

        threading.Thread(target=worker, name="semantic-tile-scan", daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "scan":
                    result, bounds, source = payload
                    self._scan = result
                    self._selected = None
                    self.status_var.set(
                        f"Captura {source}: {bounds.width}×{bounds.height}; {len(result.cells)} células analisadas."
                    )
                    self._refresh_unknown_list()
                    self._refresh_stats()
                    self._redraw()
                    self._select_first_unknown()
                elif kind == "status":
                    self.status_var.set(str(payload))
                else:
                    self.status_var.set(f"Erro: {payload}")
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _threshold_changed(self, rescan: bool = True) -> None:
        value = float(self.threshold_var.get())
        self.threshold_label.configure(text=f"{value:.1%}")
        self.engine.similarity_threshold = value
        self.knowledge.similarity_threshold = value
        if rescan and self._scan is not None:
            self._scan = self.engine.scan(self._scan.frame)
            self._refresh_unknown_list()
            self._refresh_stats()
            self._redraw()

    def _refresh_unknown_list(self) -> None:
        self.unknown_list.delete(0, "end")
        if self._scan is None:
            return
        for cell in self._scan.unknown_cells:
            self.unknown_list.insert(
                "end",
                f"{cell.crop.id}  melhor={cell.classification.confidence:.1%}",
            )

    def _refresh_stats(self) -> None:
        if self._scan is None:
            self.stats_var.set("Nenhuma captura analisada")
            return
        counts = self._scan.counts()
        examples = self.knowledge.counts()
        lines = [
            f"Grid: {self.calibration.tile_size_px}×{self.calibration.tile_size_px} px",
            f"Células analisadas: {len(self._scan.cells)}",
            f"Desconhecidas: {len(self._scan.unknown_cells)}",
            f"Exemplos ensinados: {len(self.knowledge.examples)}",
            "",
        ]
        for category in TileClass:
            if category == TileClass.UNKNOWN:
                continue
            lines.append(
                f"{TILE_CLASS_LABELS_PT_BR[category]}: tela={counts.get(category, 0)} | exemplos={examples.get(category, 0)}"
            )
        self.stats_var.set("\n".join(lines))

    def _select_first_unknown(self) -> None:
        if self._scan and self._scan.unknown_cells:
            self.unknown_list.selection_clear(0, "end")
            self.unknown_list.selection_set(0)
            self.unknown_list.activate(0)
            self._selected = self._scan.unknown_cells[0]
            self._refresh_selected()

    def _select_from_unknown_list(self, _event: Any) -> None:
        if self._scan is None:
            return
        selected = self.unknown_list.curselection()
        if not selected:
            return
        unknown = self._scan.unknown_cells
        index = int(selected[0])
        if 0 <= index < len(unknown):
            self._selected = unknown[index]
            self._refresh_selected()
            self._redraw()

    def _select_from_canvas(self, event: tk.Event[Any]) -> None:
        if self._scan is None or self._display_scale <= 0:
            return
        local_x = event.x - self._display_left
        local_y = event.y - self._display_top
        if not (0 <= local_x < self._display_width and 0 <= local_y < self._display_height):
            return
        source_x = int(local_x / self._display_scale)
        source_y = int(local_y / self._display_scale)
        selected = self._scan.find_at(source_x, source_y)
        if selected is not None:
            self._selected = selected
            self._refresh_selected()
            self._redraw()

    def _refresh_selected(self) -> None:
        selected = self._selected
        if selected is None:
            self.crop_label.configure(image="")
            self.selected_var.set("Selecione uma célula")
            return
        import cv2
        from PIL import Image, ImageTk

        rgb = cv2.cvtColor(selected.crop.image, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        image = image.resize((192, 192), Image.Resampling.NEAREST)
        self._crop_photo = ImageTk.PhotoImage(image)
        self.crop_label.configure(image=self._crop_photo)
        classification = selected.classification
        self.selected_var.set(
            "\n".join(
                [
                    f"Célula: {selected.crop.id}",
                    f"Área: ({selected.crop.x0},{selected.crop.y0})–({selected.crop.x1},{selected.crop.y1})",
                    f"Resultado: {TILE_CLASS_LABELS_PT_BR[classification.category]}",
                    f"Confiança / similaridade: {classification.confidence:.1%}",
                    f"Exemplo correspondente: {classification.matched_example_id or 'nenhum'}",
                ]
            )
        )

    def _teach(self, category: TileClass) -> None:
        selected = self._selected
        if selected is None:
            messagebox.showwarning("Kage MapMaker", "Selecione uma célula antes de ensinar.")
            return
        example = self.knowledge.add_example(selected.crop.image, category)
        crop_path = self.repository.save_tile_example_crop(self.region_id, example.id, selected.crop.image)
        example.crop_path = str(crop_path)
        self._save_knowledge()
        current_frame = self._scan.frame if self._scan is not None else None
        if current_frame is not None:
            self._scan = self.engine.scan(current_frame)
        self.status_var.set(
            f"Aprendido: {selected.crop.id} → {TILE_CLASS_LABELS_PT_BR[category]}. Células semelhantes reavaliadas."
        )
        self._selected = None
        self._refresh_unknown_list()
        self._refresh_stats()
        self._redraw()
        self._select_first_unknown()

    def _draw_overlay(self) -> Any:
        import cv2

        if self._scan is None:
            return None
        frame = self._scan.frame.copy()
        overlay = frame.copy()
        colors = {
            TileClass.UNKNOWN: (0, 200, 255),
            TileClass.WALKABLE: (60, 210, 80),
            TileClass.WALL: (40, 40, 230),
            TileClass.WALKABLE_WITH_JUTSU: (230, 210, 40),
            TileClass.BLOCKING_OBJECT: (30, 130, 240),
            TileClass.NPC: (220, 120, 40),
            TileClass.TRANSITION: (210, 60, 210),
            TileClass.DANGER: (20, 230, 230),
            TileClass.IGNORE_DYNAMIC: (150, 150, 150),
        }
        symbols = {
            TileClass.UNKNOWN: "?",
            TileClass.WALKABLE: ".",
            TileClass.WALL: "#",
            TileClass.WALKABLE_WITH_JUTSU: "J",
            TileClass.BLOCKING_OBJECT: "B",
            TileClass.NPC: "N",
            TileClass.TRANSITION: "T",
            TileClass.DANGER: "!",
            TileClass.IGNORE_DYNAMIC: "I",
        }
        for cell in self._scan.cells:
            category = cell.classification.category
            color = colors[category]
            cv2.rectangle(
                overlay,
                (cell.crop.x0, cell.crop.y0),
                (cell.crop.x1 - 1, cell.crop.y1 - 1),
                color,
                -1,
            )
        cv2.addWeighted(overlay, 0.20, frame, 0.80, 0.0, frame)
        for cell in self._scan.cells:
            category = cell.classification.category
            color = colors[category]
            thickness = 3 if cell is self._selected else 1
            border = (255, 255, 255) if cell is self._selected else color
            cv2.rectangle(
                frame,
                (cell.crop.x0, cell.crop.y0),
                (cell.crop.x1 - 1, cell.crop.y1 - 1),
                border,
                thickness,
            )
            cv2.putText(
                frame,
                f"{symbols[category]} {cell.classification.confidence:.0%}",
                (cell.crop.x0 + 4, cell.crop.y0 + 17),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        return frame

    def _redraw(self) -> None:
        if self._scan is None or not hasattr(self, "canvas"):
            return
        import cv2
        from PIL import Image, ImageTk

        rendered = self._draw_overlay()
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

    def _save_knowledge(self) -> None:
        self.knowledge.similarity_threshold = float(self.threshold_var.get())
        self.repository.save_tile_knowledge(self.region_id, self.knowledge.to_dict())

    def _save_knowledge_dialog(self) -> None:
        path = self.repository.save_tile_knowledge(self.region_id, self.knowledge.to_dict())
        messagebox.showinfo("Kage MapMaker", f"Conhecimento salvo em:\n{path}")

    def _close(self) -> None:
        try:
            self._save_knowledge()
        finally:
            self._hotkey.stop()
            self.capture.close()
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
