# LeafOS Interpreter v3.2.1 — Durable System Revelations

[English](LEAFOS_INTERPRETER_V3_2_1.en.md) · [v3.2](LEAFOS_INTERPRETER_V3_2.md) · [Bíblia principal](AGENTS.md) · [Capítulo normativo do Interpreter](AGENTS_INTERPRETER.md)

A v3.2.1 é uma camada **aditiva** sobre a v3.2. Ela não reescreve a v3.1 nem a v3.2.

Baselines preservados:

```text
v3.1: pc_agent/leafos_interpreter_v31.py
snapshot: archive/interpreter-v3.1-working
commit validado: 8d0d2a0d3996ee4a6b66a7f7646dc69e4f024700

v3.2: pc_agent/leafos_interpreter_v32.py
```

O executável empacotado importa `leafos_interpreter_v321.py`, que herda da v3.2.

## Problema observado em uso real

Uma sessão composta quase toda por ações mecânicas foi corretamente filtrada pela v3.2, porém continha duas linhas duráveis explícitas do sistema:

```text
Your primary Element is: Fire
Your secondary Element is: Earth
```

Como o modelo pode omitir essas linhas, uma informação pode ser simultaneamente:

- explícita e verificável;
- durável;
- importante para revisão;
- mas ausente da saída do LLM.

Por isso a v3.2.1 não depende somente do modelo para formatos de sistema conhecidos.

## Sintaxe real confirmada no jogo

A validação real da sessão `2026-07-26_011` mostrou que o Processor preserva essas mensagens dentro do wrapper visual do jogo:

```text
(***Anbu** Your primary Element is: Fire*)
(***Anbu** Your secondary Element is: Earth*)
```

IDs observados nessa sessão:

```text
13863 → primary Element = Fire
13864 → secondary Element = Earth
```

O wrapper `***Anbu**` é tratado somente como apresentação/transporte da mensagem. Ele **não prova** que o resultado pertence a Anbu, a Leafos ou ao `primary_character` configurado.

## Regra da v3.2.1

Depois do Grounding Guard e do Salience Gate, a v3.2.1 executa uma extração determinística para **formatos de revelação do sistema já observados e testados**.

A primeira família reconhecida é:

```text
Your primary Element is: <valor>
Your secondary Element is: <valor>
```

Ela é aceita tanto em forma direta quanto no wrapper real observado:

```text
(***<identidade visível>** Your primary Element is: <valor>*)
(***<identidade visível>** Your secondary Element is: <valor>*)
```

Cada linha gera um candidato `facts` independente, por exemplo:

```json
{
  "statement": "The system reported the primary Element as Fire.",
  "kind": "system_revelation",
  "confidence": 1.0,
  "source_message_ids": [13863],
  "review_status": "pending_review"
}
```

## Substituição de interpretação redundante do modelo

Na validação real, o LLM produziu candidatos como:

```text
Revealing Primary Element
Anbu revealed the primary element as Fire.

Revealing Secondary Element
Anbu revealed the secondary element as Earth.
```

Esses candidatos eram grounded nos IDs corretos, mas introduziam uma atribuição de identidade desnecessária.

A v3.2.1 agora reconhece esse caso pelo mesmo `source_message_id` + campo + valor e:

1. remove a versão do modelo da fila normal do Reviewer;
2. preserva a versão original em `suppressed_candidates` para auditoria com `decision: replaced_by_durable_system_revelation`;
3. coloca no Reviewer somente o fato determinístico neutro.

Resultado esperado para a sessão real:

```text
The system reported the primary Element as Fire.
The system reported the secondary Element as Earth.
```

## Identidade continua conservadora

A v3.2.1 **não** transforma:

```text
(***Anbu** Your primary Element is: Fire*)
```

em:

```text
Leafos has Fire as primary Element
```

nem em:

```text
Anbu has Fire as primary Element
```

sem uma resolução explícita de identidade.

O candidato permanece neutro:

```text
The system reported the primary Element as Fire.
```

Assim, a informação é preservada sem inventar quem é o dono daquele resultado.

## Por que é determinístico

Esse caminho não depende do modelo perceber a importância da linha. O código só cria candidato quando a mensagem corresponde a um formato conhecido e testado.

Isso evita três problemas:

1. perder uma revelação durável porque o LLM decidiu não gerar candidato;
2. atribuir a revelação a uma identidade visível sem prova de ownership;
3. generalizar arbitrariamente mensagens de sistema desconhecidas.

Novos formatos, como rank, clã, vila ou habilidade, só devem entrar depois de observarmos seu texto real no log e criarmos regressão específica.

## Salience e auditoria

Quando a v3.2 havia suprimido uma versão equivalente ou o modelo havia produzido uma versão reviewable redundante, a v3.2.1 mantém uma única versão determinística na fila normal e preserva o necessário para auditoria em `suppressed_candidates`.

O bundle registra também:

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

## Regressão da validação real

O teste automatizado reproduz agora a sintaxe e os IDs observados em `2026-07-26_011`:

```text
13863 (***Anbu** Your primary Element is: Fire*)
13864 (***Anbu** Your secondary Element is: Earth*)
```

Ele também reproduz os dois eventos gerados pelo modelo e exige como saída final do Reviewer somente os dois `facts` neutros.

## Segurança

A v3.2.1 não:

- altera RAW;
- altera sessões do Processor;
- altera o Grounding Guard da v3.1;
- remove o Salience Gate da v3.2;
- cria Canonical Memory automaticamente;
- resolve `Anbu = Leafos`;
- usa conhecimento externo;
- usa um segundo LLM.

O Memory Reviewer continua sendo o gate humano obrigatório.
