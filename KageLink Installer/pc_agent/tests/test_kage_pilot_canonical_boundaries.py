from __future__ import annotations

from pathlib import Path
import unittest

import kage_pilot_loop
import kage_pilot_round
from pc_agent.kage_pilot import DojoTrainingService
from pc_agent.kage_pilot.combat_control import (
    LiveCombatControlPlanner,
    LiveControlCommand,
    MotionBurstGuard,
    MotionBurstState,
)
from pc_agent.kage_pilot.dojo_request import (
    DojoRoundWithoutCombatError,
    request_taijutsu_dojo_spar_single_click,
)
from pc_agent.kage_pilot.dojo_templates import DojoTemplateStore
from pc_agent.kage_pilot.dojo_training_service import DojoTrainingService as CanonicalService
from pc_agent.kage_pilot.dojo_training_v03k import DojoTrainingService as LegacyService
from pc_agent.kage_pilot.ko_identity import RoundKOIdentityGate
from pc_agent.kage_pilot.ko_identity_v03k import RoundKOIdentityGate as LegacyKOIdentityGate
from pc_agent.kage_pilot.post_combat import (
    PostCombatDecision,
    VisualProgressPostCombatRecoveryEngine,
)
from pc_agent.kage_pilot.trainer_search import TrainerSearchMotionGate


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "pc_agent"
INSTALLER = ROOT / "installer"


class KagePilotCanonicalBoundaryTests(unittest.TestCase):
    def test_public_package_exports_canonical_service(self):
        self.assertIs(DojoTrainingService, CanonicalService)
        self.assertIs(LegacyService, CanonicalService)

    def test_legacy_ko_module_is_only_a_compatibility_alias(self):
        self.assertIs(LegacyKOIdentityGate, RoundKOIdentityGate)

    def test_canonical_responsibility_modules_are_importable(self):
        self.assertTrue(callable(request_taijutsu_dojo_spar_single_click))
        self.assertTrue(issubclass(DojoRoundWithoutCombatError, Exception))
        self.assertTrue(callable(DojoTemplateStore))
        self.assertTrue(callable(TrainerSearchMotionGate))
        self.assertTrue(callable(LiveCombatControlPlanner))
        self.assertTrue(callable(LiveControlCommand))
        self.assertTrue(callable(MotionBurstGuard))
        self.assertTrue(callable(MotionBurstState))
        self.assertTrue(callable(PostCombatDecision))
        self.assertTrue(callable(VisualProgressPostCombatRecoveryEngine))

    def test_source_runtime_uses_versionless_entrypoints(self):
        service = CanonicalService(project_dir=AGENT, python_executable="python-test")
        self.assertEqual(service.script_path.name, "kage_pilot_loop.py")
        self.assertTrue((AGENT / "kage_pilot_loop.py").exists())
        self.assertTrue((AGENT / "kage_pilot_round.py").exists())
        self.assertTrue(callable(kage_pilot_loop.main))
        self.assertTrue(callable(kage_pilot_round.main))

    def test_pyinstaller_specs_target_canonical_entrypoints(self):
        dojo_spec = (INSTALLER / "KagePilotDojo.spec").read_text(encoding="utf-8")
        round_spec = (INSTALLER / "KagePilotRound.spec").read_text(encoding="utf-8")
        self.assertIn("kage_pilot_loop.py", dojo_spec)
        self.assertNotIn("kage_pilot_loop_v03", dojo_spec)
        self.assertIn("kage_pilot_round.py", round_spec)
        self.assertNotIn("kage_pilot_live_v03", round_spec)

    def test_canonical_ko_gate_preserves_opponent_buffer_contract(self):
        gate = RoundKOIdentityGate("Jounin: Old", required_visual_hits=2)
        gate.observe_target(target_id=1, target_mode="VISIBLE")
        gate.observe_target(target_id=1, target_mode="OCCLUDED")
        repeated = gate.evaluate("Jounin: Old has been Knocked-Out")
        current = gate.evaluate("Jounin: New has been Knocked-Out")
        self.assertFalse(repeated.accepted)
        self.assertEqual(repeated.reason, "REPEATED_PREVIOUS_OPPONENT")
        self.assertTrue(current.accepted)
        self.assertEqual(current.reason, "NEW_OPPONENT_KO")


if __name__ == "__main__":
    unittest.main()
