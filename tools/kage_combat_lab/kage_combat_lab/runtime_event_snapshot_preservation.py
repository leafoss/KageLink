from __future__ import annotations

import json


_INSTALLED = False


def install_trigger_frame_json_preservation() -> None:
    """Rewrite frozen trigger payloads after occupancy close metadata.

    OccupancyEventRecorder writes generic round-close metadata after its parent
    recorder closes. That was overwriting the EVENT_TRIGGER_FRAME payloads for
    FACE_ONLY_LOCK_CHANGED and DANGER_MOVED. The frozen payloads remain in the
    recorder instance, so this final wrapper restores them after all close hooks.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    from . import event_recorder as event_module

    CurrentRecorder = event_module.CombatEventVideoRecorder

    class TriggerFramePreservingRecorder(CurrentRecorder):
        def close(self) -> None:
            super().close()
            restored = 0
            for path, payload in getattr(self, "_pr26_payload_by_path", {}).items():
                path.with_suffix(".json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                restored += 1
            if restored:
                print(
                    "PR26_EVENT_TRIGGER_JSON_RESTORED "
                    f"count={restored} snapshot_timing=EVENT_TRIGGER_FRAME"
                )

    event_module.CombatEventVideoRecorder = TriggerFramePreservingRecorder
    _INSTALLED = True
    print(
        "PR26.17 EVENT SNAPSHOT PRESERVATION: trigger-frame FACE_ONLY/DANGER_MOVED/"
        "COMBAT_LOCK JSON survives all recorder close hooks"
    )


__all__ = ["install_trigger_frame_json_preservation"]
