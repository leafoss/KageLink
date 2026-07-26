# LeafOS Interpreter v3

[Português](LEAFOS_INTERPRETER.md) · [README](README.md) · [Development Bible](AGENTS.en.md)

The **LeafOS Interpreter** is the semantic layer between a session closed by `LeafOSProcessor` and the candidates shown to the **Memory Reviewer**.

It answers only this question:

> **What does this session support as a candidate, based on the messages that were actually recorded?**

The Interpreter **does not write canonical memory**.

```text
Shinobi Story Online
        ↓
KageLink / RAW
        ↓
LeafOSProcessor
        ↓
Closed session
        ↓
LeafOS Interpreter v3
        ↓
Interpretation Bundle
status: pending_review
        ↓
Memory Reviewer
        ↓
Approve / Edit + approve / Reject
        ↓
Canonical Memory
```

## Input contract

The Interpreter reads only closed sessions from:

```text
<Vault>/80 - Processor/Sessions/*.json
```

The Processor session remains the input contract. The Interpreter does not reconstruct past history by querying the KageLink database again and does not modify the original session.

Important fields include:

- `session_id`;
- `started_at` / `ended_at`;
- `primary_character`;
- `participants`;
- `message_ids`;
- `raw_sources`;
- `messages`.

## Evidence rule

Every candidate must cite one or more IDs that were actually supplied to the model:

```json
"source_message_ids": [101, 102]
```

Unknown IDs are removed. A candidate with no valid evidence is discarded.

The chain remains:

```text
candidate
   ↓
source_message_ids
   ↓
Processor session
   ↓
raw_source
   ↓
original RAW
```

## What changed in v3

v2 sent a large session to `qwen3:14b` in one request. Sessions beyond the old limit could also use only a head + tail selection. On local hardware this could produce `OLLAMA_TIMEOUT: 600s`, while messages in the middle might never reach the model.

v3 removes that behavior from normal processing.

### Lossless chunking

The default approximate transcript size per chunk is:

```text
9000 transcript characters per chunk
```

with a default overlap of:

```text
2 messages across chunk boundaries
```

Example:

```text
Large session
    │
    ├── Chunk 1
    ├── Chunk 2
    ├── Chunk 3
    └── Chunk 4
            ↓
       qwen3:14b
            ↓
 normalized partial results
            ↓
 deterministic merge
            ↓
 one Interpretation Bundle
```

Every message belongs to at least one chunk. v3 no longer uses the old head/tail cut for normal large-session interpretation.

The final bundle records:

```json
{
  "prompt_version": "leafos-interpreter-v3",
  "interpretation_mode": "chunked",
  "chunk_count": 4,
  "chunk_chars": 9000,
  "chunk_overlap_messages": 2,
  "transcript_truncated": false
}
```

Small sessions still use one chunk and record:

```json
"interpretation_mode": "single"
```

## Boundary context

The small overlap reduces the chance of separating a line or reaction from the immediately preceding context.

The prompt explicitly tells the model that it is seeing only one chunk. It is forbidden from inventing omitted chunks or continuity not present in the supplied messages.

## Deterministic merge

v3 **does not use another LLM to summarize or combine chunk outputs**.

The merge is code-driven:

```text
Chunk 1 candidates
Chunk 2 candidates
Chunk 3 candidates
        ↓
conservative deduplication
        ↓
union source_message_ids
        ↓
maximum confidence across exact duplicates
        ↓
pending_review
```

Candidates are treated as duplicates only when their structured semantic content is equivalent after simple normalization. Different content stays separate for the Reviewer to decide.

## Checkpoints and partial retry

During a multi-chunk session, temporary checkpoints are written to:

```text
<Vault>/80 - Interpreter/Checkpoints/<session_id>.json
```

Each completed chunk is persisted atomically before the next chunk starts.

Therefore, if this happens:

```text
Chunk 1 ✓
Chunk 2 ✓
Chunk 3 → OLLAMA_TIMEOUT
Chunk 4
Chunk 5
```

a later retry starts as:

```text
Chunk 1 ✓ reused
Chunk 2 ✓ reused
Chunk 3 → retry
Chunk 4 → process
Chunk 5 → process
```

Time spent on successful chunks is not discarded.

After the final bundle is created successfully, the temporary checkpoint for that session is removed.

## Stale-checkpoint protection

A checkpoint stores a fingerprint of the semantic session input, including messages, primary character, prompt version and chunk settings.

If the session or chunk configuration changes, old partial results are not reused. A new checkpoint is started.

## Failures

A failure still promotes nothing to canonical memory.

State in:

```text
<Vault>/80 - Interpreter/interpreter_state.json
```

records the session and, when applicable:

```json
{
  "error": "OLLAMA_TIMEOUT: 600s",
  "attempts": 2,
  "chunk_number": 3,
  "total_chunks": 5,
  "completed_chunks": 2,
  "last_failed_at": "..."
}
```

The session is **not** added to `processed_sessions` until the complete bundle exists.

The **Interpret pending** action can therefore retry the session while reusing a valid checkpoint.

## Desktop progress

The Desktop receives Interpreter progress events. During a large session, the status line can show:

```text
Working... · 2026-07-24_001 · 2/5
```

Failure dialogs also include the chunk position when available.

## Local AI / privacy

Default configuration:

```text
URL: http://127.0.0.1:11434
Model: qwen3:14b
Timeout: 600 seconds per chunk
```

With the default URL, content is sent only to the local Ollama server. A remote URL can transmit RP content to another computer/service.

The endpoint remains:

```text
POST /api/chat
```

with `stream: false`, `think: false`, temperature `0`, and JSON-Schema structured output.

## Output

The final bundle remains at:

```text
<Vault>/70 - LeafOS Inbox/Interpretations/<session_id>.json
```

Categories remain:

- `events`;
- `characters`;
- `locations`;
- `relationships`;
- `facts`;
- `leafos_memories`.

Everything remains:

```text
status: pending_review
```

No candidate becomes permanent memory without the Memory Reviewer and explicit human action.

## Execution

Normal use should go through `KageLink.exe`.

The CLI remains available for development and diagnostics:

```powershell
cd "KageLink Installer\pc_agent"
python -m pc_agent.leafos_interpreter `
  --vault "C:\path\LeafOS-Vault"
```

Useful test parameters:

```text
--chunk-chars 9000
--chunk-overlap-messages 2
--timeout 600
--max-sessions 1
```

`--max-transcript-chars` remains accepted as a compatibility alias for chunk size.

## What the Interpreter is still forbidden to do

v3 does not:

- write canonical memory automatically;
- modify character sheets;
- modify the official timeline;
- decide by itself that an inference is true;
- use OOC information to complete RP;
- query the internet or a wiki;
- use earlier sessions as implicit knowledge;
- delete RAW;
- modify Processor sessions;
- invent identities, ranks, factions, motives, locations, or outcomes.

The **Memory Reviewer** remains the mandatory gate between interpretation and canonical memory.
