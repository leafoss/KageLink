# KageLink 3.5.0 — Dojo Trainer utilizável

[English](KAGELINK_3_5_DOJO.en.md) · [Bíblia normativa](AGENTS_DOJO.md)

## Objetivo

A versão 3.5.0 transforma o Kage Pilot v0.3j validado no repositório em uma funcionalidade realmente distribuída:

```text
Setup Windows
├── KageLink.exe
├── KagePilotDojo.exe
└── KagePilotRound.exe

Desktop ou APK
        ↓ API autenticada
DojoTrainingService no PC
        ↓
Shinobi Story Online
```

O APK não contém nem executa o motor de visão. Ele controla remotamente o mesmo serviço que existe no Desktop.

## Desktop

A navegação do KageLink passa a incluir **Dojo Trainer** com:

- número de rodadas, incluindo `0` para execução contínua;
- estado do runtime instalado;
- fase atual;
- rodada atual e total concluído;
- último evento ou erro;
- iniciar treino;
- parar com segurança;
- aviso permanente sobre F12.

## Android

Depois de conectar ao PC Agent, o aplicativo oferece duas áreas principais:

```text
KageLink — OOC, IC/RP, GAME e STATUS
Dojo — controle e telemetria do treinamento
```

A tela Dojo consulta o estado periodicamente e permite iniciar ou parar o motor usando o token já salvo no Android.

## Segurança de comandos concorrentes

Enquanto o treino está ativo, o PC Agent rejeita:

- ativação manual dos controles GAME;
- envio manual das teclas GAME;
- clique remoto no centro do jogo.

Chat e STATUS permanecem disponíveis. O bloqueio é autoritativo no Windows, portanto não depende apenas de um botão desabilitado na UI.

## Processo isolado e instalação

O `DojoTrainingService` preserva o isolamento validado:

- no repositório, usa os scripts Python existentes;
- no programa congelado, usa `KagePilotDojo.exe`;
- o loop de Dojo usa `KagePilotRound.exe` por rodada;
- nenhum Python externo é exigido do usuário final.

## API 3.5.0

### Consultar

```http
GET /api/dojo/status
Authorization: Bearer <token>
```

### Iniciar

```http
POST /api/dojo/start
Authorization: Bearer <token>
Content-Type: application/json

{"rounds": 10}
```

### Parar

```http
POST /api/dojo/stop
Authorization: Bearer <token>
```

Os thresholds mínimos continuam protegidos em 90% de HP e 50% de Chakra.

## Distribuição

A Release 3.5.0 continuará usando os links estáveis:

```text
releases/latest/download/KageLink-Windows-Setup.exe
releases/latest/download/KageLink-Android.apk
releases/latest/download/SHA256SUMS.txt
```

O Setup contém os helpers internamente; o usuário não precisa baixá-los separadamente.

## Gate antes do merge

- CI Python e Kage Pilot;
- três executáveis Windows;
- smoke dos helpers;
- Setup 3.5.0;
- Flutter localization/analyze/test;
- APK release;
- teste real do Setup instalado;
- teste real Desktop → Dojo;
- teste real APK → Dojo;
- F12 e bloqueio GAME;
- aprovação explícita de Rafael.

Enquanto os testes físicos finais não forem concluídos, o PR permanece draft e não deve ser mesclado.
