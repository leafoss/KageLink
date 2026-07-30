"""Canonical Kage Pilot Dojo loop boundary.

The validated request, dialog and combat providers remain unchanged. KageLink 3.5.1
adds a sidecar visual monitor that captures the confirmed Trainer anchor before combat
and transfers position/keyframes into the isolated round process.
"""

from __future__ import annotations

from pathlib import Path

import kage_pilot_loop_v03j as _validated_engine

from pc_agent.kage_pilot.dojo_anchor_monitor_compat_v351 import (
    install_anchor_monitor_tracker_compat,
)
from pc_agent.kage_pilot.dojo_position_bridge import (
    DojoAnchorMonitor,
    restore_tracker_state,
)
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
    def confirm_click(self, click_target) -> bool:
        preserved = tuple(self.tracker.keyframes)
        confirmed = super().confirm_click(click_target)
        if confirmed and preserved:
            merge_nonorigin_keyframes(self.tracker, preserved)
        return confirmed


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
        restored = restore_tracker_state(monitor.tracker, _SESSION_STATE_PATH)
        snapshot = monitor.tracker.snapshot()
        _telemetry(
            "DOJO_SESSION_MAP_RESTORED" if restored else "DOJO_SESSION_MAP_RESTORE_FAILED",
            {
                "path": str(_SESSION_STATE_PATH),
                "x": f"{snapshot.x:.4f}",
                "y": f"{snapshot.y:.4f}",
                "state": snapshot.state.value,
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
    _validated_engine.request_taijutsu_dojo_spar_single_click = _request_with_position_bridge
    _validated_engine._round_command = _round_command_with_position_bridge
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
