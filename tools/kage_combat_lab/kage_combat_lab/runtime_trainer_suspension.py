from __future__ import annotations

import os


def suspend_trainer_detector_for_validation(detector_class: type) -> bool:
    """Disable expensive Trainer template matching while combat cannot finish."""

    mode = os.environ.get("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY").strip().upper()
    if mode == "FULL_COMBAT":
        return False
    if getattr(detector_class, "_pr26_validation_suspended", False):
        return True

    def suspended_best_visual(self, frame_bgr, *, arena_rect=None):
        del frame_bgr, arena_rect
        self.last_template_scores = {}
        self.last_template_scales = {}
        self.last_accepted_template_mode = None
        self.last_accepted_template_source = None
        self.last_rejection_reason = "suspended-during-validation"
        self.last_raw_score = -1.0
        self.last_raw_scale = 1.0
        self.last_raw_location = None
        self.last_raw_template_mode = "-"
        self.last_raw_template_source = "-"
        return None

    detector_class._best_visual = suspended_best_visual
    detector_class._pr26_validation_suspended = True
    print(
        f"PR26.5 TRAINER SCAN SUSPENDED mode={mode}; "
        "template matching resumes only in FULL_COMBAT/post-KO flow"
    )
    return True


__all__ = ["suspend_trainer_detector_for_validation"]
