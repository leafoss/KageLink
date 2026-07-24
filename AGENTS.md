# KageLink — Bíblia de Desenvolvimento

[English](AGENTS.en.md) · [README em Português](README.pt-BR.md) · [English README](README.md)

Este documento é a **fonte operacional de verdade para qualquer pessoa ou agente de IA que altere o KageLink**.

Seu objetivo é impedir regressões, versões divergentes, refatorações desnecessárias, documentação que promete recursos inexistentes e o antigo fluxo baseado em ZIPs.

Antes de modificar código, leia este arquivo e os arquivos diretamente relacionados à tarefa.

---

## 1. Fonte oficial do projeto

Repositório oficial:

```text
https://github.com/leafoss/KageLink
```

### Regra absoluta

**O GitHub é a única fonte oficial de código do KageLink.**

Não considerar como fonte principal:

- ZIPs antigos;
- cópias em Desktop;
- pastas locais não commitadas;
- builds já instalados;
- arquivos isolados enviados em conversas;
- um EXE/APK sem rastreabilidade até um commit.

Se uma funcionalidade existe apenas localmente, ela não é uma funcionalidade oficial do `main` até ser levada para o GitHub e validada.

### Fluxo oficial

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
validação
  ↓
merge
```

---

## 2. Idiomas da documentação

A Bíblia possui duas versões:

- `AGENTS.md` — Português do Brasil;
- `AGENTS.en.md` — English.

As duas devem representar as **mesmas regras técnicas**.

Quando uma regra permanente mudar, atualizar ambas no mesmo PR sempre que possível.

Os READMEs seguem o mesmo princípio:

- `README.pt-BR.md`;
- `README.md` em inglês.

---

## 3. Estado oficial atual

A versão identificada atualmente no `main` é:

```text
KageLink 3.3.0 — GAME V1
```

Componentes oficiais:

1. **KageLink Android App** — Flutter/Android;
2. **KageLink PC Agent** — Windows/Python;
3. **KageLink Windows Installer** — empacota o PC Agent.

O APK Android e o instalador Windows são artefatos diferentes e possuem pipelines de build separados.

### Importante

O instalador Windows **não gera o APK**.

O APK é gerado por:

```text
KageLink Installer\COMPILAR_APK.bat
```

O instalador do PC Agent é gerado por:

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

---

## 4. Filosofia principal

KageLink é um projeto funcional usado em ambiente real.

### Mandamento principal

> **Não quebrar o que já funciona.**

Toda alteração deve ser:

- mínima;
- localizada;
- rastreável;
- justificável;
- testável;
- compatível com o comportamento existente, salvo quando a tarefa exigir explicitamente uma mudança.

### Não fazer

- refatorar por estética durante uma correção;
- renomear arquivos/classes/rotas sem necessidade;
- reorganizar pastas durante um bugfix;
- trocar dependências sem motivo funcional;
- modificar UI incidentalmente;
- alterar protocolo durante uma correção local;
- mudar mapeamento de controles sem solicitação;
- apagar histórico/configuração para “resolver” um bug;
- substituir um módulo inteiro quando uma alteração pequena resolve;
- aproveitar uma tarefa limitada para “melhorar” áreas não solicitadas.

Uma correção de parser não autoriza alterar GAME.

Uma correção de GAME não autoriza alterar chat.

Uma correção documental não autoriza mudar comportamento de produção, exceto quando a própria documentação revela um erro diretamente ligado ao fluxo documentado e a correção é pequena, explícita e revisada.

---

## 5. Arquitetura oficial

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
    │   ├── CRIAR_INSTALADOR.bat
    │   ├── KageLink.spec
    │   └── KageLink_PC_Agent.iss
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

Antes de alterar qualquer arquivo, descobrir qual componente realmente controla o comportamento observado.

---

## 6. Separação de responsabilidades

### Android App

Responsável principalmente por:

- interface de conexão/perfis;
- OOC;
- IC/RP;
- GAME;
- apresentação do histórico;
- conexão HTTP/WebSocket;
- reconexão;
- armazenamento seguro da chave dos perfis;
- navegação;
- idioma;
- calibração solicitada pelo usuário;
- controles GAME enviados pelo protocolo permitido.

### PC Agent

Responsável principalmente por:

- localizar `Shinobi Story Online`;
- ler chat;
- classificar OOC/IC;
- manter histórico e estado do parser;
- localizar campos OOC/IC;
- enviar texto ao jogo;
- autenticar o cliente;
- API/WebSockets;
- servidor local;
- Cloudflare Tunnel;
- captura GAME;
- controle GAME;
- foco da janela do jogo;
- proteção contra teclas presas.

### Installer

Responsável por:

- empacotar a fonte atual do PC Agent;
- incluir dependências de runtime;
- incluir `cloudflared` validado;
- instalar `KageLink.exe`;
- preservar dados em atualização normal;
- oferecer remoção de dados no uninstall.

**Nunca corrigir um bug do Agent somente no instalador. Corrigir a fonte do Agent e então garantir que o instalador empacote essa fonte.**

---

## 7. Uma única fonte para decisões de domínio

Quando uma mesma decisão aparece em várias partes do projeto, deve existir uma implementação canônica sempre que possível.

Exemplo crítico:

```text
classificação OOC/IC
```

Fluxo conceitual correto:

```text
texto capturado
    ↓
