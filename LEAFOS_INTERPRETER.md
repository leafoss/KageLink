# LeafOS Interpreter v1

[English](LEAFOS_INTERPRETER.en.md) · [README](README.pt-BR.md) · [Bíblia](AGENTS.md)

O **LeafOS Interpreter** é a camada semântica entre as sessões técnicas produzidas pelo `LeafOSProcessor` e uma futura memória canônica do personagem.

Ele responde à pergunta:

> **O que provavelmente aconteceu nesta sessão, segundo apenas o que foi registrado no RP?**

## Princípio fundamental

O Interpreter **não escreve memória canônica**.

Fluxo:

```text
Shinobi Story Online
        ↓
KageLink / ChatChannelParser
        ↓
RAW imutável
        ↓
LeafOSProcessor
        ↓
Sessão fechada
        ↓
LeafOS Interpreter
        ↓
70 - LeafOS Inbox/Interpretations
        ↓
REVISÃO HUMANA
        ↓
memória canônica futura
```

Tudo criado pelo Interpreter recebe:

```text
status: pending_review
```

Nenhuma inferência deve ser promovida automaticamente como verdade do universo ou memória de Leafos.

---

## Por que existe uma camada separada

O RAW responde:

> O que foi escrito no jogo?

O Processor responde:

> Quais mensagens pertencem à mesma sessão?

O Interpreter responde:

> Que acontecimentos, fatos, relações e memórias podem ser candidatos a partir desta sessão?

A memória canônica futura responderá:

> O que foi revisado e aceito como verdade?

Misturar essas etapas destruiria a rastreabilidade do LeafOS.

---

## Entrada

O Interpreter lê somente sessões já fechadas em:

```text
<Vault>/80 - Processor/Sessions/*.json
```

Uma sessão contém, entre outros campos:

- `session_id`;
- `started_at`;
- `ended_at`;
- `participants`;
- `message_ids`;
- `raw_sources`;
- `messages`.

O Interpreter não lê diretamente o banco do KageLink para reinterpretar o passado. A sessão fechada é seu contrato de entrada.

---

## Saída

Cada sessão interpretada gera um bundle em:

```text
<Vault>/70 - LeafOS Inbox/Interpretations/<session_id>.json
```

O bundle pode conter candidatos para:

- `events` — acontecimentos ou decisões;
- `characters` — observações sobre personagens;
- `locations` — lugares explicitamente sustentados pela sessão;
- `relationships` — observações relacionais entre participantes;
- `facts` — fatos/lore candidatos sustentados pelas mensagens;
- `leafos_memories` — possíveis memórias subjetivas de Leafos.

Também contém:

- resumo da sessão;
- timestamps;
- participantes detectados;
- `message_ids` originais;
- `raw_sources`;
- modelo utilizado;
- versão do prompt;
- indicação se o transcript precisou ser truncado;
- status de revisão.

---

## Regra de evidência

Todo candidato deve possuir:

```json
"source_message_ids": [101, 102]
```

O Interpreter valida esses IDs contra as mensagens realmente enviadas ao modelo.

Se um modelo inventar um ID inexistente, o candidato é descartado.

Se um candidato não possuir nenhuma fonte válida, ele também é descartado.

Isso cria a cadeia:

```text
candidato
   ↓
source_message_ids
   ↓
sessão
   ↓
raw_source
   ↓
RAW original
```

---

## Inferência não é fato

O prompt do Interpreter proíbe usar conhecimento externo de Naruto ou conhecimento anterior do modelo.

Ele é instruído a:

- usar somente o transcript fornecido;
- não inventar identidade;
- não inventar rank;
- não inventar facção;
- não inventar localização;
- não inventar motivo;
- não inventar desfecho;
- preferir omitir algo a especular.

Memórias de Leafos possuem perspectiva:

```text
observed
said
inferred
```

Mesmo uma memória marcada como `observed` continua `pending_review` até existir uma etapa formal de aprovação.

---

## IA local / privacidade

O Interpreter v1 usa **Ollama local** por padrão.

Configuração padrão do comando:

```text
URL: http://127.0.0.1:11434
Modelo: qwen3:14b
```

Isso significa que o transcript é enviado ao servidor Ollama configurado. Com a URL padrão, o processamento ocorre na própria máquina.

