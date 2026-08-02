from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from kage_combat_lab import runtime_round_diagnostics as diagnostics_module
from kage_combat_lab.runtime_round_diagnostics import (
    RoundRuntimeDiagnostics,
    _decode_capture,
)


def test_failed_round_writes_console_and_result(tmp_path: Path) -> None:
    diagnostics_module._ACTIVE_RECORDER = None
    with RoundRuntimeDiagnostics(tmp_path) as diagnostics:
        print("FULL ROUND STOPPED / RODADA INTERROMPIDA: RuntimeError: synthetic")
        diagnostics.finish(1)

    console = diagnostics.console_path.read_text(encoding="utf-8")
    result = json.loads(diagnostics.result_path.read_text(encoding="utf-8"))

    assert "FULL ROUND STOPPED" in console
    assert "PR26_ROUND_FAILED_REPORT" in console
    assert result["exit_code"] == 1
    assert result["replay"]["frames"] == 0
    assert result["replay"]["path"] is None


def test_success_result_records_active_replay(tmp_path: Path) -> None:
    diagnostics_module._ACTIVE_RECORDER = SimpleNamespace(
        full_replay_path=tmp_path / "full_combat_replay.avi",
        full_replay_frames=12,
        full_replay_mode="VIDEO",
        full_replay_codec="MJPG",
        writer_errors=("mp4v failed",),
    )
    try:
        with RoundRuntimeDiagnostics(tmp_path) as diagnostics:
            diagnostics.finish(0)
        result = json.loads(
            diagnostics.result_path.read_text(encoding="utf-8")
        )
        assert result["exit_code"] == 0
        assert result["replay"]["frames"] == 12
        assert result["replay"]["mode"] == "VIDEO"
        assert result["replay"]["codec"] == "MJPG"
    finally:
        diagnostics_module._ACTIVE_RECORDER = None


def test_capture_jpeg_can_be_decoded_for_bootstrap_frame() -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    frame[10:20, 12:24] = 255
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok

    decoded = _decode_capture(SimpleNamespace(jpeg=encoded.tobytes()))

    assert decoded is not None
    assert decoded.shape == frame.shape
