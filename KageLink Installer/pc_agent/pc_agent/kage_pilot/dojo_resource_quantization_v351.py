from __future__ import annotations

from typing import Any


HEALTH_FULL_PX_960 = 46.0
CHAKRA_FULL_PX_960 = 44.0


def install_resource_quantization_bridge(runtime: Any):
    """Make recovery thresholds aware of the HUD reader's pixel resolution.

    A 960px capture represents HP with roughly 46 fill columns and Chakra with
    roughly 44. A requested threshold may fall between two observable columns.
    Comparing only the raw ratio can therefore deadlock at values such as 89.4%
    for a 90% target. Half a measured pixel is used as uncertainty; configured
    targets are not lowered.
    """

    engine_type = runtime.ClosedLoopVisualRecoveryEngine
    if bool(getattr(engine_type, "_kagelink_v351_resource_quantization", False)):
        return engine_type

    original_read_levels = engine_type._read_levels
    telemetry = runtime._telemetry

    def quantized_read_levels(self, frame_bgr):
        levels = original_read_levels(self, frame_bgr)
        width = int(frame_bgr.shape[1]) if frame_bgr is not None and frame_bgr.size else 960
        scale = max(0.25, float(width) / 960.0)
        reader = getattr(self, "resource_reader", None)
        health_full = float(getattr(reader, "HEALTH_FULL_PX_960", HEALTH_FULL_PX_960)) * scale
        chakra_full = float(getattr(reader, "CHAKRA_FULL_PX_960", CHAKRA_FULL_PX_960)) * scale
        self._v351_health_measurement_tolerance = 0.5 / max(1.0, health_full)
        self._v351_chakra_measurement_tolerance = 0.5 / max(1.0, chakra_full)
        self._v351_last_resource_levels = levels
        return levels

    def level_ready(self, value, target, resource: str) -> bool:
        if value is None:
            return False
        tolerance = float(
            getattr(
                self,
                "_v351_health_measurement_tolerance"
                if str(resource).lower() == "health"
                else "_v351_chakra_measurement_tolerance",
                0.0,
            )
            or 0.0
        )
        return float(value) + max(0.0, tolerance) >= float(target)

    def quantized_levels_ready(self, levels) -> bool:
        if not bool(getattr(levels, "valid", False)):
            return False
        hp = float(levels.health or 0.0)
        chakra = float(levels.chakra or 0.0)
        hp_target = float(self.health_target)
        chakra_target = float(self.chakra_target)
        hp_ready = level_ready(self, hp, hp_target, "health")
        chakra_ready = level_ready(self, chakra, chakra_target, "chakra")
        ready = hp_ready and chakra_ready
        exact = hp >= hp_target and chakra >= chakra_target
        if ready and not exact:
            marker = (
                int(getattr(levels, "health_fill_px", 0) or 0),
                int(getattr(levels, "chakra_fill_px", 0) or 0),
                round(hp_target, 4),
                round(chakra_target, 4),
            )
            if marker != getattr(self, "_v351_last_quantization_marker", None):
                self._v351_last_quantization_marker = marker
                telemetry(
                    "DOJO_RESOURCE_QUANTIZATION_ACCEPTED",
                    {
                        "hp": f"{hp:.3f}",
                        "hp_tolerance": f"{float(getattr(self, '_v351_health_measurement_tolerance', 0.0)):.4f}",
                        "chakra": f"{chakra:.3f}",
                        "chakra_tolerance": f"{float(getattr(self, '_v351_chakra_measurement_tolerance', 0.0)):.4f}",
                        "hp_target": f"{hp_target:.3f}",
                        "chakra_target": f"{chakra_target:.3f}",
                    },
                )
        return ready

    engine_type._read_levels = quantized_read_levels
    engine_type._levels_ready = quantized_levels_ready
    engine_type._v351_level_ready = level_ready
    engine_type._kagelink_v351_resource_quantization = True
    telemetry(
        "DOJO_RESOURCE_QUANTIZATION_BRIDGE_INSTALLED",
        {"health_full_px_960": "46", "chakra_full_px_960": "44", "uncertainty": "half_pixel"},
    )
    return engine_type


__all__ = ["install_resource_quantization_bridge"]
