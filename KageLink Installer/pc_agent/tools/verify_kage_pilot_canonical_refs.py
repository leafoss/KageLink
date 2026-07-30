from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent.parent

PUBLIC_CONSUMERS = (
    ROOT / "kage_pilot.py",
    ROOT / "kage_pilot_dojo.py",
    ROOT / "kage_pilot_loop.py",
    ROOT / "kage_pilot_round.py",
    ROOT / "pc_agent" / "dojo_api.py",
    ROOT / "pc_agent" / "dojo_templates_api_v35.py",
    ROOT / "pc_agent" / "kage_pilot" / "__init__.py",
    ROOT / "pc_agent" / "kage_pilot" / "dojo_training_service.py",
    REPOSITORY_ROOT / "installer" / "KagePilotDojo.spec",
    REPOSITORY_ROOT / "installer" / "KagePilotRound.spec",
)

# These are deliberate compatibility boundaries. They may name the historical
# implementation provider until real Windows/BYOND validation authorizes the
# provider extraction and snapshot deletion.
COMPATIBILITY_ADAPTERS = (
    ROOT / "kage_pilot_loop.py",
    ROOT / "kage_pilot_round.py",
)

VERSIONED_REFERENCE = re.compile(r"(?:^|[^A-Za-z0-9])(?:[A-Za-z0-9_]*_v03[A-Za-z0-9_]*|v0\.3[A-Za-z0-9_]*)")


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def main() -> int:
    failures: list[str] = []
    for path in PUBLIC_CONSUMERS:
        if not path.exists():
            failures.append(f"MISSING:{relative(path)}")
            continue
        text = path.read_text(encoding="utf-8")
        if path in COMPATIBILITY_ADAPTERS:
            continue
        matches = sorted({match.group(0).strip() for match in VERSIONED_REFERENCE.finditer(text)})
        if matches:
            failures.append(f"VERSIONED_REFERENCE:{relative(path)}:{','.join(matches)}")

    if failures:
        print("KAGE_PILOT_CANONICAL_REFERENCE_GATE_FAILED")
        for failure in failures:
            print(failure)
        return 1

    print("KAGE_PILOT_CANONICAL_REFERENCE_GATE_OK")
    for path in PUBLIC_CONSUMERS:
        print(relative(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
