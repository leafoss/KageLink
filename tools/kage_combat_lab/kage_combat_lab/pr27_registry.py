from __future__ import annotations

from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .pr27_fragments import DescriptorFactory
from .pr27_model import AppearanceDescriptor, KnownSprite, SpriteClass


class KnownSpriteRegistry:
    def __init__(self, sprites: Iterable[KnownSprite] = ()) -> None:
        self.sprites = tuple(sprites)

    @classmethod
    def from_directory(cls, root: Path) -> "KnownSpriteRegistry":
        if not root.is_dir():
            return cls()
        sprites: list[KnownSprite] = []
        for category in SpriteClass:
            category_root = root / category.value.lower()
            if not category_root.is_dir():
                continue
            for file_path in sorted(category_root.glob("*.png")):
                image = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                mask = np.where(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) > 3, 255, 0).astype(np.uint8)
                sprites.append(
                    KnownSprite(
                        sprite_id=file_path.stem,
                        name=file_path.stem,
                        category=category,
                        descriptors=(DescriptorFactory.from_masked_crop(image, mask),),
                    )
                )
        return cls(sprites)

    def best_match(self, descriptor: AppearanceDescriptor) -> tuple[KnownSprite | None, float]:
        best: KnownSprite | None = None
        best_score = 0.0
        for sprite in self.sprites:
            score = max(DescriptorFactory.similarity(descriptor, reference) for reference in sprite.descriptors)
            if score > best_score:
                best, best_score = sprite, score
        return best, best_score
