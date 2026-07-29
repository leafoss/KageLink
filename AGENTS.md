# KageLink — Bíblia de Desenvolvimento

[English](AGENTS.en.md) · [Runtime e organização](AGENTS_RUNTIME.md) · [Kage Pilot](KAGE_PILOT.md) · [README PT-BR](README.pt-BR.md) · [README EN-US](README.md)

Este arquivo é a **fonte operacional de verdade para qualquer pessoa ou agente de IA que altere o KageLink**.

Ele governa a versão oficial publicada no `main`, incluindo Android, PC Agent, Installer, LeafOS e Kage Pilot. Contratos especializados estão nos capítulos vinculados acima e têm força normativa equivalente dentro de seus escopos.

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
- APK ou EXE isolado;
- arquivo enviado em conversa;
- log de execução;
- ambiente virtual;
- configuração local;
- cópia local não commitada.

Fluxo correto:

```text
main
  ↓
branch de trabalho
  ↓
alteração mínima e coerente
  ↓
testes
  ↓
revisão do diff
  ↓
Pull Request
  ↓
validação real quando necessária
  ↓
merge explícito
```

Nunca usar ZIP como substituto do Git.

---

## 2. Versão oficial

A versão de release é definida por:

```text
RELEASE_VERSION
```

Essa é a única fonte humana editável. Flutter, Installer, backend, `/api/health`, labels, artefatos, workflows e READMEs devem permanecer sincronizados por geração ou teste automático.

O `main` analisado após o PR #16 contém release `3.4.2` e Kage Pilot Dojo validado. Não manter referências manuais a `3.4.1` como estado atual.

Não aumentar versão por alteração local ainda não validada sem decisão explícita de release.

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
- reversível quando possível;
- compatível com comportamento funcional não relacionado.

### Proibido durante uma tarefa limitada

- refatorar por estética;
- trocar biblioteca sem motivo funcional;
- alterar UI ou protocolo não relacionado;
- mudar mapeamentos padrão sem solicitação;
- apagar histórico/configuração para “resolver” bug;
- substituir módulo inteiro quando uma mudança pequena resolve;
- ampliar o escopo por conveniência;
- criar nova cópia versionada quando o arquivo canônico pode ser atualizado.

Quando o usuário disser **“mude somente X”**, isso é uma restrição dura.

Uma reorganização ampla só é permitida quando explicitamente solicitada, como nesta consolidação do Kage Pilot, e deve possuir inventário, testes, rollback e PR dedicado.

---

## 4. Arquitetura oficial

Produtos principais:

1. **KageLink Android App** — Flutter.
2. **KageLink PC Agent** — Windows/Python.
3. **Installer Windows** — empacota o PC Agent.
4. **LeafOS integration** — módulo opcional dentro do Agent.
5. **Kage Pilot** — subsistema local de percepção, combate e treinamento no Dojo.

Estrutura canônica:

```text
KageLink/
├── AGENTS.md
├── AGENTS.en.md
├── AGENTS_RUNTIME.md
├── AGENTS_RUNTIME.en.md
├── KAGE_PILOT.md
├── KAGE_PILOT.en.md
├── README.md
├── README.pt-BR.md
├── RELEASE_VERSION
└── KageLink Installer/
    ├── installer/
    ├── lib/
    ├── pc_agent/
    ├── test/
    └── pubspec.yaml
```

A composição empacotada, workers, falhas, persistência, janelas e regras de organização estão em `AGENTS_RUNTIME.md`.

Antes de editar, identificar qual componente realmente controla o comportamento observado.

---

## 5. Responsabilidades

### Android App

Responsável por:

- perfis de conexão;
- armazenamento seguro do token;
- OOC e IC/RP;
- GAME e STATS;
- apresentação e reconciliação do histórico;
- HTTP/WebSocket e reconexão;
- idioma PT-BR/EN-US;
- navegação e calibração;
- configuração/persistência dos controles `ABCD`/`ZXVU`.

### PC Agent

Responsável por:

