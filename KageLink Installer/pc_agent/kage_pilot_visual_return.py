"""Canonical KageLink visual-position and Trainer-return adapter.

Public entry points and packaging specs import this stable module. The physically
validated compatibility provider remains encapsulated behind this boundary until
real Windows/BYOND stress testing authorizes a provider extraction.
"""

from __future__ import annotations


def main() -> int:
    from kage_pilot_live_v0351_round import main as reliability_main

    return reliability_main()


__all__ = ["main"]
