# LeafOS Memory Reviewer v1

O **LeafOS Memory Reviewer** é a camada humana entre os bundles `pending_review` do `LeafOS Interpreter` e a primeira memória canônica estruturada do personagem.

Ele responde à pergunta:

> **Quais candidatos do Interpreter foram revisados por uma pessoa e podem entrar na memória permanente?**

## Limite arquitetural

```text
Shinobi Story Online
        ↓
KageLink / Chat Parser
        ↓
RAW imutável
        ↓
LeafOSProcessor
        ↓
Sessão fechada
        ↓
LeafOS Interpreter
        ↓
Interpretation Bundle (pending_review)
        ↓
LeafOS Memory Reviewer v1
        ↓
Canonical Memory
        ↓
futuro Memory Retrieval
        ↓
futuro World Model
        ↓
futuro Council
```

O v1 termina em **memória canônica revisada por humano**. Ele não implementa World Model, Council, Executor ou automação de gameplay.

## Princípios

1. O Interpreter produz candidatos, nunca verdades automáticas.
2. Nenhum candidato vira memória sem `Aprovar` ou `Editar + aprovar` por uma pessoa.
3. RAW, sessão do Processor e bundle do Interpreter são somente leitura para o Reviewer.
4. Promoção exige cadeia de evidência válida até o RAW.
5. Rejeições ficam registradas e não reaparecem como pendentes.
6. O Reviewer não usa LLM. Validação, deduplicação, evidência e persistência são determinísticas.
7. `PRIMARY_CHARACTER` é respeitado; o Reviewer nunca presume Leafos.

## Entrada

Bundles do Interpreter:

```text
<Vault>/70 - LeafOS Inbox/Interpretations/*.json
```

O Reviewer lê as categorias atuais:

- `events`;
- `characters`;
- `locations`;
- `relationships`;
- `facts`;
- `leafos_memories` (nome legado; semanticamente pertence ao `PRIMARY_CHARACTER`).

## Saídas graváveis

O Reviewer só escreve dentro de duas estruturas novas.

### Auditoria de revisão

```text
<Vault>/80 - Memory Reviewer/Reviews/<session_id>.json
```

Cada candidato recebe uma decisão persistida:

```text
approved
edited_and_approved
rejected
```

A ausência de decisão equivale a `pending_review`.

### Memória canônica

Fonte computável única:

```text
<Vault>/60 - Canonical Memory/memory.json
```

Visualização para Obsidian:

```text
<Vault>/60 - Canonical Memory/MEMORY.md
```

`MEMORY.md` é explicitamente **DERIVED VIEW**. Ele é regenerado a partir de `memory.json` e não é uma segunda fonte canônica.

## Categorias canônicas

O `memory.json` usa:

```text
events
characters
locations
relationships
lore
memories
```

Mapeamento do Interpreter:

```text
events           → events
characters       → characters
locations        → locations
relationships    → relationships
facts            → lore
leafos_memories  → memories
```

## Identidade e idempotência

Cada candidato recebe um `candidate_id` determinístico calculado a partir de:

- `session_id`;
- categoria;
- posição no bundle;
- conteúdo original do candidato.

A memória promovida usa:

```text
memory_id = mem-<candidate_id>
```

Repetir uma aprovação não cria uma segunda memória.

Bundles do Interpreter são tratados como imutáveis; mudar um bundle já emitido não faz parte do fluxo normal.

## Cadeia de evidência

Antes de aprovar ou editar+aprovar, o Reviewer valida:

```text
Candidate
   ↓
Interpretation Bundle
   ↓
source_message_ids
   ↓
Processor Session
   ↓
message.raw_source
   ↓
RAW marker + metadata + text
```

Para cada `source_message_id`, ele verifica:

- ID presente no bundle;
- ID presente na sessão fechada do Processor;
- mensagem correspondente existente na sessão;
- `raw_source` pertencente às fontes da sessão;
- arquivo RAW existente;
- marcador RAW contendo o mesmo ID;
- timestamp coerente;
- canal coerente;
- speaker coerente;
- texto coerente.

Qualquer inconsistência bloqueia **promoção**.

Um candidato com evidência quebrada ainda pode ser **rejeitado**. A rejeição grava `evidence_valid: false` e o erro encontrado, evitando que o mesmo candidato defeituoso reapareça indefinidamente.

## Aprovar

`Aprovar` preserva o candidato do Interpreter e cria uma entrada canônica com:

- `memory_id`;
- categoria canônica;
- categoria de origem;
- `session_id`;
- `primary_character`;
- confiança original do Interpreter;
- conteúdo aprovado;
- perspectiva/estado epistêmico;
- evidência completa;
- caminhos para bundle, sessão e RAW;
- timestamp de revisão;
- snapshot do candidato original.

## Editar + aprovar

A edição humana pode corrigir conteúdo sem apagar a proposta original.

O Reviewer registra:

```text
original_candidate
approved_candidate
review_status: edited_and_approved
reviewed_at
```

