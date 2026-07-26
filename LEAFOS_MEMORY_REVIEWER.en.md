# LeafOS Memory Reviewer v1

[Português (Brasil)](LEAFOS_MEMORY_REVIEWER.md)

The **LeafOS Memory Reviewer** is the human review layer between `pending_review` bundles produced by the LeafOS Interpreter and structured canonical memory.

It answers:

> **Which Interpreter candidates were reviewed by a human and may enter permanent memory?**

## Architectural boundary

```text
Shinobi Story Online
  → KageLink / Chat Parser
  → immutable RAW
  → LeafOS Processor
  → closed session
  → LeafOS Interpreter
  → Interpretation Bundle (pending_review)
  → LeafOS Memory Reviewer v1
  → Canonical Memory
  → future Memory Retrieval
  → future World Model
  → future Council
```

v1 stops at **human-reviewed canonical memory**. It does not implement World Model, Council, Executor or gameplay automation.

## Principles

1. The Interpreter produces candidates, never automatic truth.
2. No candidate becomes memory without human `Approve` or `Edit + approve`.
3. RAW, Processor sessions and Interpreter bundles are read-only to the Reviewer.
4. Promotion requires a valid evidence chain back to RAW.
5. Rejections remain recorded and do not return as pending.
6. The Reviewer does not use an LLM; validation and persistence are deterministic.
7. `PRIMARY_CHARACTER` is respected. The Reviewer never assumes Leafos.
8. Human-facing UI, controlled errors, CLI help and documentation support PT-BR and EN-US.

## Input and outputs

Input: `<Vault>/70 - LeafOS Inbox/Interpretations/*.json`

Review audit: `<Vault>/80 - Memory Reviewer/Reviews/<session_id>.json`

Canonical source: `<Vault>/60 - Canonical Memory/memory.json`

Obsidian projection: `<Vault>/60 - Canonical Memory/MEMORY.md`

`MEMORY.md` is a **DERIVED VIEW / VISUALIZAÇÃO DERIVADA** generated from `memory.json`; it is not a second canonical source. Structural labels are bilingual while approved memory content is preserved without automatic translation.

## Evidence and decisions

Before promotion the Reviewer validates Candidate → Interpretation Bundle → `source_message_ids` → Processor Session → `message.raw_source` → RAW marker + metadata + text.

Any inconsistency blocks promotion. A candidate with broken evidence may still be rejected.

- **Approve** preserves the Interpreter candidate and records canonical metadata and evidence.
- **Edit + approve** may correct content but cannot alter protected evidence fields.
- **Reject** creates no canonical memory and persists the reviewed decision.

Subjective memory requires a non-empty `primary_character`. Perspectives remain `observed`, `said`, or `inferred`. Dialogue and claims are not silently converted into objective truth.

## Local UI v1

The Tkinter UI is separate from the main Agent and supports pending sessions, `PRIMARY_CHARACTER`, candidate categories, confidence, perspective, evidence inspection, approve, edit + approve, reject, and live PT-BR/EN-US switching.

## Run

```powershell
python -m pc_agent.leafos_memory_reviewer --vault "C:\path\LeafOS-Vault"
python -m pc_agent.leafos_memory_reviewer --vault "C:\path\LeafOS-Vault" --lang en-US
python -m pc_agent.leafos_memory_reviewer --vault "C:\path\LeafOS-Vault" --list
```

## Tests

```powershell
python -m unittest tests.test_localization_contract -v
python -m unittest discover -s tests -p "test_leafos_memory_reviewer.py" -v
python -m unittest discover -s tests -v
python -m compileall .
```

## Deliberate v1 limitations

No decision reopening, automatic semantic merge, automatic contradiction resolution, LLM inside the Reviewer, RAW/Processor/Interpreter Bundle mutation, gameplay actions, World Model, or Council.
