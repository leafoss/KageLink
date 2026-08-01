from __future__ import annotations


def main() -> int:
    # This process is created independently for every round. Install the same
    # canonical 64px day/night detector before importing the validated round
    # chain so post-combat return and meditation use identical visual authority.
    from .dojo_multitemplate import install_day_night_dojo_detector

    install_day_night_dojo_detector()

    from .full_round import main as full_round_main

    print("TRAINER: day-64 + night-64 enabled for post-combat return")
    return int(full_round_main())


if __name__ == "__main__":
    raise SystemExit(main())
