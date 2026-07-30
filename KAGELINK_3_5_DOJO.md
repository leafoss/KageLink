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

A navegação canônica do KageLink é:

```text
Visão geral
Memória
Conexão
Dojo Trainer
Configurações
```

`Configurações` deve permanecer sempre como último item. Novas páginas entram antes dela.

A página **Dojo Trainer** contém:

- número de rodadas, incluindo `0` para execução contínua;
- estado do runtime instalado;
- fase atual;
- rodada atual e total concluído;
- último evento ou erro;
- upload independente de template para modo 32×32;
- upload independente de template para modo 64×64;
- pré-visualização e remoção de cada template;
- iniciar treino;
- parar com segurança;
- aviso permanente sobre F12.

## Templates do Trainer

O KageLink 3.5.0 não usa uma imagem empacotada como autoridade principal. O usuário fornece o recorte que funciona na sua instalação e seleciona a qual modo do jogo ele pertence.

Persistência canônica:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates\
├── dojo_trainer_32.png
├── dojo_trainer_64.png
└── templates.json
```

Características:

- aceita PNG, JPEG, WebP e BMP na UI;
- valida e normaliza o arquivo para PNG;
- preserva os templates em atualização normal;
- carrega os dois modos simultaneamente quando ambos existem;
- escolhe o candidato visual aceito com maior score;
- rejeita ambiguidade forte entre modos;
- não inicia o runtime instalado sem ao menos um template válido;
- mantém a calibração antiga do código-fonte apenas para diagnóstico local por Python.

## Android

Depois de conectar ao PC Agent, o aplicativo oferece duas áreas principais:

```text
KageLink — OOC, IC/RP, GAME e STATUS
Dojo — controle e telemetria do treinamento
```

A tela Dojo consulta o estado periodicamente e permite iniciar ou parar o motor usando o token já salvo no Android. A calibração visual pertence ao PC Desktop, que possui acesso ao arquivo local e à captura do jogo.

## Segurança de comandos concorrentes

Enquanto o treino está ativo, o PC Agent rejeita:

- ativação manual dos controles GAME;
- envio manual das teclas GAME;
- clique remoto no centro do jogo;
- substituição ou remoção de templates pelo Desktop.

Chat e STATUS permanecem disponíveis. O bloqueio é autoritativo no Windows, portanto não depende apenas de um botão desabilitado na UI.

## Processo isolado e instalação

O `DojoTrainingService` preserva o isolamento validado:

- no repositório, usa os scripts Python existentes;
- no programa congelado, usa `KagePilotDojo.exe`;
- o loop de Dojo usa `KagePilotRound.exe` por rodada;
- nenhum Python externo é exigido do usuário final;
- os helpers leem os templates do perfil do usuário, fora do executável.

## API 3.5.0

### Consultar estado

```http
GET /api/dojo/status
Authorization: Bearer <token>
```

### Consultar templates

```http
GET /api/dojo/templates
Authorization: Bearer <token>
```

### Enviar template

```http
POST /api/dojo/templates/64
Authorization: Bearer <token>
Content-Type: application/json

{
  "filename": "trainer.png",
  "image_base64": "..."
}
```

O mesmo contrato aceita `/32`.

### Remover template

```http
DELETE /api/dojo/templates/32
Authorization: Bearer <token>
```

### Iniciar

```http
POST /api/dojo/start
Authorization: Bearer <token>
Content-Type: application/json

{"rounds": 10}
```

Sem template válido, retorna falha fechada com `DOJO_TRAINER_TEMPLATE_REQUIRED`.

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

O Setup contém os helpers internamente; o usuário não precisa baixá-los separadamente. Os templates não precisam ser empacotados.

## Gate antes do merge

- CI Python e Kage Pilot;
- três executáveis Windows;
- smoke dos helpers;
- Setup 3.5.0;
- Settings como último item do menu;
- upload e persistência dos templates 32×32 e 64×64;
- detecção real em modo 32×32;
- detecção real em modo 64×64;
- Flutter localization/analyze/test;
- APK release;
- teste real do Setup instalado;
- teste real Desktop → Dojo;
- teste real APK → Dojo;
- F12 e bloqueio GAME;
- aprovação explícita de Rafael.

Enquanto os testes físicos finais não forem concluídos, o PR permanece draft e não deve ser mesclado.