- localizar `Shinobi Story Online`;
- ler e classificar chat;
- persistir histórico e parser;
- localizar campos OOC/IC;
- enviar texto;
- autenticação, API e WebSockets;
- servidor local e Cloudflare Tunnel;
- captura/controle GAME;
- captura/controle STATS;
- foco e proteção contra inputs presos;
- LeafOS RAW/Processor/Interpreter/Reviewer quando habilitados;
- serviços estáveis expostos ao Kage Pilot.

### Installer

Responsável por:

- empacotar a fonte atual;
- incluir dependências e `cloudflared` verificado;
- instalar `KageLink.exe`;
- preservar dados em atualização normal;
- oferecer remoção deliberada de dados no uninstall.

**Nunca corrigir um bug do Agent somente no instalador.**

### Kage Pilot

Responsável por:

- percepção e tracking no jogo;
- seleção de alvo;
- aquisição do treinador;
- fluxo determinístico do Dojo;
- combate, KO, retorno e recuperação;
- telemetria e parada de emergência.

O contrato completo está em `KAGE_PILOT.md`.

---

## 6. Fonte única de lógica

Decisões de domínio devem possuir uma implementação canônica.

Exemplo OOC/IC:

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

O RAW não decide novamente o canal.

Para Kage Pilot:

```text
entrypoint estável
    ↓
serviço canônico
    ↓
módulos internos por responsabilidade
```

Não criar `v03l`, `v03m` ou equivalente como nova fonte oficial. Atualizar o nome canônico e preservar histórico pelo Git.

---

## 7. Contrato OOC / IC — REGRA PROTEGIDA

### IC por bloco de roleplay

Todo bloco iniciado por `(*` e encerrado pelo próximo `*)` é IC/RP. Blocos fragmentados permanecem pendentes até o fechamento.

### IC por fala `Says:`

A regra é **literal e case-sensitive**.

Marcador válido:

```text
Says:
```

Devem ser IC:

```text
**Anbu** Says: ???
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Não ativam essa regra:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: test
Leafos Says Hello
```

Não tornar `Says:` case-insensitive sem nova decisão explícita.

A regra deve permanecer alinhada em parser, testes, speaker extraction, LeafOS, READMEs e Bíblia.

Nomes de falante podem conter espaços, vírgulas, apóstrofos, clã e Markdown. A classificação depende do marcador, não de regex rígida do nome.

---

## 8. Envio OOC / IC

