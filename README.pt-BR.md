# KageLink 3.4.1

[English](README.md) · [Bíblia de desenvolvimento](AGENTS.md) · [Development Bible](AGENTS.en.md)

O **KageLink** é um aplicativo complementar para **Shinobi Story Online**. Ele conecta o jogo executado em um computador Windows a um aplicativo Android para leitura e envio de chat, controle remoto do jogo, visualização da janela `Status | Inventory` e integração opcional com o **LeafOS/Obsidian**.

A versão oficial descrita neste documento é **KageLink 3.4.1**. O aplicativo Flutter está versionado como `3.4.1+20`.

> O KageLink depende do Shinobi Story Online aberto no computador onde o PC Agent está instalado. O aplicativo Android é uma interface remota; ele não executa o jogo sozinho.

---

## 1. Componentes

### KageLink PC Agent — Windows

O PC Agent é instalado no mesmo computador que executa o Shinobi Story Online. Ele:

- localiza a janela `Shinobi Story Online`;
- lê o chat do cliente BYOND;
- classifica mensagens em OOC e IC/RP;
- mantém histórico persistente em SQLite;
- localiza separadamente os campos de entrada OOC e IC;
- envia texto para o campo correto do jogo;
- expõe API HTTP e WebSockets autenticados;
- cria e preserva uma chave de acesso;
- oferece endereço de rede local;
- inicia, por padrão, um túnel HTTPS externo da Cloudflare;
- transmite a janela do jogo para a aba GAME;
- recebe controles GAME permitidos;
- localiza e transmite `Status | Inventory` para a aba STATS;
- permite clique esquerdo e clique direito na janela STATS;
- exporta RAW para LeafOS/Obsidian quando a integração está habilitada;
- executa o processador LeafOS em segundo plano quando configurado;
- mantém GAME, STATS, chat e LeafOS isolados para que uma falha local não derrube todo o Agent.

### KageLink Android App

O aplicativo Android oferece:

- perfis de conexão salvos;
- token armazenado em armazenamento seguro do Android;
- conexão por rede interna, túnel externo ou endereço personalizado;
- aba **OOC**;
- aba **IC / RP**;
- aba **GAME**;
- aba **STATS**;
- histórico sincronizado;
- atualizações em tempo real por WebSocket;
- reconexão automática;
- calibração independente dos campos OOC e IC;
- controles GAME configuráveis;
- dois bancos de botões: `ABCD` e `ZXVU`;
- Português do Brasil e English;
- tema Chakra Night.

---

## 2. Instalação para o usuário final

A instalação possui duas partes: **PC Agent no Windows** e **APK no Android**.

### 2.1 Instalar o PC Agent

Use o instalador da mesma versão do aplicativo:

```text
KageLink-PC-Agent-Setup-v3.4.1.exe
```

1. Feche uma instalação antiga do KageLink, caso esteja aberta.
2. Execute o Setup.
3. Escolha Português do Brasil ou English no instalador.
4. Mantenha o diretório padrão salvo em `%LocalAppData%\KageLink PC Agent`, salvo se houver uma necessidade específica de alteração.
5. O atalho na área de trabalho é opcional.
6. Conclua a instalação e marque a opção para abrir o KageLink.

Uma atualização normal foi projetada para preservar configuração, chave, histórico e dados do usuário. Na desinstalação, o instalador pergunta se esses dados também devem ser removidos.

### 2.2 Primeira execução do Agent

Na primeira execução é apresentado um assistente.

#### Idioma

Escolha:

- `Português do Brasil`; ou
- `English`.

O idioma pode ser alterado posteriormente em **Configurações**.

#### Porta

A porta padrão é:

```text
8765
```

Para a maioria dos usuários não é necessário alterar.

Se a porta configurada estiver ocupada, o Agent procura outra porta disponível e atualiza a configuração. Portanto, ao conectar o celular, sempre use o endereço atualmente mostrado pelo Agent.

#### Chave de acesso

O KageLink cria automaticamente uma chave aleatória e segura. Essa chave autentica o aplicativo Android.

Não publique essa chave e não a coloque no GitHub.