Campos de evidência/medição do Interpreter não podem ser adulterados durante a edição:

```text
source_message_ids
confidence
review_status
```

A perspectiva pode ser corrigida, mas, quando presente, precisa continuar em:

```text
observed
said
inferred
```

## Rejeitar

`Rejeitar` não cria memória canônica.

A decisão é persistida em `80 - Memory Reviewer/Reviews` para impedir reaparecimento do candidato.

O v1 não possui fluxo de “reabrir decisão”. Uma mudança futura desse tipo deve ser explícita e auditável.

## PRIMARY_CHARACTER e memória subjetiva

Uma entrada oriunda de `leafos_memories` exige `primary_character` não vazio.

Exemplo conceitual:

```json
{
  "category": "memories",
  "primary_character": "Matsunaya, Raika",
  "epistemic": {
    "type": "character_memory",
    "perspective": "said",
    "known_by": "Matsunaya, Raika",
    "speaker": "Uzumaki, Urahara"
  }
}
```

Dessa forma, memórias de personagens diferentes podem coexistir no mesmo armazenamento sem perder o proprietário epistemológico.

## Perspectiva e epistemologia

O schema v1 distingue pelo menos:

### Memória subjetiva

```text
observed
said
inferred
```

### `facts` do Interpreter

Um `fact` com `kind` do tipo `statement`, `claim`, `said`, `report` ou `reported` é armazenado como:

```text
epistemic.type = claim
epistemic.perspective = said
```

Quando a evidência possui um único speaker, ele é preservado.

Um `fact` com `kind` contendo `infer` é armazenado como inferência.

Outros candidatos humanos aprovados permanecem `reviewed_world`, preservando integralmente o conteúdo original e a evidência.

O Reviewer não transforma automaticamente uma fala em fato objetivo do mundo.

## Interface local v1

A UI usa somente a biblioteca padrão Python/Tkinter e permanece separada do Agent principal para reduzir risco de regressão.

Ela permite:

- listar sessões com candidatos pendentes;
- ver `PRIMARY_CHARACTER`;
- listar candidatos por categoria;
- ver confiança;
- ver perspectiva;
- validar e visualizar evidência;
- aprovar;
- editar e aprovar;
- rejeitar.

Ações de promoção ficam desabilitadas quando a evidência não chega corretamente ao RAW.

## Executar

Da pasta do PC Agent:

```powershell
cd "KageLink Installer\pc_agent"
python -m pc_agent.leafos_memory_reviewer `
  --vault "C:\caminho\LeafOS-Vault"
```

Listar sessões pendentes sem abrir UI:

```powershell
python -m pc_agent.leafos_memory_reviewer `
  --vault "C:\caminho\LeafOS-Vault" `
  --list
```

## Testes

Teste focado:

```powershell
cd "KageLink Installer\pc_agent"
python -m unittest tests.test_leafos_memory_reviewer -v
```

Suíte completa Python:

```powershell
python -m unittest discover -s tests -v
python -m compileall .
```

O Draft PR também executa CI de regressão para o PC Agent e para o app Flutter.

## Gate manual antes do merge

1. gerar ou selecionar uma sessão real já fechada;
2. rodar o Interpreter com `qwen3:14b`;
3. conferir o bundle `pending_review`;
4. calcular SHA-256 do RAW, sessão e bundle;
5. abrir o Reviewer;
6. selecionar um candidato e conferir a evidência exibida;
7. aprovar um candidato;
8. conferir `60 - Canonical Memory/memory.json`;
9. conferir `MEMORY.md` como projeção;
10. editar e aprovar outro candidato;
11. rejeitar outro candidato;
12. fechar e abrir novamente o Reviewer;
13. confirmar que os candidatos revisados não reaparecem;
14. confirmar separação de memória por `PRIMARY_CHARACTER` quando houver mais de um personagem;
15. recalcular SHA-256 do RAW, sessão e bundle e confirmar igualdade.

## Limitações deliberadas do v1

- não reabre decisões já registradas;
- não funde automaticamente memórias semanticamente semelhantes vindas de sessões diferentes;
- não resolve contradições entre duas memórias aprovadas;
- não consulta sessões passadas para “completar” contexto;
- não usa LLM no Reviewer;
- não altera RAW;
- não altera Processor;
- não altera bundles do Interpreter;
- não modifica chat/GAME/STATS/Android;
- não executa ações no jogo;
- não implementa World Model;
- não implementa Council.

Essas limitações são intencionais. A prioridade do v1 é construir uma memória permanente **humana, rastreável e segura** antes de adicionar recuperação semântica ou deliberação.

## Próximo passo arquitetural

Somente após validar o Reviewer em sessões reais, a evolução natural é uma camada de **Memory Retrieval** capaz de responder, com fontes:

```text
O que aconteceu?
O que este personagem sabe?
Quem disse isso?
Qual a evidência?
Quando aconteceu?
É fato revisado, fala, observação ou inferência?
```

World Model e Council continuam posteriores a essa etapa.
