# KageLink — Bíblia de Desenvolvimento

[English](AGENTS.en.md) · [README](README.pt-BR.md) · [Kage Pilot](KAGE_PILOT.md) · [Interpreter](AGENTS_INTERPRETER.md)

Este arquivo é a **fonte operacional de verdade para qualquer pessoa ou agente de IA que altere o KageLink**.

## 1. Fonte oficial

Repositório canônico:

```text
https://github.com/leafoss/KageLink
```

**GitHub é a única fonte oficial do código.**

Não tratar como fonte primária:

- ZIP antigo;
- cópia no Desktop;
- EXE/APK isolado;
- instalação local;
- arquivo colado em conversa;
- pasta sem commit.

Fluxo obrigatório:

```text
main
→ branch de trabalho
→ menor mudança suficiente
→ testes
→ revisão do diff
→ Pull Request
→ validação real quando necessária
→ merge
```

## 2. Versão oficial

A fonte editável da versão é:

```text
RELEASE_VERSION
```

A versão vigente é **3.4.2**.

CI e release devem manter coerentes:

- `RELEASE_VERSION`;
- `pubspec.yaml`;
- Inno Setup;
- backend `/api/health`;
- labels de versão;
- nomes de artefatos;
- READMEs;
- workflows.

Não criar números de versão manuais em múltiplos arquivos quando o valor puder ser lido ou gerado da fonte canônica.

## 3. Filosofia central

**Não quebrar o que já funciona.**

Toda mudança deve ser:

- rastreável;
- reversível;
- testável;
- localizada ao escopo;
- compatível com módulos não relacionados.

Não realizar refatoração estética, troca de dependência, alteração de protocolo, limpeza destrutiva ou reorganização incidental sem pedido explícito.

Quando Rafael autorizar uma reorganização, ela deve possuir inventário, atualização de referências, testes e rollback pelo Git.

## 4. Arquitetura oficial

Produtos principais:

1. aplicativo Android em Flutter;
2. PC Agent Windows/Python;
3. instalador Windows;
4. integração LeafOS opcional;
5. Kage Pilot experimental e local.

### 4.1 Runtime empacotado

O executável oficial é composto por:

```text
KageLink.spec
→ unified_entry.py
→ unified_launcher.py
→ kagelink_launcher.py
→ unified_app.py
→ app.py
```

Esse caminho inclui herança, substituição de módulo e seleção runtime do Interpreter.

Antes de alterar o PC Agent, identificar:

1. entrypoint empacotado;
2. classe efetivamente instanciada;
3. backend efetivamente importado;
4. monkeypatch/substituição aplicável;
5. teste que percorre a mesma rota;
6. arquivo mantido apenas por compatibilidade.

Uma correção aplicada somente a uma camada que o executável não usa não está pronta.

## 5. Uma fonte canônica por responsabilidade

Regra geral:

```text
uma responsabilidade
→ um módulo canônico
→ consumidores reutilizam esse módulo
```

Versões históricas pertencem ao Git, não a arquivos ativos como:

```text
final2.py
v03l.py
hotfix_new.py
copia.py
```

Compatibilidade temporária deve ser pequena, explicitamente marcada e possuir plano de remoção.

### Kage Pilot

Superfície pública canônica:

```text
KageLink Installer/pc_agent/kage_pilot.py
```

Comando Dojo:

```powershell
python kage_pilot.py dojo
```

Documentação normativa:

```text
KAGE_PILOT.md
KAGE_PILOT.en.md
```

Workflow:

```text
.github/workflows/kage-pilot.yml
```

Novos comportamentos do Pilot não criam outro entrypoint versionado. Módulos internos recebem nomes por responsabilidade.

## 6. Contrato OOC / IC — REGRA PROTEGIDA

### Blocos IC

Todo bloco iniciado por `(*` e encerrado pelo próximo `*)` é IC/RP. Blocos fragmentados permanecem pendentes até o fechamento.

### Falas IC

O marcador oficial é literal e case-sensitive:

```text
Says:
```

IC:

```text
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Não ativa a regra:

```text
says:
SAYS:
sAyS:
Says Hello
```

Não tornar `Says:` case-insensitive sem nova decisão explícita.

A regra deve permanecer alinhada em parser, testes, histórico, speaker extraction, RAW, READMEs e Bíblias.

## 7. Envio OOC / IC

Endpoints dedicados:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` é compatibilidade.