Endpoints dedicados:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` permanece para compatibilidade.

O Agent deve:

1. receber o canal explicitamente;
2. validar/focar o jogo;
3. relocalizar os controles;
4. selecionar somente o canal solicitado;
5. recusar se o controle não existir;
6. nunca usar o outro canal como fallback silencioso.

O mesmo HWND não representa simultaneamente OOC e IC.

---

## 9. Histórico e parser

Histórico padrão:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

Preservar:

- IDs;
- timestamps;
- direção;
- canal;
- estado do monitor/parser;
- replay/resync;
- monotonicidade de IDs em relação à Vault.

Não apagar banco como solução padrão.

Limite atual de mensagem: `32000`. Preservar migração de configurações antigas com limite 400.

---

## 10. LeafOS / RAW

A integração é opcional e desativada por padrão.

Configuração padrão:

```text
enabled: false
export_ic: true
export_ooc: false
processor_interval_seconds: 30
session_idle_seconds: 900
```

Nunca hardcode Vault pessoal.

### RAW

```text
RAW/
├── IC/YYYY-MM-DD.md
└── OOC/YYYY-MM-DD.md
```

Regras:

- append-only;
- UTF-8;
- IDs como identidade;
- sem duplicação após restart;
- erro de escrita não avança cursor;
- canal vem do histórico canônico;
- speaker usa `Says:` literal;
- Obsidian não precisa estar aberto.

### Fluxo de memória

```text
RAW imutável
→ Processor
→ sessão fechada
→ Interpreter
→ Bundle pending_review
→ Memory Reviewer
→ Canonical Memory
```

Regras permanentes:

- Interpreter produz candidatos;
- promoção exige aprovação humana;
- Reviewer não altera RAW/Processor/Bundle;
- evidência deve voltar ao RAW;
- `memory.json` é fonte canônica;
- `MEMORY.md` é projeção derivada;
- JSON canônico inválido bloqueia escrita.

Políticas completas de persistência e corrupção estão em `AGENTS_RUNTIME.md`.

---

## 11. GAME e STATS

Janela alvo:

```text
Shinobi Story Online
```

GAME padrão:

```text
JPEG
960 × 540
quality 70
~10 FPS
sem áudio
```

Modos:

```text
full
zoom
```

GAME deve permanecer isolado de chat, LeafOS e STATS. Falha de captura/controle não derruba o restante.

STATS trabalha com `Status | Inventory` e deve validar HWND, PID, título, classe, frame esperado e coordenadas dentro do client antes do clique.

O gate comum de janelas e inputs está em `AGENTS_RUNTIME.md` e também se aplica ao Kage Pilot.

---

## 12. Segurança

- token aleatório e comparação segura;
- tokens Android em secure storage;
- não registrar tokens ou query strings sensíveis;
- `cloudflared` fixado por versão e SHA-256;
- teclado GAME/Kage Pilot limitado a teclas autorizadas;
- inputs liberados em erro/desconexão/shutdown;
- fallback de captura genérica somente após validar e focar a janela correta;
- nenhuma automação deve executar programas, URLs ou comandos arbitrários recebidos do usuário.

---

## 13. PT-BR e EN-US

Todos os textos de produto devem suportar `pt-BR` e `en-US`.

- UI usa catálogos de localização;
- controllers/services retornam códigos, não prosa localizada;
- API/WebSocket usa códigos técnicos estáveis;
- documentação de usuário possui par equivalente;
- IDs, campos JSON e códigos não são traduzidos;
- ausência de tradução não pode quebrar funcionalidade.

---

## 14. Organização de arquivos

A árvore ativa não é arquivo histórico.

### Regra canônica

- um arquivo público por entrypoint estável;
- módulos internos por responsabilidade;
- nenhum sufixo de tentativa em nova implementação oficial;
- testes por contrato, não por versão transitória;
- relatórios antigos permanecem no Git, não como manual atual;
- scripts descartáveis saem da árvore quando absorvidos por testes;
- versões substituídas são removidas após atualização de imports, workflows e testes.

“Um Kage Pilot” significa uma superfície única e coerente, não um monólito de milhares de linhas.

Toda consolidação deve ocorrer em branch dedicada e passar pela suíte completa.

---

## 15. Testes

Antes de declarar pronto, executar o conjunto proporcional ao risco.

### Python

```powershell
cd "KageLink Installer\pc_agent"
python -m unittest discover -s tests -v
python -m compileall .
```

### Flutter

```powershell
cd "KageLink Installer"
flutter pub get
flutter gen-l10n
flutter analyze
flutter test
```

### Empacotamento

Validar build, smoke launch e installer quando entrypoint/dependência/release forem afetados.

### Kage Pilot

Executar suíte direcionada, suíte completa do PC Agent e validação real no Windows/BYOND quando a mudança afetar percepção, input, janela, timing, KO ou Dojo.

Nunca afirmar teste não executado.

---

## 16. Definição de pronto

Uma tarefa só está pronta quando:

- o escopo foi conferido;
- a fonte ativa foi identificada;
- contratos não relacionados foram preservados;
- testes proporcionais foram executados;
- cleanup e falhas foram considerados;
- documentação PT-BR/EN-US foi atualizada;
- versão permanece coerente;
- nenhuma informação sensível foi publicada;
- validação real pendente foi declarada;
- a árvore ativa não ganhou novo snapshot redundante;
- a mudança está em branch/PR revisável.

Em caso de dúvida, preservar o comportamento atual, registrar a incerteza e voltar às Bíblicas antes de alterar.
