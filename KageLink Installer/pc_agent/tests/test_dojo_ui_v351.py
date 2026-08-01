from __future__ import annotations

from pathlib import Path
import unittest

import unified_dojo_debug_v351
import unified_dojo_responsive_v351
import unified_dojo_stop_v351
import unified_dojo_ui_v351
import unified_launcher
from unified_dojo_templates_ui_v35 import CANONICAL_SIDEBAR_ORDER


class DojoDesktopV351ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = Path(unified_dojo_ui_v351.__file__).resolve()
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.responsive_source = Path(unified_dojo_responsive_v351.__file__).read_text(
            encoding="utf-8"
        )
        cls.debug_source = Path(unified_dojo_debug_v351.__file__).read_text(
            encoding="utf-8"
        )
        cls.stop_source = Path(unified_dojo_stop_v351.__file__).read_text(
            encoding="utf-8"
        )

    def test_four_canonical_tabs_exist_in_both_languages(self):
        required = {
            "dojo_tab_summary",
            "dojo_tab_settings",
            "dojo_tab_images",
            "dojo_tab_logs",
        }
        for language in ("pt-BR", "en-US"):
            self.assertTrue(required.issubset(unified_launcher.TEXT[language]))
        self.assertEqual(unified_dojo_ui_v351._DOJO_TABS, ("summary", "settings", "images", "logs"))

    def test_settings_remains_last_sidebar_item(self):
        self.assertEqual(CANONICAL_SIDEBAR_ORDER[-1], "settings")
        self.assertLess(CANONICAL_SIDEBAR_ORDER.index("dojo"), CANONICAL_SIDEBAR_ORDER.index("settings"))

    def test_layout_uses_grid_after_replacing_the_old_dojo_children(self):
        self.assertIn("for child in page.winfo_children():", self.source)
        self.assertIn("child.destroy()", self.source)
        self.assertIn('page.grid_columnconfigure(0, weight=1)', self.source)
        self.assertIn('page.grid_rowconfigure(2, weight=1)', self.source)
        self.assertIn('sticky="nsew"', self.source)

    def test_first_frame_initialization_and_resize_debounce_are_present(self):
        self.assertIn("self._rebuild_dojo_page_v351()", self.source)
        self.assertIn("self.root.after_idle(self._dojo_apply_responsive_layout)", self.source)
        self.assertIn('self.root.bind("<Configure>"', self.source)
        self.assertIn("self.root.after_cancel(self._dojo_resize_after)", self.source)
        self.assertIn("self.root.after(120, self._dojo_apply_responsive_layout)", self.source)
        self.assertNotIn("state('zoomed')", self.source)
        self.assertNotIn("iconify()", self.source)

    def test_ui_does_not_add_concept_only_combat_parameters(self):
        forbidden_catalog_keys = {
            "dojo_hp_target",
            "dojo_stamina_target",
            "dojo_chakra_target",
            "dojo_hit_wait",
            "dojo_continuous_mode",
        }
        for language in ("pt-BR", "en-US"):
            self.assertTrue(forbidden_catalog_keys.isdisjoint(unified_launcher.TEXT[language]))

    def test_editable_settings_are_backend_loaded_but_start_bound(self):
        self.assertIn("self._dojo_setting_dirty", self.debug_source)
        self.assertIn("_dojo_mark_setting_dirty", self.debug_source)
        self.assertIn("field not in self._dojo_setting_dirty", self.debug_source)
        self.assertIn("opacity_percent / 100.0", self.debug_source)
        self.assertIn("10.0 <= opacity_percent <= 100.0", self.debug_source)
        self.assertIn("40.0 <= chakra <= 100.0", self.debug_source)
        self.assertIn("self._dojo_setting_dirty.clear()", self.debug_source)
        self.assertNotIn("command=self._dojo_update_debug_live", self.debug_source)
        self.assertNotIn("command=lambda _value: self._dojo_update_debug_live()", self.debug_source)

    def test_stop_remains_available_while_start_request_is_busy(self):
        self.assertIn("self._dojo_stop_busy", self.stop_source)
        self.assertIn("self._dojo_running or self._dojo_busy", self.stop_source)
        self.assertIn("DojoStopStartupSafe", self.stop_source)
        self.assertNotIn("if self._dojo_busy:\n                return", self.stop_source)

    def test_images_are_built_in_64_then_32_order_and_centered(self):
        self.assertIn('for column, mode in enumerate(("64", "32"))', self.source)
        self.assertIn("cards = list(image_grid.winfo_children())", self.responsive_source)
        self.assertNotIn("reversed(image_grid.winfo_children())", self.responsive_source)
        template_source = Path(unified_dojo_ui_v351.__file__).with_name(
            "unified_dojo_templates_ui_v35.py"
        ).read_text(encoding="utf-8")
        self.assertIn('anchor="center"', template_source)
        self.assertIn("_fit_preview_image", template_source)

    def test_log_page_is_summary_only_not_a_live_console(self):
        required = {
            "dojo_log_state",
            "dojo_log_time",
            "dojo_log_summary",
            "dojo_log_file",
            "dojo_log_open",
            "dojo_log_open_folder",
        }
        for language in ("pt-BR", "en-US"):
            self.assertTrue(required.issubset(unified_launcher.TEXT[language]))
        self.assertNotIn("Text(", self.source)


if __name__ == "__main__":
    unittest.main()
