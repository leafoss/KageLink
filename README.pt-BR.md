# KageLink 3.5.0

[English](README.md) · [Downloads](DOWNLOAD.md) · [Bíblia de desenvolvimento](AGENTS.md) · [Kage Pilot](KAGE_PILOT.md)

## Download

| Windows | Android |
| --- | --- |
| **[Baixar KageLink para Windows](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Windows-Setup.exe)** | **[Baixar KageLink para Android](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Android.apk)** |

[Ver Release e SHA-256](https://github.com/leafoss/KageLink/releases/latest) · [Guia rápido](DOWNLOAD.md)

O **KageLink** conecta o **Shinobi Story Online** executado no Windows a uma interface Desktop e a um aplicativo Android. A versão 3.5.0 inclui chat OOC/IC, GAME, STATUS, integração opcional LeafOS e o **Dojo Trainer** instalado.

```text
KageLink: 3.5.0
Flutter/Android: 3.5.0+23
```

> O Android é uma interface remota. Captura, visão, decisões e comandos de teclado executam somente no PC Agent.

## Componentes

### Windows

O Setup instala:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

- `KageLink.exe`: Desktop, Agent, API, chat, GAME, STATUS e integração LeafOS.
- `KagePilotDojo.exe`: loop isolado de treinamento.
- `KagePilotRound.exe`: execução isolada de uma rodada.

O usuário final não precisa instalar Python.

### Android

O aplicativo oferece:

- perfis de conexão;
- token em armazenamento seguro;
- OOC e IC/RP;
- GAME remoto;
- STATUS remoto;
- controle e telemetria do Dojo;
- reconexão;
- PT-BR e EN-US.

## Instalação rápida

### Windows

1. Baixe `KageLink-Windows-Setup.exe`.
2. Feche qualquer versão antiga aberta.
3. Execute o Setup.
4. Escolha PT-BR ou EN-US.
5. Abra o KageLink e copie o endereço e a chave exibidos.

A porta padrão é `8765`. O KageLink cria uma chave segura e, por padrão, uma rota HTTPS temporária da Cloudflare.

Atualizações normais preservam configuração, histórico, chave e templates do Dojo.

### Android

1. Baixe `KageLink-Android.apk`.
2. Instale o APK.
3. Crie um perfil usando o endereço e a chave mostrados no Windows.
4. Use rede local quando o celular estiver na mesma rede ou a URL HTTPS quando estiver fora dela.

## Chat OOC e IC/RP

OOC e IC são canais diferentes na leitura e no envio.

```text
/api/send/ooc
/api/send/ic
```

O Agent nunca deve usar silenciosamente o outro campo como fallback.

### Regra IC protegida

Todo bloco `(* ... *)` é IC/RP.

O marcador de fala é literal e case-sensitive:

```text
Says:
```

```text
**Anbu** Says: test     → IC
**Anbu** says: test     → não ativa a regra
```

## GAME

A área GAME transmite a janela específica do jogo e aceita apenas teclas validadas.

- captura JPEG `960 × 540`;
- aproximadamente 10 FPS;
- modos Full e Zoom;
- joystick e bancos `ABCD` / `ZXVU`;
- heartbeat e proteção contra teclas presas;
- liberação ao desconectar, trocar de tela ou perder condições seguras.

GAME não executa programas, scripts, URLs ou comandos de sistema.

## STATUS

Alvo esperado:

```text
Título: Status | Inventory
Classe: #32770
```

O Agent valida que a janela pertence ao mesmo processo do jogo antes de transmitir ou clicar. Toque simples envia clique esquerdo; toque longo envia clique direito.

## Dojo Trainer

O Dojo Trainer executa no Windows e pode ser controlado pelo Desktop ou Android.

```text
Desktop/APK
→ API autenticada
→ KageLink.exe
→ KagePilotDojo.exe
→ KagePilotRound.exe
→ Shinobi Story Online
```

### Templates do Trainer

O usuário cadastra imagens independentes para os modos 32×32 e 64×64:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates\
```

O treino instalado não começa sem pelo menos um template válido. Os templates são preservados em atualizações normais.

### Segurança

- exatamente um clique no Trainer por rodada;
- retries de diálogo nunca repetem o clique;
- F12 é parada de emergência;
- HP mínimo de recuperação: 90%;
- Chakra mínimo de recuperação: 50%;
- controles GAME manuais são bloqueados durante o treino;
- toda saída libera inputs.

Detalhes: [KAGE_PILOT.md](KAGE_PILOT.md) e [AGENTS_DOJO.md](AGENTS_DOJO.md).

## LeafOS / Obsidian

A integração LeafOS é opcional e desativada por padrão.

```text
histórico classificado
→ RAW append-only
→ Processor
→ sessão
→ Interpreter
→ Memory Reviewer
→ aprovação humana
→ Canonical Memory
```

Uma falha de LeafOS não deve interromper chat, GAME, STATUS, túnel ou Dojo.

Nunca publique RAW pessoal, Vault privada, banco de histórico, tokens, URLs temporárias ou configuração pessoal.

## Rede e segurança

- use o endereço local quando PC e celular estiverem na mesma rede;
- use a rota HTTPS para acesso externo;
- trate a chave como senha;
- não publique tokens ou URLs privadas;
- os endpoints e WebSockets sensíveis exigem Bearer Token.

## Diagnóstico

### Jogo não localizado

- abra o Shinobi Story Online;
- restaure a janela se estiver minimizada;
- use a tentativa novamente;
- consulte `logs\kagelink.log`.

### OOC ou IC não envia

Abra a calibração e selecione separadamente os dois controles.

### Dojo não inicia

Confirme:

- runtime instalado;
- pelo menos um template 32×32 ou 64×64 válido;
- jogo aberto e visível;
- nenhum treinamento já ativo;
- logs e último código exibido na tela Dojo.

## Desenvolvedores

Leia [AGENTS.md](AGENTS.md) antes de alterar o projeto.

### Testes Python

```powershell
cd "KageLink Installer\pc_agent"
python -m unittest discover -s tests -v
python -m compileall .
```

### Kage Pilot

```powershell
python kage_pilot.py dojo --show-config
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
```

### Flutter

```powershell
cd "KageLink Installer"
flutter pub get
flutter gen-l10n
flutter analyze
flutter test
```

### Build Windows

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

### Build Android

```text
KageLink Installer\COMPILAR_APK.bat
```

## Documentação canônica

- [Bíblia do KageLink](AGENTS.md)
- [Dojo — regras normativas](AGENTS_DOJO.md)
- [Kage Pilot](KAGE_PILOT.md)
- [Interpreter](AGENTS_INTERPRETER.md)
- [Memory Reviewer](LEAFOS_MEMORY_REVIEWER.md)
- [Desktop](LEAFOS_DESKTOP.md)
- [Downloads](DOWNLOAD.md)

## Licença

Código-fonte copyright © 2026 Rafael Demari Dib. Uso, modificação e compilação pessoal são permitidos ao proprietário. Redistribuição ou publicação comercial exige autorização. Dependências de terceiros mantêm suas próprias licenças.
