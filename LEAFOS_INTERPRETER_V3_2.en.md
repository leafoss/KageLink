# LeafOS Interpreter v3.2 — Category Discipline + Salience Gate

[Português](LEAFOS_INTERPRETER_V3_2.md) · [Interpreter v3](LEAFOS_INTERPRETER.en.md) · [Development Bible](AGENTS.en.md)

v3.2 is an **additive** layer on top of the already live-validated v3.1 implementation.

v3.1 remains intact at:

```text
KageLink Installer/pc_agent/pc_agent/leafos_interpreter_v31.py
```

A separate Git snapshot preserves the validated working state:

```text
branch: archive/interpreter-v3.1-working
commit: 8d0d2a0d3996ee4a6b66a7f7646dc69e4f024700
```

v3.2 does not replace or rewrite that file. The preview executable imports `leafos_interpreter_v32.py`, which subclasses v3.1.

## Pipeline

```text
RAW
 ↓
Processor
 ↓
Interpreter v3 chunking/checkpoint
 ↓
v3.1 Grounding Guard
 ↓
v3.2 Category Gate
 ↓
v3.2 Salience Gate
 ↓
┌───────────────────────┬─────────────────────────┐
│ review candidates     │ suppressed_candidates   │
│ Memory Reviewer       │ retained for audit      │
└───────────────────────┴─────────────────────────┘
```

## Category Gate

The Category Gate does not decide whether something is true. It asks whether a grounded candidate belongs in the proposed category.

Example:

```text
Anbu repeatedly picked up and dropped a Large Kunai.
```

That is an event, but by itself it is not a persistent character trait of `Anbu`.

Therefore a `characters` candidate that only describes a transient action is moved to `suppressed_candidates` with:

```json
{
  "decision": "invalid_category",
  "signals": ["transient_character_observation"]
}
```

Relationships also require lexical evidence of a relationship rather than mere co-occurrence of two names.

## Salience Gate

After the Category Gate, valid candidates receive a deterministic score.

Positive signals include, among others:

- decisions/agreements;
- promises, commitments, or threats;
- state changes or consequences;
- relationship changes/revelations;
- meaningful object transfers;
- conflict/capture;
- durable character revelations;
- dialogue;
- explicit Primary Character presence in the evidence.

Negative signals include:

- repetitive mechanical actions;
- pickup/drop actions without consequence or meaningful context;
- transient actions without observable change.

The initial threshold is:

```text
score >= 2  → Memory Reviewer
score < 2   → suppressed_candidates
```

The decision remains auditable. Every suppressed candidate preserves:

```json
{
  "category": "events",
  "decision": "low_salience",
  "score": -2,
  "signals": ["transient_object_interaction:-2"],
  "candidate": {
    "...": "original grounded candidate"
  }
}
```

Nothing is promoted to Canonical Memory automatically.

## Regression case: Senbon / Large Kunai

Grounded input:

```text
Anbu picks up Senbon
Anbu picks up Large Kunai
Anbu drops Large Kunai
...
```

v3.1 remains responsible for blocking invented training or mission-preparation explanations.

v3.2 adds:

```text
characters: "Anbu was interacting with objects..."
    → invalid_category

event: "Anbu picks up Senbon"
    → low_salience

event: "Anbu repeatedly picks up and drops Large Kunai"
    → low_salience
```

The candidates remain available under `suppressed_candidates`, but they do not enter the main Memory Reviewer queue.

## Example of an event that should pass

```text
Kaede Says: Take this sealed scroll and deliver it to the Hokage.
Kaede gives Sealed Scroll to Anbu.
```

The transfer plus instruction/dialogue produce enough signals for the candidate to reach the Reviewer.

## Compatibility and safety

v3.2:

- preserves v3 chunking and partial retry;
- preserves the v3.1 Grounding Guard;
- preserves `source_message_ids` and the RAW → Processor → Interpretation evidence chain;
- does not modify RAW;
- does not modify Processor sessions;
- does not automatically resolve `Anbu = Leafos`;
- does not write Canonical Memory;
- does not use a second LLM to decide salience;
- keeps suppressed candidates in the bundle for audit;
- uses `prompt_version: leafos-interpreter-v3.2`, invalidating older checkpoints for the new pipeline.

Already completed v3.1 bundles are not overwritten automatically.
