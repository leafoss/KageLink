# Kage Pilot v0.3j — Knocked-out opponent identity buffer

**Date:** 2026-07-29  
**Status:** implementation complete; automated and physical validation pending  
**Scope:** chat victory authority across consecutive rounds

## Observed real-game failure

`Jounin: Matsuda, Al` was defeated and the round ended correctly. During the next round, Matsuda's body was still present. He stood up, was selected again and received a second knockout while the new opponent, `Jounin: Aoki, Ian`, continued attacking the player.

The second valid line:

```text
Jounin: Matsuda, Al has been Knocked-Out
```

was incorrectly treated as the new round's victory. Post-combat started while Aoki remained alive and contaminated the following round.

## Solution

The parent loop keeps the last accepted KO identity:

```text
last_accepted_ko_name = "Jounin: Matsuda, Al"
```

The identity is everything before:

```text
has been Knocked-Out
```

Normalization uses collapsed whitespace and `casefold()` for comparison while preserving the original label for telemetry.

## Acceptance rule

A KO line may end the round only when:

```text
current name != last accepted name
+ at least two current visual enemy observations occurred in this round
```

Accepted current visual modes:

```text
VISIBLE
OCCLUDED
CONTACT_REBIND
```

Isolated `CONTACT_MEMORY` is not current-enemy evidence.

## Repeated KO

```text
buffer: Jounin: Matsuda, Al
line:   Jounin: Matsuda, Al has been Knocked-Out
```

Result:

```text
KO_CANDIDATE name="Jounin: Matsuda, Al"
KO_REJECTED reason=REPEATED_PREVIOUS_OPPONENT
TARGET_INVALIDATED reason=KO_IDENTITY_REJECTED
COMBAT_CONTINUES
```

Rejection releases all inputs, does not start post-combat, does not replace the buffer, clears target/contact/facing/movement/burst state, preserves learned dynamic-background memory and requires new visual evidence before another KO can be accepted.

## Different opponent KO

```text
buffer: Jounin: Matsuda, Al
line:   Jounin: Aoki, Ian has been Knocked-Out
```

With a current enemy validated:

```text
KO_ACCEPTED reason=NEW_OPPONENT_KO
VICTORY_CHAT / VITORIA_CHAT: Jounin: Aoki, Ian has been Knocked-Out
KO_BUFFER_UPDATE previous=Jounin: Matsuda, Al current=Jounin: Aoki, Ian
```

The next round receives Aoki as the previous accepted identity.

## Different name without current-enemy evidence

A different name is still rejected when the round has not produced two current visual enemy observations:

```text
KO_REJECTED reason=NO_CURRENT_ROUND_ENEMY
```

This protects against replayed history, recreated chat controls and out-of-context messages.

## Persistence

The buffer lives in the parent loop and is passed to each child runtime through the internal argument:

```text
--previous-ko-name "Jounin: Matsuda, Al"
```

It persists throughout one multi-round run and is not stored permanently between independent executions.

## Canonical path

```text
kage_pilot_dojo.py
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
→ kage_pilot_live_v03k_round.py
→ RoundKOIdentityGate
```

`v03k` is an internal runtime hotfix layer. The public entry point remains `kage_pilot_dojo.py`, and the external release candidate remains labeled v0.3j.

## Files

```text
pc_agent/kage_pilot/ko_identity_v03k.py
kage_pilot_live_v03k_round.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_v03k_ko_identity.py
.github/workflows/kage-pilot-v03.yml
```

## Deliberate limitation

Two legitimate consecutive rounds with exactly the same generated opponent name are treated as suspicious. This conservative release-candidate policy prevents the observed revived-body failure. A future richer identity may combine the name, spawn event and visual signature.

## Remaining physical gate

Validate this sequence in a long run:

```text
Matsuda KO accepted
→ Matsuda revives and is knocked out again
→ KO_REJECTED
→ COMBAT_CONTINUES
→ Aoki KO accepted
→ buffer updated to Aoki
```

The PR remains a draft and is not merged.
