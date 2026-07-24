# KageLink — Bíblia de Desenvolvimento

[English](AGENTS.en.md) · [README em Português](README.pt-BR.md) · [README in English](README.md)

Este arquivo é a **fonte operacional de verdade para qualquer pessoa ou agente de IA que altere o KageLink**.

Ele descreve os contratos que devem ser preservados na versão oficial atual, **KageLink 3.4.1**, e o processo obrigatório para evitar regressões, versões divergentes e o antigo fluxo baseado em ZIPs.

---

## 1. Fonte oficial

Repositório oficial:

```text
https://github.com/leafoss/KageLink
```

### Regra absoluta

**O GitHub é a única fonte oficial do código.**

Não tratar como fonte principal:

- ZIP antigo;
- pasta no Desktop;
- build instalado;
- APK isolado;
- EXE isolado;
- arquivo enviado em conversa;
- cópia local não commitada.

Fluxo correto:

```text
main
  ↓
branch de trabalho
  ↓
alteração mínima
  ↓
testes
  ↓
revisão do diff
  ↓
Pull Request
  ↓
validação real quando necessária
  ↓
merge
```

Nunca usar um ZIP como substituto do versionamento Git.

---

## 2. Versão oficial atual

A documentação desta Bíblia descreve:

```text
KageLink 3.4.1
Flutter: 3.4.1+20
```

A versão deve permanecer coerente entre:

- `pubspec.yaml`;
- `APP_VERSION` do PC Agent;
- `COMPILAR_APK.bat`;
- `CRIAR_INSTALADOR.bat`;
- `KageLink_PC_Agent.iss`;
- nomes de artefatos;
- textos de versão no app;
- READMEs quando uma nova release for publicada.

Não aumentar versão por uma alteração local ainda não validada sem uma decisão explícita de release.

---

## 3. Filosofia principal

KageLink é usado em ambiente real.

### Mandamento principal

**Não quebrar o que já funciona.**

Toda alteração deve ser:

- mínima;
- localizada;
- rastreável;
- testável;
- compatível com comportamento funcional não relacionado.

### Proibido durante uma tarefa limitada

- refatorar por estética;
- renomear arquivos/classes/rotas sem necessidade;
- reorganizar pastas incidentalmente;
- trocar bibliotecas sem motivo funcional;
- alterar UI não relacionada;
- alterar protocolo não relacionado;
- mudar mapeamentos padrão sem solicitação;
- apagar histórico/configuração para “resolver” bug;
- substituir módulo inteiro quando uma mudança pequena resolve;
- ampliar o escopo porque “seria melhor aproveitar”.

Quando o usuário disser **“mude somente X”**, isso é uma restrição dura.

---

## 4. Arquitetura oficial 3.4.1

Produtos principais:

1. **KageLink Android App** — Flutter.
2. **KageLink PC Agent** — Windows/Python.
3. **Installer Windows** — empacota o PC Agent.
4. **LeafOS integration** — módulo opcional dentro do Agent.

Estrutura principal:

