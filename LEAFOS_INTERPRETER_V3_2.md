# LeafOS Interpreter v3.2 — Category Discipline + Salience Gate

[English](LEAFOS_INTERPRETER_V3_2.en.md) · [Interpreter v3](LEAFOS_INTERPRETER.md) · [Bíblia](AGENTS.md)

A v3.2 é uma camada **aditiva** sobre a v3.1 já validada em uso real.

A v3.1 foi preservada intacta em:

```text
KageLink Installer/pc_agent/pc_agent/leafos_interpreter_v31.py
```

E existe um snapshot Git separado do estado funcional validado:

```text
branch: archive/interpreter-v3.1-working
commit: 8d0d2a0d3996ee4a6b66a7f7646dc69e4f024700
```

A v3.2 não substitui nem reescreve esse arquivo. O executável de preview passa a importar `leafos_interpreter_v32.py`, que herda da v3.1.

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
│ Memory Reviewer       │ preservados para audit  │
└───────────────────────┴─────────────────────────┘
```

## Category Gate

O Category Gate não decide se algo é verdadeiro. Ele pergunta se um candidato verdadeiro pertence à categoria proposta.

Exemplo:

```text
Anbu repeatedly picked up and dropped a Large Kunai.
```

É um evento, mas não é por si só uma característica persistente de `Anbu`.

Assim, um candidato `characters` que descreve apenas uma ação transitória é movido para `suppressed_candidates` com:

```json
{
  "decision": "invalid_category",
  "signals": ["transient_character_observation"]
}
```

Relacionamentos também exigem evidência lexical de uma relação, e não mera coocorrência de dois nomes.

## Salience Gate

Depois do Category Gate, candidatos válidos recebem um score determinístico.

Sinais positivos incluem, entre outros:

- decisão/acordo;
- promessa, compromisso ou ameaça;
- mudança de estado ou consequência;
- mudança/revelação de relacionamento;
- transferência significativa de objeto;
- conflito/captura;
- revelação durável sobre personagem;
- diálogo;
- presença explícita do Primary Character na evidência.

Sinais negativos incluem:

- ação mecânica repetitiva;
- pickup/drop sem consequência ou contexto significativo;
- ação transitória sem mudança observável.

O threshold inicial é:

```text
score >= 2  → Memory Reviewer
score < 2   → suppressed_candidates
```

A decisão é auditável. Cada candidato suprimido preserva:

```json
{
  "category": "events",
  "decision": "low_salience",
  "score": -2,
  "signals": ["transient_object_interaction:-2"],
  "candidate": {
    "...": "candidato grounded original"
  }
}
```

Nada é promovido para Canonical Memory automaticamente.

## Caso de regressão: Senbon / Large Kunai

Entrada factual:

```text
Anbu picks up Senbon
Anbu picks up Large Kunai
Anbu drops Large Kunai
...
```

A v3.1 continua responsável por impedir invenções como treinamento ou preparação de missão.

A v3.2 acrescenta:

```text
characters: "Anbu was interacting with objects..."
    → invalid_category

event: "Anbu picks up Senbon"
    → low_salience

event: "Anbu repeatedly picks up and drops Large Kunai"
    → low_salience
```

Os candidatos continuam presentes em `suppressed_candidates`, mas não entram na fila principal do Memory Reviewer.

## Exemplo de evento que deve passar

```text
Kaede Says: Take this sealed scroll and deliver it to the Hokage.
Kaede gives Sealed Scroll to Anbu.
```

A transferência + instrução/dialogue fornecem sinais suficientes para chegar ao Reviewer.

## Compatibilidade e segurança

A v3.2:

- mantém o chunking e retry parcial da v3;
- mantém o Grounding Guard da v3.1;
- mantém `source_message_ids` e a cadeia RAW → Processor → Interpretation;
- não altera RAW;
- não altera sessões do Processor;
- não resolve `Anbu = Leafos` automaticamente;
- não escreve Canonical Memory;
- não usa um segundo LLM para decidir saliência;
- mantém candidatos suprimidos no bundle para auditoria;
- usa `prompt_version: leafos-interpreter-v3.2`, invalidando checkpoints anteriores para o novo pipeline.

Bundles v3.1 já concluídos não são sobrescritos automaticamente.
