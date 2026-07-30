from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time

import cv2

from .dojo_fight_v03e import DojoFightRequestError, TrainerClickTarget, f12_pressed
from .dojo_fight_v03f import _click_target_from_match


@dataclass(slots=True)
class TrainerSearchMotionGate:
    """Keep trainer acquisition stationary long enough for stable visual confirmation.

    The search is deliberately pulse-based. It never holds a direction and every
    movement is followed by a stationary visual dwell.
    """

    initial_scan_seconds: float = 1.50
    reveal_scan_seconds: float = 0.75
    post_move_scan_seconds: float = 0.35
    reveal_direction: str = "right"

    started_at: float | None = None
    hold_until: float = -1e9
    hold_phase: str = "INITIAL"
    reveal_sent: bool = False

    def __post_init__(self) -> None:
        self.initial_scan_seconds = max(0.50, min(5.0, float(self.initial_scan_seconds)))
        self.reveal_scan_seconds = max(0.25, min(3.0, float(self.reveal_scan_seconds)))
        self.post_move_scan_seconds = max(0.15, min(1.5, float(self.post_move_scan_seconds)))
        direction = str(self.reveal_direction or "right").strip().lower()
        self.reveal_direction = direction if direction in {"left", "right"} else "right"

    def begin(self, *, now: float) -> None:
        if self.started_at is not None:
            return
        self.started_at = float(now)
        self.hold_until = float(now) + self.initial_scan_seconds
        self.hold_phase = "INITIAL"

    def next_action(self, *, now: float) -> tuple[str, str | None]:
        now = float(now)
        self.begin(now=now)

        if now < self.hold_until:
            return f"{self.hold_phase}_SCAN_HOLD", None

        if not self.reveal_sent:
            self.reveal_sent = True
            self.hold_until = now + self.reveal_scan_seconds
            self.hold_phase = "REVEAL"
            return "SELF_OCCLUSION_REVEAL", self.reveal_direction

        return "SEARCH_ALLOWED", None

    def record_search_move(self, *, now: float) -> None:
        self.hold_until = float(now) + self.post_move_scan_seconds
        self.hold_phase = "POST_MOVE"

    def remaining(self, *, now: float) -> float:
        return max(0.0, float(self.hold_until) - float(now))


def _detector_description(detector) -> str:
    describe = getattr(detector, "describe", None)
    if callable(describe):
        try:
            return str(describe())
        except Exception:
            pass
    return (
        f"source={getattr(detector, 'template_source', '-')} "
        f"threshold={float(getattr(detector, 'threshold', 0.0)):.3f}"
    )


def _detector_diagnostics(detector) -> str:
    diagnostics = getattr(detector, "diagnostics_text", None)
    if callable(diagnostics):
        try:
            return str(diagnostics(limit=8))
        except Exception:
            pass
    return (
        f"raw={float(getattr(detector, 'last_raw_score', -1.0)):.3f} "
        f"need={float(getattr(detector, 'threshold', 0.0)):.3f} "
        f"scale={float(getattr(detector, 'last_raw_scale', 1.0)):.3f}"
    )