Regenerar a chave nas configurações desconecta os perfis que ainda possuem a chave antiga.

#### Conexão externa

Por padrão, o Agent inicia um **Cloudflare Quick Tunnel** HTTPS. Isso permite utilizar o KageLink fora da rede Wi-Fi local sem abrir manualmente uma porta pública no roteador.

O endereço `trycloudflare.com` é temporário e pode mudar quando o túnel é reiniciado. Se mudar, atualize o perfil externo no aplicativo.

### 2.3 Entendendo a janela do PC Agent

A janela principal mostra estados para:

- **AGENTE** — backend interno;
- **JOGO** — localização do Shinobi Story Online;
- **CHAT** — leitura do chat;
- **ENTRADA** — disponibilidade do campo de envio;
- **CONEXÃO EXTERNA** — estado do túnel.

Também mostra:

- **Endereço externo recomendado**;
- **Endereço local**;
- **Chave de acesso**.

Botões úteis:

- **Copiar endereço**;
- **Copiar chave**;
- **Copiar ambos**;
- **Abrir informações**;
- **Reiniciar conexão**;
- **Tentar novamente**;
- **Abrir logs**;
- **Configurações**;
- **Abrir pasta**;
- **Encerrar KageLink**.

As informações de conexão também são gravadas em:

```text
%LocalAppData%\KageLink PC Agent\KAGELINK_CONNECTION.txt
```

### 2.4 Instalar o APK no Android

Use:

```text
KageLink-v3.4.1.apk
```

1. Transfira o APK para o Android.
2. Abra o arquivo.
3. Caso o Android solicite autorização para instalar aplicativos dessa origem, autorize apenas a origem usada para abrir o APK.
4. Instale o KageLink.
5. Abra o aplicativo.

O APK e o PC Agent devem preferencialmente pertencer à mesma versão do KageLink.

---

## 3. Criar uma conexão no Android

Na tela inicial, crie uma rota/perfil.

### Nome

É apenas um nome para identificar a conexão, por exemplo:

```text
PC de casa
Rede local
KageLink externo
```

### Tipo de conexão

O aplicativo oferece:

- **Rede interna**;
- **Rota externa**;
- **Personalizada**.

O tipo organiza o perfil; a conexão real é determinada pelo endereço informado.

### Endereço interno

Use o endereço local exibido pelo PC Agent, por exemplo:

```text
192.168.0.25:8765
```

O celular e o computador precisam conseguir se alcançar na mesma rede.

### Endereço externo

Use o endereço HTTPS mostrado pelo Agent, por exemplo:

```text
https://exemplo.trycloudflare.com
```

Essa é a opção indicada quando o celular está fora da rede local.

### Chave de acesso

Cole exatamente a chave exibida no PC Agent.

O token é salvo no Android usando armazenamento seguro. Os demais dados do perfil são persistidos nas preferências do aplicativo.

### Perfis e favoritos

Após uma conexão bem-sucedida, o perfil pode ser reutilizado. Perfis favoritos permanecem priorizados na lista.

---

## 4. Chat OOC e IC/RP

O KageLink trata OOC e IC como canais independentes tanto na leitura quanto no envio.

### 4.1 OOC

A aba OOC recebe mensagens classificadas como OOC pelo Agent.

Ao enviar por OOC, o aplicativo utiliza o endpoint específico de OOC e o Agent procura exclusivamente o campo de entrada configurado para OOC. Se não localizar esse campo, o envio é recusado em vez de usar silenciosamente o campo IC.

### 4.2 IC / RP

A aba IC recebe duas formas de conteúdo.

#### Blocos de roleplay

Qualquer bloco iniciado por:

```text
(*
```

e encerrado pelo próximo:

```text
*)
```

é IC.

Exemplo:

```text
(*Uchiha, Leafos lowers his head.*)
```

Se o bloco chegar fragmentado em leituras diferentes do chat, o parser mantém o texto pendente até receber o fechamento.

#### Falas com `Says:`

A regra oficial é **literal e case-sensitive**.

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

