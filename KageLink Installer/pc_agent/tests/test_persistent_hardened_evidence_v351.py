from __future__ import annotations

import unittest

from pc_agent.kage_pilot.combat_strategy_v351 import (
    CombatStrategyConfig,
    GridObservation,
    ObservationClass,
    SpatialCombatTarget,
    create_combat_target_strategy,
)
from pc_agent.kage_pilot.persistent_hardened_strategy_v351 import (
    PersistentHardenedEvidenceStrategy,
)


class PersistentHardenedEvidenceV351Tests(unittest.TestCase):
    def test_registry_uses_evidence_aware_persistent_fallback(self):
        strategy = create_combat_target_strategy(
            "persistent_hardened",
            CombatStrategyConfig(strategy="persistent_hardened"),
        )
        self.assertIsInstance(strategy, PersistentHardenedEvidenceStrategy)

    def test_missing_appearance_has_zero_contribution_and_is_renormalized(self):
        strategy = PersistentHardenedEvidenceStrategy(
            CombatStrategyConfig(strategy="persistent_hardened")
        )
        target = SpatialCombatTarget(
            combat_target_id=1,
            confirmed_cell=(1, 0),
            predicted_cell=(1, 0),
            clean_visual_track_id=10,
            acquired_at=0.0,
            last_clean_seen_at=0.0,
            last_any_activity_at=0.0,
            last_clean_frame=0,
            confidence=0.8,
            appearance_signature=(),
            body_size=(28.0, 52.0),
            last_confirmed_direction="RIGHT",
        )
        candidate = GridObservation(
            frame_index=1,
            timestamp=0.1,
            track_id=11,
            anchor_cell=(1, 0),
            bbox_cells=frozenset({(1, 0)}),
            visible=True,
            body_like=True,
            contaminated=False,
            enemy_score=80.0,
            appearance_signature=(),
            body_size=(28.0, 52.0),
            body_cell_coverage=0.8,
            classification=ObservationClass.CLEAN_SINGLE_CELL_BODY.value,
        )
        appearance, available = strategy._appearance_evidence((), ())
        self.assertEqual(appearance, 0.0)
        self.assertFalse(available)
        score = strategy._score(target, candidate)
        self.assertGreaterEqual(score, strategy.config.minimum_rebind_score)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
