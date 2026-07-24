# KageLink

[English](README.md) · [Bíblia de desenvolvimento](AGENTS.md) · [Development Bible in English](AGENTS.en.md)

O **KageLink** é um aplicativo complementar para **Shinobi Story Online**. Ele conecta o jogo executado em um computador Windows a um aplicativo Android para leitura e envio de chat OOC/IC, visualização remota da janela do jogo e controles GAME.

A branch `main` atual identifica o projeto como **KageLink 3.3.0 — GAME V1**.

> **Importante:** o KageLink não é um serviço independente. Para ler o chat, enviar mensagens ou usar GAME, o **Shinobi Story Online precisa estar em execução no computador onde o KageLink PC Agent está instalado**.

---

## 1. Componentes do KageLink

O projeto é dividido em dois produtos que trabalham em conjunto:

### KageLink PC Agent — Windows

É o programa instalado no computador onde o Shinobi Story Online está aberto. Ele é responsável por:

- localizar a janela `Shinobi Story Online`;
- ler o chat do cliente BYOND;
- separar mensagens OOC e IC/RP;
- manter o histórico persistente em SQLite;
- localizar os campos de entrada OOC e IC;
- enviar mensagens para o campo correto do jogo;
- disponibilizar API e WebSockets para o aplicativo Android;
- criar uma chave de acesso exclusiva;
- disponibilizar uma conexão pela rede local;
- iniciar, por padrão, um túnel HTTPS externo da Cloudflare;
- transmitir a imagem da janela do jogo para a aba GAME;
- receber somente os controles GAME permitidos;
- proteger contra teclas que fiquem presas após desconexões ou troca de aba.

### KageLink Android App

É a interface usada no celular. Ele fornece:

- cadastro de conexões/perfis;
- armazenamento seguro da chave de acesso do perfil;
- aba **OOC**;
- aba **IC / RP**;
- aba **GAME**;
- histórico sincronizado com o PC Agent;
- atualização em tempo real por WebSocket;
- reconexão automática em caso de interrupção;
- calibração separada dos campos OOC e IC;
- idioma Português do Brasil e English;
- visual Chakra Night;
- perfis salvos e favoritos.

---

## 2. Funcionalidades habilitadas na versão 3.3.0

### 2.1 Chat OOC

A aba **OOC** mostra somente mensagens classificadas como OOC pelo PC Agent.

O histórico é armazenado no computador e reaparece quando o aplicativo se reconecta. O aplicativo também recebe novas mensagens em tempo real.

Ao enviar uma mensagem pela aba OOC, o Agent procura especificamente o campo configurado como OOC. Se esse campo não estiver localizado, o envio é bloqueado em vez de enviar silenciosamente para o campo errado.

### 2.2 Chat IC / RP

A aba **IC / RP** é independente da aba OOC e usa seu próprio campo de envio.

Na versão atual, o parser classifica como IC:

1. blocos de roleplay iniciados por `(*` e encerrados pelo próximo `*)`;
2. linhas comuns que contenham o marcador literal e **case-sensitive** `Says:`.

Exemplos que entram em IC:

