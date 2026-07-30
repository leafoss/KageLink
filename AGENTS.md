# KageLink — Bíblia de Desenvolvimento

[English](AGENTS.en.md) · [README PT-BR](README.pt-BR.md) · [Kage Pilot](KAGE_PILOT.md) · [Runtime](AGENTS_RUNTIME.md) · [Dojo](AGENTS_DOJO.md) · [Interpreter](AGENTS_INTERPRETER.md)

Este arquivo é a fonte operacional de verdade para qualquer pessoa ou agente de IA que altere o KageLink.

## 1. Fonte oficial

Repositório oficial: `leafoss/KageLink`.

**O GitHub é a única fonte oficial do código.** ZIP, Desktop, build instalado, APK/EXE isolado, arquivo colado em conversa e cópia local não commitada são somente materiais auxiliares.

Fluxo obrigatório:

```text
main → branch → mudança mínima → testes → revisão do diff → PR → validação real → merge
```

Nunca publicar diretamente em `main` durante desenvolvimento normal.

## 2. Versão oficial

A versão atual é:

```text
KageLink 3.5.0
```

`RELEASE_VERSION` é a fonte editável de versão. CI deve manter coerência entre PC Agent, Flutter, Inno Setup, builders, nomes de artefatos, `/api/health`, READMEs e releases.

Não hardcodar a versão corrente em novos caminhos ou textos quando ela puder ser derivada de `RELEASE_VERSION` ou do pacote.

## 3. Filosofia

**Não quebrar o que já funciona.**

Toda mudança deve ser mínima, localizada, rastreável, testável e compatível com comportamento não relacionado.

Durante tarefa limitada, não:

- refatorar por estética;
- reorganizar pastas incidentalmente;
- trocar bibliotecas sem necessidade;
- alterar UI/protocolo fora do escopo;
- apagar histórico/configuração para resolver bug;
- substituir módulo inteiro quando patch pequeno resolve;
- ampliar escopo sem autorização.

Quando Rafael disser “mude somente X”, a restrição é dura.

## 4. Arquitetura oficial 3.5.0

Produtos:

1. Android App — Flutter.
2. Desktop/PC Agent — Windows/Python.
3. Installer Windows.
4. Kage Pilot Dojo instalado.
5. Integração LeafOS opcional.

Runtime distribuído:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

O caminho empacotado usa camadas `unified_*` sobre componentes legados. Antes de editar, identificar entrypoint, classe efetivamente instanciada, monkeypatch/substituição, spec PyInstaller e teste que percorre a mesma rota.

Nunca declarar correção pronta quando ela foi aplicada somente a uma camada que o executável oficial não usa.

## 5. Fonte única por responsabilidade

Uma decisão de domínio deve possuir uma implementação canônica.

Exemplos:

- OOC/IC: `ChatChannelParser`.
- memória canônica: `memory.json` após Reviewer humano.
- Kage Pilot público: `kage_pilot.py`.
- documentação do Pilot: `KAGE_PILOT.md` e `KAGE_PILOT.en.md`.
- versão: `RELEASE_VERSION`.

Arquivos ativos devem ser nomeados pela responsabilidade, não por versão. Não criar `v03x`, `final2`, `new`, `hotfix` ou equivalentes. O histórico pertence ao Git.

Módulos versionados que ainda compõem o motor fisicamente validado podem permanecer temporariamente como compatibilidade, mas não podem ser usados como nova superfície pública. Sua remoção exige extração semântica, suíte verde e nova validação real.

## 6. OOC / IC — regra protegida

Blocos `(* ... *)` são IC/RP, inclusive quando chegam fragmentados.

O marcador de fala é literal e case-sensitive:

```text
Says:
```

`**Anbu** Says: test` é IC. `says:`, `SAYS:` e `sAyS:` não ativam essa regra.

Nomes podem conter espaços, vírgulas, apóstrofos, clã e Markdown. Não usar regex rígida de nome para classificar canal.

O Android usa `/api/send/ooc` e `/api/send/ic`. O Agent deve localizar somente o controle do canal solicitado e nunca usar o outro como fallback silencioso.

## 7. Histórico, RAW e memória

Preservar IDs, timestamps, direção, canal, parser, cursores e ressincronização.

RAW é append-only e recebe o canal já classificado. Não reinterpretar OOC/IC no exportador.

Pipeline:

```text
RAW imutável → Processor → sessão fechada → Interpreter → Bundle pending_review → Reviewer humano → Canonical Memory
```

O Interpreter produz candidatos, nunca verdade canônica automática. Evidência deve voltar aos `source_message_ids`.

`memory.json` é a fonte computável; `MEMORY.md` é projeção regenerável.