```text
KageLink/
├── AGENTS.md
├── AGENTS.en.md
├── README.md
├── README.pt-BR.md
├── LICENSE
└── KageLink Installer/
    ├── COMPILAR_APK.bat
    ├── DIAGNOSTICAR_KAGELINK.bat
    ├── android_overlay/
    ├── assets/
    ├── installer/
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

Antes de editar, identificar qual componente realmente controla o comportamento observado.

---

## 5. Responsabilidades

### Android App

Responsável por:

- perfis de conexão;
- armazenamento seguro do token;
- OOC;
- IC/RP;
- GAME;
- STATS;
- apresentação do histórico;
- conexão HTTP/WebSocket;
- reconexão;
- idioma;
- navegação;
- calibração solicitada ao Agent;
- configuração dos controles GAME;
- persistência do banco ativo `ABCD`/`ZXVU` e mapeamentos no Android.

### PC Agent

Responsável por:

- localizar `Shinobi Story Online`;
- ler chat;
- classificar OOC/IC;
- persistir histórico;
- persistir estado do parser;
- localizar campos OOC/IC;
- enviar texto ao jogo;
- autenticação;
- API/WebSockets;
- servidor local;
- Cloudflare Tunnel;
- captura GAME;
- controle GAME;
- foco da janela do jogo;
- proteção contra teclas presas;
- captura/controle STATS;
- LeafOS RAW;
- LeafOS Processor quando habilitado.

### Installer

Responsável por:

- empacotar a fonte atual do Agent;
- incluir runtime/dependências necessárias;
- incluir `cloudflared` preparado/verificado;
- instalar `KageLink.exe`;
- preservar dados durante atualização normal;
- permitir remoção deliberada de dados no uninstall.

**Nunca corrigir um bug do Agent somente no instalador. Corrigir a fonte e garantir que o instalador empacote essa fonte.**

---

## 6. Regra de fonte única de lógica

Decisões de domínio devem ter implementação canônica.

Exemplo crítico:

```text
classificação OOC / IC
```

Fluxo correto:

```text
texto capturado
    ↓
ChatChannelParser
    ↓
mensagem classificada
    ├── SQLite/history
    ├── API/WebSocket
    ├── Android App
    └── LeafOS RAW
```

O RAW não deve decidir novamente se a mensagem é OOC ou IC.

O campo `channel` exportado pelo LeafOS deve vir do registro persistido que já passou pelo parser canônico.

---

## 7. Contrato OOC / IC — REGRA PROTEGIDA

### 7.1 IC por bloco de roleplay

Todo bloco iniciado por:

```text
(*
```

e encerrado pelo próximo:

```text
*)
```

é IC/RP.

Exemplo:

```text
(*Uchiha, Leafos nods.*)
```

Blocos podem chegar fragmentados. O parser deve manter o conteúdo pendente até receber `*)`.

### 7.2 IC por fala `Says:`

A regra oficial é **literal e case-sensitive**.

O marcador válido é exatamente:

```text
Says:
```

Exemplos que DEVEM ser IC:

```text
**Anbu** Says: ???
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Exemplos que NÃO ativam essa regra:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: test
Leafos Says Hello
```

Se nenhuma outra regra IC se aplicar, esses exemplos permanecem OOC.

### Regra dura

**Não tornar `Says:` case-insensitive sem uma nova decisão explícita do projeto.**

Essa regra deve permanecer alinhada em:

- `pc_agent/chat_channels.py`;
- testes do parser;
- `pc_agent/leafos.py` para extração de `speaker`;
- testes LeafOS;
- READMEs;
- esta Bíblia.

### Nome do falante

Não assumir nome simples. Pode conter:

- espaços;
- vírgulas;
- apóstrofos;
- clã + nome;
- Markdown/asteriscos como `**Anbu**`.

O parser não deve depender de uma regex rígida de nome para decidir o canal. A decisão de canal depende do marcador canônico.

---

## 8. Contrato de envio OOC / IC

OOC e IC são destinos diferentes.

O Android 3.4.1 utiliza endpoints dedicados:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` permanece apenas para compatibilidade.

O Agent deve:

1. receber o canal explicitamente;
2. trazer/confirmar o jogo em condição válida;
3. localizar novamente os controles;
4. escolher somente o controle do canal solicitado;
5. recusar envio se o controle não for encontrado;
6. nunca usar o outro canal como fallback silencioso.

O mesmo HWND não pode representar simultaneamente OOC e IC.

---

## 9. Histórico e parser

Histórico padrão:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

Preservar:

- IDs;
- timestamps;
- direção incoming/outgoing;
- `channel`;
- estado do monitor/parser;
- comportamento de replay/resync.

Não “consertar” histórico apagando banco como comportamento padrão.