```text
(*Uchiha, Leafos nods.*)
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Exemplos que **não** ativam a regra de fala IC:

```text
**Anbu** says: test
**Anbu** SAYS: test
```

Ou seja: para a regra de fala, o marcador reconhecido é exatamente `Says:` com `S` maiúsculo.

Blocos `(* ... *)` fragmentados entre leituras são mantidos em buffer até o delimitador de fechamento chegar.

### 2.3 Histórico e atualização em tempo real

O histórico é mantido pelo PC Agent em:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

O aplicativo carrega o histórico quando conecta e recebe novas mensagens por WebSocket. O estado do parser também é persistido para reduzir perda ou duplicação de blocos IC durante reinicializações e ressincronizações.

### 2.4 Perfis de conexão

O aplicativo permite salvar múltiplos perfis. Cada perfil possui:

- nome;
- endereço;
- chave de acesso;
- tipo de conexão: interna, externa ou personalizada;
- opção de favorito;
- informação de último uso.

A chave de acesso do perfil é armazenada no Android usando armazenamento seguro, enquanto os demais dados do perfil são mantidos nas preferências do aplicativo.

### 2.5 GAME

A aba **GAME** transmite a janela do Shinobi Story Online para o Android.

Características atuais:

- imagem JPEG;
- resolução de saída de `960 × 540`;
- alvo aproximado de `8–12 FPS`;
- sem áudio;
- orientação automática para paisagem ao entrar em GAME;
- retorno para retrato ao voltar para OOC/IC;
- modo **Tela inteira / Full**;
- modo **Aproximado / Zoom** com recorte central;
- indicador de FPS;
- indicador aproximado de latência;
- opção de ocultar/mostrar controles;
- joystick digital de oito direções;
- suporte a diagonais;
- suporte a toque, hold e multitouch.

Mapeamento padrão:

| Controle no app | Entrada no PC |
| --- | --- |
| Joystick | Setas ↑ ↓ ← → |
| A | E |
| B | Espaço |
| C | G |
| D | V |

Ao entrar na aba GAME, o aplicativo solicita ao Agent um clique de foco no centro da área capturada do jogo. Isso ajuda a devolver o foco do teclado ao Shinobi Story Online depois de usar o chat.

O protocolo GAME aceita somente:

```text
up, down, left, right, e, space, g, v
```

Ele não oferece controle genérico do desktop, macros arbitrárias, execução de comandos, Alt+F4, tecla Windows ou injeção irrestrita de teclado.

### 2.6 Proteção contra teclas presas

O KageLink envia liberações de tecla ao:

- sair da aba GAME;
- colocar o aplicativo em segundo plano;
- perder a conexão de controle;
- perder a janela do jogo;
- ocorrer timeout do heartbeat;
- encerrar a sessão GAME.

Isso existe para evitar que uma seta ou botão permaneça virtualmente pressionado no Windows.

---

# 3. Instalação completa para usuário final

A instalação possui duas partes:

1. instalar o **KageLink PC Agent** no Windows;
2. instalar o **KageLink APK** no Android.

A ordem recomendada é instalar e iniciar primeiro o PC Agent. Assim, quando o aplicativo Android for aberto, o endereço e a chave de acesso já estarão disponíveis.

---

## 4. Instalar o KageLink PC Agent no Windows

O arquivo esperado do instalador é:

```text
KageLink-PC-Agent-Setup-v3.3.0.exe
```

### Passo 1 — Executar o instalador

Abra o instalador no computador onde você joga Shinobi Story Online.

O instalador:

- suporta interface em Português do Brasil e English;
- instala no perfil do usuário atual;
- não exige privilégios administrativos elevados para a instalação normal;
- instala por padrão em:

```text
%LocalAppData%\KageLink PC Agent
```

- cria uma entrada no menu KageLink;
- pode criar opcionalmente um atalho na área de trabalho;
- oferece abrir o KageLink ao terminar.

O usuário final não precisa instalar Python, pip, Pillow, MSS, PyInstaller ou Inno Setup para executar o Agent já compilado.

### Passo 2 — Primeira execução

Na primeira abertura aparece o assistente **First Run / Primeira execução**.

#### Tela 1 — Idioma

Escolha:

- `Português do Brasil`; ou
- `English`.

O idioma pode ser alterado mais tarde nas configurações do Agent.

#### Tela 2 — Porta do servidor

A porta padrão é:

```text
8765
```

Ela funciona para a maioria das instalações.

Caso a porta esteja ocupada, o KageLink pode selecionar automaticamente outra porta disponível e atualizar o endereço local mostrado na interface.

#### Tela 3 — Segurança

O Agent cria automaticamente uma chave de acesso criptograficamente aleatória.

Essa chave autentica o aplicativo Android contra o PC Agent.

**Não publique nem compartilhe essa chave.** Quem possuir o endereço ativo e a chave pode tentar autenticar no seu Agent.

#### Tela 4 — Conexão externa

Por padrão, o KageLink inicia:

- o servidor local; e
- um Cloudflare Quick Tunnel HTTPS.

O túnel permite acesso externo sem configurar redirecionamento de porta no roteador.

#### Tela 5 — Concluir

Ao concluir, o KageLink inicia o Agent e mostra os dados de conexão.

---

## 5. Entendendo a tela do PC Agent

O Agent mostra cinco estados principais:

### AGENTE

Indica se o servidor interno do KageLink está ativo.

### JOGO

Indica se a janela `Shinobi Story Online` foi localizada.

### CHAT

Indica se o controle de chat do jogo foi localizado e pode ser lido.

### ENTRADA

Indica se o campo OOC de entrada está disponível. O campo IC possui calibração independente no aplicativo.

### CONEXÃO EXTERNA

Indica o estado do túnel Cloudflare.

A tela também mostra:

### Endereço externo recomendado

Exemplo:

```text
https://example-random-name.trycloudflare.com
```

É o endereço recomendado quando o celular está fora da mesma rede do computador.

O endereço `trycloudflare.com` é criado durante a execução do túnel e pode mudar quando a conexão externa é reiniciada. Se isso acontecer, atualize o perfil no aplicativo.

### Endereço local

Exemplo:

```text
http://192.168.1.25:8765
```

Use esse endereço quando o celular e o computador estiverem na mesma rede local.

### Chave de acesso

É o token necessário para autenticar o aplicativo.

O Agent possui botões para:

- copiar o endereço;
- copiar a chave;
- copiar ambos;
- abrir o arquivo de informações;
- reiniciar a conexão externa;
- tentar novamente a inicialização;
- abrir logs;
- abrir configurações;
- abrir a pasta do KageLink;
- encerrar o Agent.

As mesmas informações são gravadas em:

```text
%LocalAppData%\KageLink PC Agent\KAGELINK_CONNECTION.txt
```

---

# 6. Instalar o APK no Android

O arquivo esperado é:

```text
KageLink-v3.3.0.apk
```

### Passo 1 — Transferir o APK

Envie o APK para o celular por USB, Drive, mensageiro, navegador ou outro método de sua preferência.

### Passo 2 — Permitir a instalação

Como o APK é instalado fora da Play Store, o Android pode solicitar autorização para **instalar aplicativos desconhecidos** a partir do aplicativo usado para abrir o arquivo.

Conceda essa autorização somente se você tiver obtido o APK de uma build confiável do projeto KageLink.

### Passo 3 — Instalar

Abra `KageLink-v3.3.0.apk` e conclua a instalação.

Em uma atualização, normalmente o novo APK pode ser instalado por cima da versão existente desde que seja compatível com a instalação anterior.

### Passo 4 — Abrir o KageLink

Na primeira tela você verá o gerenciador de rotas/perfis de conexão.

---

# 7. Conectar o aplicativo ao computador

Antes de conectar:

1. abra o Shinobi Story Online no computador;
2. abra o KageLink PC Agent;
3. espere o Agent ficar ativo;
4. copie o endereço e a chave.

No Android, crie ou edite um perfil.

### Tipo de conexão

Escolha uma das categorias:

- **Rede interna** — para um endereço local do PC;
- **Externa** — para o endereço HTTPS do Cloudflare;
- **Personalizado** — para outro endereço compatível.

A categoria organiza o perfil; o endereço informado é o que efetivamente será usado.

### Nome

Use qualquer nome que ajude a reconhecer a conexão, por exemplo:

```text
Meu PC - Casa
KageLink Externo
Notebook
```

### Endereço

Para rede local:

```text
192.168.1.25:8765
```

ou:

```text
http://192.168.1.25:8765
```

Para Cloudflare:

```text
https://example-random-name.trycloudflare.com
```

Se você omitir `http://` ou `https://`, o aplicativo acrescenta `http://` automaticamente. Para o endereço Cloudflare, prefira copiar a URL HTTPS completa mostrada pelo Agent.

