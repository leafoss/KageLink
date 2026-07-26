# KageLink — Development Bible — LeafOS Interpreter Chapter

[Português](AGENTS_INTERPRETER.md) · [Main Bible](AGENTS.en.md) · [Interpreter v3.2.1](LEAFOS_INTERPRETER_V3_2_1.en.md)

This file is a **normative extension of `AGENTS.en.md`** for changes to the LeafOS Interpreter, Memory Reviewer, and contracts directly connected to the KageLink memory pipeline.

If there is a conflict, `AGENTS.en.md` remains the higher operational source. For Interpreter work, both must be read before changing code.

## 1. Protected pipeline

```text
immutable RAW
   ↓
Processor
   ↓
closed session
   ↓
Interpreter
   ↓
Interpretation Bundle / pending_review
   ↓
Memory Reviewer
   ↓
explicit human approval
   ↓
Canonical Memory
```

Permanent rules:

- RAW is not rewritten by the Interpreter;
- Processor sessions are not modified by the Interpreter;
- an Interpretation Bundle is not canonical memory;
- the Memory Reviewer remains a mandatory human gate;
- Canonical Memory cannot be created automatically by the Interpreter;
- evidence must remain traceable through `source_message_ids` back to Processor and RAW.

## 2. Interpreter v3 — long sessions

Large sessions must use ordered chunking instead of one oversized request.

Current contract:

```text
approximate chunk: 9000 characters
default overlap: 2 messages
timeout: per chunk
```

No middle message may be dropped by the normal flow. Completed chunks may be checkpointed and reused during partial retry.

A stale checkpoint must not be reused when the session, prompt, or chunk configuration changes.

## 3. Grounding v3.1

The model interprets only supplied evidence.

It is forbidden to invent or complete content using outside knowledge, including:

- identity;
- intent;
- training;
- mission preparation;
- item definitions;
- rank;
- faction;
- relationships;
- location;
- consequences.

The visible identity `Anbu` never proves `Anbu = Leafos` automatically.

## 4. Category Discipline + Salience v3.2

After grounding, deterministic gates may keep grounded but transient or miscategorized material from cluttering the Reviewer.

Suppressed candidates must not be silently deleted: they remain auditable in `suppressed_candidates`.

Suppression is not a canonical rejection. It only controls the normal Reviewer queue.

## 5. Durable System Revelations v3.2.1

Explicit durable system formats may receive deterministic extractors **only after the real syntax has been observed and covered by regression tests**.

First approved contract:

```text
Your primary Element is: <value>
Your secondary Element is: <value>
```

The real syntax observed in Processor output may also be wrapped:

```text
(***<visible identity>** Your primary Element is: <value>*)
(***<visible identity>** Your secondary Element is: <value>*)
```

The identity wrapper is presentation/transport evidence and **does not authorize ownership attribution**.

Reviewable output must remain neutral:

```text
The system reported the primary Element as Fire.
The system reported the secondary Element as Earth.
```

Do not automatically produce:

```text
Leafos has Fire/Earth
Anbu has Fire/Earth
```

## 6. Conflict between LLM output and deterministic extraction

When the LLM creates a redundant interpretation of the same revelation, for example:

```text
Anbu revealed the primary element as Fire.
```

with the same `source_message_id`, field, and value as the deterministic format:

1. the LLM version must not remain in the normal Reviewer queue;
2. the original LLM version must be preserved for audit in `suppressed_candidates`;
3. the Reviewer must receive the neutral deterministic version;
4. no identity resolution may be inferred during this replacement.

## 7. Canonical regression case

Real session used as the regression contract:

```text
session_id: 2026-07-26_011
13863: (***Anbu** Your primary Element is: Fire*)
13864: (***Anbu** Your secondary Element is: Earth*)
```

In the real run, the Reviewer showed that the LLM understood both elements but published them as events attributed to the visible `Anbu` wrapper:

```text
Revealing Primary Element
Anbu revealed the primary element as Fire.

Revealing Secondary Element
Anbu revealed the secondary element as Earth.
```

That result was used to harden the contract before merge. The automated regression uses the exact observed syntax and IDs and requires final post-processing to produce:

- two neutral `facts` candidates;
- IDs `13863` and `13864` preserved separately;
- no `Leafos`/`Anbu` ownership in final statements;
- redundant model versions only in audit data;
- mechanical pickup/drop noise remains outside the normal queue.

The manual validation proves the real input and that the pipeline detects the content; the neutral final form added after that log is covered by the corresponding automated regression.

## 8. Adding new system formats

Rank, clan, village, ability, attribute, or any new format may receive deterministic extraction only after:

1. capturing the real RAW/Processor line;
2. recording expected behavior;
3. adding a regression test with the real syntax;
4. preserving exact `source_message_ids`;
5. explicitly defining whether ownership is proven;
6. validating that v3/v3.1/v3.2 behavior is not broken;
7. updating PT-BR and EN-US documentation.

Do not create a generic system-message parser merely for convenience.

## 9. Definition of done for Interpreter changes

An Interpreter change is complete only when:

- Python tests pass;
- `compileall` passes;
- packaged build remains valid when affected;
- evidence stays traceable;
- Reviewer remains a human gate;
- identity is not inferred without proof;
- relevant real regressions are covered;
- PT-BR and EN-US documentation is updated;
- manual-validation limitations are recorded honestly.
