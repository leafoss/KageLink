from __future__ import annotations

import sys


def extract_post_ok_gate(argv: list[str]) -> tuple[bool, list[str]]:
    from .full_loop_pr27 import POST_OK_GATE_ARG

    found = POST_OK_GATE_ARG in argv
    return found, [arg for arg in argv if arg != POST_OK_GATE_ARG]


def main() -> int:
    from .dojo_multitemplate import install_day_night_dojo_detector
    from .runtime_trainer_suspension import suspend_trainer_detector_for_validation

    detector_class = install_day_night_dojo_detector()
    suspend_trainer_detector_for_validation(detector_class)

    post_ok_confirmed, remaining = extract_post_ok_gate(sys.argv[1:])
    sys.argv = [sys.argv[0], *remaining]
    if not post_ok_confirmed:
        raise RuntimeError(
            "PR27_REQUIRES_POST_OK_GATE: launch through PR27 FullLoop after trainer/dialog/OK"
        )

    from . import full_round_pr27

    print("PR27 ENTRY: old PR26 combat disconnected")
    print("PR27 ENTRY: NativeGameCapture -> ArenaCropper -> NativeGrid64")
    print("PR27 ENTRY: CellBaselineStore -> CellDifferenceDetector -> ChangedCellGrouper")
    print("PR27 ENTRY: SpriteFragmentExtractor -> SpriteTracker -> CombatController")
    return int(full_round_pr27.main())


if __name__ == "__main__":
    raise SystemExit(main())