Não configure uma URL remota sem compreender que isso pode transmitir conteúdo do RP para outro computador/serviço.

O Interpreter usa o endpoint:

```text
POST /api/chat
```

com `stream: false`, temperatura `0` e resposta estruturada por JSON Schema.

Nenhuma biblioteca Python adicional do Ollama é necessária; a implementação utiliza a biblioteca padrão do Python.

---

## Como executar

Pré-requisitos:

1. O LeafOS Processor já precisa ter fechado pelo menos uma sessão.
2. Ollama deve estar instalado e em execução.
3. O modelo escolhido deve existir localmente.

Exemplo com o modelo padrão:

```powershell
cd "KageLink Installer\pc_agent"
python -m pc_agent.leafos_interpreter `
  --vault "C:\caminho\LeafOS-Vault"
```

Usando outro modelo:

```powershell
python -m pc_agent.leafos_interpreter `
  --vault "C:\caminho\LeafOS-Vault" `
  --model "qwen3:14b"
```

Interpretar somente uma sessão nova por execução:

```powershell
python -m pc_agent.leafos_interpreter `
  --vault "C:\caminho\LeafOS-Vault" `
  --max-sessions 1
```

Servidor Ollama diferente:

```powershell
python -m pc_agent.leafos_interpreter `
  --vault "C:\caminho\LeafOS-Vault" `
  --ollama-url "http://127.0.0.1:11434"
```

---

## Estado e idempotência

O Interpreter mantém seu próprio estado em:

```text
<Vault>/80 - Interpreter/interpreter_state.json
```

Ele registra sessões já processadas para não interpretar repetidamente o mesmo arquivo.

Se uma interpretação falhar, a sessão **não é marcada como processada**. Portanto ela poderá ser tentada novamente depois que o problema for corrigido.

Se o arquivo final de interpretação já existir, o Interpreter evita criar duplicata.

---

## Sessões grandes

O limite padrão do transcript enviado ao modelo é:

```text
48000 caracteres
```

Quando uma sessão excede o limite, o Interpreter preserva uma parte do início e uma parte do final da sessão e registra:

```json
"transcript_truncated": true
```

Os `source_message_ids` aceitos passam a ser somente IDs realmente incluídos na parte enviada ao modelo.

Esse comportamento evita que o modelo alegue evidência em mensagens que ele não recebeu.

---

## Falhas do Ollama

Se Ollama estiver desligado, o modelo não existir ou a resposta não for JSON válido:

- nenhuma memória canônica é alterada;
- a sessão não é marcada como concluída;
- o erro fica em `interpreter_state.json`;
- a sessão poderá ser processada novamente.

---

## Exemplo conceitual de saída

```json
{
  "type": "interpretation_bundle",
  "session_id": "2026-07-24_003",
  "status": "pending_review",
  "summary": "Leafos propõe mover o grupo antes do anoitecer e Urahara concorda.",
  "events": [
    {
      "title": "Decisão de movimentação",
      "description": "Leafos propôs mover o grupo antes do anoitecer; Urahara concordou.",
      "event_type": "decision",
      "confidence": 0.96,
      "source_message_ids": [18453, 18457],
      "review_status": "pending_review"
    }
  ],
  "facts": [],
  "relationships": [],
  "leafos_memories": []
}
```

O texto acima é somente um exemplo de formato; o Interpreter real deve produzir conteúdo baseado exclusivamente em cada sessão.

---

## O que ainda NÃO faz parte do Interpreter v1

O v1 deliberadamente não:

- escreve notas canônicas automaticamente;
- altera fichas de personagens;
- altera timeline oficial;
- decide sozinho se uma inferência é verdade;
- usa informação OOC para completar RP;
- consulta internet;
- consulta wiki de Naruto;
- mistura sessões anteriores como conhecimento implícito;
- apaga RAW;
- modifica sessões do Processor.

---

## Próxima etapa após validar o v1

A próxima camada deve ser um **Reviewer / Memory Promoter**.

Fluxo esperado:

```text
Interpretation Bundle
        ↓
revisão
        ├── aprovar
        ├── editar
        └── rejeitar
        ↓
Canonical Memory
        ├── Events
        ├── Characters
        ├── Locations
        ├── Relationships
        ├── Lore
        └── Leafos Memory
```

Somente essa futura etapa poderá promover candidatos para a memória permanente.