# KageLink — Bíblia de Desenvolvimento

[English](AGENTS.en.md) · [README](README.pt-BR.md) · [Kage Pilot](KAGE_PILOT.md) · [Dojo](AGENTS_DOJO.md) · [Interpreter](AGENTS_INTERPRETER.md)

Este arquivo é a **fonte operacional de verdade para qualquer pessoa ou agente que altere o KageLink**. Os capítulos especializados complementam esta Bíblia; em caso de conflito, prevalece a regra mais conservadora para segurança, integridade de dados e rastreabilidade.

## 1. Fonte oficial

Repositório canônico:

```text
https://github.com/leafoss/KageLink
```

**O GitHub é a única fonte oficial do código.**

Não tratar como fonte primária:

- ZIP antigo;
- cópia no Desktop;
- build instalado;
- APK ou EXE isolado;
- arquivo enviado em conversa;
- pasta local sem commit.

Fluxo obrigatório:

```text
main
→ branch de trabalho
→ menor mudança suficiente
→ testes
→ revisão do diff
→ Pull Request
→ validação real quando necessária
→ aprovação explícita
→ merge
```

## 2. Versão oficial

A única fonte humana editável da versão é:

```text
RELEASE_VERSION
```

Versão atual:

```text
KageLink 3.5.0
```

CI e release devem manter coerentes:

- `RELEASE_VERSION`;
- `pubspec.yaml`;
- Inno Setup;
- PC Agent e `/api/health`;
- scripts manuais de build;
- labels de UI;
- nomes de artefatos;
- workflows;
- READMEs.

Não manter números de versão hardcoded em múltiplas superfícies quando o valor puder ser lido ou gerado da fonte canônica.

## 3. Filosofia central

**Não quebrar o que já funciona.**

Toda mudança deve ser:

- rastreável;
- reversível;
- testável;
- limitada ao escopo;
- compatível com módulos não relacionados.

Não realizar refatoração estética, troca de dependência, alteração de protocolo, limpeza destrutiva ou reorganização incidental sem pedido explícito.

Quando Rafael autorizar uma reorganização, ela deve possuir:

1. inventário dos arquivos;
2. identificação da fonte ativa;
3. atualização de imports, specs, workflows e documentação;
4. testes de regressão;
5. rollback pelo Git;
6. validação real quando houver Windows/BYOND/input.

## 4. Produtos e responsabilidades

### Android App

Responsável por UI, perfis, token seguro, OOC, IC/RP, GAME, STATUS, Dojo remoto, HTTP/WebSocket, reconexão, idioma e persistência das preferências locais.

O APK não executa visão computacional, teclado, lógica de combate ou autonomia do Dojo.

### PC Agent

Responsável por localizar o jogo, capturar chat e imagem, classificar mensagens, persistir histórico, enviar OOC/IC, autenticar clientes, hospedar API/WebSockets, controlar GAME/STATUS, operar LeafOS e executar o Kage Pilot no Windows.

### Installer

Responsável por empacotar exatamente a fonte atual, incluir dependências verificadas, preservar dados do usuário em atualizações normais e instalar:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

Nunca corrigir um bug do Agent apenas no Installer. Corrigir a fonte e provar que o build empacota a fonte corrigida.

### LeafOS

Integração opcional e desativada por padrão. Falhas de LeafOS não devem interromper chat, GAME, STATUS, Desktop, túnel ou Dojo.

## 5. Runtime empacotado

O Desktop oficial é composto por:

```text
KageLink.spec
→ unified_entry.py
→ unified_launcher.py
→ kagelink_launcher.py
→ unified_app.py / camada ativa de integração
→ app.py
```

A arquitetura usa herança, substituição de módulo e camadas de compatibilidade. Antes de alterar comportamento, identificar:

1. entrypoint empacotado;
2. classe efetivamente instanciada;
3. backend realmente importado;
4. monkeypatch ou facade aplicável;
5. teste que percorre a mesma rota;
6. arquivo mantido apenas por compatibilidade.

Editar uma camada não utilizada pelo executável não constitui correção.

## 6. Uma fonte canônica por responsabilidade

Regra geral:

```text
uma responsabilidade
→ um módulo canônico
→ consumidores reutilizam esse módulo
```

Versões históricas pertencem ao Git, não à árvore ativa como:

```text
final2.py
v03l.py
hotfix_new.py
copy.py
```

Uma camada de compatibilidade temporária deve ser pequena, identificada, testada e possuir condição de remoção.

### Kage Pilot

Superfície pública humana:

```text
KageLink Installer/pc_agent/kage_pilot.py
```

Comando canônico:

```powershell
python kage_pilot.py dojo
```

O Installer usa entrypoints internos versionless dentro de `pc_agent.kage_pilot`. A cadeia fisicamente validada pode manter internamente nomes históricos enquanto sua extração semântica não for validada; esses nomes não podem voltar a ser apresentados como comandos públicos.

