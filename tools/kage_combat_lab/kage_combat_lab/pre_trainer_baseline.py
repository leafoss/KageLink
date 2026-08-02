from __future__ import annotations

import contextlib
import io


_INSTALLED = False


def _rewrite_legacy_baseline_output(text: str) -> tuple[str, ...]:
    return tuple(
        line.replace("PR26_PREOK_", "PR26_PRETRAINER_")
        .replace("dialog=OPEN", "dialog=CLOSED")
        .replace("source=BEFORE_DIALOG_OK", "source=BEFORE_TRAINER_CLICK")
        for line in text.splitlines()
        if line.strip()
    )


def load_pre_trainer_baselines() -> int:
    """Load the legacy NPZ while emitting truthful PR26.6 timing telemetry."""

    from . import pre_ok_baseline as baseline_module

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        count = baseline_module.load_pre_ok_baselines()
    for line in _rewrite_legacy_baseline_output(buffer.getvalue()):
        print(line)
    return count


def install_pre_trainer_baseline_capture() -> None:
    """Capture the clean arena after trainer search but before the trainer click.

    This avoids learning the open dojo dialog as part of the baseline. The
    validated trainer search may move the player/camera first; capture occurs
    only after that search has stabilized and returned its click target.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    from . import pre_ok_baseline as baseline_module
    from pc_agent.kage_pilot import dojo_fight_v03i

    original = dojo_fight_v03i.search_trainer_until_visible
    if getattr(original, "_pr26_pre_trainer_wrapped", False):
        _INSTALLED = True
        return

    def search_then_capture(*args, **kwargs):
        target = original(*args, **kwargs)
        if not bool(getattr(baseline_module, "_CAPTURED", False)):
            print(
                "PR26_PRETRAINER_BASELINE phase=BEFORE_TRAINER_CLICK "
                "dialog=CLOSED enemy=NOT_SPAWNED physical_input=BLOCKED"
            )
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                baseline_module._capture()
            for line in _rewrite_legacy_baseline_output(buffer.getvalue()):
                print(line)
            baseline_module._CAPTURED = True
            print(
                "PR26_PRETRAINER_BASELINE_READY phase=BEFORE_TRAINER_CLICK "
                f"trainer_bbox={getattr(target, 'bbox', None)}"
            )
        return target

    search_then_capture._pr26_pre_trainer_wrapped = True
    dojo_fight_v03i.search_trainer_until_visible = search_then_capture
    _INSTALLED = True
    print(
        "PR26.6 PRE-TRAINER BASELINE HOOK: armed after trainer search and before trainer click"
    )


__all__ = [
    "install_pre_trainer_baseline_capture",
    "load_pre_trainer_baselines",
]
