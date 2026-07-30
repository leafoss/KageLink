# AGENTS_RUNTIME.md — Runtime, estado e organização

[English](AGENTS_RUNTIME.en.md) · [Bíblia](AGENTS.md) · [Addendum 3.5](AGENTS_3_5.md)

Este capítulo governa entrypoints, workers, subprocessos, persistência, input Windows e reorganizações estruturais.

## Runtime empacotado

```text
KageLink.spec → unified_entry.py → unified_launcher.py → unified_app.py → app.py
KagePilotDojo.spec → kage_pilot_dojo.py → kage_pilot.py dojo
KagePilotRound.spec → runtime isolado da rodada
```

Antes de alterar comportamento, identificar qual arquivo é fonte, wrapper de compatibilidade e entrypoint realmente empacotado.

## Organização canônica

- uma superfície pública por subsistema;
- um documento canônico por idioma e subsistema;
- nomes ativos sem versão;
- histórico no Git, tags, releases e PRs;
- snapshots versionados não permanecem indefinidamente na árvore ativa.

Não apagar módulos ainda importados por runtime, specs, workflows ou testes.

### Fases de consolidação

1. inventariar arquivos e referências;
2. definir nome canônico;
3. criar wrapper compatível;
4. migrar imports, specs, workflows e testes;
5. executar suíte completa;
6. realizar validação física proporcional ao risco;
7. remover snapshots superseded;
8. atualizar documentação e registrar rollback.

## Workers e subprocessos

Toda thread, task, timer, watcher e subprocesso declara:

- owner;
- condição de início/parada;
- timeout;
- cancelamento;
- cleanup;
- resultado;
- retry;
- impacto de falha.

`daemon=True` não substitui lifecycle. Subprocessos registram comando sem segredos, exit code e política de terminate/kill. Nenhum filho pode deixar inputs ativos.

## Gate de janela e input

Antes de input:

1. localizar novamente;
2. validar HWND;
3. validar título/classe;
4. validar PID/processo;
5. validar root/child;
6. rejeitar invisível/minimizado;
7. confirmar foreground quando necessário;
8. revalidar imediatamente antes do input;
9. validar coordenadas;
10. executar e liberar em `finally`.

Nunca confiar cegamente em HWND ou coordenada antiga.

## Persistência

- canônico/evidência/identidade/cursor: fail closed;
- cache regenerável: quarentena e reconstrução;
- configuração: backup e defaults com aviso.

Estado inválido de sessão, identidade ou cursor nunca vira vazio silenciosamente.

## Release

`RELEASE_VERSION` é a fonte de versão. Workflows e builders não devem hardcodar a versão corrente em caminhos.

CI deve proteger entrypoints, specs, protocolos, localização, persistência, `AGENTS*.md`, Kage Pilot e Installer.

## Rollback

Toda reorganização deve ser reversível por commit/PR e listar os nomes antigos mantidos temporariamente para compatibilidade.
