from __future__ import annotations

import sys


def extract_post_ok_gate(argv: list[str]) -> tuple[bool, list[str]]:
    from .full_loop import POST_OK_GATE_ARG

    found = POST_OK_GATE_ARG in argv
    return found, [arg for arg in argv if arg != POST_OK_GATE_ARG]


def main() -> int:
    from .dojo_multitemplate import install_day_night_dojo_detector

    install_day_night_dojo_detector()

    post_ok_confirmed, remaining = extract_post_ok_gate(sys.argv[1:])
    sys.argv = [sys.argv[0], *remaining]
    if not post_ok_confirmed:
        raise RuntimeError(
            "START_FACE_RIGHT_REQUIRES_POST_OK_GATE: the facing-authority round "
            "must be launched by FullLoop after dialog/OK/spawn"
        )

    from . import full_round as full_round_module
    from .runtime_facing_patch import install_runtime_facing_patch
    from .runtime_startup_inherited import install_inherited_post_ok_startup

    install_runtime_facing_patch(full_round_module)
    install_inherited_post_ok_startup()
    print("TRAINER: day-64 + night-64 enabled for post-combat return")
    print("POST_OK_GATE: confirmed; child inherits the one outer RIGHT pulse")
    return int(full_round_module.main())


if __name__ == "__main__":
    raise SystemExit(main())