## 8. Integridade de estado persistente

Cada arquivo persistente deve declarar uma política:

- **fail closed:** RAW, sessões, Reviewer, Canonical Memory, identidade e cursores de evidência;
- **quarentena e reconstrução:** somente cache/checkpoint comprovadamente regenerável;
- **backup e defaults:** configuração recuperável, com aviso explícito.

Estado existente porém inválido de cursor, sessão ou identidade nunca pode ser tratado silenciosamente como vazio.

Novos IDs devem ser maiores que qualquer ID já existente em SQLite, RAW, Processor ou Vault.

## 9. GAME, STATS e automação Windows

Falhas de GAME, STATS, Dojo ou LeafOS não devem derrubar chat ou módulos independentes.

Antes de clique, key-down, texto ou captura fallback:

1. localizar novamente o alvo;
2. validar HWND;
3. validar título/classe;
4. validar PID/processo;
5. validar root/child;
6. validar visibilidade e rejeitar minimizado;
7. confirmar foreground quando necessário;
8. revalidar imediatamente antes do input;
9. validar coordenadas dentro do client;
10. garantir mouse-up/key-up e cleanup.

Nunca confiar cegamente em HWND ou coordenada antiga.

GAME e STATS não podem virar controle genérico do desktop. Manter whitelist de teclas, limites de protocolo e isolamento.

## 10. Kage Pilot / Dojo

Aplicam-se `KAGE_PILOT.md` e `AGENTS_DOJO.md`.

Contratos permanentes:

- exatamente um clique no treinador por rodada;
- retries de diálogo nunca repetem busca, movimento ou clique do treinador;
- uma espera/verificação inicial + até três adicionais;
- falha final encerra somente a rodada quando seguro;
- F12 libera inputs e encerra o loop;
- manual GAME input é bloqueado durante treino autônomo;
- templates 32×32 e 64×64 pertencem ao usuário e ficam em `%LOCALAPPDATA%\KageLink\data\kage_pilot\templates`;
- atualização normal preserva templates;
- ausência de template válido falha fechado;
- pisos de recuperação: HP ≥ 90% e Chakra ≥ 50%.

## 11. Falhas, retries e shutdown

Resultados normativos:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

`NOT_FOUND`, `TIMEOUT` e `FAILED` não são automaticamente fatais.

Retries repetem somente a etapa falha. Ação one-shot confirmada não pode ser repetida enquanto se aguarda resposta.

Toda thread, task, timer, watcher e subprocesso deve possuir owner, start, stop, timeout, cancelamento, cleanup, resultado, política de retry e impacto de falha. `daemon=True` não substitui lifecycle.

## 12. Protocolos, localização e segurança

PT-BR e EN-US são idiomas de primeira classe.

API/WebSocket devem preferir códigos estáveis como `INVALID_TOKEN`, `GAME_NOT_FOUND` e `DOJO_TRAINER_TEMPLATE_REQUIRED`. A UI traduz códigos; services/controllers não devem criar prosa visível hardcoded.

Nunca registrar token, query string com segredo, secure storage, URL privada completa, RAW pessoal ou payload sensível integral.

KageLink não executa comandos genéricos, programas ou scripts arbitrários enviados pelo cliente.

## 13. Release e Installer

Corrigir a fonte, não somente o instalador.

Toda release deve validar:

- suíte Python completa;
- `compileall`;
- Flutter localization/analyze/test;
- build e smoke de `KageLink.exe`;
- build e `--help` de `KagePilotDojo.exe` e `KagePilotRound.exe`;
- Windows Setup;
- APK;
- coerência de versão;
- assets/templates conforme contrato;
- preservação de dados em upgrade normal.

## 14. Processo obrigatório

1. atualizar `main`;
2. criar branch;
3. reproduzir/entender o estado;
4. localizar todas as implementações relacionadas;
5. fazer mudança mínima;
6. executar testes proporcionais ao risco;
7. revisar o diff;
8. remover linhas não necessárias;
9. commit claro;
10. PR draft;
11. validação real quando aplicável;
12. merge somente após aprovação.

Nunca afirmar que um teste passou se não foi executado.

## 15. Definição de pronto

Uma mudança está pronta quando:

- a fonte ativa foi identificada;
- o entrypoint empacotado foi considerado;
- falha, retry e cleanup estão definidos;
- estado persistente possui política de corrupção;
- PT-BR e EN-US estão equivalentes;
- testes pertinentes passaram ou limitações foram registradas;
- versão e artefatos estão coerentes;
- validação física necessária foi registrada;
- não existem alterações não solicitadas conhecidas;
- não existe versão correta somente em ZIP, Desktop ou build local.
