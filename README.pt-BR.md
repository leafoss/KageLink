# KageLink

[English](README.md)

KageLink é um aplicativo complementar para **Shinobi Story Online** que conecta o cliente do jogo no Windows a uma interface móvel Android. A versão **3.3.0 — GAME V1** preserva o sistema validado de chat OOC/IC e adiciona um módulo GAME isolado para visualização e controle remoto do jogo.

## O que o KageLink faz

O aplicativo móvel possui três abas:

- **OOC** — chat fora de personagem.
- **IC / RP** — chat de interpretação, com histórico e rascunhos independentes.
- **GAME** — imagem ao vivo do jogo e controles remotos.

O módulo GAME foi mantido isolado do chat. Se o jogo estiver fechado, minimizado, indisponível ou o stream falhar, a leitura, parsing, histórico, autenticação e envio de mensagens OOC/IC continuam funcionando.

## Destaques da versão 3.3.0

- Stream autenticado do jogo em **960×540**, JPEG, alvo de **8–12 FPS**, sem áudio.
- Dois modos de visualização: **Tela inteira** e **Aproximado** (recorte central 16:9 de aproximadamente 2×).
- Joystick transparente de oito direções mapeado para as setas.
- Botões de ação com toque, hold e multitouch:

| Botão | Tecla |
| --- | --- |
| A | E |
| B | Espaço |
| C | G |
| D | V |

- Orientação paisagem automática na aba GAME e retorno ao retrato ao voltar para o chat.
- Janela-alvo exata: `Shinobi Story Online`.
- Soltura automática das teclas ao desconectar, sair da aba, colocar o app em segundo plano, expirar heartbeat, perder o jogo ou encerrar o agente.
- Protocolo OOC/IC existente preservado da versão 3.2.0.

A referência visual aprovada permanece em `KageLink Installer/docs/Idea.png`.

## Arquitetura

O KageLink reutiliza o mesmo servidor, perfil de conexão, túnel Cloudflare e token de autenticação para chat e GAME, mantendo as novas rotas GAME separadas.

### Rotas existentes do chat

- `/api/auth`
- `/api/status`
- `/api/history`
- `/api/send`
- `/api/input-candidates`
- `/api/input-preference`
- `/ws`

### Rotas GAME

- `/api/game/status`
- `/ws/game/stream`
- `/ws/game/control`

O PC Agent no Windows localiza a janela do jogo e tenta capturar um controle interno adequado de renderização. Quando necessário, utiliza a área cliente da janela principal como fallback. O projeto foi desenhado para não transmitir a área de trabalho completa.

## Modelo de segurança

O protocolo de controle GAME aceita somente esta whitelist:

```text
up, down, left, right, e, space, g, v
```

Comandos arbitrários, envio de texto, Alt+F4, tecla Windows, Ctrl+Esc, macros e controle geral da área de trabalho não fazem parte do protocolo.

A entrada do jogo só é enviada após localizar e validar a janela `Shinobi Story Online`. A camada de controle acompanha o estado das teclas pressionadas para evitar key-down duplicado e key-up perdido.

## Estrutura do repositório

