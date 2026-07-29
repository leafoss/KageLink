from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from pc_agent.release_version import release_version, release_version_path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INSTALLER_ROOT = REPOSITORY_ROOT / "KageLink Installer"


class ReleaseVersionContractTests(unittest.TestCase):
    def test_release_version_loader_uses_repository_source(self):
        expected = (REPOSITORY_ROOT / "RELEASE_VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(release_version_path(), REPOSITORY_ROOT / "RELEASE_VERSION")
        self.assertEqual(release_version(), expected)

    def test_release_consumers_match_canonical_value(self):
        version = release_version()
        pubspec = (INSTALLER_ROOT / "pubspec.yaml").read_text(encoding="utf-8")
        installer = (
            INSTALLER_ROOT / "installer" / "KageLink_PC_Agent.iss"
        ).read_text(encoding="utf-8-sig")
        readme_en = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        readme_pt = (REPOSITORY_ROOT / "README.pt-BR.md").read_text(encoding="utf-8")
        agents_en = (REPOSITORY_ROOT / "AGENTS.en.md").read_text(encoding="utf-8")
        agents_pt = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertRegex(pubspec, rf"(?m)^version: {version.replace('.', r'\.') }\+[0-9]+$")
        self.assertIn(f'#define MyAppVersion "{version}"', installer)
        for text in (readme_en, readme_pt, agents_en, agents_pt):
            self.assertIn(version, text)

    def test_packaged_entry_applies_version_to_backend_and_health_source(self):
        # Importing unified_entry is Windows-only. Keep this contract platform-
        # independent by checking the narrow helper body and its runtime targets.
        source = (INSTALLER_ROOT / "pc_agent" / "unified_entry.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from pc_agent.release_version import release_version", source)
        self.assertIn("unified_backend.legacy.APP_VERSION = version", source)
        self.assertIn("unified_backend.legacy.app.version = version", source)
        self.assertIn("unified_backend.app.version = version", source)

    def test_pyinstaller_bundles_release_version(self):
        spec = (INSTALLER_ROOT / "installer" / "KageLink.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn("RELEASE_VERSION", spec)


if __name__ == "__main__":
    unittest.main()
