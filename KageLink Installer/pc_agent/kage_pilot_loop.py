"""Canonical Kage Pilot Dojo loop boundary.

The validated request, dialog and combat providers remain unchanged. KageLink 3.5.1
adds resolution-independent Trainer calibration plus a sidecar visual monitor that
transfers position/keyframes into the isolated round process.
"""

from __future__ import annotations

from pathlib import Path

import kage_pilot_loop_v03j as _validated_engine

from pc_agent.kage_pilot.dojo_resolution_bridge_v351 import (
    apply_tracker_geometry,
    geometry_cli_args,
    install_resolution_independent_dojo,
    read_dojo_geometry,
    reset_dojo_geometry,
    restore_tracker_state_resolution_safe,
)
from pc_agent.kage_pilot.dojo_resolution_gate_compat_v351 import (
    install_resolution_gate_slots_compat,
)

# This must run before DojoAnchorMonitor imports direct detector/decoder aliases.
install_resolution_independent_dojo()
install_resolution_gate_slots_compat()

from pc_agent.kage_pilot.dojo_anchor_monitor_compat_v351 import (
    install_anchor_monitor_tracker_compat,
)
from pc_agent.kage_pilot.dojo_position_bridge import DojoAnchorMonitor
from pc_agent.kage_pilot.position_map_continuity import merge_nonorigin_keyframes
from pc_agent.kage_pilot.visual_position_guard import install_visual_position_guard


install_visual_position_guard()
install_anchor_monitor_tracker_compat()

# Compatibility handles retained for established packaged-runtime tests and callers.
sys = _validated_engine.sys
subprocess = _validated_engine.subprocess

_ORIGINAL_REQUEST = _validated_engine.request_taijutsu_dojo_spar_single_click
_ORIGINAL_ROUND_COMMAND = _validated_engine._round_command
_ACTIVE_MONITOR: DojoAnchorMonitor | None = None
_SESSION_STATE_PATH: Path | None = None


def _telemetry(event: str, fields: dict[str, object]) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    print(f"{event}{(' ' + suffix) if suffix else ''}")


class _SessionAnchorMonitor(DojoAnchorMonitor):
    """Anchor with the measured tile size instead of the nominal 32/64 label."""

    def confirm_click(self, click_target) -> bool:
        preserved = tuple(self.tracker.keyframes)
        wanted_bbox = tuple(int(item) for item in click_target.bbox)
        with self._lock:
            candidates = [item for item in self._frames if item.trainer_bbox is not None]
            if not candidates:
                self._emit("DOJO_ANCHOR_CONFIRM_FAILED", {"reason": "no_visual_candidate"})
                return False
            candidate = min(
                candidates,
                key=lambda item: (
                    self._bbox_distance(item.trainer_bbox or wanted_bbox, wanted_bbox),
                    -item.sequence,
                ),
            )
            frame = candidate.frame()
            state = candidate.observer_state()
            mode = candidate.trainer_mode if candidate.trainer_mode in {"32", "64"} else "32"
            geometry = read_dojo_geometry()
            if geometry is not None and geometry.template_mode == mode:
                cell_size = float(geometry.effective_tile_size)
                scale = float(geometry.template_scale)
            else:
                cell_size = float(mode)
                scale = 1.0
            apply_tracker_geometry(self.tracker, cell_size)
            self.tracker.set_anchor(frame, state, mode=mode)
            for item in self._frames:
                if item.sequence <= candidate.sequence:
                    continue
                self.tracker.observe(item.frame(), item.observer_state())
            self._click_confirmed = True
            snapshot = self.tracker.snapshot()
            self._emit(
                "DOJO_CLICK_ANCHOR_CONFIRMED",
                {
                    "mode": mode,
                    "scale": f"{scale:.3f}",
                    "cell_size": f"{cell_size:.3f}",
                    "score": f"{candidate.trainer_score:.3f}",
                    "x": f"{snapshot.x:.4f}",
                    "y": f"{snapshot.y:.4f}",
                    "state": snapshot.state.value,
                    "confidence": f"{snapshot.confidence:.3f}",
                },
            )
        if preserved:
            merge_nonorigin_keyframes(self.tracker, preserved)
        return True


