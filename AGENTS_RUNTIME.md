# AGENTS_RUNTIME.md — Runtime, estado e organização do KageLink

[English](AGENTS_RUNTIME.en.md) · [Bíblia principal](AGENTS.md)

Este capítulo complementa `AGENTS.md` e governa entrypoints, workers, subprocessos, persistência, input Windows, release e reorganizações estruturais.

## Runtime empacotado

```text
KageLink.spec → unified_entry.py → unified_launcher.py → unified_app.py → app.py
KagePilotDojo.spec → kage_pilot_dojo.py → kage_pilot.py dojo
KagePilotRound.spec → helper isolado da rodada
```

Antes de alterar comportamento, identificar qual arquivo é fonte, qual é wrapper de compatibilidade e qual é realmente empacotado.

## Organização canônica

- Uma superfície pública por subsistema.
- Um documento canônico por idioma e subsistema.
- Nomes ativos sem versão.
- Histórico preservado em Git, tags, releases e PRs.
- Snapshots versionados não devem permanecer indefinidamente na árvore ativa.
- Não apagar módulos versionados ainda importados por specs, testes ou runtime; primeiro criar fronteira canônica, migrar referências, executar CI e validar no jogo.

### Fases obrigatórias de consolidação

1. inventário de arquivos e referências;
2. definição do nome canônico;
3. criação de wrapper compatível;
4. migração de imports, specs, workflows e testes;
5. suíte completa;
6. validação física proporcional ao risco;
7. remoção dos snapshots superseded;
8. atualização documental e rollback identificável.

## Falhas e retries

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

Retries repetem somente a etapa falha. Ações one-shot confirmadas não são repetidas enquanto a resposta é aguardada.

## Workers e subprocessos

Toda thread, task, timer, watcher e subprocesso declara:

- owner;
- condição de início;
- condição de parada;
- timeout;
- cancelamento;
- cleanup;
- resultado;
- retry;
- impacto de falha.

Subprocessos devem registrar comando sem segredos, exit code, timeout, terminate/kill e cleanup. Nenhum processo-filho pode deixar tecla pressionada.

## Gate de janela e input

Antes de qualquer input:

1. localizar novamente;
2. validar HWND;
3. validar título/classe;
4. validar PID/processo;
5. validar root/child;
6. rejeitar invisível/minimizado;
7. confirmar foreground quando necessário;
8. revalidar antes do input;
9. validar coordenadas;
10. executar e liberar em `finally`.

## Persistência

- canônico/evidência/identidade/cursor: fail closed;
- cache regenerável: quarentena e reconstrução;
- configuração: backup e defaults com aviso.

Nunca converter silenciosamente estado inválido de sessão, identidade ou cursor em estado vazio.

## Release

`RELEASE_VERSION` é a fonte de versão. Workflows e builders não devem hardcodar o número corrente em caminhos.

CI deve proteger mudanças em entrypoints, specs, protocolos, localização, persistência, `AGENTS*.md`, Kage Pilot e Installer.

## Rollback

Toda reorganização estrutural deve ser reversível por commit/PR e deve listar explicitamente quais nomes antigos continuam como compatibilidade temporária.