O limite configurado de mensagem na 3.4.1 é `32000`. A migração de configurações antigas com limite 400 deve ser preservada.

---

## 10. LeafOS / RAW — contrato oficial 3.4.1

A integração LeafOS existe na fonte oficial e é **desativada por padrão**.

Configuração padrão:

```text
enabled: false
export_ic: true
export_ooc: false
processor_interval_seconds: 30
session_idle_seconds: 900
```

O usuário pode configurar:

- Vault;
- diretório RAW;
- exportação IC;
- exportação OOC.

Se Vault existe e RAW está vazio, a migração pode usar:

```text
<Vault>\90 - KageAgent\Raw
```

Nunca hardcode uma Vault pessoal como padrão universal.

### Estrutura RAW

```text
RAW/
├── IC/
│   └── YYYY-MM-DD.md
└── OOC/
    └── YYYY-MM-DD.md
```

Formato:

```html
<!-- kagelink-raw-begin {"id":7538,"timestamp":"...","channel":"ic","speaker":"**Anbu**"} -->
**Anbu** Says: test
<!-- kagelink-raw-end -->
```

Regras:

- append-only;
- UTF-8;
- um arquivo diário por canal;
- IDs são identidade primária;
- não duplicar após restart;
- não reexportar histórico antigo ao trocar caminho;
- erro de escrita não deve avançar cursor;
- `channel` vem do histórico canônico;
- `speaker` reconhece a forma literal `Says:`;
- bloco `(* ... *)` pode ter `speaker: null`;
- Obsidian não precisa estar aberto.

### Processor

Quando habilitado e configurado, o processador:

- consome RAW;
- mantém `last_processed_id`;
- identifica participantes quando possível;
- cria sessões;
- fecha sessão por inatividade conforme `session_idle_seconds`;
- não deve reprocessar IDs antigos;
- deve permanecer isolado de chat/GAME/STATS/túnel.

### Privacidade

Nunca commitar:

- RAW pessoal;
- `config.json` pessoal;
- tokens;
- URLs privadas/temporárias;
- banco de histórico;
- logs sensíveis;
- Vault privada.

---

## 11. GAME — contrato 3.4.1

Janela alvo:

```text
Shinobi Story Online
```

Captura padrão:

```text
JPEG
960 × 540
qualidade 70
~10 FPS
sem áudio
```

Modos:

```text
full
zoom
```

GAME deve permanecer isolado do chat.

Falha de captura/controle não pode derrubar:

- OOC;
- IC;
- histórico;
- autenticação;
- LeafOS;
- STATS.

### Foco e segurança operacional

Ao ativar controle:

- validar janela do jogo;
- rejeitar jogo minimizado;
- focar a janela antes de key-down quando necessário;
- liberar teclas ao desativar;
- liberar teclas em erro/desconexão;
- evitar estado de tecla preso.

---

## 12. Controles GAME configuráveis

Bancos:

```text
ABCD
ZXVU
```

Padrões:

```text
A -> E
B -> Space
C -> G
D -> V

Z -> Z
X -> X
V -> V
U -> U
```

Banco inicial:

```text
ABCD
```

Mapeamentos são persistidos no Android.

Whitelist atual do protocolo:

```text
A-Z
0-9
up, down, left, right
space
enter
escape
tab
shift
ctrl
alt
backspace
insert
delete
home
end
pageup
pagedown
F1-F12
```

Não ampliar essa lista incidentalmente.

Como modificadores e teclas de função fazem parte da whitelist atual, mudanças de UI/protocolo que alterem combinações devem ser revisadas com cuidado.

O KageLink não deve virar um sistema genérico de execução de comandos/programas.

---

## 13. STATS — contrato 3.4.1

STATS é independente de GAME.

Alvo:

```text
Título: Status | Inventory
Classe: #32770
```

A janela deve:

- existir;
- estar visível;
- pertencer ao mesmo PID do Shinobi Story Online;
- corresponder ao título/classe esperados.

