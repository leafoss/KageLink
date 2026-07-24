# KageLink — Bíblia de Desenvolvimento

Este arquivo é a **fonte operacional de verdade para qualquer pessoa ou agente de IA que altere o KageLink**.

O objetivo é impedir regressões, versões divergentes, refatorações desnecessárias e o antigo fluxo baseado em ZIPs. Antes de modificar qualquer código, leia este arquivo e os arquivos diretamente relacionados à tarefa.

---

## 1. Fonte oficial do projeto

O repositório oficial é:

`https://github.com/leafoss/KageLink`

### Regra absoluta

**O GitHub é a única fonte oficial de código.**

Não considerar ZIPs, cópias em Desktop, builds antigos ou arquivos enviados isoladamente como versão principal do projeto.

Se uma funcionalidade existir apenas localmente, ela deve ser levada para uma branch do GitHub antes de continuar o desenvolvimento.

### Nunca mais trabalhar assim

- alterar um ZIP inteiro;
- gerar um novo ZIP como “versão final”;
- manter uma correção apenas em uma pasta local;
- assumir que o arquivo anexado mais recente representa todo o projeto;
- sobrescrever o projeto inteiro para corrigir um único bug.

### Sempre trabalhar assim

`main -> branch de trabalho -> alteração mínima -> testes -> revisão -> merge`

---

## 2. Filosofia principal

KageLink é um projeto funcional em produção/uso real.

### Regra mais importante

**Não quebrar o que já funciona.**

Toda alteração deve ser:

- mínima;
- localizada;
- rastreável;
- testável;
- compatível com o comportamento existente, salvo quando a tarefa explicitamente exigir mudança.

### Não fazer

- refatorar por estética;
- renomear arquivos, classes, rotas ou funções sem necessidade;
- reorganizar pastas durante correção de bug;
- trocar bibliotecas sem necessidade;
- mudar comportamento não relacionado;
- “otimizar” código funcional sem solicitação explícita;
- substituir um módulo inteiro quando uma correção localizada resolve;
- alterar UI, protocolo, teclas ou persistência incidentalmente.

Uma correção de parser não é autorização para alterar GAME.
Uma correção de GAME não é autorização para alterar chat.
Uma correção do instalador não é autorização para alterar o Agent.

---

## 3. Arquitetura oficial

O projeto possui dois produtos que precisam continuar compatíveis entre si:

1. **KageLink Mobile App** — Flutter/Android.
2. **KageLink PC Agent** — Windows/Python.

O instalador Windows empacota o PC Agent para o usuário final.

Estrutura principal conhecida:

```text
KageLink/
├── README.md
├── README.pt-BR.md
├── AGENTS.md
├── LICENSE
└── KageLink Installer/
    ├── COMPILAR_APK.bat
    ├── DIAGNOSTICAR_KAGELINK.bat
    ├── android_overlay/
    ├── assets/
    ├── docs/
    ├── installer/
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

Antes de alterar qualquer arquivo, descobrir qual componente é realmente responsável pelo comportamento observado.

---

## 4. Separação de responsabilidades

### Mobile App

Responsável principalmente por:

- interface OOC;
- interface IC/RP;
- interface GAME;
- histórico apresentado ao usuário;
- conexão com o Agent;
- envio de comandos permitidos;
- estado visual, navegação, drafts e preferências do app.

### PC Agent

Responsável principalmente por:

- localizar o Shinobi Story Online;
- ler/capturar chat;
- classificar mensagens;
- manter histórico/persistência do backend;
- autenticação;
- API/WebSocket;
- envio de texto para o jogo;
- captura GAME;
- controle remoto permitido;
- Cloudflare Tunnel;
- integração RAW/Obsidian quando habilitada.

### Installer

Responsável por:

- empacotar o Agent;
- incluir dependências necessárias;
- preservar dados do usuário durante atualizações;
- entregar uma instalação funcional sem exigir ambiente Python de desenvolvimento.

**Não corrigir comportamento do Agent apenas no instalador. Corrigir a fonte do Agent e garantir que o instalador empacote essa fonte.**

---

## 5. Regra de uma única fonte de lógica

Quando uma mesma decisão aparece em várias partes do projeto, deve existir uma implementação canônica sempre que possível.

Exemplo crítico:

**classificação de mensagens OOC/IC.**

Não criar uma regra para o histórico, outra para WebSocket, outra para RAW e outra para o aplicativo.

O fluxo correto deve ser conceitualmente:

```text
texto capturado
    ↓
