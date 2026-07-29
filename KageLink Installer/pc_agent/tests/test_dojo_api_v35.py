from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

import unified_dojo_ui  # noqa: F401 - installs the bilingual catalog additions
import unified_launcher


class KageLinkDojoApiV35Tests(unittest.TestCase):
    def test_v35_backend_exposes_authenticated_dojo_routes_in_clean_process(self):
        project_dir = Path(__file__).resolve().parents[1]
        probe = f'''\
import json
import sys
sys.path.insert(0, {str(project_dir)!r})
import unified_app
import unified_app_v35

payload = []
for route in unified_app_v35.app.routes:
    path = getattr(route, "path", "")
    if path.startswith("/api/dojo/"):
        payload.append({{
            "path": path,
            "methods": sorted(getattr(route, "methods", set())),
            "dependencies": len(getattr(route, "dependant").dependencies),
        }})
print("DOJO_V35_ROUTES=" + json.dumps(payload, sort_keys=True))
print("DOJO_V35_VERSION=" + unified_app_v35.app.version)
'''
        result = subprocess.run(
            [sys.executable, "-I", "-c", probe],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"clean backend probe failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        route_line = next(
            (line for line in result.stdout.splitlines() if line.startswith("DOJO_V35_ROUTES=")),
            "",
        )
        version_line = next(
            (line for line in result.stdout.splitlines() if line.startswith("DOJO_V35_VERSION=")),
            "",
        )
        self.assertTrue(route_line, result.stdout)
        routes = json.loads(route_line.partition("=")[2])
        by_key = {
            (method, item["path"]): item
            for item in routes
            for method in item["methods"]
        }
        for key in (
            ("GET", "/api/dojo/status"),
            ("POST", "/api/dojo/start"),
            ("POST", "/api/dojo/stop"),
        ):
            self.assertIn(key, by_key, result.stdout)
            self.assertGreaterEqual(
                int(by_key[key]["dependencies"]),
                1,
                f"{key} must require the KageLink authorization dependency",
            )
        self.assertEqual(len(routes), 3, result.stdout)
        self.assertEqual(version_line, "DOJO_V35_VERSION=3.5.0")

    def test_desktop_dojo_catalog_has_pt_br_en_us_parity(self):
        required = {
            "dojo",
            "dojo_title",
            "dojo_help",
            "dojo_rounds",
            "dojo_start",
            "dojo_stop",
            "dojo_phase",
            "dojo_progress",
            "dojo_runtime",
            "dojo_last_event",
            "dojo_f12",
        }
        pt = unified_launcher.TEXT["pt-BR"]
        en = unified_launcher.TEXT["en-US"]
        self.assertTrue(required.issubset(pt))
        self.assertTrue(required.issubset(en))
        self.assertEqual(
            {key for key in pt if key.startswith("dojo")},
            {key for key in en if key.startswith("dojo")},
        )


if __name__ == "__main__":
    unittest.main()