Estes exemplos **não ativam** a regra de fala IC:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: Hello
```

Eles seguem o fluxo OOC, salvo se fizerem parte de um bloco `(* ... *)`.

> Esta regra é deliberadamente rígida. Não alterar para case-insensitive sem uma nova decisão explícita do projeto.

### 4.3 Envio de mensagens

A versão 3.4.1 aumenta o limite configurado do Agent para até `32000` caracteres. Antes do envio, quebras de linha são normalizadas para espaços porque o destino final é um campo de entrada do jogo.

O Agent possui endpoints distintos para envio:

```text
/api/send/ooc
/api/send/ic
```

O endpoint legado `/api/send` é mantido por compatibilidade.

### 4.4 Histórico

O histórico é persistido em:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

O aplicativo carrega o histórico ao conectar e recebe novas mensagens por WebSocket.

---

## 5. Calibração OOC / IC

O Shinobi Story Online pode expor múltiplos controles `Edit`. O KageLink não deve presumir que um único controle representa ambos os canais.

No aplicativo:

1. conecte ao Agent;
2. abra o menu;
3. escolha **Calibrar entrada / Abrir varredura de entrada**;
4. mantenha o Shinobi Story Online aberto no PC;
5. escolha separadamente um candidato para **OOC** e outro para **IC**;
6. confirme o estado dos dois canais.

O candidato `002` é a referência inicial conhecida para IC, mas a geometria completa é salva após a calibração. O HWND pode mudar quando o BYOND recria controles; por isso a identificação não depende somente do número de janela.

O mesmo HWND nunca deve ser usado simultaneamente como OOC e IC.

---

## 6. Aba GAME

A aba GAME transmite a janela do Shinobi Story Online.

Características atuais:

- captura específica da janela do jogo;
- saída JPEG;
- resolução `960 × 540`;
- qualidade JPEG padrão 70;
- alvo de aproximadamente 10 FPS;
- sem áudio;
- modo **Full**;
- modo **Zoom**;
- indicador de FPS;
- indicador aproximado de latência;
- joystick digital com oito direções;
- diagonais;
- toque, hold e multitouch;
- opção para mostrar/ocultar os controles;
- liberação automática de teclas ao sair da aba, desconectar ou perder condições seguras de controle.

Ao entrar em GAME, o app solicita foco na janela do jogo e o Agent utiliza um clique de foco quando necessário.

### 6.1 Bancos de botões

A versão 3.4.1 possui dois bancos:

```text
ABCD
ZXVU
```

Padrões:

| Botão | Tecla padrão |
| --- | --- |
| A | E |
| B | Space |
| C | G |
| D | V |
| Z | Z |
| X | X |
| V | V |
| U | U |

O banco inicial é `ABCD`. O banco ativo e os mapeamentos são persistidos no Android.

### 6.2 Configurar os botões

No aplicativo:

```text
Configurações → Controles GAME
```

É possível alterar o mapeamento e restaurar um banco ou todos os padrões.

Teclas atualmente aceitas pelo protocolo:

```text
A-Z
0-9
UP / DOWN / LEFT / RIGHT
SPACE
ENTER
ESC
TAB
SHIFT
CTRL
ALT
BACKSPACE
INSERT
DELETE
HOME
END
PAGE UP / PAGE DOWN
F1-F12
```

O Agent rejeita identificadores de tecla fora dessa whitelist. Como modificadores e teclas de função estão presentes na lista, mapeamentos devem ser configurados conscientemente.

---

## 7. Aba STATS

STATS é independente de GAME e foi criada para a janela do Shinobi Story Online:

```text
Status | Inventory
```

Classe Windows esperada:

```text
#32770
```

O Agent confirma que essa janela pertence ao mesmo processo do jogo antes de aceitá-la.

Características:

- stream JPEG independente;
- alvo de `5 FPS`;
- indicador de FPS e latência;
- botão/tentativa para abrir a janela quando ela não está disponível;
- toque simples no Android → clique esquerdo;
- toque longo → clique direito;
- coordenadas normalizadas para a área realmente exibida;
- validação do identificador da janela antes do clique.

STATS não é um controle genérico do desktop; o alvo é especificamente `Status | Inventory` pertencente ao processo do Shinobi Story Online.

---

## 8. LeafOS / Obsidian

A integração LeafOS existe oficialmente na 3.4.1, mas vem **desativada por padrão**.

### 8.1 Ativar

No PC Agent:

1. abra **Configurações**;
2. marque **Ativar integração LeafOS / Enable LeafOS integration**;
3. selecione o caminho da Vault;
4. selecione ou informe o diretório RAW;
5. escolha se deseja **Exportar IC**;
6. escolha se deseja **Exportar OOC**;
7. salve; o Agent reinicia para aplicar a configuração.

Padrão da configuração:

```text
LeafOS: desativado
Exportar IC: ativado
Exportar OOC: desativado
```

Se uma Vault for informada e o caminho RAW ficar vazio, a configuração pode derivar:

```text
<Vault>\90 - KageAgent\Raw
```

O caminho continua configurável e não é hardcoded para uma Vault pessoal específica.

### 8.2 Estrutura RAW

O exporter cria:

```text
RAW/
├── IC/
│   └── YYYY-MM-DD.md
└── OOC/
    └── YYYY-MM-DD.md
