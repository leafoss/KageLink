from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from ..storage import JsonRepository
from .continuous_mapping import ContinuousMappingResult, ContinuousSemanticMapper, UnknownTileGroup
from .tile_knowledge import TILE_CLASS_LABELS_PT_BR, TileClass
from .tile_overlay import display_category, render_tile_classification_overlay, tile_overlay_text
from .window_capture import WindowsClientCapture


class _ReviewHotkey:
    """Passive F7 listener used only to request the review window."""

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
            if key == keyboard.Key.f7 and not self._pressed:
                self._pressed = True
                self.callback()

        def on_release(key: Any) -> None:
            if key == keyboard.Key.f7:
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


class ContinuousMapperWindow:
    """Background semantic mapper with live tile diagnostics and grouped review."""

    def __init__(
        self,
        mapper: ContinuousSemanticMapper,
        capture: WindowsClientCapture,
        repository: JsonRepository,
        region_id: str,
        capture_interval: float = 0.75,
        auto_start: bool = True,
        minimize_on_start: bool = True,
    ) -> None:
        if capture_interval < 0.20:
            raise ValueError("capture_interval must be at least 0.20 seconds")
        self.mapper = mapper
        self.capture = capture
        self.repository = repository
        self.region_id = region_id
        self.capture_interval = float(capture_interval)
        self.auto_start = bool(auto_start)
        self.minimize_on_start = bool(minimize_on_start)

        self.root = tk.Tk()
        self.root.title("Kage Continuous Semantic Mapper — PR 24")
        self.root.geometry("1600x940")
        self.root.minsize(1180, 760)
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._running = threading.Event()
        self._closing = threading.Event()
        self._engine_lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._review_hotkey = _ReviewHotkey(lambda: self._events.put(("show", None)))
        self._selected_group_id: str | None = None
        self._selected_cell_id: str | None = None
        self._group_ids: list[str] = []
        self._crop_photo: Any | None = None
        self._frame_photo: Any | None = None
        self._display_scale = 1.0
        self._display_left = 0.0
        self._display_top = 0.0
        self._display_width = 0
        self._display_height = 0

        self.status_var = tk.StringVar(value="Pronto. F7 abre esta janela sem interromper automaticamente o jogo.")
        self.stats_var = tk.StringVar(value="Nenhuma captura processada.")
        self.selected_var = tk.StringVar(value="Selecione um grupo desconhecido para ensinar.")
        self.running_var = tk.StringVar(value="Iniciar")

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(60, self._poll_events)
        self._review_hotkey.start()
        self._load_unknown_group_images()
        self._refresh_all()

        if self.auto_start:
            self.root.after(250, self.start)
        if self.minimize_on_start:
            self.root.after(700, self.root.iconify)

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Mapeamento contínuo: captura o jogo, mostra o grid 64×64 e agrupa dúvidas para revisão.",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(header, textvariable=self.running_var, command=self._toggle).grid(row=0, column=1, padx=4)
        ttk.Button(header, text="Capturar agora", command=self._capture_once).grid(row=0, column=2, padx=4)
        ttk.Button(header, text="Minimizar", command=self.root.iconify).grid(row=0, column=3, padx=4)
        ttk.Button(header, text="Salvar", command=self._save_dialog).grid(row=0, column=4, padx=4)

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        preview_frame = ttk.LabelFrame(
            body,
            text="Shinobi Story Online — grid calibrado + classificação e confiança por tile",
            padding=6,
        )
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(preview_frame, background="#111111", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", lambda _event: self._redraw_preview())
        self.preview_canvas.bind("<Button-1>", self._select_from_preview)
        ttk.Label(
            preview_frame,
            text=(
                ". chão  # parede  J jutsu  B bloqueio  P jogador  N NPC  "
                "T transição  ! perigo  I ignorar  ? desconhecido — clique em uma célula para inspecionar"
            ),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        body.add(preview_frame, weight=4)

        right = ttk.Frame(body, padding=(8, 0, 0, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        body.add(right, weight=2)

        stats_frame = ttk.LabelFrame(right, text="Estado contínuo", padding=8)
        stats_frame.grid(row=0, column=0, sticky="ew")
        ttk.Label(stats_frame, textvariable=self.stats_var, justify="left", wraplength=470).grid(sticky="w")

        queue_frame = ttk.LabelFrame(right, text="Grupos desconhecidos — revise com F7", padding=8)
        queue_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)
        self.group_list = tk.Listbox(queue_frame, exportselection=False, font=("Consolas", 10))
        self.group_list.grid(row=0, column=0, sticky="nsew")
        queue_scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self.group_list.yview)
        queue_scroll.grid(row=0, column=1, sticky="ns")
        self.group_list.configure(yscrollcommand=queue_scroll.set)
        self.group_list.bind("<<ListboxSelect>>", self._select_group)

        selected_frame = ttk.LabelFrame(right, text="Exemplo representativo", padding=8)
        selected_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        selected_frame.columnconfigure(0, weight=1)
        self.crop_label = ttk.Label(selected_frame, anchor="center")
        self.crop_label.grid(row=0, column=0, sticky="ew")
        ttk.Label(selected_frame, textvariable=self.selected_var, justify="left", wraplength=470).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        teaching = ttk.LabelFrame(right, text="Ensinar grupo", padding=8)
        teaching.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        teaching.columnconfigure(0, weight=1)
        teaching.columnconfigure(1, weight=1)
        categories = [
            TileClass.WALKABLE,
            TileClass.WALL,
            TileClass.WALKABLE_WITH_JUTSU,
            TileClass.BLOCKING_OBJECT,
            TileClass.PLAYER,
            TileClass.NPC,
            TileClass.TRANSITION,
            TileClass.DANGER,
            TileClass.IGNORE_DYNAMIC,
        ]
        for index, category in enumerate(categories):
            ttk.Button(
                teaching,
                text=TILE_CLASS_LABELS_PT_BR[category],
                command=lambda selected=category: self._teach_selected(selected),
            ).grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 4) if index % 2 == 0 else (4, 0),
                pady=3,
                ipady=2,
            )

        ttk.Label(self.root, textvariable=self.status_var, padding=(8, 5), anchor="w").grid(
            row=2, column=0, sticky="ew"
        )

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self.running_var.set("Pausar")
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._worker_loop, name="continuous-semantic-mapper", daemon=True)
            self._worker.start()
        self.status_var.set("Mapeamento contínuo ativo. F7 abre a revisão; nenhuma pergunta será exibida sobre o jogo.")

    def pause(self) -> None:
        self._running.clear()
        self.running_var.set("Continuar")
        self.status_var.set("Mapeamento pausado. O mapa e a fila permanecem salvos.")

    def _toggle(self) -> None:
        self.pause() if self._running.is_set() else self.start()

    def _worker_loop(self) -> None:
        while not self._closing.is_set():
            if not self._running.wait(timeout=0.10):
                continue
            started = time.monotonic()
            self._capture_and_process(require_foreground=True)
            delay = max(0.05, self.capture_interval - (time.monotonic() - started))
            self._closing.wait(delay)

    def _capture_once(self) -> None:
        threading.Thread(
            target=lambda: self._capture_and_process(require_foreground=False),
            name="continuous-manual-capture",
            daemon=True,
        ).start()

    def _capture_and_process(self, require_foreground: bool) -> None:
        try:
            frame, bounds = self.capture.capture()
            if require_foreground and not bounds.foreground:
                self._events.put(("status", "Pausado automaticamente: o jogo não está em primeiro plano."))
                return
            with self._engine_lock:
                result = self.mapper.process_frame(frame)
                self._persist_unknown_crops()
                self._save_state()
            self._events.put(("result", (result, bounds.capture_backend)))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    def _persist_unknown_crops(self) -> None:
        for group in self.mapper.review_queue.groups.values():
            if group.crop_path or group.representative_image is None:
                continue
            path = self.repository.save_unknown_group_crop(
                self.region_id,
                group.id,
                group.representative_image,
            )
            group.crop_path = str(path)

    def _load_unknown_group_images(self) -> None:
        import cv2

        for group in self.mapper.review_queue.groups.values():
            if group.representative_image is not None or not group.crop_path:
                continue
            path = Path(group.crop_path)
            if path.is_file():
                group.representative_image = cv2.imread(str(path), cv2.IMREAD_COLOR)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "result":
                    result, backend = payload
                    self.status_var.set(
                        f"Frame {result.frame_index} processado por {backend}; localização={result.localization_reason}."
                    )
                    self._refresh_all(result)
                elif kind == "show":
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
                    self.status_var.set("Revisão aberta por F7. O mapeamento pausa enquanto o jogo perde o foco.")
                    self._refresh_all()
                elif kind == "status":
                    self.status_var.set(str(payload))
                else:
                    self.status_var.set(f"Erro: {payload}")
        except queue.Empty:
            pass
        if not self._closing.is_set():
            self.root.after(60, self._poll_events)

    def _refresh_all(self, result: ContinuousMappingResult | None = None) -> None:
        result = result or self.mapper.last_result
        player = self.mapper.player_world
        bounds = self.mapper.world.bounds()
        dimensions = "0×0"
        if bounds is not None:
            dimensions = f"{bounds[2] - bounds[0] + 1}×{bounds[3] - bounds[1] + 1}"
        lines = [
            f"Rodando: {'sim' if self._running.is_set() else 'não'}",
            f"Frames processados: {self.mapper.frame_index}",
            f"Jogador mundial: {player if player is not None else 'não localizado'}",
            f"Tiles de terreno: {self.mapper.world.terrain_count}",
            f"Área observada: {dimensions}",
            f"Grupos desconhecidos: {len(self.mapper.review_queue.groups)}",
            f"Conflitos semânticos: {self.mapper.world.conflict_count}",
            f"Grid visual: {self.mapper.calibration.tile_size_px}×{self.mapper.calibration.tile_size_px} px",
        ]
        if result is not None:
            lines.extend(
                [
                    f"Último frame estável: {'sim' if result.settled else 'não — aguardando a câmera parar'}",
                    f"Confirmados ≥ {self.mapper.auto_threshold:.0%}: {result.confirmed_cells}",
                    f"Provisórios ≥ {self.mapper.review_threshold:.0%}: {result.provisional_cells}",
                    f"Desconhecidos < {self.mapper.review_threshold:.0%}: {result.unknown_cells}",
                ]
            )
        self.stats_var.set("\n".join(lines))
        self._refresh_group_list()
        self._redraw_preview(result)

    def _redraw_preview(self, result: ContinuousMappingResult | None = None) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        result = result or self.mapper.last_result
        self.preview_canvas.delete("all")
        if result is None:
            width = max(1, self.preview_canvas.winfo_width())
            height = max(1, self.preview_canvas.winfo_height())
            self.preview_canvas.create_text(
                width // 2,
                height // 2,
                text="Aguardando a primeira captura do Shinobi Story Online...",
                fill="#e8e8e8",
                font=("Segoe UI", 12, "bold"),
            )
            return

        import cv2
        from PIL import Image, ImageTk

        rendered = render_tile_classification_overlay(
            result.scan,
            selected_cell_id=self._selected_cell_id,
            auto_threshold=self.mapper.auto_threshold,
            review_threshold=self.mapper.review_threshold,
        )
        rgb = cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        canvas_width = max(1, self.preview_canvas.winfo_width())
        canvas_height = max(1, self.preview_canvas.winfo_height())
        scale = min(canvas_width / image.width, canvas_height / image.height)
        display_width = max(1, int(image.width * scale))
        display_height = max(1, int(image.height * scale))
        image = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        self._frame_photo = ImageTk.PhotoImage(image)
        self._display_scale = scale
        self._display_width = display_width
        self._display_height = display_height
        self._display_left = (canvas_width - display_width) / 2.0
        self._display_top = (canvas_height - display_height) / 2.0
        self.preview_canvas.create_image(
            self._display_left,
            self._display_top,
            image=self._frame_photo,
            anchor="nw",
        )

    def _select_from_preview(self, event: tk.Event[Any]) -> None:
        result = self.mapper.last_result
        if result is None or self._display_scale <= 0:
            return
        local_x = event.x - self._display_left
        local_y = event.y - self._display_top
        if not (0 <= local_x < self._display_width and 0 <= local_y < self._display_height):
            return
        source_x = int(local_x / self._display_scale)
        source_y = int(local_y / self._display_scale)
        cell = result.scan.find_at(source_x, source_y)
        if cell is None:
            return

        self._selected_cell_id = cell.crop.id
        category = display_category(cell)
        primary, _secondary = tile_overlay_text(cell)
        self.status_var.set(
            f"Tile {cell.crop.id}: {TILE_CLASS_LABELS_PT_BR[category]} — {primary}; "
            f"área=({cell.crop.x0},{cell.crop.y0})–({cell.crop.x1},{cell.crop.y1})."
        )

        matches = [
            group
            for group in self.mapper.review_queue.groups.values()
            if group.latest_screen_cell == cell.crop.id
        ]
        if matches:
            group = max(matches, key=lambda item: item.last_seen_frame)
            self._selected_group_id = group.id
            self._refresh_group_list()
        else:
            self._redraw_preview(result)

    def _refresh_group_list(self) -> None:
        previous = self._selected_group_id
        groups = self.mapper.review_queue.sorted_groups()
        self._group_ids = [group.id for group in groups]
        self.group_list.delete(0, "end")
        selected_index: int | None = None
        for index, group in enumerate(groups):
            self.group_list.insert(
                "end",
                f"{group.id[:8]}  ocorrências={group.count:4d}  melhor={group.best_similarity:.1%}",
            )
            if group.id == previous:
                selected_index = index
        if selected_index is not None:
            self.group_list.selection_set(selected_index)
            self.group_list.activate(selected_index)
        elif groups:
            self.group_list.selection_set(0)
            self.group_list.activate(0)
            self._selected_group_id = groups[0].id
        else:
            self._selected_group_id = None
        self._refresh_selected_group()

    def _select_group(self, _event: Any) -> None:
        selected = self.group_list.curselection()
        if not selected:
            return
        index = int(selected[0])
        if 0 <= index < len(self._group_ids):
            self._selected_group_id = self._group_ids[index]
            self._refresh_selected_group()

    def _selected_group(self) -> UnknownTileGroup | None:
        if self._selected_group_id is None:
            return None
        return self.mapper.review_queue.groups.get(self._selected_group_id)

    def _refresh_selected_group(self) -> None:
        group = self._selected_group()
        if group is None:
            self.crop_label.configure(image="")
            self.selected_var.set("Nenhum grupo desconhecido pendente.")
            self._redraw_preview()
            return
        self._selected_cell_id = group.latest_screen_cell
        image = group.representative_image
        if image is not None:
            import cv2
            from PIL import Image, ImageTk

            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            rendered = Image.fromarray(rgb).resize((224, 224), Image.Resampling.NEAREST)
            self._crop_photo = ImageTk.PhotoImage(rendered)
            self.crop_label.configure(image=self._crop_photo)
        else:
            self.crop_label.configure(image="")
        self.selected_var.set(
            "\n".join(
                [
                    f"Grupo: {group.id}",
                    f"Ocorrências agrupadas: {group.count}",
                    f"Melhor similaridade conhecida: {group.best_similarity:.1%}",
                    f"Última célula da tela: {group.latest_screen_cell}",
                    "Uma resposta ensina todo o grupo visualmente semelhante.",
                ]
            )
        )
        self._redraw_preview()

    def _teach_selected(self, category: TileClass) -> None:
        group = self._selected_group()
        if group is None:
            messagebox.showwarning("Kage Continuous Mapper", "Selecione um grupo desconhecido.")
            return
        try:
            with self._engine_lock:
                image = group.representative_image
                example = self.mapper.teach_group(group.id, category)
                if image is not None:
                    path = self.repository.save_tile_example_crop(self.region_id, example.id, image)
                    example.crop_path = str(path)
                self.repository.save_tile_knowledge(self.region_id, self.mapper.knowledge.to_dict())
                self._save_state()
            self._selected_group_id = None
            self._selected_cell_id = None
            self.status_var.set(
                f"Grupo ensinado como {TILE_CLASS_LABELS_PT_BR[category]}. Próximas capturas serão reclassificadas."
            )
            self._refresh_all()
        except Exception as exc:
            messagebox.showerror("Kage Continuous Mapper", str(exc))

    def _save_state(self) -> None:
        self.repository.save_continuous_mapping(self.region_id, self.mapper.to_dict())
        self.repository.save_tile_knowledge(self.region_id, self.mapper.knowledge.to_dict())

    def _save_dialog(self) -> None:
        with self._engine_lock:
            self._persist_unknown_crops()
            self._save_state()
        path = self.repository.continuous_mapping_path(self.region_id)
        messagebox.showinfo("Kage Continuous Mapper", f"Mapa contínuo salvo em:\n{path}")

    def _close(self) -> None:
        self._closing.set()
        self._running.clear()
        try:
            with self._engine_lock:
                self._persist_unknown_crops()
                self._save_state()
        finally:
            self._review_hotkey.stop()
            self.capture.close()
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