ChatChannelParser
    ↓
mensagem classificada
    ├── histórico
    ├── API/WebSocket
    └── aplicativo
```

Não criar regras independentes para UI, histórico e backend se todos podem consumir o mesmo `channel` já classificado.

Qualquer futura integração RAW também deve consumir essa classificação canônica, não criar um segundo parser divergente.

---

## 8. Contrato oficial de classificação OOC / IC

Este é comportamento protegido.

### 8.1 IC por bloco de roleplay

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

Blocos podem chegar fragmentados entre leituras. O parser deve manter o bloco pendente até receber o fechamento.

### 8.2 IC por fala `Says:`

A regra oficial atual é **literal e case-sensitive**.

O marcador válido é exatamente:

```text
Says:
```

Exemplos IC:

```text
**Anbu** Says: ???
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Exemplos que não ativam essa regra e permanecem no fluxo OOC caso nenhuma outra regra IC se aplique:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: test
```

### Regra dura

**Não tornar `Says:` case-insensitive sem uma nova decisão explícita do projeto.**

Essa regra foi corrigida no parser canônico e possui testes de regressão.

### Nome do falante

Não presumir que o nome é uma única palavra. O texto pode conter:

- vírgulas;
- espaços;
- apóstrofos;
- clã + nome;
- Markdown/asteriscos, como `**Anbu**`;
- outros formatos emitidos pelo jogo.

A implementação atual identifica o marcador na linha, sem depender de um formato rígido de nome.

### OOC

Tudo que não satisfizer uma regra IC válida continua OOC.

Não alterar o comportamento OOC durante uma correção exclusiva de IC.

---

## 9. Contrato de envio OOC / IC

OOC e IC são destinos diferentes.

O Agent deve:

1. localizar a janela do jogo;
2. confirmar foco;
3. localizar novamente os controles `Edit`;
4. escolher o controle correspondente ao canal solicitado;
5. bloquear envio se o controle não for encontrado;
6. nunca usar o outro canal como fallback silencioso.

Um mesmo HWND não pode representar simultaneamente OOC e IC.

Quando a detecção automática não for suficiente, o app oferece calibração separada.

---

## 10. Histórico e persistência

O histórico de chat pertence ao PC Agent e usa SQLite.

Dados de usuário que devem ser preservados em atualizações normais quando aplicável:

- `config.json`;
- chave de acesso;
- banco de histórico;
- preferências OOC/IC;
- estado persistente do parser;
- logs;
- demais configurações compatíveis da instalação.

Nunca resolver um bug apagando banco, configuração ou histórico como comportamento padrão.

Migração destrutiva exige autorização explícita e estratégia de backup/migração.

---

## 11. RAW / Obsidian — status e contrato

### Status do `main` 3.3.0

A Bíblia registra o contrato desejado para integração RAW/Obsidian, porém a fonte oficial atual do `main` **não expõe configuração RAW em `AppConfig`**.

Portanto:

- não anunciar RAW/Obsidian como recurso padrão da release 3.3.0;
- não presumir que um RAW gerado por um build local existe no GitHub;
- se a implementação existir apenas fora do repositório, primeiro trazê-la para uma branch.

### Contrato para quando RAW entrar oficialmente

A integração deve:

- usar a mesma mensagem já classificada pelo parser canônico;
- não reclassificar OOC/IC no writer;
- funcionar com Obsidian fechado;
- permitir caminho configurável;
- criar diretório quando apropriado;
- usar UTF-8;
- preservar o texto bruto;
- preferir organização diária quando esse for o formato aprovado;
- fazer append sem reescrever histórico desnecessariamente;
- manter metadados suficientes para timestamp/id/canal;
- tratar replay/duplicação;
- nunca commitar RAW pessoal.

Formato de referência previamente utilizado em desenvolvimento:

```html
<!-- kagelink-raw-begin {"id":7538,"timestamp":"...","channel":"ic","speaker":null} -->
mensagem original
<!-- kagelink-raw-end -->
```

Esse formato só deve ser considerado oficial quando a implementação correspondente também estiver no repositório.

---

## 12. Contrato GAME

GAME é deliberadamente isolado do chat.

Falha em GAME não deve derrubar:

- OOC;
- IC/RP;
- histórico;
- autenticação;
- parser;
- envio de chat.

### Janela alvo

```text
Shinobi Story Online
```

Não transformar KageLink em controle remoto genérico do desktop.

### Stream GAME V1

Contrato atual:

- JPEG;
- `960 × 540`;
- alvo aproximado de `8–12 FPS`;
- sem áudio;
- modo Full;
- modo Zoom central;
- conexão separada do WebSocket do chat;
- sem fila crescente intencional de frames.

### Orientação

- OOC/IC: retrato;
- GAME: paisagem;
- ao sair de GAME: retornar para retrato.

### Foco

Ao ativar GAME, o cliente solicita um `focus_click`.

O Agent:

1. valida a janela alvo;
2. recusa jogo minimizado;
3. traz o jogo para frente;
4. clica no centro da área capturada.

---

## 13. Controles GAME protegidos

Mapeamento atual:

```text
Joystick -> setas
A -> E
B -> Space
C -> G
D -> V
```

Whitelist atual:

```text
up, down, left, right, e, space, g, v
```

Não adicionar silenciosamente:

- Alt+F4;
- tecla Windows;
- Ctrl+Esc;
- comandos arbitrários;
- execução de programas;
- macros genéricas;
- controle amplo do desktop.

### Teclas presas

O projeto deve continuar liberando estado de tecla ao:

- sair de GAME;
- colocar app em background;
- perder conexão;
- perder foco de forma insegura;
- perder janela do jogo;
- atingir timeout de heartbeat;
- encerrar Agent/sessão.

---

## 14. Conexão e segurança

### Rede local

O Agent publica o servidor em host configurado, atualmente `0.0.0.0`, com porta padrão `8765`.

A UI calcula e exibe o endereço local atual.

Se a porta estiver ocupada, o Agent pode selecionar outra e persistir a nova porta.

### Cloudflare

Por padrão, a conexão externa usa Cloudflare Quick Tunnel.

O Agent:

- prepara/valida `cloudflared`;
- verifica SHA-256;
- verifica cabeçalho executável;
- valida versão;
- inicia túnel para o servidor local;
- extrai a URL `trycloudflare.com`;
- grava a informação de conexão.

### Token

A chave de acesso:

- é gerada automaticamente;
- deve possuir entropia adequada;
- é necessária para autenticação;
- não deve aparecer em logs públicos ou commits;
- pode ser regenerada nas configurações do Agent.

Regenerar a chave invalida as credenciais já salvas nos perfis Android.

### Arquivos privados

Nunca commitar:

- `config.json` de usuário;
- `KAGELINK_CONNECTION.txt` real;
- tokens/chaves;
- URLs temporárias privadas associadas a token;
- banco de histórico pessoal;
- RAWs pessoais;
- logs contendo credenciais.

---

## 15. APIs e protocolo

Rotas de chat atuais:

```text
/api/auth
/api/status
/api/history
/api/send
/api/input-candidates
/api/input-preference
/ws
```

Rotas GAME atuais:

```text
/api/game/status
/ws/game/stream
/ws/game/control
```

Não mudar nomes, payloads ou semântica incidentalmente.

Mudança de protocolo exige:

1. motivo explícito;
2. atualização coordenada Agent + App;
3. testes;
4. documentação;
5. estratégia de compatibilidade quando necessária.

---

## 16. Contrato do instalador

O Setup Windows instala o PC Agent por padrão em:

```text
%LocalAppData%\KageLink PC Agent
```

A instalação normal deve continuar funcionando sem exigir que o usuário final instale manualmente Python ou dependências de desenvolvimento.

O instalador deve preservar dados existentes em atualização normal.

No uninstall, pode oferecer a remoção explícita dos dados do usuário.

### Documentação embutida

O `.iss` deve apontar para os READMEs que realmente existem no repositório.

Após a consolidação da documentação na raiz, as fontes corretas são:

```text
README.pt-BR.md
README.md
```

Não reintroduzir referências a READMEs removidos dentro de `KageLink Installer/`.

---

## 17. Contrato do APK

O build oficial usa:

```text
KageLink Installer\COMPILAR_APK.bat
```

O script atualmente:

1. valida Flutter;
2. valida catálogos de localização;
3. cria workspace Android limpo;
4. copia fontes/assets/testes/overlay;
5. executa `flutter pub get`;
6. gera localização;
7. executa `flutter analyze`;
8. gera APK release;
9. copia o artefato final.

Saída atual:

```text
KageLink Installer\KageLink-v3.3.0.apk
```

Não afirmar que o APK foi validado em dispositivo real se isso não aconteceu.

---

## 18. Versionamento

Manter coerência entre:

- `pubspec.yaml`;
- versão do PC Agent;
- versão do instalador;
- nomes de artefatos;
- documentação de release quando aplicável.

Não aumentar versão por uma alteração local ainda não validada sem decisão explícita de release.

---

## 19. Fluxo obrigatório para mudanças

### 1. Atualizar contexto

```bash
git checkout main
git pull
```

### 2. Criar branch

Exemplos:

```text
fix/ic-says-classification
fix/game-focus
feat/raw-obsidian
chore/installer-build
docs/installation-guide
```

Não desenvolver diretamente no `main` para mudanças relevantes.

### 3. Reproduzir/definir o comportamento

Registrar:

- comportamento observado;
- comportamento esperado;
- entrada que reproduz;
- componente provável;
- evidência necessária para aceitar a correção.

### 4. Localizar todas as implementações relacionadas

Pesquisar por:

- função;
- classe;
- constante;
- regex/string marcador;
- rota;
- modelo;
- writer/persistência;
- teste existente;
- script de empacotamento.

### 5. Alteração mínima

Modificar somente o necessário.

### 6. Testar

Rodar testes relevantes e criar regressão quando o bug permitir.

### 7. Revisar diff

Pergunta obrigatória:

> Existe alguma linha alterada que não é necessária para esta tarefa?

Se sim, remover.

### 8. Commit claro

Exemplos:

```text
Fix exact Says: IC classification
Preserve GAME controls on tab exit
Fix installer documentation paths
Document complete installation flow
```

### 9. Pull Request

O PR deve explicar:

- problema/objetivo;
- causa quando aplicável;
- alterações;
- arquivos afetados;
- testes executados;
- validação manual pendente.

### 10. Merge depois da validação apropriada

Bugs dependentes de BYOND/Windows real podem exigir teste manual antes de serem considerados definitivamente resolvidos.

---

## 20. Testes mínimos por área

### Parser/chat

Cobrir pelo menos:

```text
(*Roleplay*)                  -> IC
**Anbu** Says: test           -> IC
Uchiha, Leafos Says: hello    -> IC
Hozuki, Shin'ya Says: hello   -> IC
**Anbu** says: test           -> OOC
**Anbu** SAYS: test           -> OOC
texto OOC normal              -> OOC
bloco IC fragmentado          -> reconstruído
```

Também testar conteúdo misto e falsos positivos relevantes.

### Envio OOC/IC

Validar:

- OOC encontrado;
- IC encontrado;
- OOC ausente;
- IC ausente;
- controles diferentes;
- sem fallback silencioso;
- foco do jogo;
- recriação de controles BYOND.

### Histórico

Validar:

- migração;
- persistência de `channel`;
- estado pendente do parser;
- ressincronização;
- replay/duplicação;
- reinício.

### RAW — somente quando existir na branch

Validar:

- configuração;
- diretório;
- arquivo diário se esse for o contrato vigente;
- append;
- UTF-8;
- id/timestamp/channel;
- `Says:` exato;
- `says:` minúsculo permanecendo OOC;
- Markdown/asteriscos;
- Obsidian fechado;
- replay/duplicação.

### GAME

Validar:

- jogo aberto;
- jogo fechado;
- minimizado;
- maximizado;
- stream;
- Full;
- Zoom;
- FPS sem fila crescente;
- joystick;
- diagonais;
- A/B/C/D;
- tap;
- hold;
- multitouch;
- `focus_click`;
- troca de aba;
- background;
- desconexão segurando tecla;
- nenhuma tecla presa;
- OOC/IC durante falha GAME.

### Flutter

Quando ambiente disponível:

```bash
flutter analyze
flutter test
```

### Python

Quando aplicável e de acordo com a estrutura da branch:

```bash
python -m pytest
python -m compileall .
```

Nunca inventar resultado de teste.

---

## 21. Como investigar bugs persistentes

Quando um bug continua após alterar um arquivo, investigar nesta ordem:

1. esse arquivo realmente é executado?
2. existe outra implementação da mesma regra?
3. a branch correta foi compilada?
4. o instalador empacotou a fonte nova?
5. o EXE instalado é o build novo?
6. existe workspace/cache antigo?
7. App e Agent usam protocolo compatível?
8. o bug acontece antes ou depois do parser?
9. o dado persistido usa `channel` classificado ou reprocessa texto?
10. o comportamento está apenas num build local não commitado?

Não repetir correções aleatórias antes de rastrear o fluxo do dado.

---

## 22. Resolução histórica — bug `Says:`

O bug observado em que:

```text
**Anbu** Says: ???
**Anbu** Says: test
```

não era classificado como IC foi rastreado até o parser canônico da fonte oficial, que originalmente reconhecia apenas `(* ... *)`.

A correção oficial adicionou a regra literal:

```python
"Says:" in line
```

A decisão final do projeto é:

```text
Says:  -> regra IC
says:  -> não ativa a regra
SAYS:  -> não ativa a regra
```

Foram adicionados testes de regressão para falante comum, `**Anbu**`, lowercase e conteúdo misto.

Este problema não deve mais permanecer descrito como “em investigação” na documentação atual.

---

## 23. GitHub como memória técnica

Decisões importantes devem ficar registradas através de:

- `AGENTS.md` / `AGENTS.en.md` para regras permanentes;
- READMEs para instalação e uso;
- commits para histórico;
- Pull Requests para contexto e validação;
- Issues para problemas e funcionalidades ainda não resolvidos.

Conversas externas podem orientar o desenvolvimento, mas não devem ser a única memória de decisões críticas.

---

## 24. Regras específicas para agentes de IA

Ao receber uma tarefa sobre KageLink:

1. usar este repositório como fonte oficial;
2. ler `AGENTS.md` ou `AGENTS.en.md`;
3. inspecionar a branch atual antes de editar;
4. procurar implementações duplicadas;
5. verificar testes existentes;
6. preservar comportamento não relacionado;
7. trabalhar em branch;
8. manter o diff mínimo;
9. testar quando possível;
10. declarar claramente limitações de validação;
11. nunca afirmar que um teste passou sem executá-lo/evidência;
12. nunca criar ZIP como fonte paralela de verdade;
13. não fazer merge automaticamente de mudança que ainda exige validação real sem registrar essa necessidade;
14. não documentar como “habilitada” uma função que não está no `main`.

### Quando o usuário disser “mude somente X”

Tratar como restrição dura.

Não usar a tarefa para alterar Y ou Z.

---

## 25. Obrigação de manter documentação correta

README e Bíblia fazem parte do produto.

Quando uma mudança altera:

- instalação;
- conexão;
- UI;
- regra de parser;
- controles;
- protocolo;
- build;
- limitações;
- segurança;

avaliar se `README.md`, `README.pt-BR.md`, `AGENTS.md` e `AGENTS.en.md` precisam ser atualizados.

### Regra de factualidade

**Não prometer no README uma funcionalidade que a fonte atual não contém.**

Quando houver diferença entre build local e `main`, documentar o `main` como oficial até a implementação ser commitada.

---

## 26. Definição de pronto

Uma tarefa está pronta quando:

- o objetivo está claro;
- a causa foi identificada quando necessária;
- o código/documentação está no GitHub;
- o diff está limitado ao escopo;
- testes relevantes passaram ou limitações foram registradas;
- não existe regressão conhecida;
- documentação necessária foi atualizada;
- artefato real foi validado quando a tarefa depende de build;
- não existe uma “versão correta” escondida fora do repositório.

---

# Mandamento final

> **KageLink deve evoluir sem perder o que já funciona. GitHub é a memória oficial; mudanças são mínimas, rastreáveis e testadas; documentação descreve apenas o que a fonte realmente suporta; e nenhum ZIP local pode voltar a competir com o repositório como fonte de verdade.**