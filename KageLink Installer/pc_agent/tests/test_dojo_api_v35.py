from __future__ import annotations

import unittest

import unified_app
import unified_app_v35
import unified_dojo_ui  # noqa: F401 - installs the bilingual catalog additions
import unified_launcher


class KageLinkDojoApiV35Tests(unittest.TestCase):
    def test_canonical_backend_exposes_authenticated_dojo_routes(self):
        self.assertIs(unified_app_v35.app, unified_app.app)
        self.assertIs(unified_app_v35.dojo_service, unified_app.dojo_service)

        routes = [
            route
            for route in unified_app.app.routes
            if str(getattr(route, "path", "")).startswith("/api/dojo/")
        ]
        by_key = {
            (method, route.path): route
            for route in routes
            for method in getattr(route, "methods", set())
        }
        for key in (
            ("GET", "/api/dojo/status"),
            ("POST", "/api/dojo/start"),
            ("POST", "/api/dojo/stop"),
        ):
            self.assertIn(key, by_key)
            self.assertGreaterEqual(
                len(getattr(by_key[key], "dependant").dependencies),
                1,
                f"{key} must require the KageLink authorization dependency",
            )
        self.assertEqual(len(routes), 3)
        self.assertEqual(unified_app.APP_VERSION, "3.5.0")
        self.assertEqual(unified_app.app.version, "3.5.0")

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
