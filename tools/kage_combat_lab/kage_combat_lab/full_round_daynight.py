from __future__ import annotations

import sys


def main() -> int:
    from .dojo_multitemplate import install_day_night_dojo_detector
    from .full_loop import POST_OK_GATE_ARG

    install_day_night_dojo_detector()

    post_ok_confirmed = POST_OK_GATE_ARG in sys.argv[1:]
    sys.argv = [sys.argv[0], *[arg for arg in sys.argv[1:] if arg != POST_OK_GATE_ARG]]
    if not post_ok_confirmed:
        raise RuntimeError(
            "START_FACE_RIGHT_REQUIRES_POST_OK_GATE: the facing-authority round "
            "must be launched by FullLoop after dialog/OK/spawn"
        )

    from . import full_round as full_round_module
    from .runtime_facing_patch import install_runtime_facing_patch

    install_runtime_facing_patch(full_round_module)
    print("TRAINER: day-64 + night-64 enabled for post-combat return")
    print("POST_OK_GATE: confirmed; START_FACE_RIGHT transaction is authorized")
    return int(full_round_module.main())


if __name__ == "__main__":
    raise SystemExit(main())
