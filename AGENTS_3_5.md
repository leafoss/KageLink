# AGENTS_3_5.md — Addendum normativo do KageLink 3.5.0

[English](AGENTS_3_5.en.md) · [Bíblia principal](AGENTS.md) · [Runtime](AGENTS_RUNTIME.md) · [Kage Pilot](KAGE_PILOT.md)

Este addendum complementa `AGENTS.md`. Os contratos detalhados da Bíblia principal continuam válidos. Em caso de conflito com referências antigas de versão ou arquitetura, este addendum governa o estado oficial 3.5.0.

## 1. Versão e fonte oficial

```text
KageLink 3.5.0
Fonte de versão: RELEASE_VERSION
```

`RELEASE_VERSION` é a única fonte humana editável da versão. PC Agent, Flutter, Inno Setup, builders, workflows, `/api/health`, artefatos e textos de release devem permanecer coerentes por validação automática.

## 2. Produto instalado

A distribuição Windows oficial inclui:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

- `KageLink.exe` hospeda Desktop, API e estado público.
- `KagePilotDojo.exe` isola o loop entre rodadas.
- `KagePilotRound.exe` isola uma rodada.
- Os helpers não são implementações concorrentes; devem encaminhar para fronteiras canônicas.
- A instalação oficial não depende de Python instalado nem de scripts `.py` soltos.

## 3. Superfície canônica do Kage Pilot

```text
kage_pilot.py
kage_pilot_loop.py
KAGE_PILOT.md
KAGE_PILOT.en.md
```

Novas integrações não devem importar diretamente filenames versionados.

Arquivos internos `v03*` ainda necessários ao motor fisicamente validado são compatibilidade temporária. Não removê-los até que imports, specs, workflows e testes migrem para nomes canônicos, a suíte completa fique verde e a validação real seja refeita.

## 4. Organização futura

- Uma responsabilidade possui um único nome canônico.
- Versões pertencem ao Git, tags, releases e changelog.
- Não criar novos arquivos com `v03x`, datas, `final`, `new`, `hotfix` ou equivalentes.
- Documentos incrementais devem ser condensados no documento canônico da grande atualização.
- O histórico removido da árvore ativa continua acessível pelo Git e PRs.

## 5. Templates 32×32 e 64×64

Templates do Dojo Trainer são fornecidos pelo usuário e persistidos em:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Regras protegidas:

- cada modo possui arquivo e metadados independentes;
- update/reinstall normal preserva os templates;
- ausência de template válido bloqueia o início;
- template não deve ser embutido como autoridade primária no executável;
- uma correspondência antiga ou memória isolada não autoriza input;
- Desktop e Android exibem o mesmo estado do serviço público.

## 6. Falhas e retries

Resultados normativos:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

`NOT_FOUND`, `TIMEOUT` ou `FAILED` não são automaticamente fatais.

Retries repetem somente a etapa que falhou. Uma ação one-shot confirmada não pode ser repetida enquanto se aguarda sua resposta.

No Dojo:

```text
1 clique no Trainer
→ 1 espera/verificação inicial
→ até 3 esperas/verificações adicionais
→ falha final encerra somente a rodada quando seguro
```

## 7. Segurança e isolamento

- manual GAME input fica bloqueado durante treino autônomo;
- F12 libera inputs e encerra o loop;
- falha do Dojo não derruba chat, histórico, STATS ou LeafOS;
- qualquer subprocesso deve ter owner, timeout, exit code, terminate/kill e cleanup;
- nenhuma transição pode deixar tecla ou mouse pressionado.

## 8. Estado persistente

Cada estado deve declarar uma política:

- fail closed: evidência, identidade, sessão, cursor e memória canônica;
- quarentena e reconstrução: cache comprovadamente regenerável;
- backup e defaults: configuração recuperável com aviso.

Nunca tratar silenciosamente um estado existente porém inválido de identidade, sessão ou cursor como vazio.

## 9. Protocolos e idiomas

PT-BR e EN-US são obrigatórios.

API e WebSocket devem preferir códigos estáveis, como:

```text
DOJO_TRAINER_TEMPLATE_REQUIRED
GAME_NOT_FOUND
FOREGROUND_FAILED
INVALID_TOKEN
```

A camada de apresentação traduz o código. Services/controllers não devem criar novas frases visíveis hardcoded quando existe localização.

## 10. Release gate

Antes de publicar:

- suíte Python completa;
- compileall/py_compile;
- Flutter gen-l10n, analyze e tests;
- build/smoke de `KageLink.exe`;
- build/`--help` de `KagePilotDojo.exe` e `KagePilotRound.exe`;
- Windows Setup;
- APK;
- paridade de versão;
- preservação dos dados/templates;
- validação física proporcional às mudanças.

Nunca afirmar que um teste ou validação passou sem execução real.
