from __future__ import annotations

from types import SimpleNamespace
import time
import unittest

from pc_agent.kage_pilot import dojo_combat_runtime as runtime
from pc_agent.kage_pilot.validated_combat_core import CombatV3State, VisualEvidence


LOGICAL_ID = "DOJO_CURRENT_OPPONENT"


class FakeObserver:
    def __init__(self, *, mode: str = "VISIBLE", dx: int = 3, dy: int = 0) -> None:
        self.target_mode = mode
        self.dx = int(dx)
        self.dy = int(dy)

    def metrics_for(self, track_id):
        if track_id is None:
            return None
        return SimpleNamespace(
            cell=(10 + self.dx, 10 + self.dy),
            player_cell=(10, 10),
        )


class KagePilotV03KAlpha6CombatTests(unittest.TestCase):
    def tearDown(self) -> None:
        runtime._arm_combat()

    @staticmethod
    def _core_visual(timestamp: float, dx: int, dy: int, track_id: int = 1) -> VisualEvidence:
        return VisualEvidence(
            timestamp=timestamp,
            dx=dx,
            dy=dy,
            track_id=track_id,
            confidence=0.90,
            body_valid=True,
            source="DOJO_CURRENT_TARGET",
            combatant_verified=True,
            noncombatant=False,
            appearance_score=None,
            binding_reason="TEST",
            entity_id=LOGICAL_ID,
            identity_confidence=1.0,
            hostility=1.0,
            network_fused=False,
        )

    def test_exact_alpha6_core_chases_and_uses_cardinal_melee_h(self):
        state = CombatV3State(runtime_at=100.0)
        state.on_materialization(100.0)
        state.on_identity(LOGICAL_ID, 100.1, identity_confidence=1.0, hostility=1.0)
        state.on_visual(self._core_visual(100.1, 3, 0))

        chase = state.decide(100.2, 50.0)
        self.assertEqual(chase.state, "CHASE")
        self.assertEqual(chase.navigation, "MOVE_RIGHT")
        self.assertTrue(chase.hold_r)

        state.on_visual(self._core_visual(100.3, 1, 0))
        melee = state.decide(100.31, 50.1)
        self.assertEqual(melee.state, "MELEE")
        self.assertEqual(melee.face, "RIGHT")
        self.assertTrue(melee.h_request)

    def test_exact_alpha6_hf1_skips_only_first_repeated_distance_two_visual(self):
        state = CombatV3State(runtime_at=100.0)
        state.on_materialization(100.0)
        state.on_identity(LOGICAL_ID, 100.1, identity_confidence=1.0, hostility=1.0)
        state.on_visual(self._core_visual(100.1, 2, 0))
        self.assertEqual(state.decide(100.2, 50.0).navigation, "MOVE_RIGHT")

        state.mark_move(100.2, 50.0, None)
        state.on_visual(self._core_visual(100.3, 2, 0))
        skipped = state.decide(100.31, 50.1)
        self.assertEqual(skipped.state, "TRACKING")
        self.assertEqual(skipped.navigation, "HOLD")

        state.on_visual(self._core_visual(100.4, 2, 0))
        resumed = state.decide(100.41, 50.2)
        self.assertEqual(resumed.state, "CHASE")
        self.assertEqual(resumed.navigation, "MOVE_RIGHT")

    def test_dojo_adapter_cannot_create_target_without_existing_dojo_authority(self):
        runtime._arm_combat()
        empty_state = SimpleNamespace(target=None)
        runtime._feed_existing_dojo_target(empty_state, FakeObserver())

        self.assertIsNone(runtime._ALPHA6.target_entity_id)
        self.assertIsNone(runtime._ALPHA6.last_visual)

    def test_dojo_adapter_uses_existing_target_without_reclassifying_it(self):
        runtime._arm_combat()
        target = SimpleNamespace(track_id=42, enemy_score=91.0)
        state = SimpleNamespace(target=target)
        runtime._feed_existing_dojo_target(
            state,
            FakeObserver(mode="VISIBLE", dx=3, dy=0),
        )

        self.assertEqual(runtime._ALPHA6.target_entity_id, LOGICAL_ID)
        self.assertEqual(runtime._CURRENT_TRACK_ID, 42)
        self.assertEqual(runtime._ALPHA6.last_visual.track_id, 42)
        self.assertEqual(runtime._ALPHA6.last_visual.binding_reason, "EXISTING_DOJO_TARGET_AUTHORITY")
        decision = runtime._ALPHA6.decide(time.time(), time.monotonic())
        self.assertEqual(decision.state, "CHASE")
        self.assertEqual(decision.navigation, "MOVE_RIGHT")

    def test_contact_memory_does_not_mint_fresh_alpha6_body_authority(self):
        runtime._arm_combat()
        target = SimpleNamespace(track_id=9, enemy_score=90.0)
        state = SimpleNamespace(target=target)
        runtime._feed_existing_dojo_target(
            state,
            FakeObserver(mode="CONTACT_MEMORY", dx=1, dy=0),
        )

        self.assertIsNone(runtime._ALPHA6.target_entity_id)
        self.assertIsNone(runtime._ALPHA6.last_visual)

    def test_alpha6_timing_override_does_not_change_dojo_chat_or_recovery_arguments(self):
        values = runtime._apply_alpha6_combat_timing(
            [
                "--chat-poll-seconds", "0.15",
                "--recovery-hp", "0.90",
                "--recovery-chakra", "0.50",
            ]
        )
        self.assertEqual(values[values.index("--fps") + 1], "12")
        self.assertEqual(values[values.index("--telemetry-seconds") + 1], "0.20")
        self.assertEqual(values[values.index("--move-pulse") + 1], "0.040")
        self.assertEqual(values[values.index("--chat-poll-seconds") + 1], "0.15")
        self.assertEqual(values[values.index("--recovery-hp") + 1], "0.90")
        self.assertEqual(values[values.index("--recovery-chakra") + 1], "0.50")


if __name__ == "__main__":
    unittest.main()