### Chave de acesso

Cole exatamente a chave exibida pelo PC Agent.

### Favorito

Ative para manter esse perfil no topo da lista de rotas salvas.

### Estabelecer conexão

Ao conectar, o app:

1. autentica a chave;
2. solicita o histórico;
3. consulta o status do Agent;
4. salva/atualiza o perfil;
5. abre o WebSocket do chat;
6. passa para as telas OOC/IC/GAME.

Se a conexão cair, o app tenta reconectar automaticamente com intervalos progressivos.

---

# 8. Como usar o chat OOC e IC

A interface possui três abas:

```text
OOC | IC / RP | GAME
```

A troca é feita pelos controles de navegação. O `TabBarView` não usa swipe lateral para trocar de aba, evitando que a tela GAME deslize acidentalmente durante os controles.

## OOC

1. entre na aba OOC;
2. digite a mensagem;
3. pressione enviar;
4. o PC Agent traz a janela do jogo para frente;
5. localiza novamente o campo OOC;
6. escreve o texto;
7. clica no campo;
8. envia Enter.

## IC / RP

O fluxo é o mesmo, mas usando o campo configurado especificamente para IC.

O KageLink **não faz fallback silencioso entre os campos**. Se você estiver na aba IC e o campo IC não for localizado, a mensagem não é enviada para OOC por engano.