```text
KageLink/
├── README.md
├── README.pt-BR.md
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

## Compilar o aplicativo Android

Requisitos de desenvolvimento:

- Windows
- Flutter disponível no `PATH`
- Android SDK configurado

Dentro de `KageLink Installer/`, execute:

```bat
COMPILAR_APK.bat
```

O script cria um workspace Android limpo, copia os fontes, gera localizações, executa a análise do Flutter e compila:

```text
KageLink-v3.3.0.apk
```

## Criar o instalador do PC Agent para Windows

Dentro de `KageLink Installer/`, execute:

```bat
installer\CRIAR_INSTALADOR.bat
```

O processo cria um ambiente isolado, instala as dependências necessárias para a compilação, empacota Python e bibliotecas com PyInstaller, inclui o Cloudflared e compila o instalador utilizando Inno Setup.

Resultado:

```text
installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe
```

O usuário final **não precisa** instalar manualmente Python, Pillow, MSS, pip ou ferramentas de desenvolvimento.

## Instalar / atualizar para 3.3.0

### Android

1. Execute `COMPILAR_APK.bat` no computador de desenvolvimento.
2. Instale `KageLink-v3.3.0.apk` sobre a versão atual.
3. Continue utilizando o mesmo servidor, perfil e token já salvos.

### PC Agent no Windows

1. Feche o KageLink no Windows.
2. Execute `installer\CRIAR_INSTALADOR.bat` no computador de desenvolvimento.
3. Instale `KageLink-PC-Agent-Setup-v3.3.0.exe` sobre a versão anterior.
4. O instalador preserva configuração, token, histórico, logs e dados de conexão existentes.
5. Abra o Shinobi Story Online e depois o KageLink.

O APK 3.3.0 precisa do PC Agent 3.3.0 para utilizar as funções GAME. O chat continua baseado no protocolo compatível anterior, mas agentes antigos não possuem os novos endpoints GAME.

## Funcionamento da aba GAME

### Captura

- Janela-alvo: `Shinobi Story Online`.
- Saída: `960 × 540`.
- Faixa pretendida: `8–12 FPS` (10 FPS como alvo nominal).
- Quadros JPEG binários.
- Sem áudio.
- Sempre prioriza o quadro mais recente, sem criar uma fila grande intencionalmente.

### Modos de visualização

**Tela inteira** preserva a proporção e utiliza letterbox quando necessário.

**Aproximado** utiliza um recorte central fixo 16:9 com aproximadamente 2× de aproximação. Detecção de personagem e zoom livre ficam propositalmente fora da GAME V1.

### Controles

O joystick envia estados digitais das setas em oito direções. As diagonais utilizam duas setas simultaneamente. Os botões aceitam toque rápido e pressionamento contínuo, e o multitouch permite movimentar e usar os botões de ação ao mesmo tempo.

Não existe modo toggle.

## Estado de validação

O pacote-fonte 3.3.0 registrou os seguintes resultados automatizados e estáticos:

- **26 testes Python aprovados**.
- 17 testes existentes de chat, parser, histórico e migração continuaram aprovados.
- 7 testes do protocolo GAME verificaram whitelist, rejeição de teclas arbitrárias, estado multitouch, heartbeat e modos permitidos.
- 2 testes de imagem verificaram saída 960×540, letterbox sem distorção e recorte central aproximado.
- `compileall` do Python aprovado.
- Quatro arquivos ARB válidos com **178 chaves traduzíveis equivalentes**.
- **157 referências de localização** conferidas.
- Imports relativos Dart e varredura lexical de delimitadores aprovados.
- Versões do Flutter, PC Agent e instalador alinhadas em 3.3.0.

### Homologação no Windows

O ambiente onde o fonte foi produzido não possuía Windows, Flutter/Android SDK, cliente Shinobi Story Online em execução, PyInstaller Windows ou Inno Setup. Portanto, a homologação final deve validar no ambiente real:

1. Captura em janela normal, maximizada e tela cheia.
2. Jogo ausente, minimizado, fechado e reaberto.
3. Seleção correta da área útil.
4. Comportamento real em 8–12 FPS e ausência de atraso crescente.
5. Modos Tela inteira e Aproximado.
6. Quatro direções e quatro diagonais.
7. A=E, B=Espaço, C=G, D=V.
8. Tap, hold e multitouch.
9. Saída da aba, background ou desconexão durante um hold.
10. Ausência de teclas presas.
11. Chat OOC/IC funcionando durante falhas do GAME.
12. Instalação sobre versão anterior preservando configurações e histórico.

## Histórico de versões

### 3.3.0 — GAME V1

Adicionou a aba GAME isolada, stream autenticado 960×540, modos Tela inteira/Aproximado, joystick de oito direções, controles A/B/C/D, whitelist de entrada, heartbeat e proteção contra teclas presas, localização exata da janela do jogo, novas rotas GAME, empacotamento de Pillow/MSS e testes de protocolo/imagem.

### 3.2.0 — Chats OOC e IC/RP

Adicionou abas independentes OOC e IC/RP, parsing determinístico dos blocos de RP, reconstrução de mensagens multilinha/fragmentadas, estado do parser em SQLite, modelos de histórico/API/WebSocket por canal, estado independente de não lidas/rascunhos/rolagem, localização mais segura do campo IC e testes de parser/migração.

### 3.1.1

Corrigiu logging da interface em builds PyInstaller sem console e preservou o sistema próprio de logs do KageLink.

### 3.1.0

Separou os estados do agente interno e do Cloudflare Tunnel, tornou startup/retry idempotente, adicionou verificação contínua de `/api/health`, melhorou a detecção do jogo e adicionou snapshots de janelas aos logs.

### 3.0.4

Corrigiu o tratamento do executável temporário do Cloudflared e manteve validações SHA-256, cabeçalho MZ e versão.

### 3.0.3

Atualizou a validação SHA-256 do Cloudflared 2026.7.2 e adicionou verificações de executável, cabeçalho e versão.

### 3.0.2

Melhorou a inicialização do backend/túnel, tratamento automático de porta, health check interno, diagnóstico, retry/logs e empacotamento do Cloudflared.

### 3.0.1

Corrigiu a visibilidade da primeira execução e o tratamento de erros de startup, melhorou foco/centralização e tornou o encerramento/mutex mais robustos.

### 3.0.0

Introduziu o modelo final de agente único: interface Tkinter, servidor FastAPI, túnel Cloudflare gerenciado, criação automática da configuração e arquivo de conexão, mutex de instância única, logs mascarados e experiência de instalador único no Windows.

## Regra do projeto

O KageLink é um projeto funcional. Alterações devem ser pontuais e limitadas ao escopo solicitado: não refatore nem modifique funcionalidades existentes sem necessidade explícita.

## Licença

Consulte [`LICENSE`](LICENSE).