```

Cada registro é append-only e contém envelope técnico:

```html
<!-- kagelink-raw-begin {"id":7538,"timestamp":"...","channel":"ic","speaker":"**Anbu**"} -->
**Anbu** Says: test
<!-- kagelink-raw-end -->
```

O `channel` vem da mesma classificação utilizada pelo histórico e pelo aplicativo. O RAW **não reclassifica IC/OOC**.

O campo `speaker` utiliza a mesma regra literal `Says:`. Blocos `(* ... *)` podem naturalmente ter `speaker: null`.

O Obsidian não precisa estar aberto para o Agent gravar os arquivos.

### 8.3 Processador LeafOS

Quando LeafOS está habilitado, exportação IC está ativa e Vault/RAW estão configurados, o Agent pode iniciar o processador LeafOS.

Padrões atuais:

```text
intervalo do processador: 30 segundos
inatividade para encerrar sessão: 900 segundos / 15 minutos
```

O processador mantém estado para evitar reprocessar os mesmos IDs e cria estruturas de sessões/participantes dentro da Vault.

Uma falha do processador é isolada e não deve interromper chat, GAME, STATS ou túnel.

### 8.4 Privacidade

Nunca envie para o GitHub:

- RAW pessoal;
- `config.json` pessoal;
- banco de histórico;
- tokens;
- URLs temporárias privadas;
- logs contendo informações sensíveis;
- conteúdo da Vault que não seja deliberadamente público.

---

## 9. Configurações do PC Agent

A tela **Configurações** permite, conforme a versão atual:

- alterar idioma;
- alterar porta;
- gerar nova chave;
- habilitar/desabilitar LeafOS;
- configurar Vault;
- configurar RAW;
- habilitar exportação IC;
- habilitar exportação OOC.

Alterações relevantes reiniciam o KageLink para garantir que backend, túnel e módulos opcionais usem a mesma configuração.

---

## 10. Configurações do Android

No aplicativo é possível:

- trocar idioma;
- consultar a conexão atual;
- consultar o estado do Agent;
- abrir calibração OOC/IC;
- configurar controles GAME;
- trocar de perfil/rota;
- consultar a versão.

Os mapeamentos GAME são preferências do aplicativo Android. A calibração de campos OOC/IC é salva pelo PC Agent.

---

## 11. Rede e segurança

### Rede interna

Use preferencialmente o endereço local quando PC e Android estiverem na mesma rede.

### Rede externa

O Quick Tunnel fornece HTTPS e evita a necessidade de exposição manual da porta do KageLink no roteador.

### Token

Toda API sensível e os WebSockets do aplicativo utilizam a chave do KageLink.

Trate a chave como uma senha.

### Controle remoto

GAME aceita somente identificadores presentes na whitelist de teclas da versão atual. STATS aceita somente clique esquerdo/direito normalizado na janela validada `Status | Inventory`.

---

## 12. Diagnóstico

### Agent não localiza o jogo

- abra o Shinobi Story Online;
- confirme que a janela não está minimizada;
- use **Tentar novamente**;
- abra `logs\kagelink.log`.

### App não conecta

Confirme:

1. PC Agent aberto;
2. endereço correto;
3. porta correta;
4. token correto;
5. celular alcança o computador ou o túnel;
6. URL externa atual ainda é a mesma.

### OOC ou IC não envia

Abra a calibração e confirme separadamente os dois campos.

### `**Anbu** Says: test` aparece em OOC

Isso indica regressão ou build antigo. Na regra oficial atual, essa mensagem é IC. Confirme que o PC Agent executado foi compilado a partir de uma revisão que contém o fix literal `Says:`.

### RAW não é criado

Confirme:

- LeafOS habilitado;
- caminho RAW configurado;
- exportação do canal ativada;
- permissão de escrita no diretório;
- logs do Agent.

### STATS não aparece

- mantenha o jogo aberto;
- tente abrir a aba STATS novamente;
- use o botão de nova tentativa/abertura;
- verifique se `Status | Inventory` pode ser aberto no jogo;
- não mantenha a janela minimizada.

### Diagnóstico de inicialização

O repositório inclui:

```text
KageLink Installer\DIAGNOSTICAR_KAGELINK.bat
```

O script procura a instalação em `%LocalAppData%\KageLink PC Agent`, verifica `KageLink.exe` e abre `startup_error.log` quando disponível.

---

## 13. Atualizar uma instalação

Para atualizar:

1. gere ou obtenha o Setup da nova versão;
2. feche o KageLink antigo;
3. execute o novo Setup sobre a instalação existente;
4. abra o Agent;
5. confirme endereço/token/configuração;
6. atualize o APK quando a release também alterar o aplicativo Android.

Não apague `config.json` ou `chat_history.db` como procedimento normal de atualização.

---

## 14. Compilar o APK — desenvolvedores

Requisitos:

- Windows;
- Flutter no `PATH`;
- Android SDK configurado.

Na pasta:

```text
KageLink Installer
```

execute:

```bat
COMPILAR_APK.bat
```

O script:

1. valida arquivos de localização;
2. cria um workspace Android temporário;
3. copia fonte/assets/configurações;
4. executa `flutter pub get`;
5. executa `flutter gen-l10n`;
6. executa `flutter analyze`;
7. gera APK release;
8. copia o resultado.

Saída:

```text
KageLink Installer\KageLink-v3.4.1.apk
```

**O instalador Windows não gera o APK.**

---

## 15. Criar o instalador Windows — desenvolvedores

Execute:

```bat
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

