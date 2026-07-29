# LeafOS Interpreter v3

[English](LEAFOS_INTERPRETER.en.md) · [README](README.pt-BR.md) · [Bíblia](AGENTS.md)

O **LeafOS Interpreter** é a camada semântica entre uma sessão fechada pelo `LeafOSProcessor` e os candidatos que serão apresentados ao **Memory Reviewer**.

Ele responde somente à pergunta:

> **O que esta sessão sustenta como candidato, segundo as mensagens realmente registradas?**

O Interpreter **não escreve memória canônica**.

```text
Shinobi Story Online
        ↓
KageLink / RAW
        ↓
LeafOSProcessor
        ↓
Sessão fechada
        ↓
LeafOS Interpreter v3
        ↓
Interpretation Bundle
status: pending_review
        ↓
Memory Reviewer
        ↓
Aprovar / Editar + aprovar / Rejeitar
        ↓
Canonical Memory
```

## Contrato de entrada

O Interpreter lê somente sessões fechadas em:

```text
<Vault>/80 - Processor/Sessions/*.json
```

A sessão do Processor continua sendo o contrato de entrada. O Interpreter não reconstitui o passado consultando novamente o banco do KageLink e não modifica a sessão original.

Campos importantes incluem:

- `session_id`;
- `started_at` / `ended_at`;
- `primary_character`;
- `participants`;
- `message_ids`;
- `raw_sources`;
- `messages`.

## Regra de evidência

Todo candidato precisa citar um ou mais IDs realmente enviados ao modelo:

```json
"source_message_ids": [101, 102]
```

IDs inexistentes são removidos. Um candidato sem nenhuma evidência válida é descartado.

A cadeia permanece:

```text
candidato
   ↓
source_message_ids
   ↓
sessão do Processor
   ↓
raw_source
   ↓
RAW original
```

## O que mudou no v3

O v2 enviava uma sessão grande em uma única chamada ao `qwen3:14b`. Além disso, sessões acima do limite podiam usar apenas início + final. Em hardware local isso podia provocar `OLLAMA_TIMEOUT: 600s` e também significava que mensagens do meio não chegavam ao modelo.

O v3 elimina esse comportamento do fluxo normal.

### Chunking sem descarte

O tamanho padrão aproximado de cada bloco é:

```text
9000 caracteres de transcript por chunk
```

Com sobreposição padrão de:

```text
2 mensagens entre fronteiras
```

Exemplo:

```text
Sessão grande
    │
    ├── Chunk 1
    ├── Chunk 2
    ├── Chunk 3
    └── Chunk 4
            ↓
       qwen3:14b
            ↓
 resultados parciais normalizados
            ↓
 merge determinístico
            ↓
 único Interpretation Bundle
```

Todas as mensagens continuam fazendo parte de pelo menos um chunk. O v3 não usa o antigo recorte início/fim para interpretar normalmente uma sessão grande.

O campo final passa a registrar:

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

Sessões pequenas continuam produzindo um único chunk e recebem:

```json
"interpretation_mode": "single"
```

## Contexto nas fronteiras

A pequena sobreposição reduz a chance de uma fala ou reação ser separada artificialmente da mensagem imediatamente anterior.

O prompt informa explicitamente ao modelo que ele está vendo apenas um chunk. O modelo é proibido de inventar o conteúdo dos outros blocos ou continuidade não presente nas mensagens fornecidas.

## Merge determinístico

O v3 **não usa outro LLM para resumir ou combinar os resultados dos chunks**.

A união é feita em código:

```text
Chunk 1 candidates
Chunk 2 candidates
Chunk 3 candidates
        ↓
deduplicação conservadora
        ↓
união de source_message_ids
        ↓
maior confidence entre duplicatas exatas
        ↓
pending_review
```

Candidatos somente são considerados duplicados quando seu conteúdo semântico estruturado é equivalente após normalização simples. Conteúdo diferente permanece separado para o Reviewer decidir.