O Agent deve:

1. receber canal explícito;
2. focar/revalidar o jogo;
3. relocalizar controles;
4. selecionar apenas o campo solicitado;
5. recusar quando ausente;
6. nunca usar silenciosamente o outro canal.

Um HWND não representa OOC e IC ao mesmo tempo.

## 8. Histórico e identidade de evidência

Preservar:

- IDs;
- timestamps;
- direção;
- canal;
- parser state;
- ressincronização;
- cursor RAW;
- histórico de personagem.

IDs são identidade, não sequência descartável.

Novos IDs devem ser maiores que qualquer ID já existente no SQLite, RAW, Processor ou Vault. Reinstalação não pode reiniciar IDs abaixo do `last_processed_id`.

Não apagar banco de histórico como correção padrão.

## 9. LeafOS

Integração desativada por padrão.

Fluxo protegido:

```text
histórico classificado
→ RAW imutável
→ Processor determinístico
→ sessão fechada
→ Interpreter
→ pending_review
→ Memory Reviewer
→ aprovação humana
→ Canonical Memory
```

Regras permanentes:

- RAW append-only;
- canal vem do parser canônico;
- Processor não reprocessa IDs;
- Interpreter produz candidatos;
- Reviewer é gate humano;
- evidência retorna até RAW;
- `memory.json` é fonte canônica;
- `MEMORY.md` é projeção regenerável;
- falha LeafOS não derruba chat/GAME/STATS/túnel.

Para Interpreter/Reviewer, ler também `AGENTS_INTERPRETER.md` ou `.en.md`.

## 10. Integridade de estado persistente

Cada estado deve declarar uma política.

### Fail closed

Usar para:

- RAW;
- sessões fechadas;
- Reviewer;
- Canonical Memory;
- cursores de evidência;
- identidade de personagem;
- estado cuja perda pode duplicar ou atribuir incorretamente evidência.

Arquivo existente porém inválido não pode virar estado vazio silenciosamente.

### Quarentena e reconstrução

Somente para cache/checkpoint comprovadamente regenerável a partir de fonte íntegra. Preservar o arquivo inválido e registrar o motivo.

### Backup e defaults

Permitido para configuração recuperável, com backup e aviso explícito.

Toda escrita de estado deve preferir arquivo temporário + replace atômico.

## 11. GAME e STATS

GAME permanece isolado de chat, LeafOS e STATS.

Contrato GAME:

```text
janela: Shinobi Story Online
JPEG: 960 × 540
qualidade: 70
alvo: ~10 FPS
áudio: não
modos: full | zoom
```

STATS:

```text
título: Status | Inventory
classe: #32770
alvo: 5 FPS
cliques: esquerdo | direito
```

STATS deve validar PID igual ao jogo, título, classe, visibilidade, HWND do último frame e coordenadas normalizadas.

Nenhum módulo vira controle genérico do desktop.

## 12. Gate obrigatório de janela/input

Antes de clique, key-down, texto ou captura fallback:

1. localizar novamente o alvo;
2. validar HWND;
3. validar título e classe;
4. validar PID/processo;
5. validar relação root/child;
6. validar visibilidade;
7. rejeitar minimizado;
8. confirmar foreground quando necessário;
9. revalidar imediatamente antes do input;
10. confirmar coordenada dentro do client;
11. executar;
12. garantir mouse-up/key-up e cleanup.

Nunca confiar cegamente em HWND ou coordenada de frame antigo.

Captura de tela genérica só é permitida após localizar, focar e revalidar a janela exata, evitando capturar outro aplicativo sobreposto.

## 13. Teclas e controle

Bancos Android:

```text
ABCD
ZXVU
```

A whitelist de teclas é contrato de segurança. Não expandir incidentalmente.

- liberar teclas ao desativar;
- liberar em erro/desconexão;
- liberar ao perder foreground;
- key-up antes de key-down ao trocar diagonais;
- nunca transformar KageLink em executor genérico de comandos.

## 14. Falhas e retries

Resultados operacionais:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

Regras:

- falha recuperável encerra somente a tentativa;
- aborto encerra somente operação/rodada;
- módulo indisponível não derruba módulos independentes;
- somente falha fatal encerra automaticamente o processo;
- emergency stop libera inputs e encerra imediatamente;
- `NOT_FOUND`, `TIMEOUT` e `FAILED` não são automaticamente fatais.

