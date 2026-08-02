from pathlib import Path

import numpy as np

from kage_combat_lab.domain import CombatDecision, GridCell, TargetState
from kage_combat_lab.event_recorder import CombatEventVideoRecorder


def decision() -> CombatDecision:
    return CombatDecision(
        frame_index=1,
        target_state=TargetState.REID_LOCAL,
        combat_target_id=1,
        visual_track_id=None,
        confirmed_cell=GridCell(1, 0),
        predicted_cell=GridCell(1, 0),
        grid_distance=1,
        face="RIGHT",
        move=None,
        move_pulse_profile=None,
        move_pulse_ms=None,
        post_pulse_observe_ms=150,
        hold_r=True,
        r_keydown_heartbeat_ms=250,
        press_h=False,
        h_pulse_ms=None,
        h_cooldown_remaining_seconds=1.0,
        identity_score=0.7,
        appearance_score=0.7,
        background_probability=0.1,
        reidentified=False,
        aim_requires_confirmation=False,
        action_sequence=(),
        reason="event test",
    )


def test_event_recorder_keeps_pre_and_post_frames_without_codec_dependency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recorder = CombatEventVideoRecorder(
        tmp_path,
        fps=2.0,
        pre_seconds=1.0,
        post_seconds=1.0,
    )
    written = []
    monkeypatch.setattr(recorder, "_write_clip", written.append)
    frame = np.zeros((80, 120, 3), dtype=np.uint8)

    recorder.push(frame, decision=decision(), candidate=None, actions=(), timestamp=1.0)
    recorder.push(frame, decision=decision(), candidate=None, actions=(), timestamp=1.5)
    recorder.push(
        frame,
        decision=decision(),
        candidate=None,
        actions=(),
        events=("TARGET_HARD_LOST",),
        timestamp=2.0,
    )
    recorder.push(frame, decision=decision(), candidate=None, actions=(), timestamp=2.5)
    recorder.push(frame, decision=decision(), candidate=None, actions=(), timestamp=3.0)

    assert len(written) == 1
    assert written[0].event == "TARGET_HARD_LOST"
    assert len(written[0].frames) >= 5
