from __future__ import annotations

from .grid_target_observer_v03 import GridTargetObserver


class StrictGridTargetObserver(GridTargetObserver):
    """Stricter grid gate after real water-only validation.

    Two safety changes:
    - geometry alone may acquire TARGET only in the immediately adjacent/contact cell;
      every farther candidate must show coherent cell-to-cell approach;
    - LOST tracks never refresh CONTACT MEMORY from a stale near-player position. Only
      VISIBLE adjacency or OCCLUDED contact can extend the latch.
    """

    def _grid_eligible(self, track, state, *, for_keep: bool) -> bool:
        tracker = self.tracker
        context = tracker.context_for(track.track_id)
        metrics = self._last_metrics[track.track_id]

        if context.state == "OCCLUDED":
            return True
        if context.state != "VISIBLE":
            return False

        target_eligible = getattr(tracker, "target_eligible", None)
        if callable(target_eligible) and not target_eligible(
            track.track_id,
            player_center=state.player_center,
            now=state.timestamp,
            for_keep=for_keep,
        ):
            return False

        # Adjacent cell is the only geometry-only acquisition path. This preserves
        # melee responsiveness while preventing water two or more cells away from
        # becoming TARGET due to one noisy motion spike.
        if metrics.grid_distance <= 1:
            return True

        # Any target farther than direct contact must demonstrate an actual trajectory
        # through successive cells toward PLAYER. Strong background evidence makes this
        # requirement even more important, but no separate relaxed path exists anymore.
        return metrics.coherent_approach

    def _latch_contact(self, track, state) -> None:
        context = self.tracker.context_for(track.track_id)
        metrics = self._last_metrics[track.track_id]

        real_contact = context.state == "OCCLUDED"
        visible_adjacent = context.state == "VISIBLE" and metrics.grid_distance <= 1
        if not (real_contact or visible_adjacent):
            return

        self._contact_latch_until = max(
            self._contact_latch_until,
            state.timestamp + self.contact_lock_seconds,
        )
        if context.last_visible_side != "-":
            self._contact_side = context.last_visible_side
        elif context.relative_side != "-":
            self._contact_side = context.relative_side
