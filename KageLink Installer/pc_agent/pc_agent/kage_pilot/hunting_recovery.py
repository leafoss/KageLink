from __future__ import annotations


class StaminaHudReader:
    """Fail closed until the real Stamina HUD region is physically calibrated.

    KageLink has a validated HP/Chakra reader, but the Hunting contract requires
    Stamina. Chakra is deliberately never substituted for Stamina.
    """

    calibrated = False

    def read(self, _frame_bgr) -> float | None:
        return None


__all__ = ["StaminaHudReader"]
