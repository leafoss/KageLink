from __future__ import annotations

from .water_filter_v03b import CombatSelectiveWaterAwareEntityTracker


class PersistentBackgroundWaterAwareEntityTracker(CombatSelectiveWaterAwareEntityTracker):
    """Keep learned dynamic-background memory across PLAYER recalibration resets."""

    def reset(self) -> None:
        # StableTargetObserver.reset() is used by the click calibration path. Entity
        # identities and lock state should restart, but already learned animated
        # scenery should survive repeated calibration clicks.
        self.reset_tracking(preserve_background=True)

    def full_reset(self) -> None:
        """Explicitly clear both entity state and learned environmental memory."""
        self.reset_tracking(preserve_background=False)