def _request_with_position_bridge(game_title: str, **kwargs):
    global _ACTIVE_MONITOR
    if _ACTIVE_MONITOR is not None:
        _ACTIVE_MONITOR.stop()
        _ACTIVE_MONITOR = None
    monitor = _SessionAnchorMonitor(
        leader_threshold=float(kwargs.get("leader_threshold", 0.88) or 0.88),
        telemetry=_telemetry,
    )
    if _SESSION_STATE_PATH is not None and _SESSION_STATE_PATH.exists():
        restored = restore_tracker_state_resolution_safe(monitor.tracker, _SESSION_STATE_PATH)
        snapshot = monitor.tracker.snapshot()
        _telemetry(
            "DOJO_SESSION_MAP_RESTORED" if restored else "DOJO_SESSION_MAP_RESTORE_FAILED",
            {
                "path": str(_SESSION_STATE_PATH),
                "x": f"{snapshot.x:.4f}",
                "y": f"{snapshot.y:.4f}",
                "state": snapshot.state.value,
                "cell_size": f"{monitor.tracker.cell_size:.3f}",
                "keyframes": snapshot.keyframes,
            },
        )
    monitor.start()
    _ACTIVE_MONITOR = monitor
    try:
        click = _ORIGINAL_REQUEST(game_title, **kwargs)
        monitor.confirm_click(click)
        return click
    except BaseException:
        monitor.stop()
        if _ACTIVE_MONITOR is monitor:
            _ACTIVE_MONITOR = None
        raise


def _round_command_with_position_bridge(args, *, round_number: int):
    global _ACTIVE_MONITOR, _SESSION_STATE_PATH
    command, cwd = _ORIGINAL_ROUND_COMMAND(args, round_number=round_number)

    geometry = read_dojo_geometry()
    extra_args = geometry_cli_args(geometry)
    if extra_args:
        command.extend(extra_args)
        _telemetry(
            "DOJO_ROUND_GEOMETRY",
            {
                "mode": geometry.template_mode,
                "scale": f"{geometry.template_scale:.3f}",
                "cell_size": f"{geometry.effective_tile_size:.3f}",
                "source": f"{geometry.source_width}x{geometry.source_height}",
            },
        )
    else:
        _telemetry("DOJO_ROUND_GEOMETRY_MISSING", {"fallback_cell_size": 32})

    monitor = _ACTIVE_MONITOR
    _ACTIVE_MONITOR = None
    if monitor is None:
        print("DOJO_POSITION_BRIDGE_MISSING reason=no_active_monitor")
        return command, cwd

    if _SESSION_STATE_PATH is None:
        _SESSION_STATE_PATH = Path(args.log_dir) / "dojo_session.position.json"
    saved = monitor.stop_and_save(_SESSION_STATE_PATH)
    if saved is not None:
        command.extend(["--position-state", str(saved)])
    else:
        print("DOJO_POSITION_BRIDGE_MISSING reason=anchor_not_confirmed")
    return command, cwd


def _run_round_with_ko_buffer(args, *, round_number: int) -> bool:
    return _validated_engine._run_round_with_ko_buffer(args, round_number=round_number)


def main() -> int:
    global _ACTIVE_MONITOR, _SESSION_STATE_PATH
    _SESSION_STATE_PATH = None
    reset_dojo_geometry()
    _validated_engine.request_taijutsu_dojo_spar_single_click = _request_with_position_bridge
    _validated_engine._round_command = _round_command_with_position_bridge
    print("RESOLUTION BRIDGE: canonical 960x540 control frame + automatic Trainer scale enabled")
    print("POSITION BRIDGE: click-time anchor and cross-round visual map enabled")
    try:
        return _validated_engine.main()
    finally:
        if _ACTIVE_MONITOR is not None:
            _ACTIVE_MONITOR.stop()
            _ACTIVE_MONITOR = None
        if _SESSION_STATE_PATH is not None:
            try:
                _SESSION_STATE_PATH.unlink(missing_ok=True)
            except Exception:
                pass
            _SESSION_STATE_PATH = None


_round_command = _round_command_with_position_bridge


if __name__ == "__main__":
    raise SystemExit(main())