### Limite e intervalo padrão

A configuração padrão do Agent usa:

- máximo de `400` caracteres por envio;
- intervalo mínimo de aproximadamente `1 segundo` entre envios.

Quebras de linha são normalizadas antes do envio ao campo do jogo.

---

# 9. Calibrar os campos OOC e IC

Se o aplicativo informar que um campo de entrada não foi localizado:

1. mantenha o Shinobi Story Online aberto;
2. no app, abra o menu;
3. escolha **Calibração / Calibration**;
4. atualize a lista de candidatos se necessário;
5. identifique o controle correto;
6. use **Usar como OOC** ou **Usar como IC**.

A tela de calibração mostra informações como:

- índice do controle;
- classe `Edit`;
- largura e altura;
- visibilidade;
- estado habilitado/desabilitado;
- posição relativa;
- indicação de compatibilidade.

O OOC e o IC precisam apontar para controles diferentes. O Agent rejeita uma configuração ambígua em que os dois canais resolvam para o mesmo HWND.

A preferência é persistida no `config.json` do PC Agent.

---

# 10. Como usar a aba GAME

Antes de entrar em GAME:

- o jogo deve estar aberto;
- a janela não pode estar minimizada;
- o Agent deve estar acessível pelo aplicativo.

Ao selecionar GAME:

1. o aplicativo muda para paisagem;
2. abre um WebSocket de stream;
3. abre um WebSocket separado de controle;
4. solicita a ativação do controle;
5. solicita um clique no centro da área do jogo para devolver foco;
6. começa a mostrar os frames recebidos;
7. libera joystick e botões quando stream e controle estão ativos.

### Tela inteira / Full

Mantém a imagem inteira preservando a proporção.

### Aproximado / Zoom

Usa o modo de recorte central definido pelo GAME V1.

### Ocultar controles

O botão de visibilidade pode esconder joystick e botões para visualizar melhor o jogo. Ao ocultá-los, o app também libera os controles pressionados.

### Indicadores

A barra superior mostra:

- LIVE/OFFLINE;
- latência aproximada em ms;
- FPS recebido;
- modo de visualização;
- visibilidade dos controles.

### Quando GAME não funciona

Estados previstos incluem:

- jogo não localizado;
- jogo minimizado;
- stream indisponível;
- controle desconectado.

Uma falha de GAME não deve interromper o histórico OOC/IC, parsing, autenticação ou envio de chat.

---

# 11. Configurações

## No aplicativo Android

A tela de configurações permite:

- visualizar a rota/endereço atual;
- consultar o estado operacional do Agent;
- trocar o idioma;
- abrir a calibração de inputs;
- trocar de rota/perfil;
- consultar a versão do aplicativo.

## No PC Agent

O botão **Configurações / Settings** permite:

- alterar o idioma entre `pt-BR` e `en-US`;
- alterar a porta;
- gerar uma nova chave de acesso.

