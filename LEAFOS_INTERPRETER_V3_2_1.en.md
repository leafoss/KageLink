# LeafOS Interpreter v3.2.1 — Durable System Revelations

[Português](LEAFOS_INTERPRETER_V3_2_1.md) · [v3.2](LEAFOS_INTERPRETER_V3_2.en.md) · [Main Bible](AGENTS.en.md) · [Normative Interpreter chapter](AGENTS_INTERPRETER.en.md)

v3.2.1 is an **additive** layer on top of v3.2. It does not rewrite v3.1 or v3.2.

Preserved baselines:

```text
v3.1: pc_agent/leafos_interpreter_v31.py
snapshot: archive/interpreter-v3.1-working
validated commit: 8d0d2a0d3996ee4a6b66a7f7646dc69e4f024700

v3.2: pc_agent/leafos_interpreter_v32.py
```

The packaged executable imports `leafos_interpreter_v321.py`, which subclasses v3.2.

## Problem observed in real use

A session composed mostly of mechanical actions was correctly filtered by v3.2, but it also contained two explicit durable system lines:

```text
Your primary Element is: Fire
Your secondary Element is: Earth
```

Because the model may omit those lines, information can be simultaneously:

- explicit and verifiable;
- durable;
- worth human review;
- yet absent from the LLM output.

For that reason, v3.2.1 does not rely only on the model for known system formats.

## Real syntax confirmed in the game

Real validation of session `2026-07-26_011` showed that the Processor preserves those messages inside the game's visible RP-style wrapper:

```text
(***Anbu** Your primary Element is: Fire*)
(***Anbu** Your secondary Element is: Earth*)
```

Observed IDs in that session:

```text
13863 → primary Element = Fire
13864 → secondary Element = Earth
```

The `***Anbu**` wrapper is treated only as presentation/transport evidence. It **does not prove** that the result belongs to Anbu, Leafos, or the configured `primary_character`.

## v3.2.1 rule

After the Grounding Guard and Salience Gate, v3.2.1 performs deterministic extraction for **system-revelation formats that have been observed and regression-tested**.

The first recognized family is:

```text
Your primary Element is: <value>
Your secondary Element is: <value>
```

It is accepted both directly and in the observed real wrapper:

```text
(***<visible identity>** Your primary Element is: <value>*)
(***<visible identity>** Your secondary Element is: <value>*)
```

Each line creates an independent `facts` candidate, for example:

```json
{
  "statement": "The system reported the primary Element as Fire.",
  "kind": "system_revelation",
  "confidence": 1.0,
  "source_message_ids": [13863],
  "review_status": "pending_review"
}
```

## Replacing redundant model interpretation

In real validation, the LLM produced candidates such as:

```text
Revealing Primary Element
Anbu revealed the primary element as Fire.

Revealing Secondary Element
Anbu revealed the secondary element as Earth.
```

Those candidates were grounded to the correct IDs, but they introduced unnecessary identity attribution.

v3.2.1 now recognizes the same `source_message_id` + field + value and:

1. removes the model version from the normal Reviewer queue;
2. preserves the original model output in `suppressed_candidates` for audit with `decision: replaced_by_durable_system_revelation`;
3. places only the neutral deterministic fact in the Reviewer.

Expected result for the real session:

```text
The system reported the primary Element as Fire.
The system reported the secondary Element as Earth.
```

## Identity remains conservative

v3.2.1 does **not** turn:

```text
(***Anbu** Your primary Element is: Fire*)
```

into:

```text
Leafos has Fire as primary Element
```

or:

```text
Anbu has Fire as primary Element
```

without explicit identity resolution.

The candidate remains neutral:

```text
The system reported the primary Element as Fire.
```

This preserves the revelation without inventing who owns the result.

## Why this is deterministic

This path does not depend on the model noticing the importance of the line. Code creates a candidate only when the message matches a known and tested format.

This prevents three failure modes:

1. losing a durable revelation because the LLM chose not to create a candidate;
2. assigning the revelation to a visible identity without proof of ownership;
3. broadly generalizing unknown system messages.

Additional formats such as rank, clan, village, or ability should be added only after their real log syntax is observed and a specific regression test exists.

## Salience and audit

When v3.2 had already suppressed an equivalent version, or the model produced a redundant reviewable version, v3.2.1 keeps one deterministic version in the normal queue and preserves the necessary audit record under `suppressed_candidates`.

The bundle also records:

```json
{
  "prompt_version": "leafos-interpreter-v3.2.1",
  "grounding_prompt_version": "leafos-interpreter-v3.1",
  "salience_base_version": "leafos-interpreter-v3.2",
  "durable_system_revelations": {
    "mode": "deterministic_explicit_patterns",
    "identity_attribution": "not_inferred",
    "wrapped_log_syntax_supported": true,
    "replaced_model_candidates": 2
  }
}
```

## Regression from real validation

The automated regression now reproduces the syntax and IDs observed in `2026-07-26_011`:

```text
13863 (***Anbu** Your primary Element is: Fire*)
13864 (***Anbu** Your secondary Element is: Earth*)
```

It also reproduces the two model-generated events and requires the final Reviewer output to contain only the two neutral `facts`.

## Safety

v3.2.1 does not:

- modify RAW;
- modify Processor sessions;
- alter the v3.1 Grounding Guard;
- remove the v3.2 Salience Gate;
- create Canonical Memory automatically;
- resolve `Anbu = Leafos`;
- use outside knowledge;
- use a second LLM.

The Memory Reviewer remains the mandatory human gate.
