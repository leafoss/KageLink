# KageLink

[English](README.md)

O KageLink é um aplicativo complementar para **Shinobi Story Online** que conecta o cliente do jogo no Windows a uma interface Android para chat, visualização do jogo e controles remotos.

A branch `main` atual identifica o projeto como **3.3.0 — GAME V1**.

## Recursos

- **Chat OOC** com histórico persistente.
- **Chat IC / RP** com histórico, rascunhos e parsing determinístico de RP independentes.
- **Aba GAME** com stream JPEG autenticado em 960×540, alvo de 8–12 FPS e sem áudio.
- **Joystick de oito direções** mapeado para as setas do teclado.
- **Botões de ação:** A = E, B = Espaço, C = G, D = V.
- Suporte a toque, hold, diagonais e multitouch.
- Conexão pela rede interna e acesso externo opcional via Cloudflare Tunnel.
- Token de autenticação compartilhado entre aplicativo e PC Agent.
- Proteções para soltar teclas automaticamente e evitar controles presos.

## Arquitetura

O KageLink é dividido em dois componentes principais:

- **Aplicativo Android (Flutter):** interface móvel para OOC, IC/RP e GAME.
- **PC Agent para Windows (Python):** lê o cliente do Shinobi Story Online, administra histórico e entradas, disponibiliza API/WebSockets e gerencia a conexão opcional pelo Cloudflare.

O módulo GAME é isolado do chat. Uma falha de captura ou controle do GAME não deve interromper histórico OOC/IC, parsing, autenticação ou envio de mensagens.

## Protocolo GAME

Principais rotas do GAME:

```text
/api/game/status
/ws/game/stream
/ws/game/control
```

O protocolo de controle aceita somente as teclas previstas para o jogo. Ele não oferece controle arbitrário da área de trabalho, execução de comandos, macros ou injeção irrestrita de teclado.

## Compilar o aplicativo Android

Requisitos na máquina de desenvolvimento:

- Windows
- Flutter disponível no `PATH`
- Android SDK configurado

Dentro de `KageLink Installer/`, execute:

```bat
COMPILAR_APK.bat
```

Saída esperada:

```text
KageLink-v3.3.0.apk
```

## Criar o instalador do PC Agent

Dentro de `KageLink Installer/`, execute:

```bat
installer\CRIAR_INSTALADOR.bat
```

Saída esperada:

```text
installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe
```

O usuário final do Windows não precisa instalar manualmente Python, pip, Pillow, MSS ou as ferramentas de desenvolvimento.

## Estrutura do repositório

```text
KageLink/
├── README.md
├── README.pt-BR.md
└── KageLink Installer/
    ├── android_overlay/
    ├── assets/
    ├── installer/
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── COMPILAR_APK.bat
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

`pc_agent/requirements.txt` é um arquivo funcional de dependências usado no build do Windows e por isso permanece no repositório.

## Uso e licença

Código-fonte do KageLink copyright © 2026 Rafael Demari Dib.

É permitido usar, modificar e compilar o código-fonte para uso pessoal do proprietário. Redistribuição ou publicação comercial exige autorização do proprietário. Pacotes Flutter de terceiros continuam sujeitos às respectivas licenças.
