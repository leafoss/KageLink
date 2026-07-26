from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "RELEASE_VERSION").read_text(encoding="utf-8").strip()
PUBSPEC = (ROOT / "KageLink Installer" / "pubspec.yaml").read_text(encoding="utf-8")
PUBSPEC_VERSION_MATCH = re.search(r"^version:\s*([^\s]+)\s*$", PUBSPEC, re.MULTILINE)
if PUBSPEC_VERSION_MATCH is None:
    raise SystemExit("Could not read Flutter version from pubspec.yaml")
FLUTTER_VERSION = PUBSPEC_VERSION_MATCH.group(1)
START = "<!-- kagelink-downloads-start -->"
END = "<!-- kagelink-downloads-end -->"
WINDOWS_URL = "https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Windows-Setup.exe"
ANDROID_URL = "https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Android.apk"
RELEASE_URL = "https://github.com/leafoss/KageLink/releases/latest"


def block(language: str) -> str:
    if language == "pt-BR":
        return f"""{START}

## ⬇️ Download

**Versão estável atual: KageLink {VERSION}**

| Windows | Android |
| --- | --- |
| **[Baixar KageLink para Windows]({WINDOWS_URL})** | **[Baixar KageLink para Android]({ANDROID_URL})** |

No Windows, baixe o Setup e execute o instalador. O aplicativo Android é opcional e funciona como interface remota.

[Todos os downloads e SHA-256]({RELEASE_URL}) · [Guia rápido de instalação](DOWNLOAD.md)

{END}"""

    return f"""{START}

## ⬇️ Download

**Current stable version: KageLink {VERSION}**

| Windows | Android |
| --- | --- |
| **[Download KageLink for Windows]({WINDOWS_URL})** | **[Download KageLink for Android]({ANDROID_URL})** |

On Windows, download the Setup and run the installer. The Android app is optional and works as the remote interface.

[All downloads and SHA-256 checksums]({RELEASE_URL}) · [Quick installation guide](DOWNLOAD.md)

{END}"""


def insert_or_replace(path: Path, language: str) -> None:
    text = path.read_text(encoding="utf-8")
    replacement = block(language)

    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END),
        re.DOTALL,
    )
    if pattern.search(text):
        updated = pattern.sub(replacement, text, count=1)
    else:
        lines = text.splitlines()
        insert_at = None
        for index, line in enumerate(lines[:20]):
            if line.startswith("[") and ("README" in line or "AGENTS" in line):
                insert_at = index + 1
                break
        if insert_at is None:
            insert_at = 1
        lines[insert_at:insert_at] = ["", replacement, ""]
        updated = "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    updated = re.sub(
        r"(Flutter application is versioned as `)[^`]+(`\.)",
        rf"\g<1>{FLUTTER_VERSION}\g<2>",
        updated,
        count=1,
    )
    updated = re.sub(
        r"(aplicativo Flutter está versionado como `)[^`]+(`\.)",
        rf"\g<1>{FLUTTER_VERSION}\g<2>",
        updated,
        count=1,
    )

    # User-facing release assets intentionally use stable names. Keep developer
    # build-output references later in the README unchanged by replacing only
    # the first installation occurrence.
    updated = updated.replace(
        f"KageLink-PC-Agent-Setup-v{VERSION}.exe",
        "KageLink-Windows-Setup.exe",
        1,
    )
    updated = updated.replace(
        f"KageLink-v{VERSION}.apk",
        "KageLink-Android.apk",
        1,
    )

    path.write_text(updated, encoding="utf-8")


def main() -> None:
    insert_or_replace(ROOT / "README.md", "en-US")
    insert_or_replace(ROOT / "README.pt-BR.md", "pt-BR")


if __name__ == "__main__":
    main()
