from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from kage_combat_lab.event_recorder import CombatEventVideoRecorder


class _FakeWriter:
    def __init__(self, *, opened: bool = True) -> None:
        self.frames: list[np.ndarray] = []
        self.released = False
        self.opened = opened

    def isOpened(self) -> bool:
        return self.opened

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())

    def release(self) -> None:
        self.released = True


def _decision():
    return SimpleNamespace(
        turn_direction=None,
        contact_deadzone_active=False,
        r_authorized=False,
        target_state=SimpleNamespace(value="SEARCH"),
        combat_target_id=None,
        visual_track_id=None,
        grid_distance=None,
        raw_target_bearing=None,
        stable_target_bearing=None,
        commanded_facing=None,
        confirmed_facing=None,
        facing_confidence=0.0,
        turn_attempt=0,
        h_authorized=False,
        orientation_invalidated_reason=None,
        identity_score=0.0,
        appearance_score=0.0,
        background_probability=0.0,
        reidentified=False,
    )


def test_clean_round_without_events_still_records_full_replay(
    monkeypatch,
    tmp_path: Path,
) -> None:
    writer = _FakeWriter()
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter_fourcc",
        lambda *args: 0,
    )

    recorder = CombatEventVideoRecorder(tmp_path, fps=8.0)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    recorder.push(
        frame,
        decision=_decision(),
        candidate=None,
        actions=(),
        events=(),
    )
    recorder.push(
        frame,
        decision=_decision(),
        candidate=None,
        actions=("WAIT",),
        events=(),
    )

    assert recorder.full_replay_path == tmp_path / "full_combat_replay.mp4"
    assert recorder.full_replay_frames == 2
    assert recorder.full_replay_mode == "VIDEO"
    assert recorder.full_replay_codec == "mp4v"
    assert len(writer.frames) == 2

    recorder.close()

    assert writer.released is True
    assert recorder.full_replay_path in recorder.saved_paths


def test_terminal_marker_is_appended_to_full_replay(
    monkeypatch,
    tmp_path: Path,
) -> None:
    writer = _FakeWriter()
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter_fourcc",
        lambda *args: 0,
    )

    recorder = CombatEventVideoRecorder(tmp_path, fps=4.0)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    recorder.push(
        frame,
        decision=_decision(),
        candidate=None,
        actions=(),
    )

    recorder.mark_terminal_event("VICTORY_CHAT", seconds=1.0)

    assert recorder.full_replay_frames == 5
    assert len(writer.frames) == 5
    assert np.any(writer.frames[-1] != writer.frames[0])

    recorder.close()


def test_second_replay_uses_collision_safe_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "full_combat_replay.mp4").write_bytes(b"existing")
    writer = _FakeWriter()
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter",
        lambda *args, **kwargs: writer,
    )
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter_fourcc",
        lambda *args: 0,
    )

    recorder = CombatEventVideoRecorder(tmp_path)
    recorder.push(
        np.zeros((64, 64, 3), dtype=np.uint8),
        decision=_decision(),
        candidate=None,
        actions=(),
    )

    assert recorder.full_replay_path == tmp_path / "full_combat_replay_2.mp4"
    recorder.close()


def test_windows_codec_fallback_can_open_avi(
    monkeypatch,
    tmp_path: Path,
) -> None:
    writers = [
        _FakeWriter(opened=False),
        _FakeWriter(opened=False),
        _FakeWriter(opened=True),
    ]

    def writer_factory(*args, **kwargs):
        return writers.pop(0)

    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter",
        writer_factory,
    )
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter_fourcc",
        lambda *args: 0,
    )

    recorder = CombatEventVideoRecorder(tmp_path)
    recorder.push(
        np.zeros((64, 64, 3), dtype=np.uint8),
        decision=_decision(),
        candidate=None,
        actions=(),
    )

    assert recorder.full_replay_mode == "VIDEO"
    assert recorder.full_replay_codec == "XVID"
    assert recorder.full_replay_path is not None
    assert recorder.full_replay_path.suffix == ".avi"
    recorder.close()


def test_all_codec_failures_fall_back_to_png_sequence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter",
        lambda *args, **kwargs: _FakeWriter(opened=False),
    )
    monkeypatch.setattr(
        "kage_combat_lab.event_recorder.cv2.VideoWriter_fourcc",
        lambda *args: 0,
    )

    recorder = CombatEventVideoRecorder(tmp_path, fps=3.0)
    recorder.push(
        np.zeros((121, 161, 3), dtype=np.uint8),
        decision=_decision(),
        candidate=None,
        actions=(),
    )
    recorder.mark_terminal_event("TIMEOUT", seconds=1.0)
    recorder.close()

    assert recorder.full_replay_mode == "PNG_SEQUENCE"
    assert recorder.full_replay_codec == "PNG"
    assert recorder.full_replay_path is not None
    assert recorder.full_replay_path.is_dir()

    first = recorder.full_replay_path / "frame_000000.png"
    manifest_path = recorder.full_replay_path / "replay_manifest.json"
    assert first.exists()
    assert manifest_path.exists()

    image = cv2.imread(str(first))
    assert image is not None
    assert image.shape[:2] == (122, 162)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["format"] == "PNG_SEQUENCE"
    assert manifest["frames"] == recorder.full_replay_frames
    assert len(manifest["writer_errors"]) == 4