Retries repetem somente a etapa que falhou.

Depois de uma ação one-shot confirmada, polling não pode repetir a ação. Exemplos: clique no treinador, envio de mensagem, abertura de subprocesso e finalização de sessão.

## 15. Workers, tasks, timers e subprocessos

Todo worker deve declarar:

- owner;
- nome;
- condição de início;
- condição de parada;
- timeout;
- cancelamento;
- cleanup;
- resultado;
- retry;
- impacto de falha.

`daemon=True` não substitui lifecycle.

Monitor cancelado durante transação crítica deve ser retomado em `finally`, salvo shutdown definitivo.

Subprocesso precisa de exit code, timeout, terminate/kill limitados, logs sem segredo e cleanup de inputs.

## 16. Protocolos e localização

API/WebSocket devem preferir códigos estáveis:

```text
INVALID_TOKEN
GAME_NOT_FOUND
FOREGROUND_FAILED
IC_INPUT_NOT_FOUND
STATS_WINDOW_CHANGED
```

A UI converte códigos para PT-BR ou EN-US.

Não usar frase localizada como contrato de protocolo. Controllers/services não devem criar prosa visível quando existe camada de localização.

PT-BR e EN-US são idiomas oficiais de primeira classe. Chaves novas devem existir nos dois idiomas antes da conclusão.

Não traduzir IDs, campos JSON, nomes de arquivo ou códigos técnicos.

## 17. Segurança e privacidade

Nunca versionar ou registrar:

- token;
- token em query string;
- conteúdo de secure storage;
- URL privada com segredo;
- `config.json` pessoal;
- banco de histórico;
- RAW/Vault pessoal;
- dataset visual pessoal;
- logs sensíveis;
- traceback bruto em UI.

Cloudflared e dependências externas preparadas devem possuir versão e SHA-256 verificados.

## 18. Persistência e upgrade

Upgrade normal preserva quando aplicável:

- configuração;
- token;
- histórico;
- calibração OOC/IC;
- parser state;
- LeafOS;
- perfis Android;
- favoritos;
- banco e mapeamentos GAME.

Migração destrutiva exige autorização explícita e rollback.

## 19. Fluxo obrigatório de mudança

1. atualizar `main`;
2. ler Bíblia e documentação do componente;
3. criar branch;
4. reproduzir/definir comportamento esperado;
5. localizar todas as implementações duplicadas;
6. alterar a fonte canônica;
7. atualizar consumidores/testes/docs;
8. executar testes disponíveis;
9. revisar diff;
10. abrir PR com limitações de validação;
11. validar fisicamente quando Windows/BYOND exigir;
12. merge somente após aprovação.

## 20. Testes mínimos

Python:

```powershell
python -m unittest discover -s tests -v
python -m compileall .
```

Flutter:

```text
flutter analyze
flutter test
```

Kage Pilot:

```powershell
python -m compileall -q pc_agent/kage_pilot
python -m py_compile kage_pilot.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python kage_pilot.py dojo --show-config
```

Adicionar testes proporcionais para sucesso, ausência, timeout, retry, cancelamento, shutdown, corrupção de estado, janela substituída, PID errado, perda de foco e cleanup.

Nunca afirmar que um teste passou sem execução real.

## 21. Release

CI deve falhar quando versão, backend, Android, installer, documentação ou artefatos divergirem.

Workflows leem `RELEASE_VERSION`; não hardcodam a versão corrente em caminhos.

Mudanças em `AGENTS*`, protocolos, estado persistente, entrypoints, workflow, installer ou localização acionam regressões pertinentes.

## 22. Definição de pronto

Uma tarefa está pronta quando:

- fonte ativa foi identificada;
- entrypoint empacotado foi considerado;
- escopo foi respeitado;
- duplicações foram removidas ou justificadas;
- classe de falha e cleanup estão claros;
- estado persistente possui política de corrupção;
- testes passaram ou limitações foram registradas;
- PT-BR/EN-US foram verificados;
- documentação está atualizada;
- rollback existe;
- validação real necessária está registrada;
- não existe versão correta somente em ZIP/Desktop;
- GitHub contém o resultado rastreável.

# Mandamento final

> **O KageLink deve evoluir sem perder o que já funciona. GitHub é a memória oficial; `Says:` é contrato exato; chat, GAME, STATS, LeafOS e Kage Pilot permanecem coerentes, isolados, seguros e rastreáveis.**
