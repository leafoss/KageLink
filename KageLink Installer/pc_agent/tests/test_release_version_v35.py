from __future__ import annotations

from pathlib import Path
import re
import unittest


class KageLinkReleaseVersionV35Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository_root = Path(__file__).resolve().parents[3]
        cls.installer_root = cls.repository_root / "KageLink Installer"
        cls.expected = (cls.repository_root / "RELEASE_VERSION").read_text(
            encoding="utf-8"
        ).strip()

    def test_canonical_release_version_is_350(self):
        self.assertEqual(self.expected, "3.5.0")

    def test_android_pubspec_matches_release_version(self):
        pubspec = (self.installer_root / "pubspec.yaml").read_text(encoding="utf-8")
        self.assertRegex(
            pubspec,
            rf"(?m)^version:\s*{re.escape(self.expected)}\+\d+\s*$",
        )

    def test_pc_agent_matches_release_version(self):
        unified_app = (
            self.installer_root / "pc_agent" / "unified_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(f'APP_VERSION = "{self.expected}"', unified_app)

    def test_windows_setup_matches_release_version(self):
        iss = (
            self.installer_root / "installer" / "KageLink_PC_Agent.iss"
        ).read_text(encoding="utf-8-sig")
        self.assertIn(f'#define MyAppVersion "{self.expected}"', iss)
        self.assertIn(
            f"OutputBaseFilename=KageLink-PC-Agent-Setup-v{self.expected}",
            iss,
        )
        self.assertIn(f"VersionInfoVersion={self.expected}.0", iss)

    def test_manual_build_outputs_match_release_version(self):
        apk_builder = (self.installer_root / "COMPILAR_APK.bat").read_text(
            encoding="utf-8"
        )
        setup_builder = (
            self.installer_root / "installer" / "CRIAR_INSTALADOR.bat"
        ).read_text(encoding="utf-8")
        self.assertIn(f"KageLink-v{self.expected}.apk", apk_builder)
        self.assertIn(
            f"KageLink-PC-Agent-Setup-v{self.expected}.exe",
            setup_builder,
        )

    def test_ci_builds_matching_windows_and_android_preview_artifacts(self):
        workflow = (
            self.repository_root / ".github" / "workflows" / "leafos-memory-reviewer.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(f"KageLink-{self.expected}-Windows-preview", workflow)
        self.assertIn(f"KageLink-{self.expected}-Android-preview", workflow)
        self.assertIn(
            f"KageLink-PC-Agent-Setup-v{self.expected}.exe",
            workflow,
        )
        self.assertIn("flutter build apk --release", workflow)


if __name__ == "__main__":
    unittest.main()