Target atual:

```text
5 FPS
```

Controles permitidos:

```text
left click
right click
```

O clique usa coordenadas normalizadas e o `window_id` do último frame válido.

Não transformar STATS em controle genérico do desktop.

---

## 14. API e protocolo

Rotas principais de chat:

```text
/api/health
/api/auth
/api/status
/api/history
/api/input-candidates
/api/input-preference
/api/send/ooc
/api/send/ic
/api/send        # compatibilidade
/ws
```

GAME:

```text
/api/game/status
/ws/game/stream
/ws/game/control
```

STATS possui protocolo/stream próprios no Agent e no app.

Mudança de rota, payload ou semântica exige:

1. motivo explícito;
2. atualização coordenada Agent + App;
3. testes;
4. documentação.

---

## 15. Persistência e atualização

Atualização normal deve preservar, quando aplicável:

- `config.json`;
- token;
- histórico;
- calibração OOC/IC;
- logs úteis;
- estado do parser;
- configuração LeafOS.

O Android preserva:

- perfis;
- tokens em secure storage;
- favoritos;
- banco GAME ativo;
- mapeamentos GAME.

Migração destrutiva exige autorização explícita.

---

## 16. Fluxo obrigatório de mudança

### 1. Atualizar contexto

```bash
git checkout main
git pull
```

### 2. Criar branch

Exemplos:

```text
fix/ic-says-parser
fix/leafos-speaker
fix/stats-click
feat/game-controls
chore/installer-build
docs/3.4.1
```

Não desenvolver diretamente no `main` para mudanças relevantes.

### 3. Reproduzir

Registrar:

- comportamento observado;
- comportamento esperado;
- entrada que causa o erro;
- componente responsável;
- teste de regressão.

### 4. Localizar todas as implementações relacionadas

Pesquisar:

- funções;
- constantes;
- regex;
- strings marcadoras;
- modelos;
- rotas;
- testes;
- documentação.

O bug de `Says:` em 3.4.1 mostrou por que isso é obrigatório: parser, testes e extrator LeafOS precisam compartilhar o mesmo contrato.

### 5. Alteração mínima

Modificar somente o necessário.

### 6. Testar

Executar testes disponíveis.

### 7. Revisar diff

Pergunta obrigatória:

> Existe alguma linha alterada que não é necessária para esta tarefa?

Se sim, remover.

### 8. Commit claro

Exemplos:

```text
Restore exact Says marker classification
Align LeafOS speaker extraction with Says marker
Document KageLink 3.4.1
```

### 9. Pull Request

Explicar:

- problema;
- causa;
- mudança;
- arquivos;
- testes;
- validação manual ainda necessária.

### 10. Merge após validação

Bugs dependentes de BYOND/Windows real podem exigir teste manual antes do merge.

---

## 17. Testes mínimos

### Parser/chat

Obrigatório cobrir:

```text
(*Roleplay*)                         -> IC
**Anbu** Says: test                  -> IC
**Anbu** Says: ???                   -> IC
Uchiha, Leafos Says: hello           -> IC
Hozuki, Shin'ya Says: hello          -> IC
**Anbu** says: test                  -> OOC
**Anbu** SAYS: test                  -> OOC
texto OOC normal                     -> OOC
bloco IC fragmentado                 -> preservado
fala Says: fragmentada               -> uma mensagem lógica
```

### LeafOS

Validar:

- `Says:` extrai speaker;
- `says:` não extrai speaker;
- Markdown no nome;
- RAW diário;
- IC/OOC separados;
- append;
- restart sem duplicação;
- IDs iguais/textos diferentes;
- textos iguais/IDs diferentes;
- troca de caminho;
- erro de escrita não avança cursor;
- processor não reprocessa;
- sessão fecha por gap;
- falha do processor é isolada.

### GAME

Validar:

