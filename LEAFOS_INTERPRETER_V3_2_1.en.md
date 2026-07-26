# LeafOS Interpreter v3.2.1 — Durable System Revelations

[Português](LEAFOS_INTERPRETER_V3_2_1.md) · [v3.2](LEAFOS_INTERPRETER_V3_2.en.md) · [Development Bible](AGENTS.en.md)

v3.2.1 is an **additive** layer on top of v3.2. It does not rewrite v3.1 or v3.2.

Preserved baselines:

```text
v3.1: pc_agent/leafos_interpreter_v31.py
snapshot: archive/interpreter-v3.1-working
validated commit: 8d0d2a0d3996ee4a6b66a7f7646dc69e4f024700

v3.2: pc_agent/leafos_interpreter_v32.py
```

The preview executable now imports `leafos_interpreter_v321.py`, which subclasses v3.2.

## Problem observed in real use

A session composed mostly of mechanical actions was correctly filtered by v3.2, but it also contained two explicit durable system lines:

```text
Your primary Element is: Fire
Your secondary Element is: Earth
```

Because the model produced no candidates for those lines, the Reviewer was empty. This showed that information can be simultaneously:

- explicit and verifiable;
- durable;
- worth human review;
- yet absent from the LLM output.

## v3.2.1 rule

After the Grounding Guard and Salience Gate, v3.2.1 performs deterministic extraction for **system-revelation formats that have been observed and regression-tested**.

The first recognized family is:

```text
Your primary Element is: <value>
Your secondary Element is: <value>
```

Each line creates an independent `facts` candidate, for example:

```json
{
  "statement": "The system reported the primary Element as Fire.",
  "kind": "system_revelation",
  "confidence": 1.0,
  "source_message_ids": [12345],
  "review_status": "pending_review"
}
```

## Identity remains conservative

v3.2.1 does **not** turn:

```text
Your primary Element is: Fire
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

This prevents two failure modes:

1. losing a durable revelation because the LLM chose not to create a candidate;
2. broadly generalizing unknown system messages.

Additional formats such as rank, clan, village, or ability should be added only after their real log syntax is observed and a specific regression test exists.

## Salience and audit

When v3.2 had already suppressed an equivalent version of the same fact because of a low score, v3.2.1 removes only that matching `suppressed_candidates` record and keeps one reviewable version.

The bundle also records:

```json
{
  "prompt_version": "leafos-interpreter-v3.2.1",
  "grounding_prompt_version": "leafos-interpreter-v3.1",
  "salience_base_version": "leafos-interpreter-v3.2",
  "durable_system_revelations": {
    "mode": "deterministic_explicit_patterns",
    "identity_attribution": "not_inferred"
  }
}
```

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
