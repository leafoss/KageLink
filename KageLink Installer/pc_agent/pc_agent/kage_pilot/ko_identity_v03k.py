from __future__ import annotations

from dataclasses import dataclass
import re


_KO_IDENTITY_RE = re.compile(
    r"^(?P<name>.*?)\s+has\s+been\s+knocked(?:\s*-\s*|\s+)out\b",
    re.IGNORECASE,
)
_CURRENT_VISUAL_MODES = {"VISIBLE", "OCCLUDED", "CONTACT_REBIND"}


def collapse_spaces(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def extract_ko_identity(text: str) -> str | None:
    """Return the complete opponent label before ``has been Knocked-Out``.

    Examples:
        ``Jounin: Matsuda, Al has been Knocked-Out`` -> ``Jounin: Matsuda, Al``
        ``Jounin: Aoki, Ian has been knocked out`` -> ``Jounin: Aoki, Ian``
    """

    candidate = collapse_spaces(text)
    match = _KO_IDENTITY_RE.search(candidate)
    if match is None:
        return None
    name = collapse_spaces(match.group("name"))
    return name or None


def normalize_ko_identity(value: str | None) -> str:
    return collapse_spaces(value or "").casefold()


@dataclass(frozen=True, slots=True)
class KOIdentityDecision:
    accepted: bool
    reason: str
    candidate_name: str | None
    candidate_key: str
    previous_name: str | None
    previous_key: str
    visual_enemy_hits: int


class RoundKOIdentityGate:
    """Reject a repeated previous-round opponent KO and require current-round enemy evidence.

    The gate is intentionally independent from disposable visual track IDs. A target may receive
    several IDs during particles or occlusion. Two observations with current visual authority are
    enough to prove that this round contained a real enemy before a *different* KO name can end it.

    A repeated previous name always loses authority. That is the real-game corpse/revival case:
    the old opponent stood up, was attacked again and generated a second valid chat KO while the
    new opponent remained alive.
    """

    def __init__(
        self,
        previous_accepted_name: str | None = None,
        *,
        required_visual_hits: int = 2,
    ) -> None:
        previous = collapse_spaces(previous_accepted_name or "")
        self.previous_name = previous or None
        self.previous_key = normalize_ko_identity(previous)
        self.required_visual_hits = max(1, min(10, int(required_visual_hits)))
        self._visual_enemy_hits = 0

    @property
    def visual_enemy_hits(self) -> int:
        return self._visual_enemy_hits

    @property
    def current_round_enemy_validated(self) -> bool:
        return self._visual_enemy_hits >= self.required_visual_hits

    def observe_target(self, *, target_id: int | None, target_mode: str | None) -> bool:
        mode = str(target_mode or "").upper()
        if target_id is None or mode not in _CURRENT_VISUAL_MODES:
            return self.current_round_enemy_validated
        self._visual_enemy_hits = min(
            self.required_visual_hits,
            self._visual_enemy_hits + 1,
        )
        return self.current_round_enemy_validated

    def reset_current_enemy_evidence(self) -> None:
        self._visual_enemy_hits = 0

    def evaluate(self, text: str) -> KOIdentityDecision:
        candidate = extract_ko_identity(text)
        candidate_key = normalize_ko_identity(candidate)

        if not candidate_key:
            return KOIdentityDecision(
                accepted=False,
                reason="KO_IDENTITY_NOT_FOUND",
                candidate_name=candidate,
                candidate_key=candidate_key,
                previous_name=self.previous_name,
                previous_key=self.previous_key,
                visual_enemy_hits=self._visual_enemy_hits,
            )

        if self.previous_key and candidate_key == self.previous_key:
            return KOIdentityDecision(
                accepted=False,
                reason="REPEATED_PREVIOUS_OPPONENT",
                candidate_name=candidate,
                candidate_key=candidate_key,
                previous_name=self.previous_name,
                previous_key=self.previous_key,
                visual_enemy_hits=self._visual_enemy_hits,
            )

        if not self.current_round_enemy_validated:
            return KOIdentityDecision(
                accepted=False,
                reason="NO_CURRENT_ROUND_ENEMY",
                candidate_name=candidate,
                candidate_key=candidate_key,
                previous_name=self.previous_name,
                previous_key=self.previous_key,
                visual_enemy_hits=self._visual_enemy_hits,
            )

        return KOIdentityDecision(
            accepted=True,
            reason="NEW_OPPONENT_KO",
            candidate_name=candidate,
            candidate_key=candidate_key,
            previous_name=self.previous_name,
            previous_key=self.previous_key,
            visual_enemy_hits=self._visual_enemy_hits,
        )


__all__ = [
    "KOIdentityDecision",
    "RoundKOIdentityGate",
    "collapse_spaces",
    "extract_ko_identity",
    "normalize_ko_identity",
]