def _save_debug_capture(
    detector,
    frame,
    arena_rect,
    *,
    reason: str,
) -> tuple[Path | None, Path | None, Path | None]:
    """Save the exact frame used by the detector before search movement changes it."""

    try:
        from .post_combat_v03b import DEFAULT_LEADER_TEMPLATE_PATH

        debug_dir = DEFAULT_LEADER_TEMPLATE_PATH.parent / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        frame_path = debug_dir / "trainer_search_last_frame.png"
        overlay_path = debug_dir / "trainer_search_last_overlay.png"
        text_path = debug_dir / "trainer_search_last.txt"

        overlay_builder = getattr(detector, "debug_overlay", None)
        if callable(overlay_builder):
            overlay = overlay_builder(frame, arena_rect=arena_rect)
        else:
            overlay = frame.copy()

        frame_ok = bool(cv2.imwrite(str(frame_path), frame))
        overlay_ok = bool(cv2.imwrite(str(overlay_path), overlay))
        text_path.write_text(
            "\n".join(
                (
                    f"reason={reason}",
                    f"frame={frame.shape[1]}x{frame.shape[0]}",
                    f"arena_rect={arena_rect}",
                    f"detector={_detector_description(detector)}",
                    f"vision={_detector_diagnostics(detector)}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        return (
            frame_path if frame_ok else None,
            overlay_path if overlay_ok else None,
            text_path,
        )
    except Exception as error:
        print(
            "TRAINER_DEBUG_SAVE_FAILED "
            f"type={type(error).__name__} detail={error}"
        )
        return None, None, None


def search_trainer_until_visible_diagnostic(
    controller,
    *,
    timeout_seconds: float = 90.0,
    leader_threshold: float = 0.88,
    fps: float = 8.0,
    move_pulse_seconds: float = 0.09,
    telemetry_seconds: float = 0.50,
    confirm_frames: int = 2,
    initial_scan_seconds: float = 1.50,
    reveal_scan_seconds: float = 0.75,
    post_move_scan_seconds: float = 0.35,
    near_candidate_hold_seconds: float = 2.50,
) -> TrainerClickTarget:
    """Find the Trainer with stable visual confirmation before one click.

    Search movement is allowed only after stationary acquisition. A near-threshold
    candidate receives an additional stationary dwell instead of being walked
    past. The exact pre-search frame is saved automatically when acquisition
    still fails.
    """

    from .entity_observer import decode_jpeg
    from .observer_runtime_v03 import V03ObserverConfig
    from .particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
    from .persistent_water_tracker_v03 import PersistentBackgroundWaterAwareEntityTracker
    from .post_combat_v03c import PersistentDojoLeaderDetector
    from .post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine
    from .recorder import WindowsGameFrameSource

    config = V03ObserverConfig(
        player_x=0.5181,
        player_y=0.4706,
        player_exclusion_radius=19.0,
        player_box_width=18.0,
        player_box_height=38.0,
        dynamic_background_enabled=True,
    ).normalized()
    observer = ParticleSafeGridTargetObserver(
        config,
        tile_size=32.0,
        contact_lock_seconds=2.8,
        show_grid=False,
        contact_confirm_frames=2,
    )
    observer.tracker = PersistentBackgroundWaterAwareEntityTracker(config)
    detector = PersistentDojoLeaderDetector(threshold=leader_threshold)
    engine = ObstacleAwarePostCombatRecoveryEngine(
        leader_detector=detector,
        search_delay_seconds=0.25,
        search_timeout_seconds=timeout_seconds,
        search_pulses_per_tile=4,
    )
    source = WindowsGameFrameSource()
    gate = TrainerSearchMotionGate(
        initial_scan_seconds=initial_scan_seconds,
        reveal_scan_seconds=reveal_scan_seconds,
        post_move_scan_seconds=post_move_scan_seconds,
    )

    interval = 1.0 / max(1.0, min(20.0, float(fps)))
    pulse = max(0.03, min(0.14, float(move_pulse_seconds)))
    deadline = time.monotonic() + max(5.0, float(timeout_seconds))
    next_telemetry = 0.0
    visual_hits = 0
    previous_center: tuple[float, float] | None = None
    required_hits = max(1, int(confirm_frames))
    near_hold_started: float | None = None
    near_hold_limit = max(0.50, min(8.0, float(near_candidate_hold_seconds)))
    debug_saved = False
    last_frame = None
    last_arena_rect = None
    found = False

    print(f"TRAINER_DETECTOR {_detector_description(detector)}")

    try:
        while time.monotonic() < deadline:
            loop_started = time.monotonic()
            if f12_pressed():
                if last_frame is not None and not debug_saved:
                    paths = _save_debug_capture(
                        detector,
                        last_frame,
                        last_arena_rect,
                        reason="F12_STOP_BEFORE_CONFIRMATION",
                    )
                    debug_saved = any(path is not None for path in paths)
                    if debug_saved:
                        print(
                            "TRAINER_DEBUG_SAVED "
                            f"frame={paths[0] or '-'} overlay={paths[1] or '-'} "
                            f"text={paths[2] or '-'}"
                        )
                raise DojoFightRequestError("F12_STOP")

            frame = decode_jpeg(bytes(source.capture().jpeg))
            state = observer.process(frame)
            now = time.monotonic()
            gate.begin(now=now)
            engine.observe_movement_frame(frame, state, now=now)
            match = detector.find(
                frame,
                arena_rect=state.arena_rect,
                flow=getattr(state, "global_flow", None),
                now=now,
            )
            last_frame = frame.copy()
            last_arena_rect = state.arena_rect

            if match is not None and match.source == "visual":
                near_hold_started = None
                left, top, width, height = match.bbox
                center = (left + width * 0.5, top + height * 0.5)
                if previous_center is not None and math.hypot(
                    center[0] - previous_center[0],
                    center[1] - previous_center[1],
                ) <= 28.0:
                    visual_hits += 1
                else:
                    visual_hits = 1
                previous_center = center
                controller.apply_keys(())
                accepted_source = getattr(
                    detector,
                    "last_accepted_template_source",
                    "-",
                )
                accepted_scope = getattr(detector, "last_scope", "arena")
                if visual_hits >= required_hits:
                    target = _click_target_from_match(match, frame, state, observer)
                    print(
                        f"TRAINER_VISUAL_CONFIRMED hits={visual_hits}/{required_hits} "
                        f"score={target.score:.3f} d={target.grid_distance} "
                        f"bbox={target.bbox} template={accepted_source} "
                        f"scope={accepted_scope}"
                    )
                    found = True
                    return target

                if now >= next_telemetry:
                    print(
                        f"TRAINER_VISUAL_CONFIRM hits={visual_hits}/{required_hits} "
                        f"score={match.score:.3f} template={accepted_source} "
                        f"scope={accepted_scope}"
                    )
                    print(f"TRAINER_VISION_RAW {_detector_diagnostics(detector)}")
                    next_telemetry = now + max(0.10, float(telemetry_seconds))
                elapsed = time.monotonic() - loop_started
                if elapsed < interval:
                    time.sleep(interval - elapsed)
                continue

            visual_hits = 0
            previous_center = None

            near_method = getattr(detector, "near_visual_candidate", None)
            near_candidate = False
            if callable(near_method):
                try:
                    near_candidate = bool(near_method(ratio=0.82))
                except Exception:
                    near_candidate = False

            if near_candidate:
                if near_hold_started is None:
                    near_hold_started = now
                near_elapsed = now - near_hold_started
                if near_elapsed < near_hold_limit:
                    controller.apply_keys(())
                    if now >= next_telemetry:
                        print(
                            "TRAINER_NEAR_CANDIDATE_HOLD "
                            f"elapsed={near_elapsed:.2f}/{near_hold_limit:.2f}s move=-"
                        )
                        print(f"TRAINER_VISION_RAW {_detector_diagnostics(detector)}")
                        next_telemetry = now + max(0.10, float(telemetry_seconds))
                    elapsed = time.monotonic() - loop_started
                    if elapsed < interval:
                        time.sleep(interval - elapsed)
                    continue
            else:
                near_hold_started = None

            action, direction = gate.next_action(now=now)
            controller.apply_keys(())

            if action == "SELF_OCCLUSION_REVEAL" and direction is not None:
                if not debug_saved:
                    paths = _save_debug_capture(
                        detector,
                        frame,
                        state.arena_rect,
                        reason="INITIAL_STATIONARY_SCAN_MISSED",
                    )
                    debug_saved = any(path is not None for path in paths)
                    if debug_saved:
                        print(
                            "TRAINER_DEBUG_SAVED "
                            f"frame={paths[0] or '-'} overlay={paths[1] or '-'} "
                            f"text={paths[2] or '-'}"
                        )
                engine.arm_movement_probe(direction, now=now)
                controller.apply_keys((direction,))
                time.sleep(pulse)
                controller.apply_keys(())
                print(
                    f"TRAINER_REVEAL_PROBE direction={direction} duration={pulse:.3f}s "
                    "reason=one lateral pulse to reveal a trainer hidden by player / "
                    "um pulso lateral para revelar treinador oculto pelo jogador"
                )
            elif action != "SEARCH_ALLOWED":
                if now >= next_telemetry:
                    print(
                        f"TRAINER_SCAN_HOLD phase={action} "
                        f"remaining={gate.remaining(now=now):.2f}s move=-"
                    )
                    print(f"TRAINER_VISION_RAW {_detector_diagnostics(detector)}")
                    next_telemetry = now + max(0.10, float(telemetry_seconds))
            else:
                decision = engine._search_decision(now=now)
                if decision.move_pulse is not None:
                    engine.arm_movement_probe(decision.move_pulse, now=now)
                    controller.apply_keys((decision.move_pulse,))
                    time.sleep(pulse)
                    controller.apply_keys(())
                    moved_at = time.monotonic()
                    gate.record_search_move(now=moved_at)
                    print(
                        f"TRAINER_SEARCH_MOVE direction={decision.move_pulse} "
                        f"duration={pulse:.3f}s reason={decision.reason}"
                    )

                if now >= next_telemetry:
                    motion = engine.last_movement_detected
                    motion_text = "-" if motion is None else ("yes" if motion else "no")
                    print(
                        f"TRAINER_SEARCH state={decision.state} "
                        f"move={decision.move_pulse or '-'} motion={motion_text} "
                        f"reason={decision.reason}"
                    )
                    print(f"TRAINER_VISION_RAW {_detector_diagnostics(detector)}")
                    next_telemetry = now + max(0.10, float(telemetry_seconds))

            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                time.sleep(interval - elapsed)
    finally:
        try:
            controller.apply_keys(())
        except Exception:
            pass

        if not found and last_frame is not None and not debug_saved:
            paths = _save_debug_capture(
                detector,
                last_frame,
                last_arena_rect,
                reason="SEARCH_ENDED_WITHOUT_CONFIRMATION",
            )
            if any(path is not None for path in paths):
                print(
                    "TRAINER_DEBUG_SAVED "
                    f"frame={paths[0] or '-'} overlay={paths[1] or '-'} "
                    f"text={paths[2] or '-'}"
                )
        source.close()

    raise DojoFightRequestError("TRAINER_SEARCH_TIMEOUT")


__all__ = ["TrainerSearchMotionGate", "search_trainer_until_visible_diagnostic"]