parser/classificador canônico
    ↓
mensagem classificada
    ├── histórico
    ├── API/WebSocket
    ├── aplicativo
    └── RAW/Obsidian
```

O RAW não deve reinterpretar a mensagem com uma segunda versão independente das regras de IC/OOC.

Isso evita bugs em que uma mensagem aparece como IC no app, mas não é salva como IC no RAW.

---

## 6. Contrato do chat OOC / IC

O sistema OOC/IC é comportamento protegido.

### IC por bloco de roleplay

Blocos no formato:

```text
(* ... *)
```

devem ser classificados como IC/RP.

Blocos fragmentados precisam continuar sendo reconstruídos corretamente até o delimitador final.

### IC por fala

O jogo pode produzir falas como:

```text
Uchiha, Leafos Says: Hello
Uchiha, Leafos says: Hello
**Anbu** Says: test
**Anbu** says: test
Hozuki, Shin'ya Says: Hello
```

O marcador `Says:` deve ser tratado de maneira **case-insensitive**.

O nome do personagem não pode ser presumido como uma palavra simples. Ele pode conter:

- vírgulas;
- apóstrofos;
- espaços;
- clã + nome;
- Markdown/asteriscos, como `**Anbu**`;
- outras formas emitidas pelo jogo.

### Importante

A regra não deve transformar qualquer linha contendo uma sequência incidental em IC.

Testes devem cobrir falsos positivos e falsos negativos.

### OOC

Tudo que não satisfizer uma regra IC válida continua seguindo as regras OOC já existentes.

Não alterar comportamento OOC durante uma correção exclusiva de IC.

---

## 7. RAW / Obsidian — contrato obrigatório

A integração RAW serve como memória bruta do Shinobi Story Online.

Ela deve ser independente do Obsidian estar aberto.

O Obsidian apenas lê os arquivos que o Agent grava no diretório configurado.

### Diretório

O caminho de RAW deve ser configurável pelo usuário.

Exemplo atualmente utilizado em desenvolvimento:

```text
C:\Users\Rafael\Desktop\Obsidian\LeafOS-Vault\03 - Leafos e Shinobi Story\RAW
```

**Nunca hardcode esse caminho como padrão universal do aplicativo.**

### Organização

Preferência atual:

- um arquivo por dia;
- append de novos registros;
- UTF-8;
- preservar o texto bruto;
- não reescrever registros antigos sem necessidade;
- metadados suficientes para rastrear origem, timestamp e canal.

Formato atualmente esperado:

```html
<!-- kagelink-raw-begin {"id":7538,"timestamp":"...","channel":"ic","speaker":null} -->
mensagem original
<!-- kagelink-raw-end -->
```

### Regra fundamental

O campo `channel` do RAW deve vir da **mesma classificação canônica** utilizada pelo restante do KageLink.

Não duplicar parsing dentro do writer RAW.

### Privacidade

RAW pode conter roleplay privado, histórico e informações não destinadas ao repositório.

**Nunca commitar arquivos RAW no GitHub.**

Também nunca commitar:

- tokens;
- chaves;
- URLs temporárias privadas;
- arquivos de configuração pessoais;
- logs com credenciais;
- histórico pessoal do usuário.

---

## 8. Isolamento do módulo GAME

GAME é deliberadamente isolado do chat.

Falha em GAME não pode derrubar:

- OOC;
- IC/RP;
- histórico;
- autenticação;
- envio de chat;
- parser.

O inverso também deve ser respeitado sempre que possível.

### Janela alvo

A janela alvo do jogo é:

```text
Shinobi Story Online
```

Não transformar KageLink em ferramenta genérica de controle do desktop.

### Captura

Contrato conhecido do GAME V1:

- 960×540;
- JPEG;
- alvo aproximado de 8–12 FPS;
- sem áudio;
- evitar fila crescente de frames;
- capturar a janela/janela-filho adequada, não o desktop inteiro.

---

## 9. Controles GAME protegidos

Mapeamento padrão atualmente aprovado:

```text
Joystick -> setas
A -> E
B -> Space
C -> G
D -> V
```

Mudanças futuras de configuração não devem destruir o padrão existente.

O protocolo atual deve continuar rejeitando controle arbitrário do computador.

Whitelist histórica do GAME V1:

```text
up, down, left, right, e, space, g, v
```

Se a whitelist for expandida futuramente por uma funcionalidade aprovada, fazê-lo de forma explícita e testada.

Não adicionar silenciosamente:

- Alt+F4;
- tecla Windows;
- Ctrl+Esc;
- comandos arbitrários;
- macros genéricas;
- execução de programas;
- controle amplo do desktop.

---

## 10. APIs e protocolo

Rotas de chat conhecidas:

```text
/api/auth
/api/status
/api/history
/api/send
/api/input-candidates
/api/input-preference
/ws
```

Rotas GAME conhecidas:

```text
/api/game/status
/ws/game/stream
/ws/game/control
```

Não mudar nomes, payloads ou semântica dessas interfaces incidentalmente.

Mudança de protocolo exige:

1. motivo explícito;
2. atualização coordenada Agent + App;
3. testes de compatibilidade;
4. documentação.

---

## 11. Persistência e atualização

Uma atualização do KageLink não deve apagar dados do usuário.

Preservar sempre que aplicável:

- configuração;
- token;
- histórico;
- preferências;
- logs necessários;
- estado persistente do parser;
- configurações de integração RAW.

Nunca resolver um bug apagando banco, configuração ou histórico como comportamento padrão.

Migração destrutiva exige autorização explícita.

---

## 12. Versionamento

Versão do projeto deve permanecer coerente entre:

- Flutter/App;
- PC Agent;
- instalador;
- nomes de artefatos de build;
- documentação de release quando aplicável.

Não aumentar versão por uma alteração local ainda não validada, salvo decisão explícita de release.

Uma correção pode permanecer em branch até ser validada.

---

## 13. Fluxo obrigatório para mudanças

### 1. Atualizar contexto

Antes de editar:

```bash
git checkout main
git pull
```

### 2. Criar branch

Exemplos:

```text
fix/ic-says-parser
fix/raw-channel-classification
feat/raw-obsidian
feat/game-controls-config
chore/installer-build
```

Não desenvolver diretamente no `main` para mudanças relevantes.

### 3. Reproduzir o problema

Antes de corrigir, registrar:

- comportamento observado;
- comportamento esperado;
- entrada que causa o erro;
- componente responsável;
- teste que demonstrará a correção.

### 4. Localizar todas as implementações relacionadas

Antes de editar, procurar por:

- função;
- constante;
- regex;
- string usada como marcador;
- rota;
- modelo de dados;
- teste existente.

Uma correção parcial é pior do que uma busca completa por implementações duplicadas.

### 5. Alteração mínima

Modificar apenas o necessário.

### 6. Testar

Rodar testes existentes e adicionar regressão quando possível.

### 7. Revisar diff

Pergunta obrigatória:

> Existe alguma linha alterada que não é necessária para esta tarefa?

Se sim, remover.

### 8. Commit claro

Exemplos:

```text
Fix case-insensitive Says parsing for IC chat
Use canonical channel classification for RAW writer
Preserve GAME controls when switching tabs
```

### 9. Pull Request

PR deve explicar:

- problema;
- causa;
- alteração;
- arquivos afetados;
- testes executados;
- teste manual ainda necessário.

### 10. Merge somente depois da validação

Para bugs que dependem de Shinobi Story/Windows real, validação manual pode ser obrigatória antes do merge.

---

## 14. Testes mínimos por área

### Parser/chat

Testar pelo menos:

```text
(*Roleplay*)
**Anbu** Says: test
**Anbu** says: test
Uchiha, Leafos Says: hello
Hozuki, Shin'ya Says: hello
texto OOC normal
bloco IC fragmentado
fala fragmentada
```

Também testar falsos positivos.

### RAW

Validar:

- diretório configurado;
- criação automática;
- arquivo diário;
- append;
- UTF-8;
- timestamp;
- id;
- canal correto;
- reinício do Agent;
- duplicação/replay;
- mensagem multiline;
- `Says:` em diferentes capitalizações;
- personagem com Markdown/asteriscos;
- funcionamento com Obsidian fechado.

### GAME

Validar:

- jogo aberto;
- jogo fechado;
- minimizado;
- maximizado;
- captura;
- zoom;
- joystick;
- diagonais;
- A/B/C/D;
- tap;
- hold;
- multitouch;
- troca de aba;
- desconexão segurando tecla;
- nenhuma tecla presa;
- OOC/IC permanecendo funcionais durante falha GAME.

### App Flutter

Quando ambiente disponível:

```bash
flutter analyze
flutter test
```

### Python

Quando aplicável:

```bash
python -m pytest
python -m compileall .
```

Os comandos exatos podem depender da estrutura atual da branch; não inventar resultados de teste.

---

## 15. Build

### Android

O fluxo oficial documentado usa:

```text
KageLink Installer\COMPILAR_APK.bat
```

O script de build é responsável por preparar o workspace e gerar o APK.

**O installer Windows não gera o APK.**

### PC Agent

O fluxo oficial documentado usa:

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

O usuário final não deve precisar instalar manualmente Python ou dependências de desenvolvimento apenas para executar o Agent empacotado.

---

## 16. Como investigar bugs corretamente

Quando um bug parece persistir mesmo após alterar um arquivo:

**não assumir imediatamente que a alteração “não funcionou”.**

Investigar nesta ordem:

1. o arquivo alterado realmente está sendo importado/executado?
2. existe uma segunda implementação da mesma regra?
3. o instalador empacotou a fonte nova?
4. o EXE executado é realmente o build novo?
5. existe cache/workspace intermediário?
6. App e Agent estão na mesma revisão/protocolo?
7. o problema acontece antes ou depois do parser?
8. o dado salvo vem da mensagem classificada ou do texto bruto reprocessado?

### Regra para bugs de regra duplicada

Se duas partes diferentes classificam a mesma coisa, preferir eliminar a duplicação arquitetural em vez de corrigir a mesma regex em vários lugares sem controle.

---

## 17. Problema em investigação — IC `Says:` x RAW

Existe um problema observado em desenvolvimento onde mensagens como:

```text
**Anbu** Says: ???
**Anbu** Says: test
```

não chegaram ao RAW como esperado, enquanto blocos como:

```text
(***Anbu** picks up Chilli Powder*)
(*Hozuki, Shin'ya picks up Gold Ring*)
```

foram gravados corretamente.

Uma implementação de parser foi encontrada tratando `says:` de forma literal/minúscula, mas uma correção isolada nesse ponto não resolveu o comportamento completo.

### Portanto

Antes da próxima correção:

- localizar todas as ocorrências de `says:` / `Says:` / classificação IC;
- localizar todos os writers RAW;
- rastrear a mensagem desde a captura até o arquivo RAW;
- confirmar qual código está dentro do EXE instalado;
- criar teste de integração que garanta que uma mensagem `**Anbu** Says: test` termine no RAW como `channel: ic`.

Não aplicar outra correção pontual até esse rastreamento estar completo.

---

## 18. GitHub é também a memória técnica

Decisões importantes devem ficar registradas no próprio repositório através de:

- `AGENTS.md` para regras permanentes;
- README para uso/instalação;
- commits para histórico de alterações;
- Pull Requests para contexto e validação;
- Issues para bugs e funcionalidades ainda não resolvidos.

Conversas no ChatGPT podem ajudar no desenvolvimento, mas não devem ser a única memória de uma decisão crítica do projeto.

---

## 19. Regra para agentes de IA

Ao receber uma tarefa sobre KageLink:

1. considerar este repositório como fonte oficial;
2. ler este `AGENTS.md`;
3. inspecionar os arquivos atuais da branch antes de propor código;
4. procurar testes e implementações duplicadas;
5. preservar comportamento funcional não relacionado;
6. trabalhar em branch;
7. produzir diff pequeno;
8. executar testes disponíveis;
9. declarar claramente o que foi e o que não foi validado;
10. não inventar que um teste passou;
11. não gerar um ZIP como substituto do versionamento Git;
12. não fazer merge de uma mudança dependente de teste real sem registrar essa necessidade.

### Quando houver dúvida

Preferir preservar o comportamento existente e registrar a dúvida no PR/Issue.

### Quando o usuário disser “mude somente X”

Isso é uma restrição dura.

Não usar a tarefa como oportunidade para alterar Y ou Z.

---

## 20. Definição de pronto

Uma tarefa só está realmente pronta quando:

- a causa foi identificada ou a mudança foi claramente justificada;
- o código está no GitHub;
- a alteração está limitada ao escopo;
- testes relevantes passaram ou limitações foram explicitamente registradas;
- não houve regressão conhecida;
- documentação foi atualizada quando necessária;
- build real foi validado quando a tarefa depende dele;
- não existe uma “versão certa” fora do repositório.

---

# Mandamento final

> **KageLink deve evoluir sem perder o que já funciona. O GitHub é a memória oficial; mudanças são mínimas, rastreáveis, testadas e nunca dependem de um ZIP perdido em uma pasta local.**