## Checkpoint e retry parcial

Durante uma sessão com múltiplos chunks, o Interpreter grava checkpoints temporários em:

```text
<Vault>/80 - Interpreter/Checkpoints/<session_id>.json
```

Cada chunk concluído é persistido atomicamente antes do próximo começar.

Assim, se ocorrer:

```text
Chunk 1 ✓
Chunk 2 ✓
Chunk 3 → OLLAMA_TIMEOUT
Chunk 4
Chunk 5
```

uma nova tentativa começa assim:

```text
Chunk 1 ✓ reutilizado
Chunk 2 ✓ reutilizado
Chunk 3 → retry
Chunk 4 → processar
Chunk 5 → processar
```

Os minutos gastos nos chunks já concluídos não são descartados.

Quando o bundle final é criado com sucesso, o checkpoint temporário da sessão é removido.

## Proteção contra checkpoint obsoleto

O checkpoint contém uma impressão digital da entrada semântica da sessão, incluindo mensagens, personagem principal, versão do prompt e configuração de chunking.

Se a sessão ou a configuração mudar, o Interpreter não reutiliza resultados parciais antigos. Um novo checkpoint é iniciado.

## Falhas

Uma falha continua sem promover nada para memória canônica.

O estado em:

```text
<Vault>/80 - Interpreter/interpreter_state.json
```

registra a sessão e, quando aplicável:

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

A sessão **não** entra em `processed_sessions` até o bundle completo existir.

O botão **Interpretar pendentes** pode portanto tentar novamente a sessão, reaproveitando o checkpoint válido.

## Progresso na UI

O Desktop recebe eventos de progresso do Interpreter. Durante sessões grandes, a barra de status pode mostrar algo como:

```text
Processando... · 2026-07-24_001 · 2/5
```

Em uma falha, o diálogo também inclui a posição do chunk quando disponível.

## IA local / privacidade

Configuração padrão:

```text
URL: http://127.0.0.1:11434
Modelo: qwen3:14b
Timeout: 600 segundos por chunk
```

Com a URL padrão, o conteúdo é enviado apenas ao servidor Ollama local. Uma URL remota pode transmitir o RP para outro computador/serviço.

O endpoint usado permanece:

```text
POST /api/chat
```

com `stream: false`, `think: false`, temperatura `0` e resposta estruturada por JSON Schema.

## Saída

O bundle final continua em:

```text
<Vault>/70 - LeafOS Inbox/Interpretations/<session_id>.json
```

Categorias:

- `events`;
- `characters`;
- `locations`;
- `relationships`;
- `facts`;
- `leafos_memories`.

Tudo continua com:

```text
status: pending_review
```

Nenhum candidato se torna memória permanente sem o Memory Reviewer e ação humana explícita.

## Execução

O uso normal deve ser feito pelo `KageLink.exe`.

A CLI permanece disponível para desenvolvimento/diagnóstico:

```powershell
cd "KageLink Installer\pc_agent"
python -m pc_agent.leafos_interpreter `
  --vault "C:\caminho\LeafOS-Vault"
```

Parâmetros úteis para testes:

```text
--chunk-chars 9000
--chunk-overlap-messages 2
--timeout 600
--max-sessions 1
```

`--max-transcript-chars` continua aceito como alias de compatibilidade para o tamanho de chunk.

## O que o Interpreter continua proibido de fazer

O v3 não:

- escreve memória canônica automaticamente;
- altera fichas de personagens;
- altera timeline oficial;
- decide sozinho se uma inferência é verdade;
- usa informação OOC para completar RP;
- consulta internet ou wiki;
- usa sessões anteriores como conhecimento implícito;
- apaga RAW;
- modifica sessões do Processor;
- inventa identidades, ranks, facções, motivos, locais ou resultados.

O **Memory Reviewer** continua sendo o gate obrigatório entre interpretação e memória canônica.
