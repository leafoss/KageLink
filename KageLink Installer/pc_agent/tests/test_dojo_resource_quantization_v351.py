from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

from pc_agent.kage_pilot.dojo_resource_quantization_v351 import (
    install_resource_quantization_bridge,
)
from pc_agent.kage_pilot.post_combat_v03 import ResourceLevels


class _Reader:
    HEALTH_FULL_PX_960 = 46.0
    CHAKRA_FULL_PX_960 = 44.0

    def __init__(self, levels):
        self.levels = levels

    def read(self, frame):
        del frame
        return self.levels


class _Engine:
    def __init__(self, levels):
        self.resource_reader = _Reader(levels)
        self.health_target = 0.90
        self.chakra_target = 0.40
        self._v351_last_health = None
        self._v351_last_chakra = None

    def _read_levels(self, frame):
        levels = self.resource_reader.read(frame)
        self._v351_last_health = levels.health
        self._v351_last_chakra = levels.chakra
        return levels

    def _levels_ready(self, levels):
        return bool(
            levels.valid
            and float(levels.health or 0.0) >= self.health_target
            and float(levels.chakra or 0.0) >= self.chakra_target
        )


class ResourceQuantizationV351Tests(unittest.TestCase):
    @staticmethod
    def _frame():
        return np.zeros((540, 960, 3), dtype=np.uint8)

    def _install(self):
        events = []
        runtime = SimpleNamespace(
            ClosedLoopVisualRecoveryEngine=_Engine,
            _telemetry=lambda event, fields: events.append((event, fields)),
        )
        return install_resource_quantization_bridge(runtime), events

    def test_round_seven_hp_value_is_accepted_with_half_pixel_uncertainty(self):
        engine_type, events = self._install()
        levels = ResourceLevels(0.894, 0.45, 41, 20)
        engine = engine_type(levels)

        read = engine._read_levels(self._frame())

        self.assertTrue(engine._levels_ready(read))
        self.assertAlmostEqual(engine.health_target, 0.90)
        self.assertTrue(
            any(event == "DOJO_RESOURCE_QUANTIZATION_ACCEPTED" for event, _ in events)
        )

    def test_value_beyond_half_pixel_uncertainty_remains_below_target(self):
        engine_type, _events = self._install()
        levels = ResourceLevels(0.87, 0.45, 40, 20)
        engine = engine_type(levels)

        read = engine._read_levels(self._frame())

        self.assertFalse(engine._levels_ready(read))

    def test_chakra_still_must_reach_its_quantized_target(self):
        engine_type, _events = self._install()
        levels = ResourceLevels(0.894, 0.35, 41, 15)
        engine = engine_type(levels)

        read = engine._read_levels(self._frame())

        self.assertFalse(engine._levels_ready(read))
        self.assertTrue(engine._v351_level_ready(0.894, 0.90, "health"))
        self.assertFalse(engine._v351_level_ready(0.35, 0.40, "chakra"))

    def test_install_is_idempotent(self):
        engine_type, events = self._install()
        runtime = SimpleNamespace(
            ClosedLoopVisualRecoveryEngine=engine_type,
            _telemetry=lambda event, fields: events.append((event, fields)),
        )

        self.assertIs(install_resource_quantization_bridge(runtime), engine_type)
        installed = [
            event
            for event, _fields in events
            if event == "DOJO_RESOURCE_QUANTIZATION_BRIDGE_INSTALLED"
        ]
        self.assertEqual(len(installed), 1)


if __name__ == "__main__":
    unittest.main()
