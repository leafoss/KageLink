from __future__ import annotations

import unittest

import unified_app
import unified_app_v35
import unified_dojo_debug_v351  # noqa: F401
import unified_dojo_templates_ui_v35  # noqa: F401
import unified_dojo_ui  # noqa: F401
import unified_dojo_ui_v351  # noqa: F401
import unified_launcher


class KageLinkDojoApiV351Tests(unittest.TestCase):
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
            ("POST", "/api/dojo/debug"),
            ("GET", "/api/dojo/logs/latest"),
            ("GET", "/api/dojo/templates"),
            ("GET", "/api/dojo/templates/{mode}/image"),
            ("POST", "/api/dojo/templates/{mode}"),
            ("DELETE", "/api/dojo/templates/{mode}"),
        ):
            self.assertIn(key, by_key)
            self.assertGreaterEqual(
                len(getattr(by_key[key], "dependant").dependencies),
                1,
                f"{key} must require the KageLink authorization dependency",
            )
        self.assertEqual(len(routes), 9)
        self.assertEqual(unified_app.APP_VERSION, "3.5.1")
        self.assertEqual(unified_app.app.version, "3.5.1")

    def test_start_route_installs_the_351_debug_bridge(self):
        route = next(
            route
            for route in unified_app.app.routes
            if getattr(route, "path", "") == "/api/dojo/start"
            and "POST" in set(getattr(route, "methods", set()))
        )
        self.assertTrue(getattr(route.endpoint, "_kagelink_debug_bridge", False))
        self.assertIs(route.dependant.call, route.endpoint)

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
            "dojo_templates",
            "dojo_templates_help",
            "dojo_template_mode",
            "dojo_template_upload",
            "dojo_template_remove",
            "dojo_template_required",
            "dojo_tab_summary",
            "dojo_tab_settings",
            "dojo_tab_images",
            "dojo_tab_logs",
            "dojo_location_known",
            "dojo_location_uncertain",
            "dojo_location_lost",
            "dojo_log_open",
            "dojo_log_open_folder",
            "dojo_debug_title",
            "dojo_debug_enabled",
            "dojo_meditation_title",
            "dojo_meditation_enter_delay",
            "dojo_meditation_exit_delay",
            "dojo_combat_gate",
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
