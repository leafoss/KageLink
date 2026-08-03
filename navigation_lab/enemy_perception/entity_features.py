from __future__ import annotations

from typing import Any


class EntityFeatureExtractor:
    """Compact masked descriptor for a sprite-like overlay, independent from its terrain."""

    def __init__(self, normalized_size: int = 32) -> None:
        self.normalized_size = max(16, int(normalized_size))

    def extract(self, crop: Any, mask: Any) -> list[float]:
        import cv2
        import numpy as np

        if crop is None or mask is None or crop.size == 0 or mask.size == 0:
            raise ValueError("crop and mask are required")
        size = self.normalized_size
        resized = cv2.resize(crop[:, :, :3], (size, size), interpolation=cv2.INTER_AREA)
        resized_mask = cv2.resize(mask, (size, size), interpolation=cv2.INTER_NEAREST)
        pixels = resized[resized_mask > 0]
        if pixels.size == 0:
            pixels = resized.reshape(-1, 3)

        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        histogram = cv2.calcHist(
            [hsv], [0, 1], resized_mask, [12, 4], [0, 180, 0, 256]
        ).reshape(-1)
        histogram /= max(float(histogram.sum()), 1e-9)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        structure = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        structure[cv2.resize(resized_mask, (8, 8), interpolation=cv2.INTER_NEAREST) == 0] = 0
        edges = cv2.Canny(gray, 45, 135)
        edges[resized_mask == 0] = 0

        edge_blocks: list[float] = []
        occupancy: list[float] = []
        for row in range(4):
            for column in range(4):
                y0, y1 = row * size // 4, (row + 1) * size // 4
                x0, x1 = column * size // 4, (column + 1) * size // 4
                edge_blocks.append(float(edges[y0:y1, x0:x1].mean()) / 255.0)
                occupancy.append(float((resized_mask[y0:y1, x0:x1] > 0).mean()))

        ys, xs = np.where(resized_mask > 0)
        geometry = [
            float((resized_mask > 0).mean()),
            float(np.ptp(xs) + 1) / size if xs.size else 0.0,
            float(np.ptp(ys) + 1) / size if ys.size else 0.0,
            float(xs.mean()) / size if xs.size else 0.5,
            float(ys.mean()) / size if ys.size else 0.5,
        ]
        means = pixels.mean(axis=0) / 255.0
        deviations = pixels.std(axis=0) / 255.0
        vector = np.concatenate(
            [
                histogram.astype(np.float32),
                structure.reshape(-1),
                np.asarray(edge_blocks),
                np.asarray(occupancy),
                np.asarray(geometry),
                means,
                deviations,
            ]
        ).astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if norm > 1e-9:
            vector = vector / norm
        return [float(value) for value in vector]

    @staticmethod
    def similarity(left: list[float], right: list[float]) -> float:
        import numpy as np

        if not left or len(left) != len(right):
            return 0.0
        left_array = np.asarray(left, np.float32)
        right_array = np.asarray(right, np.float32)
        denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
        if denominator <= 1e-9:
            return 0.0
        return max(0.0, min(1.0, float(np.dot(left_array, right_array) / denominator)))