Alterar essas configurações reinicia o KageLink.

### Atenção ao gerar uma nova chave

Ao gerar uma nova chave, os perfis salvos no celular continuarão contendo a chave antiga. Você precisará atualizar a chave nesses perfis antes de reconectar.

---

# 12. Rede local ou conexão externa?

## Rede local

Use quando celular e computador estão na mesma rede.

Vantagens:

- menor latência;
- não depende do Quick Tunnel;
- ideal para GAME dentro de casa.

O endereço local usa HTTP por padrão. Portanto, trate a rede local como uma rede confiável e não exponha a porta diretamente à Internet.

## Cloudflare externo

Use quando o celular está fora da rede do computador.

O Agent inicia um Quick Tunnel e apresenta uma URL HTTPS `trycloudflare.com`.

Não é necessário abrir uma porta pública no roteador para esse fluxo padrão.

**Ainda assim, a chave de acesso continua sendo obrigatória. Não compartilhe a URL e a chave publicamente.**

---

# 13. Atualizar o KageLink

## Atualizar somente o PC Agent

Quando uma alteração afeta apenas Python/Agent, como uma regra de parser:

1. gere um novo instalador do PC Agent;
2. feche a versão em execução;
3. execute o novo Setup por cima da instalação existente;
4. abra o KageLink novamente.

Não é necessário recompilar o APK se o protocolo do aplicativo não mudou.

## Atualizar somente o Android

Quando a alteração é exclusivamente Flutter/UI:

1. gere um novo APK;
2. instale o APK atualizado no celular;
3. mantenha o Agent compatível com o protocolo esperado.

## Atualizações coordenadas

Mudanças em rotas, payloads, WebSockets ou protocolo GAME podem exigir atualização do Agent e do app juntos.

---

# 14. Desinstalação e preservação de dados

Ao desinstalar o PC Agent, o instalador pergunta se você também deseja remover:

- chave de acesso;
- configurações;
- histórico;
- logs.

Se você optar por **não remover os dados**, a pasta do usuário pode permanecer para uma reinstalação futura.

Nunca apague `config.json` ou `data/chat_history.db` como primeira tentativa de corrigir um problema sem antes fazer backup, pois isso pode remover preferências, chave e histórico.

---

# 15. Solução de problemas

## O app não conecta

Verifique:

1. `AGENTE` está como ativo?
2. endereço do perfil está correto?
3. porta está correta?
4. chave foi copiada sem espaços extras?
5. para rede local, celular e PC estão na mesma rede?
6. para conexão externa, o túnel aparece como ativo?
7. o endereço `trycloudflare.com` mudou após reiniciar o túnel?

## “Token inválido”

Copie novamente a chave mostrada no Agent. Se uma nova chave foi gerada, atualize todos os perfis que usavam a antiga.

## O jogo não é localizado

O KageLink procura a janela:

```text
Shinobi Story Online
```

Abra o jogo antes de testar novamente.

## GAME mostra jogo minimizado

Restaure a janela do Shinobi Story Online. O módulo GAME não considera uma janela minimizada um alvo válido para controle/stream normal.

## OOC funciona, mas IC não envia

Abra **Calibração** e confirme separadamente o campo IC. O Agent não usa o campo OOC como fallback para IC.

## `Says:` não aparece em IC

A regra oficial é literal:

```text
Says:
```

com `S` maiúsculo. `says:` minúsculo não é classificado por essa regra.

## Agent não inicia

A pasta de logs é:

```text
%LocalAppData%\KageLink PC Agent\logs
```

Arquivos importantes podem incluir:

```text
kagelink.log
startup_error.log
tunnel.log
```

O repositório também contém:

```text
KageLink Installer\DIAGNOSTICAR_KAGELINK.bat
```

Esse script verifica se o executável e a configuração estão presentes e abre `startup_error.log` quando disponível.

## Porta ocupada

O Agent tenta encontrar automaticamente outra porta disponível. Sempre use o endereço atualmente exibido na interface, especialmente depois de uma troca automática de porta.

---

# 16. Integração RAW / Obsidian

