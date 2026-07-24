# LeafOS Interpreter v1

[Português](LEAFOS_INTERPRETER.md) · [README](README.md) · [Development Bible](AGENTS.en.md)

The **LeafOS Interpreter** is the semantic layer between technical sessions produced by `LeafOSProcessor` and a future canonical character memory.

Its question is:

> **What probably happened in this session, using only what was actually recorded in RP?**

## Core rule

The Interpreter **never writes canonical memory directly**.

```text
Shinobi Story Online
        ↓
KageLink / ChatChannelParser
        ↓
immutable RAW
        ↓
LeafOSProcessor
        ↓
closed session
        ↓
LeafOS Interpreter
        ↓
70 - LeafOS Inbox/Interpretations
        ↓
HUMAN REVIEW
        ↓
future canonical memory
```

Every generated interpretation remains:

```text
status: pending_review
```

## Input

The Interpreter only reads closed sessions from:

```text
<Vault>/80 - Processor/Sessions/*.json
```

It does not independently re-read the KageLink database to reinterpret history.

## Output

One candidate bundle is written per session to:

```text
<Vault>/70 - LeafOS Inbox/Interpretations/<session_id>.json
```

A bundle may contain:

- `events`;
- `characters`;
- `locations`;
- `relationships`;
- `facts` (including lore candidates);
- `leafos_memories`.

It also preserves the original session ID, timestamps, participants, message IDs, RAW sources, model name, prompt version, truncation state, and review status.

## Evidence contract

Every candidate must contain valid source IDs:

```json
"source_message_ids": [101, 102]
```

Those IDs are checked against the exact transcript sent to the model. Candidates without valid evidence are discarded.

This preserves the chain:

```text
candidate
   ↓
source_message_ids
   ↓
session
   ↓
raw_source
   ↓
original RAW
```

## No outside knowledge

The Interpreter prompt explicitly forbids using outside Naruto knowledge, previous model knowledge, or unsupported assumptions.

It is instructed not to invent:

- identities;
- ranks;
- factions;
- locations;
- motives;
- relationships;
- outcomes;
- chronology.

Leafos memory candidates distinguish:

```text
observed
said
inferred
```

All of them still remain `pending_review`.

## Local AI and privacy

Interpreter v1 uses local **Ollama** by default:

```text
URL: http://127.0.0.1:11434
Model: qwen3:14b
```

It uses:

```text
POST /api/chat
```

with non-streaming structured JSON output and temperature `0`.

No Ollama Python package is required; the implementation uses Python's standard library.

Using a remote Ollama URL may transmit RP content to another machine, so only configure a remote endpoint intentionally.

## Running it

Prerequisites:

1. LeafOS Processor must already have at least one closed session.
2. Ollama must be running.
3. The selected model must exist.

```powershell
cd "KageLink Installer\pc_agent"
python -m pc_agent.leafos_interpreter `
  --vault "C:\path\LeafOS-Vault"
```

Select another model:

```powershell
python -m pc_agent.leafos_interpreter `
  --vault "C:\path\LeafOS-Vault" `
  --model "qwen3:14b"
```

Process only one new session:

```powershell
python -m pc_agent.leafos_interpreter `
  --vault "C:\path\LeafOS-Vault" `
  --max-sessions 1
```

## State and idempotency

State is stored in:

```text
<Vault>/80 - Interpreter/interpreter_state.json
```

Successfully processed sessions are not interpreted again. Failed sessions are **not** marked complete and can be retried later.

## Large sessions

The default transcript limit is:

```text
48000 characters
```

If a session exceeds the limit, the Interpreter preserves both the beginning and end of the session and marks:

```json
"transcript_truncated": true
```

Only IDs actually sent to the model remain valid evidence IDs.

## Failure behavior

If Ollama is unavailable, the model is missing, or structured output is invalid:

- canonical memory is untouched;
- the session is not marked complete;
- the error is stored in interpreter state;
- the session can be retried.

## Deliberate v1 limitations

Interpreter v1 does **not**:

- automatically write canonical notes;
- update official character profiles;
- modify the official timeline;
- decide that an inference is true;
- use OOC knowledge to complete RP;
- browse the internet;
- use Naruto wikis;
- silently use previous sessions as knowledge;
- delete RAW;
- modify Processor sessions.

## Next layer

After Interpreter v1 is validated, the next subsystem should be a **Reviewer / Memory Promoter**:

```text
Interpretation Bundle
        ↓
review
        ├── approve
        ├── edit
        └── reject
        ↓
Canonical Memory
        ├── Events
        ├── Characters
        ├── Locations
        ├── Relationships
        ├── Lore
        └── Leafos Memory
```

Only that future review layer should be allowed to promote candidates into permanent memory.