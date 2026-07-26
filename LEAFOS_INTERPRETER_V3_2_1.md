# LeafOS Interpreter v3.2.1 — Durable System Revelations

[English](LEAFOS_INTERPRETER_V3_2_1.en.md) · [v3.2](LEAFOS_INTERPRETER_V3_2.md) · [Bíblia](AGENTS.md)

A v3.2.1 é uma camada **aditiva** sobre a v3.2. Ela não reescreve a v3.1 nem a v3.2.

Baselines preservados:

```text
v3.1: pc_agent/leafos_interpreter_v31.py
snapshot: archive/interpreter-v3.1-working
commit validado: 8d0d2a0d3996ee4a6b66a7f7646dc69e4f024700

v3.2: pc_agent/leafos_interpreter_v32.py
```

O executável de preview passa a importar `leafos_interpreter_v321.py`, que herda da v3.2.

## Problema observado em uso real

Uma sessão composta quase toda por ações mecânicas foi corretamente filtrada pela v3.2, porém continha duas linhas duráveis explícitas do sistema:

```text
Your primary Element is: Fire
Your secondary Element is: Earth
```

Como o modelo não criou candidatos para essas linhas, o Reviewer ficou vazio. Isso mostrou que uma informação pode ser simultaneamente:

- explícita e verificável;
- durável;
- importante para revisão;
- mas ausente da saída do LLM.

## Regra da v3.2.1

Depois do Grounding Guard e do Salience Gate, a v3.2.1 executa uma extração determinística para **formatos de revelação do sistema já observados e testados**.

A primeira família reconhecida é:

```text
Your primary Element is: <valor>
Your secondary Element is: <valor>
```

Cada linha gera um candidato `facts` independente, por exemplo:

```json
{
  "statement": "The system reported the primary Element as Fire.",
  "kind": "system_revelation",
  "confidence": 1.0,
  "source_message_ids": [12345],
  "review_status": "pending_review"
}
```

## Identidade continua conservadora

A v3.2.1 **não** transforma:

```text
Your primary Element is: Fire
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

Esse caminho não depende do modelo perceber a importância da linha. O código só cria candidato quando a mensagem corresponde exatamente a um formato conhecido e testado.

Isso evita dois problemas:

1. perder uma revelação durável porque o LLM decidiu não gerar candidato;
2. generalizar arbitrariamente mensagens de sistema desconhecidas.

Novos formatos, como rank, clã, vila ou habilidade, só devem entrar depois de observarmos seu texto real no log e criarmos regressão específica.

## Salience e auditoria

Quando a v3.2 havia suprimido uma versão do mesmo fato por score baixo, a v3.2.1 remove somente esse registro equivalente de `suppressed_candidates` e mantém uma única versão reviewable.

O bundle registra também:

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
