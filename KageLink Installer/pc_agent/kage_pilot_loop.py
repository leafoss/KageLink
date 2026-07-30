"""Canonical Kage Pilot Dojo loop boundary.

The validated request, dialog and combat providers remain unchanged. KageLink 3.5.1
adds a sidecar visual monitor that captures the confirmed Trainer anchor before combat
and transfers position/keyframes into the isolated round process.
"""

from __future__ import annotations

from pathlib import Path

import kage_pilot_loop_v03j as _validated_engine

from pc_agent.kage_pilot.dojo_position_bridge import DojoAnchorMonitor
from pc_agent.kage_pilot.visual_position_guard import install_visual_position_guard


install_visual_position_guard()

# Compatibility handles retained for the established packaged-runtime tests and callers.
sys = _validated_engine.sys
subprocess = _validated_engine.subprocess

_ORIGINAL_REQUEST = _validated_engine.request_taijutsu_dojo_spar_single_click
_ORIGINAL_ROUND_COMMAND = _validated_engine._round_command
_ACTIVE_MONITOR: DojoAnchorMonitor | None = None


def _telemetry(event: str, fields: dict[str, object]) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    print(f"{event}{(' ' + suffix) if suffix else ''}")


def _request_with_position_bridge(game_title: str, **kwargs):
    global _ACTIVE_MONITOR
    if _ACTIVE_MONITOR is not None:
        _ACTIVE_MONITOR.stop()
        _ACTIVE_MONITOR = None
    monitor = DojoAnchorMonitor(
        leader_threshold=float(kwargs.get("leader_threshold", 0.88) or 0.88),
        telemetry=_telemetry,
    ).start()
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
    global _ACTIVE_MONITOR
    command, cwd = _ORIGINAL_ROUND_COMMAND(args, round_number=round_number)
    monitor = _ACTIVE_MONITOR
    _ACTIVE_MONITOR = None
    if monitor is None:
        print("DOJO_POSITION_BRIDGE_MISSING reason=no_active_monitor")
        return command, cwd

    path = Path(args.log_dir) / f"round_{round_number:03d}.position.json"
    saved = monitor.stop_and_save(path)
    if saved is not None:
        command.extend(["--position-state", str(saved)])
    else:
        print("DOJO_POSITION_BRIDGE_MISSING reason=anchor_not_confirmed")
    return command, cwd


def _run_round_with_ko_buffer(args, *, round_number: int) -> bool:
    return _validated_engine._run_round_with_ko_buffer(args, round_number=round_number)


def main() -> int:
    _validated_engine.request_taijutsu_dojo_spar_single_click = _request_with_position_bridge
    _validated_engine._round_command = _round_command_with_position_bridge
    print("POSITION BRIDGE: click-time anchor and transition keyframes enabled")
    return _validated_engine.main()


_round_command = _round_command_with_position_bridge


if __name__ == "__main__":
    raise SystemExit(main())
