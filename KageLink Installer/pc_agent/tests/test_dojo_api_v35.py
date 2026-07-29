from __future__ import annotations

import unittest

import unified_app_v35
import unified_dojo_ui  # noqa: F401 - installs the bilingual catalog additions
import unified_launcher


class KageLinkDojoApiV35Tests(unittest.TestCase):
    def test_v35_backend_exposes_authenticated_dojo_routes(self):
        routes = {
            (method, route.path): route
            for route in unified_app_v35.app.routes
            for method in getattr(route, "methods", set())
        }
        for key in (
            ("GET", "/api/dojo/status"),
            ("POST", "/api/dojo/start"),
            ("POST", "/api/dojo/stop"),
        ):
            self.assertIn(key, routes)
            self.assertGreaterEqual(
                len(getattr(routes[key], "dependant").dependencies),
                1,
                f"{key} must require the KageLink authorization dependency",
            )

        self.assertEqual(unified_app_v35.APP_VERSION, "3.5.0")
        self.assertEqual(unified_app_v35.app.version, "3.5.0")

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
            "dojo_manual_controls_blocked" if False else "dojo_f12",
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