A Bíblia de desenvolvimento contém o contrato arquitetural desejado para uma integração RAW/Obsidian. Porém, a fonte oficial atual da versão 3.3.0 em `main` **não expõe configuração RAW/Obsidian em `AppConfig` e não deve ser anunciada como funcionalidade padrão dessa release**.

Quando essa integração fizer parte oficialmente do `main`, ela deve:

- usar a mesma classificação canônica OOC/IC;
- gravar sem exigir que o Obsidian esteja aberto;
- manter o caminho configurável;
- preservar UTF-8 e texto bruto;
- não commitar RAWs pessoais no GitHub.

---

# 17. Compilar a partir do código-fonte

O GitHub é a fonte oficial do projeto:

```text
https://github.com/leafoss/KageLink
```

Clone o repositório:

```bash
git clone https://github.com/leafoss/KageLink.git
cd KageLink
```

Antes de gerar builds, atualize sua cópia:

```bash
git checkout main
git pull
```

## 17.1 Gerar o APK Android

Requisitos de desenvolvimento:

- Windows;
- Flutter disponível no `PATH`;
- Android SDK configurado;
- acesso à Internet para baixar dependências quando necessário.

Entre em:

```text
KageLink Installer
```

Execute:

```bat
COMPILAR_APK.bat
```

O script:

1. verifica Flutter;
2. valida os quatro catálogos de localização;
3. recria um workspace Android limpo;
4. copia `lib`, assets, testes e overlays Android;
5. executa `flutter pub get`;
6. executa `flutter gen-l10n`;
7. executa `flutter analyze`;
8. gera o APK release;
9. copia o resultado para a pasta principal do projeto Flutter.

Saída esperada:

```text
KageLink Installer\KageLink-v3.3.0.apk
```

**O instalador Windows não gera o APK.** O responsável pelo APK é `COMPILAR_APK.bat`.

## 17.2 Gerar o instalador Windows

Dentro de `KageLink Installer`, execute:

```bat
installer\CRIAR_INSTALADOR.bat
```

O script de build:

1. procura uma instalação adequada do Python;
2. pode instalar Python via `winget` no ambiente de desenvolvimento quando necessário;
3. cria um ambiente `.builder_venv` isolado;
4. instala as dependências do PC Agent e PyInstaller;
5. prepara/valida o `cloudflared` incorporado;
6. gera `KageLink.exe` com Python incorporado;
7. procura ou instala Inno Setup quando possível;
8. gera o Setup final.

Saída esperada:

```text
KageLink Installer\installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe
```

O usuário que recebe o Setup final não precisa possuir o ambiente de desenvolvimento usado para criá-lo.

---

# 18. Estrutura principal do repositório

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

---

# 19. Segurança e privacidade

- Não publique `config.json` da sua instalação.
- Não compartilhe sua chave de acesso.
- Não publique `KAGELINK_CONNECTION.txt` sem remover a chave.
- Não exponha a porta local diretamente à Internet como substituto do fluxo seguro sem compreender os riscos.
- O controle GAME é limitado a uma whitelist de teclas.
- O Agent valida a janela alvo antes de controlar o jogo.
- O app mantém tokens de perfis no armazenamento seguro do Android.
- O instalador preserva dados do usuário durante atualização normal.

---

# 20. Desenvolvimento e contribuições

Antes de modificar o KageLink, leia:

- [AGENTS.md — Bíblia de Desenvolvimento](AGENTS.md)
- [AGENTS.en.md — Development Bible](AGENTS.en.md)

Regra central do projeto:

> **Não quebrar o que já funciona. Mudanças devem ser mínimas, rastreáveis, testadas e mantidas no GitHub — nunca em um ZIP paralelo como fonte principal.**

---

# 21. Licença

Código-fonte do KageLink copyright © 2026 Rafael Demari Dib.

É permitido usar, modificar e compilar o código-fonte para uso pessoal do proprietário. Redistribuição ou publicação comercial exige autorização do proprietário. Pacotes Flutter de terceiros continuam sujeitos às respectivas licenças.