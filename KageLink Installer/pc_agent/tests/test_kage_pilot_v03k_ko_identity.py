from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import kage_pilot_live_v03k_round as runtime
import kage_pilot_loop_v03j as loop_v03j
from pc_agent.kage_pilot.ko_identity_v03k import (
    RoundKOIdentityGate,
    extract_ko_identity,
    normalize_ko_identity,
)


MATSuda = "Jounin: Matsuda, Al"
AOKI = "Jounin: Aoki, Ian"


class FakeSnapshotReader:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.index = 0

    def read_all_current(self):
        if not self.snapshots:
            return {}
        value = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return value


class FakeController:
    def __init__(self) -> None:
        self.release_count = 0

    def release_all(self) -> None:
        self.release_count += 1


class FakeProcess:
    def __init__(self, lines, return_code=0) -> None:
        self.stdout = iter(lines)
        self.return_code = return_code

    def wait(self):
        return self.return_code


class KagePilotV03KKOIdentityTests(unittest.TestCase):
    def tearDown(self) -> None:
        runtime._configure_round("")
        loop_v03j._LAST_ACCEPTED_KO_NAME = ""

    def test_extracts_everything_before_knockout_phrase(self):
        self.assertEqual(
            extract_ko_identity("Jounin: Matsuda, Al has been Knocked-Out"),
            MATSuda,
        )
        self.assertEqual(
            extract_ko_identity("  Jounin: Aoki,   Ian has been knocked out  "),
            AOKI,
        )
        self.assertEqual(normalize_ko_identity(" JOUNIN:  Aoki, Ian "), "jounin: aoki, ian")

    def test_repeated_previous_opponent_is_rejected_even_with_visual_enemy(self):
        gate = RoundKOIdentityGate(MATSuda, required_visual_hits=2)
        gate.observe_target(target_id=1, target_mode="VISIBLE")
        gate.observe_target(target_id=2, target_mode="OCCLUDED")

        decision = gate.evaluate(f"{MATSuda} has been Knocked-Out")

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "REPEATED_PREVIOUS_OPPONENT")
        self.assertEqual(decision.candidate_name, MATSuda)

    def test_different_name_requires_current_round_visual_enemy(self):
        gate = RoundKOIdentityGate(MATSuda, required_visual_hits=2)
        decision = gate.evaluate(f"{AOKI} has been Knocked-Out")
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "NO_CURRENT_ROUND_ENEMY")

        gate.observe_target(target_id=10, target_mode="CONTACT_MEMORY")
        gate.observe_target(target_id=10, target_mode="VISIBLE")
        still_not_ready = gate.evaluate(f"{AOKI} has been Knocked-Out")
        self.assertFalse(still_not_ready.accepted)

        gate.observe_target(target_id=11, target_mode="CONTACT_REBIND")
        accepted = gate.evaluate(f"{AOKI} has been Knocked-Out")
        self.assertTrue(accepted.accepted)
        self.assertEqual(accepted.reason, "NEW_OPPONENT_KO")

    def test_rejected_watcher_signal_releases_inputs_and_invalidates_evidence(self):
        runtime._configure_round(MATSuda)
        runtime._GATE.observe_target(target_id=1, target_mode="VISIBLE")
        runtime._GATE.observe_target(target_id=1, target_mode="VISIBLE")
        controller = FakeController()
        runtime._ACTIVE_CONTROLLER = controller
        reader = FakeSnapshotReader(
            [
                {101: "Combat started"},
                {101: f"Combat started\n{MATSuda} has been Knocked-Out"},
            ]
        )
        watcher = runtime.OpponentAwareVictoryWatcher("x", "y", reader=reader)
        watcher.prime()

        signal = watcher.poll()

        self.assertIsNone(signal)
        self.assertEqual(controller.release_count, 1)
        self.assertEqual(runtime._REJECTION_GENERATION, 1)
        self.assertEqual(runtime._GATE.visual_enemy_hits, 0)

    def test_different_opponent_signal_is_accepted(self):
        runtime._configure_round(MATSuda)
        runtime._GATE.observe_target(target_id=20, target_mode="VISIBLE")
        runtime._GATE.observe_target(target_id=21, target_mode="OCCLUDED")
        reader = FakeSnapshotReader(
            [
                {101: "Combat started"},
                {101: f"Combat started\n{AOKI} has been Knocked-Out"},
            ]
        )
        watcher = runtime.OpponentAwareVictoryWatcher("x", "y", reader=reader)
        watcher.prime()

        signal = watcher.poll()

        self.assertIsNotNone(signal)
        self.assertEqual(extract_ko_identity(signal.text), AOKI)
        self.assertEqual(runtime._REJECTION_GENERATION, 0)

    def test_parent_passes_previous_name_and_replaces_buffer_after_ready(self):
        captured_command = []
        lines = [
            f"KO_ACCEPTED reason=NEW_OPPONENT_KO previous=\"{MATSuda}\" current=\"{AOKI}\"\n",
            f"VICTORY_CHAT / VITORIA_CHAT: {AOKI} has been Knocked-Out\n",
            "Live stopped / Controle encerrado: result=ready frames=100 fps=6.0\n",
        ]

        def fake_popen(command, **_kwargs):
            captured_command.extend(command)
            return FakeProcess(lines)

        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                combat_seconds=120.0,
                post_combat_timeout=240.0,
                round_startup_delay=1.0,
                chat_poll_seconds=0.15,
                recovery_hp_percent=90.0,
                recovery_chakra_percent=50.0,
                leader_threshold=0.88,
                log_dir=Path(directory),
                disable_h=False,
            )
            loop_v03j._LAST_ACCEPTED_KO_NAME = MATSuda
            with patch.object(loop_v03j.subprocess, "Popen", side_effect=fake_popen):
                result = loop_v03j._run_round_with_ko_buffer(args, round_number=2)

        self.assertTrue(result)
        self.assertIn("--previous-ko-name", captured_command)
        previous_index = captured_command.index("--previous-ko-name") + 1
        self.assertEqual(captured_command[previous_index], MATSuda)
        self.assertEqual(loop_v03j._LAST_ACCEPTED_KO_NAME, AOKI)


if __name__ == "__main__":
    unittest.main()