O builder:

1. localiza Python 3.11 ou tenta instalá-lo via `winget`;
2. cria ambiente virtual isolado de build;
3. instala dependências e PyInstaller;
4. prepara/verifica `cloudflared`;
5. gera `KageLink.exe` com Python incorporado;
6. localiza/instala Inno Setup quando necessário;
7. compila o Setup.

Saída:

```text
KageLink Installer\installer\output\KageLink-PC-Agent-Setup-v3.4.1.exe
```

O **usuário final** não precisa instalar Python para executar o KageLink já empacotado. Python é requisito do processo de build, não do uso normal do Setup final.

---

## 16. Estrutura principal do repositório

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

---

## 17. Regras de desenvolvimento

Antes de alterar o KageLink, leia [AGENTS.md](AGENTS.md).

Princípios centrais:

- GitHub é a fonte oficial;
- não trabalhar a partir de ZIP como fonte principal;
- usar branches;
- alterações mínimas e rastreáveis;
- preservar funcionalidades não relacionadas;
- atualizar testes e documentação quando o contrato mudar;
- não afirmar que um teste passou se ele não foi realmente executado.

---

## 18. Licença

Código-fonte do KageLink copyright © 2026 Rafael Demari Dib.

É permitido usar, modificar e compilar o código-fonte para uso pessoal do proprietário. Redistribuição ou publicação comercial exige autorização do proprietário. Dependências de terceiros continuam sujeitas às respectivas licenças.
