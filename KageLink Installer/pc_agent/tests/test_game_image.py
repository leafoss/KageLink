from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pc_agent.game_image import transform_frame


class GameImageTests(unittest.TestCase):
    def test_full_mode_uses_fixed_output_without_distortion(self) -> None:
        source = Image.new("RGB", (400, 400), (255, 0, 0))
        result = transform_frame(source, "full", (960, 540))
        self.assertEqual(result.size, (960, 540))
        self.assertEqual(result.getpixel((480, 270)), (255, 0, 0))
        self.assertEqual(result.getpixel((5, 5)), (5, 7, 10))

    def test_zoom_mode_crops_around_center(self) -> None:
        source = Image.new("RGB", (800, 450), (0, 0, 0))
        draw = ImageDraw.Draw(source)
        draw.rectangle((300, 125, 500, 325), fill=(0, 255, 0))
        result = transform_frame(source, "zoom", (960, 540))
        self.assertEqual(result.size, (960, 540))
        center = result.getpixel((480, 270))
        self.assertGreater(center[1], 200)


if __name__ == "__main__":
    unittest.main()
