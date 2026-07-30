from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import threading
import time
from typing import Any


@dataclass(frozen=True, slots=True)
class DojoDebugSettings:
    enabled: bool = False
    opacity: float = 0.82
    fps: float = 15.0
    level: str = "detections"
    meditation_enter_delay_seconds: float = 5.5
    meditation_exit_delay_seconds: float = 5.5
    meditation_timeout_seconds: float = 120.0

    def normalized(self) -> "DojoDebugSettings":
        level = str(self.level or "detections").strip().lower()
        if level not in {"basic", "detections", "processed"}:
            level = "detections"
        return replace(
            self,
            enabled=bool(self.enabled),
            opacity=max(0.25, min(1.0, float(self.opacity))),
            fps=max(5.0, min(30.0, float(self.fps))),
            level=level,
            meditation_enter_delay_seconds=max(
                5.0, min(30.0, float(self.meditation_enter_delay_seconds))
            ),
            meditation_exit_delay_seconds=max(
                5.0, min(30.0, float(self.meditation_exit_delay_seconds))
            ),
            meditation_timeout_seconds=max(
                15.0, min(1800.0, float(self.meditation_timeout_seconds))
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_dict(cls, payload: Any) -> "DojoDebugSettings":
        if not isinstance(payload, dict):
            return cls()
        defaults = cls()

        def number(key: str, fallback: float) -> float:
            try:
                return float(payload.get(key, fallback))
            except (TypeError, ValueError):
                return fallback

        enabled = payload.get("enabled", defaults.enabled)
        if not isinstance(enabled, bool):
            enabled = defaults.enabled
        return cls(
            enabled=enabled,
            opacity=number("opacity", defaults.opacity),
            fps=number("fps", defaults.fps),
            level=str(payload.get("level", defaults.level) or defaults.level),
            meditation_enter_delay_seconds=number(
                "meditation_enter_delay_seconds", defaults.meditation_enter_delay_seconds
            ),
            meditation_exit_delay_seconds=number(
                "meditation_exit_delay_seconds", defaults.meditation_exit_delay_seconds
            ),
            meditation_timeout_seconds=number(
                "meditation_timeout_seconds", defaults.meditation_timeout_seconds
            ),
        ).normalized()


def canonical_debug_control_path() -> Path:
    local = str(os.getenv("LOCALAPPDATA") or "").strip()
    root = Path(local) if local else Path.home() / ".kagelink"
    return root / "KageLink" / "dojo_debug_v351.json"


def read_debug_settings(path: str | Path | None = None) -> DojoDebugSettings:
    source = Path(path) if path is not None else canonical_debug_control_path()
    try:
        return DojoDebugSettings.from_dict(
            json.loads(source.read_text(encoding="utf-8"))
        )
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return DojoDebugSettings()


def write_debug_settings(
    settings: DojoDebugSettings,
    path: str | Path | None = None,
) -> Path:
    destination = Path(path) if path is not None else canonical_debug_control_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(settings.normalized().to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


@dataclass(frozen=True, slots=True)
class DojoDebugSnapshot:
    timestamp: float
    trainer_state: str
    round_current: int = 0
    round_total: int = 0
    hp: float | None = None
    chakra: float | None = None
    meditation_state: str = "IDLE"
    meditation_elapsed: float = 0.0
    v_cooldown_remaining: float = 0.0
    position_state: str = "LOST"
    position_x: float = 0.0
    position_y: float = 0.0
    position_confidence: float = 0.0
    trainer_box: tuple[int, int, int, int] | None = None
    arena_rect: tuple[int, int, int, int] | None = None
    player_point: tuple[float, float] | None = None
    frame_size: tuple[int, int] = (960, 540)
    last_action: str = ""
    next_action: str = ""
    blocked_reason: str = ""
    combat_start_allowed: bool = False


class DojoDebugOverlay:
    """Windows click-through overlay fed only by immutable debug snapshots."""

    _TRANSPARENT = "#010101"

    def __init__(self, *, control_path: str | Path | None = None) -> None:
        self.control_path = (
            Path(control_path)
            if control_path is not None
            else canonical_debug_control_path()
        )
        self._lock = threading.Lock()
        self._snapshot: DojoDebugSnapshot | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_settings_read = -1e9
        self._settings = read_debug_settings(self.control_path)
        self._f10_down = False
        self.capture_exclusion_enabled = False

    @classmethod
    def from_environment(cls) -> "DojoDebugOverlay":
        path = str(os.getenv("KAGELINK_DOJO_DEBUG_CONTROL") or "").strip()
        return cls(control_path=path or None)

    def start(self) -> bool:
        if os.name != "nt":
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="dojo-debug-overlay-v351",
            daemon=True,
        )
        self._thread.start()
        return True

    def publish(self, snapshot: DojoDebugSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def close(self) -> None:
        self._stop.set()

    def _current_snapshot(self) -> DojoDebugSnapshot | None:
        with self._lock:
            return self._snapshot

    def _refresh_settings(self, now: float) -> DojoDebugSettings:
        if now - self._last_settings_read >= 0.5:
            self._settings = read_debug_settings(self.control_path)
            self._last_settings_read = now
        return self._settings

    def _toggle_from_f10(self) -> None:
        import ctypes

        down = bool(ctypes.windll.user32.GetAsyncKeyState(0x79) & 0x8000)
        if down and not self._f10_down:
            self._settings = replace(
                self._settings,
                enabled=not self._settings.enabled,
            ).normalized()
            write_debug_settings(self._settings, self.control_path)
            self._last_settings_read = time.monotonic()
        self._f10_down = down

    def _apply_window_style(self, root) -> None:
        import ctypes

        hwnd = int(root.winfo_id())
        user32 = ctypes.windll.user32
        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        ex_style = int(get_long(hwnd, -20))
        ex_style |= 0x00080000  # WS_EX_LAYERED
        ex_style |= 0x00000020  # WS_EX_TRANSPARENT
        ex_style |= 0x00000080  # WS_EX_TOOLWINDOW
        ex_style |= 0x08000000  # WS_EX_NOACTIVATE
        set_long(hwnd, -20, ex_style)
        try:
            self.capture_exclusion_enabled = bool(
                user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
            )
        except Exception:
            self.capture_exclusion_enabled = False

    @staticmethod
    def _scaled_rect(
        rect: tuple[int, int, int, int] | None,
        frame_size: tuple[int, int],
        target_size: tuple[int, int],
    ) -> tuple[float, float, float, float] | None:
        if rect is None:
            return None
        fw, fh = frame_size
        tw, th = target_size
        if fw <= 0 or fh <= 0 or tw <= 0 or th <= 0:
            return None
        x, y, w, h = rect
        sx = tw / fw
        sy = th / fh
        return x * sx, y * sy, (x + w) * sx, (y + h) * sy

    @staticmethod
    def _percent(value: float | None) -> str:
        return "—" if value is None else f"{max(0.0, min(1.0, value)) * 100:.0f}%"

    def _draw(self, canvas, snapshot: DojoDebugSnapshot, width: int, height: int, level: str) -> None:
        canvas.delete("all")
        frame_size = snapshot.frame_size
        arena = self._scaled_rect(snapshot.arena_rect, frame_size, (width, height))
        trainer = self._scaled_rect(snapshot.trainer_box, frame_size, (width, height))
        if level in {"detections", "processed"} and arena is not None:
            canvas.create_rectangle(*arena, outline="#4f8f62", width=1, dash=(5, 4))
        if trainer is not None:
            canvas.create_rectangle(*trainer, outline="#8df0a9", width=2)
            canvas.create_text(
                trainer[0] + 4,
                max(10, trainer[1] - 10),
                anchor="sw",
                fill="#8df0a9",
                text="DOJO TRAINER",
                font=("Consolas", 9, "bold"),
            )
        if snapshot.player_point is not None and level in {"detections", "processed"}:
            fw, fh = frame_size
            px = snapshot.player_point[0] * width / max(1, fw)
            py = snapshot.player_point[1] * height / max(1, fh)
            canvas.create_oval(px - 5, py - 5, px + 5, py + 5, outline="#f1d36b", width=2)

        blocked = snapshot.blocked_reason or "—"
        gate = "ALLOWED" if snapshot.combat_start_allowed else "BLOCKED"
        lines = [
            f"State: {snapshot.trainer_state}",
            f"Meditation: {snapshot.meditation_state}  {snapshot.meditation_elapsed:.1f}s",
            f"HP: {self._percent(snapshot.hp)}  Chakra: {self._percent(snapshot.chakra)}",
            f"V cooldown: {snapshot.v_cooldown_remaining:.1f}s",
            f"Position: {snapshot.position_state} x={snapshot.position_x:.2f} y={snapshot.position_y:.2f}",
            f"Confidence: {snapshot.position_confidence:.0%}",
            f"Combat start: {gate}",
            f"Next: {snapshot.next_action or '—'}",
            f"Blocked: {blocked}",
            "F10: toggle visual debug",
        ]
        panel_width = min(width - 20, 430)
        panel_height = 22 + len(lines) * 17
        canvas.create_rectangle(
            10,
            10,
            10 + panel_width,
            10 + panel_height,
            fill="#102018",
            outline="#4f8f62",
            width=1,
        )
        canvas.create_text(
            20,
            20,
            anchor="nw",
            fill="#e7f3e9",
            text="\n".join(lines),
            font=("Consolas", 10),
        )

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.configure(bg=self._TRANSPARENT)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", self._TRANSPARENT)
        canvas = tk.Canvas(
            root,
            bg=self._TRANSPARENT,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        root.update_idletasks()
        self._apply_window_style(root)

        def tick() -> None:
            if self._stop.is_set():
                root.destroy()
                return
            now = time.monotonic()
            self._toggle_from_f10()
            settings = self._refresh_settings(now)
            snapshot = self._current_snapshot()
            try:
                from pc_agent.game_window import locate_capture_target

                target = locate_capture_target()
            except Exception:
                target = None
            if not settings.enabled or snapshot is None or target is None or target.minimized:
                root.withdraw()
            else:
                root.geometry(f"{target.width}x{target.height}+{target.left}+{target.top}")
                root.attributes("-alpha", settings.opacity)
                root.deiconify()
                root.lift()
                self._draw(
                    canvas,
                    snapshot,
                    target.width,
                    target.height,
                    settings.level,
                )
            delay_ms = max(33, int(round(1000.0 / settings.fps)))
            root.after(delay_ms, tick)

        root.after(0, tick)
        root.mainloop()
