from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from pc_agent.kage_pilot.dojo_debug_v351 import (
    DojoDebugSettings,
    read_debug_settings,
    write_debug_settings,
)


MIN_SAFE_MEDITATION_TIMEOUT_SECONDS = 180.0
LEGACY_MEDITATION_TIMEOUT_SECONDS = 120.0


def ensure_safe_meditation_timeout(
    path: str | Path | None = None,
    *,
    telemetry: Callable[[str, dict[str, object]], None] | None = None,
) -> DojoDebugSettings:
    """Persist the physically validated minimum recovery window.

    Round 5 physical evidence showed that the 90% HP gate can legitimately be
    reached only near the old 120-second meditation timeout. Fast Chakra Y then
    starts correctly, but the old timeout requests a safe V exit before Chakra
    has enough time to cross the recovery target. Values above the safety floor
    remain user-owned; only shorter legacy/unsafe values are raised.
    """

    settings = read_debug_settings(path)
    configured = float(settings.meditation_timeout_seconds)
    if configured >= MIN_SAFE_MEDITATION_TIMEOUT_SECONDS:
        return settings

    migrated = replace(
        settings,
        meditation_timeout_seconds=MIN_SAFE_MEDITATION_TIMEOUT_SECONDS,
    ).normalized()
    write_debug_settings(migrated, path)

    if telemetry is not None:
        telemetry(
            "DOJO_MEDITATION_TIMEOUT_MIGRATED",
            {
                "previous": f"{configured:.1f}",
                "effective": f"{MIN_SAFE_MEDITATION_TIMEOUT_SECONDS:.1f}",
                "reason": (
                    "legacy_120_hp_gate"
                    if abs(configured - LEGACY_MEDITATION_TIMEOUT_SECONDS) < 1e-6
                    else "below_safe_floor"
                ),
            },
        )
    return migrated


def install_meditation_timeout_bridge(runtime: Any):
    """Keep the 180-second floor active inside every guarded round engine.

    The persisted setting is migrated before engine construction, while this
    runtime bridge prevents a stale process or a concurrent UI write from
    lowering the active guard below the physically validated safety window.
    Enter/exit delays, V ownership and the HP-gated Y rule are unchanged.
    """

    engine_type = runtime.ClosedLoopVisualRecoveryEngine
    if bool(getattr(engine_type, "_kagelink_v351_timeout_bridge", False)):
        return engine_type

    telemetry = runtime._telemetry
    original_init = engine_type.__init__
    original_refresh = getattr(engine_type, "_refresh_meditation_settings", None)

    def enforce_floor(self, *, source: str) -> None:
        guard = getattr(self, "meditation_guard", None)
        if guard is None:
            return
        previous = float(getattr(guard, "timeout_seconds", 0.0) or 0.0)
        if previous >= MIN_SAFE_MEDITATION_TIMEOUT_SECONDS:
            return
        guard.timeout_seconds = MIN_SAFE_MEDITATION_TIMEOUT_SECONDS
        telemetry(
            "DOJO_MEDITATION_TIMEOUT_EXTENDED",
            {
                "previous": f"{previous:.1f}",
                "effective": f"{MIN_SAFE_MEDITATION_TIMEOUT_SECONDS:.1f}",
                "source": source,
                "y_hp_gate_preserved": "true",
            },
        )

    def bridged_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        enforce_floor(self, source="engine_init")

    engine_type.__init__ = bridged_init

    if callable(original_refresh):
        def bridged_refresh(self, *args, **kwargs):
            result = original_refresh(self, *args, **kwargs)
            enforce_floor(self, source="settings_refresh")
            return result

        engine_type._refresh_meditation_settings = bridged_refresh

    engine_type._kagelink_v351_timeout_bridge = True
    telemetry(
        "DOJO_MEDITATION_TIMEOUT_BRIDGE_INSTALLED",
        {
            "minimum": f"{MIN_SAFE_MEDITATION_TIMEOUT_SECONDS:.1f}",
            "legacy": f"{LEGACY_MEDITATION_TIMEOUT_SECONDS:.1f}",
            "y_hp_gate_preserved": "true",
        },
    )
    return engine_type


__all__ = [
    "LEGACY_MEDITATION_TIMEOUT_SECONDS",
    "MIN_SAFE_MEDITATION_TIMEOUT_SECONDS",
    "ensure_safe_meditation_timeout",
    "install_meditation_timeout_bridge",
]
