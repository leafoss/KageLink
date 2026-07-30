from __future__ import annotations

from dataclasses import dataclass
import math
import time

from .dojo_fight_v03e import DojoFightRequestError, TrainerClickTarget, f12_pressed
from .dojo_fight_v03f import _click_target_from_match


@dataclass(slots=True)
class TrainerSearchMotionGate:
    """Keep trainer acquisition stationary long enough for stable visual confirmation.

    The real-game failure started with Leafos likely overlapping the trainer. The old search waited
    only 0.25 seconds and then pulsed almost continuously around concentric rings. That could move
    past a partially occluded trainer before two stable visual frames were available.

    This gate adds:
    - an initial stationary scan;
    - one short lateral reveal pulse for the common self-occlusion case;
    - a stationary reveal scan;
    - a short stationary dwell after every later search pulse.
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


def search_trainer_until_visible_safe(
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
) -> TrainerClickTarget:
    """Find the trainer without walking continuously through unstable visual frames."""

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

    print(f"TRAINER_DETECTOR {_detector_description(detector)}")

    try:
        while time.monotonic() < deadline:
            loop_started = time.monotonic()
            if f12_pressed():
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

            if match is not None and match.source == "visual":
                left, top, width, height = match.bbox
                center = (left + width * 0.5, top + height * 0.5)
                if previous_center is not None and math.hypot(
                    center[0] - previous_center[0], center[1] - previous_center[1]
                ) <= 48.0:
                    visual_hits += 1
                else:
                    visual_hits = 1
                previous_center = center
                controller.apply_keys(())
                mode = getattr(detector, "last_accepted_template_mode", "-") or "-"
                template = getattr(detector, "last_accepted_template_source", "-") or "-"
                if visual_hits >= required_hits:
                    target = _click_target_from_match(match, frame, state, observer)
                    print(
                        f"TRAINER_VISUAL_CONFIRMED score={target.score:.3f} "
                        f"d={target.grid_distance} bbox={target.bbox} "
                        f"mode={mode} template={template}"
                    )
                    return target

                if now >= next_telemetry:
                    print(
                        f"TRAINER_VISUAL_CONFIRM hits={visual_hits}/{required_hits} "
                        f"score={match.score:.3f} mode={mode} template={template}"
                    )
                    print(f"TRAINER_VISION_RAW {_detector_diagnostics(detector)}")
                    next_telemetry = now + max(0.10, float(telemetry_seconds))
                elapsed = time.monotonic() - loop_started
                if elapsed < interval:
                    time.sleep(interval - elapsed)
                continue

            visual_hits = 0
            previous_center = None
            action, direction = gate.next_action(now=now)
            controller.apply_keys(())

            if action == "SELF_OCCLUSION_REVEAL" and direction is not None:
                engine.arm_movement_probe(direction, now=now)
                controller.apply_keys((direction,))
                time.sleep(pulse)
                controller.apply_keys(())
                print(
                    f"TRAINER_REVEAL_PROBE direction={direction} "
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
                    gate.record_search_move(now=time.monotonic())

                if now >= next_telemetry:
                    motion = engine.last_movement_detected
                    motion_text = "-" if motion is None else ("yes" if motion else "no")
                    print(
                        f"TRAINER_SEARCH state={decision.state} move={decision.move_pulse or '-'} "
                        f"motion={motion_text} reason={decision.reason}"
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
        source.close()

    raise DojoFightRequestError("TRAINER_SEARCH_TIMEOUT")


__all__ = ["TrainerSearchMotionGate", "search_trainer_until_visible_safe"]