- janela aberta/fechada/minimizada;
- captura Full/Zoom;
- joystick;
- diagonais;
- bancos ABCD/ZXVU;
- custom mapping;
- reset de mapping;
- hold/multitouch;
- troca de aba;
- desconexão com tecla pressionada;
- nenhuma tecla presa.

### STATS

Validar:

- janela `Status | Inventory` fechada/aberta/minimizada;
- auto/open request;
- stream;
- frame dimensions;
- clique esquerdo;
- clique direito;
- coordenadas fora de faixa rejeitadas;
- `window_id` divergente rejeitado;
- processo errado rejeitado;
- falha STATS não afeta chat/GAME.

### Python

Da pasta apropriada do PC Agent:

```bash
python -m unittest discover -s tests -v
python -m compileall .
```

### Flutter

```bash
flutter analyze
flutter test
```

Nunca afirmar que um teste passou se ele não foi executado.

---

## 18. Build

### Android

```text
KageLink Installer\COMPILAR_APK.bat
```

Saída 3.4.1:

```text
KageLink Installer\KageLink-v3.4.1.apk
```

O script valida localização, roda `flutter analyze` e gera o APK release.

**O installer Windows não gera o APK.**

### PC Agent

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

Saída 3.4.1:

```text
KageLink Installer\installer\output\KageLink-PC-Agent-Setup-v3.4.1.exe
```

O builder pode instalar ferramentas de build como Python/Inno Setup. O usuário final do Setup empacotado não deve precisar de Python para executar o Agent.

---

## 19. Como investigar um bug que “continuou” após correção

Verificar nesta ordem:

1. o arquivo alterado é realmente importado?
2. existe implementação duplicada?
3. testes antigos contradizem o novo contrato?
4. outro módulo reinterpreta o dado?
5. o instalador empacotou a fonte nova?
6. o EXE instalado é realmente o novo build?
7. existe cache/workspace intermediário?
8. APK e Agent são compatíveis?
9. o problema ocorre antes ou depois do parser?
10. RAW consome `channel` persistido ou reprocessa texto?

Nunca declarar “corrigido” somente porque um arquivo foi editado.

---

## 20. GitHub como memória técnica

Registrar decisões em:

- `AGENTS.md` / `AGENTS.en.md` — contratos permanentes;
- `README.pt-BR.md` / `README.md` — instalação e uso;
- commits — alterações;
- Pull Requests — contexto e validação;
- Issues — problemas/funções ainda pendentes.

Conversas com IA podem ajudar, mas não devem ser a única memória de uma decisão crítica.

---

## 21. Regra para agentes de IA

Ao receber tarefa sobre KageLink:

1. usar este repositório como fonte oficial;
2. ler `AGENTS.md` ou `AGENTS.en.md`;
3. verificar versão atual do `main`;
4. inspecionar arquivos diretamente relacionados;
5. pesquisar implementações duplicadas;
6. preservar comportamento não relacionado;
7. trabalhar em branch;
8. produzir diff focado;
9. executar testes disponíveis;
10. declarar honestamente limitações de validação;
11. atualizar documentação quando o contrato mudar;
12. não gerar ZIP como “versão oficial”;
13. não fazer merge de mudança dependente de teste real sem registrar a necessidade.

---

## 22. Definição de pronto

Uma tarefa está pronta quando:

- causa identificada ou mudança claramente justificada;
- código está no GitHub;
- escopo está controlado;
- regras duplicadas foram verificadas;
- testes passaram ou limitações foram registradas;
- não há regressão conhecida;
- documentação relevante está atualizada;
- build real foi validado quando necessário;
- não existe uma “versão certa” somente fora do repositório.

---

# Mandamento final

> **KageLink deve evoluir sem perder o que já funciona. O GitHub é a memória oficial; `Says:` é um contrato exato; chat, GAME, STATS e LeafOS devem permanecer coerentes, isolados e rastreáveis.**