Documentação ativa:

```text
KAGE_PILOT.md
KAGE_PILOT.en.md
AGENTS_DOJO.md
AGENTS_DOJO.en.md
```

## 7. Contrato OOC / IC — REGRA PROTEGIDA

### Blocos IC

Todo bloco iniciado por `(*` e encerrado pelo próximo `*)` é IC/RP. Blocos fragmentados permanecem pendentes até o fechamento.

### Falas IC

O marcador válido é literal e case-sensitive:

```text
Says:
```

Exemplos IC:

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

O nome do falante pode conter espaços, vírgulas, apóstrofos, clã e Markdown. A decisão de canal não pode depender de uma regex rígida de nome.

## 8. Envio OOC / IC

Endpoints dedicados:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` existe somente para compatibilidade.

O Agent deve:

1. receber o canal explicitamente;
2. revalidar a janela do jogo;
3. relocalizar os controles;
4. escolher apenas o campo solicitado;
5. recusar quando o campo estiver ausente;
6. nunca usar silenciosamente o outro canal.

Um HWND não pode representar OOC e IC ao mesmo tempo.

## 9. Histórico, IDs e evidência

Preservar:

- IDs;
- timestamps;
- direção;
- canal;
- parser state;
- ressincronização;
- cursores RAW/Processor;
- histórico de personagem;
- evidence IDs.

IDs são identidade, não sequência descartável.

Novos IDs devem ser maiores que qualquer ID já existente no SQLite, RAW, Processor ou Vault. Reinstalação não pode reiniciar IDs abaixo do `last_processed_id`.

Não apagar banco ou configuração como solução padrão.

## 10. LeafOS e memória

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

- RAW é append-only;
- `channel` vem do parser canônico;
- Processor não reprocessa IDs;
- Interpreter cria candidatos, não verdade automática;
- Reviewer é gate humano;
- evidência volta ao RAW;
- `memory.json` é a fonte computável;
- `MEMORY.md` é projeção regenerável;
- JSON canônico inválido bloqueia leitura/escrita destrutiva.

Para Interpreter/Reviewer, ler também `AGENTS_INTERPRETER.md`.

## 11. Política de estado persistente

Cada arquivo persistente deve declarar uma política:

### Fail closed

RAW, sessões, Reviewer, Canonical Memory, identidade e cursores de evidência. Estado existente inválido nunca vira vazio silenciosamente.

### Quarentena e reconstrução

Somente para cache ou checkpoint comprovadamente regenerável a partir de fonte íntegra.

### Backup e defaults

Configuração recuperável pode ser preservada em backup antes de defaults, com aviso identificável.

## 12. Gate de janela e input Windows

Antes de clique, key-down, texto ou captura fallback:

1. localizar novamente o alvo;
2. validar HWND;
3. validar título e classe;
4. validar PID/processo;
5. validar root/child;
6. validar visibilidade;
7. rejeitar minimizado;
8. confirmar foreground quando necessário;
9. revalidar imediatamente antes do input;
10. validar coordenadas dentro do client;
11. executar;
12. garantir mouse-up/key-up e cleanup.

Nunca confiar cegamente em HWND ou coordenada de frame antigo.

## 13. GAME

GAME permanece isolado de chat, STATUS e LeafOS.

- captura preferencial específica da janela;
- fallback por região somente após target/foreground confirmados;
- whitelist de teclas;
- heartbeat e dead-man behavior;
- desconexão, erro, troca de tela e dispose liberam teclas;
- GAME não pode executar programas, scripts, URLs ou comandos de sistema.

Durante Kage Pilot ativo, controle manual GAME é bloqueado pelo Windows, não apenas pela UI.

## 14. STATUS

Janela esperada:

```text
Título: Status | Inventory
Classe: #32770
```

Antes de frame ou clique, validar PID igual ao jogo, HWND esperado, classe, título, visibilidade, estado não minimizado e coordenada dentro do client.

STATUS não é controle genérico do desktop.

## 15. Kage Pilot e Dojo

Ler obrigatoriamente `AGENTS_DOJO.md` antes de alterar:

- templates;
- visão do Trainer;
- loop de rodadas;
- combate;
- KO;
- retorno/recuperação;
- API Dojo;
- UI Desktop/Android;
- Installer/helpers;
- interlock GAME.

Contratos globais:

- um clique no Trainer por rodada;
- retries repetem apenas a etapa que falhou;
- F12 permanece emergency stop;
- toda saída libera inputs;
- HP mínimo 90%; Chakra mínimo 50%;
- o APK é controle remoto, não autoridade de decisão;
- Settings permanece o último item da sidebar Desktop.

## 16. Falhas, retries e continuidade

Taxonomia recomendada:

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
- aborto encerra somente a operação ou rodada;
- indisponibilidade de módulo preserva módulos independentes;
- somente falha fatal comprovada encerra o processo;
- emergency stop libera inputs e encerra imediatamente;
- `NOT_FOUND`, `TIMEOUT` e `FAILED` não são fatalidade por definição.

Ação one-shot confirmada não pode ser repetida durante polling da resposta.

Toda política de retry deve declarar espera inicial, número de retries, total de verificações, intervalo, condição de sucesso, condição de aborto, efeito no loop superior e interrupção.

## 17. Threads, tasks, timers e subprocessos

Todo worker deve possuir:

- owner;
- nome;
- condição de início;
- condição de parada;
- timeout;
- sinal de cancelamento;
- cleanup;
- resultado observável;
- política de retry;
- impacto da falha.

`daemon=True` não substitui lifecycle explícito.

Monitor cancelado para transação crítica deve ser retomado em `finally`, salvo shutdown definitivo.

Subprocessos devem registrar comando sem segredos, exit code, timeout e política terminate/kill, além de liberar inputs e impedir órfãos.

## 18. Internacionalização

PT-BR e EN-US são idiomas de primeira classe.

Toda superfície voltada ao usuário deve possuir os dois idiomas:

- Desktop;
- Android;
- erros e estados;
- tooltips;
- onboarding;
- documentação de produto.

API e WebSocket devem preferir códigos técnicos estáveis. A camada de apresentação traduz esses códigos. Controllers/services não devem criar prosa visível hardcoded quando houver localização.

IDs, campos JSON, rotas e códigos técnicos não são traduzidos.

## 19. Segurança e privacidade

Nunca versionar ou registrar:

- access token;
- token em query string;
- private/temporary URL;
- conteúdo de secure storage;
- RAW pessoal;
- banco de histórico;
- configuração pessoal;
- templates, calibração ou frames do usuário;
- logs sensíveis;
- Vault privada.

Logs devem preferir componente, operação, código, recoverability, tentativa, round/session ID e tempo decorrido.

Dependência externa empacotada deve ter versão e hash verificados.

## 20. Release e Installer

A Release oficial é reconstruída da `main`; artifacts temporários de PR não substituem a distribuição.

Assets estáveis:

```text
KageLink-Windows-Setup.exe
KageLink-Android.apk
SHA256SUMS.txt
```

Gate mínimo:

1. suíte Python completa;
2. compileall;
3. testes Flutter e localization;
4. build `KageLink.exe`;
5. build `KagePilotDojo.exe`;
6. build `KagePilotRound.exe`;
7. smoke dos helpers;
8. smoke do Desktop;
9. Setup com os três executáveis;
10. APK release;
11. teste real proporcional ao risco;
12. aprovação explícita antes do merge/publicação.

## 21. Testes mínimos por área

### Parser/chat

- blocos fragmentados;
- `Says:` literal;
- nomes complexos;
- OOC/IC sem fallback cruzado;
- replay e resync.

### LeafOS

- cursor e IDs;
- RAW append-only;
- corrupção de estado;
- fechamento e retomada de sessão;
- evidência;
- Reviewer/Canonical fail closed.

### GAME/STATUS

- janela ausente/minimizada/substituída;
- PID incorreto;
- perda de foreground;
- desconexão;
- liberação de teclas;
- frame/coordinate identity.

### Dojo

- runtime/templates ausentes;
- clique único;
- checks 1–4 do diálogo;
- round abortado sem parar loop;
- F12 em esperas;
- subprocesso nonzero/timeout;
- KO repetido;
- retorno e recuperação;
- Desktop/APK/interlock;
- packaging dos helpers.

## 22. Processo de mudança

1. atualizar `main`;
2. criar branch;
3. ler esta Bíblia e capítulos aplicáveis;
4. reproduzir/mapear o comportamento;
5. localizar todas as implementações e consumidores;
6. realizar a menor mudança suficiente;
7. atualizar PT-BR/EN-US;
8. executar testes;
9. revisar o diff;
10. abrir PR draft;
11. validar em ambiente real quando necessário;
12. merge somente após decisão explícita.

Pergunta obrigatória de diff:

> Existe alguma linha alterada que não é necessária para esta tarefa?

Se existir, removê-la.

## 23. Honestidade de validação

Nunca afirmar que um teste passou se ele não foi executado.

Distinguir:

- inspeção estática;
- teste automatizado;
- build;
- smoke test;
- validação física Windows/BYOND;
- confirmação do usuário.

Quando o ambiente não permitir execução, registrar a limitação e usar o CI do PR como gate antes do merge.

## 24. Definição de pronto

Uma tarefa só está pronta quando:

- fonte ativa identificada;
- mudança no destino correto;
- escopo conferido;
- cleanup demonstrado;
- estado persistente protegido;
- contratos de protocolo preservados;
- PT-BR e EN-US cobertos;
- testes proporcionais executados;
- build/Installer considerados quando aplicável;
- documentação atualizada;
- nenhuma versão oficial ficou apenas em ZIP/Desktop;
- próxima ação e validação pendente estão explícitas.
