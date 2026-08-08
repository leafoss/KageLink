# KageLink Remote Control v0.3.1 — Security & Session Hardening

[English](README.md)

> Protótipo isolado. Esta pasta não altera o runtime oficial do KageLink sem uma decisão explícita de integração.

A v0.3.1 reorganiza o controle remoto em torno de **consentimento local, sessão temporária e separação entre visualização e controle**. O objetivo desta revisão não é adicionar mais superfície remota, e sim tornar a base WebRTC mais segura, previsível e testável antes das otimizações de vídeo da v0.3.2.

## O que mudou

### Pareamento sem chave permanente

O navegador remoto não recebe uma senha fixa do Host.

Fluxo:

```text
Navegador remoto
    ↓
solicita pareamento por 90 s
    ↓
Admin LOCAL no PC Host
    ↓
[Aprovar controle] / [Aprovar visualização] / [Negar]
    ↓
token de sessão temporário, em memória e vinculado ao IP
    ↓
peer-grant single-use de 30 s
    ↓
WebRTC
```

O token de sessão:

- não é salvo em `localStorage`;
- não é gravado em arquivo;
- expira após 30 minutos de inatividade por padrão;
- possui limite absoluto de 8 horas por padrão;
- é vinculado ao IP que solicitou o pareamento;
- é revogado quando o Host desconecta a sessão ou usa a parada de emergência.

### Um único controlador

A v0.3.1 permite no máximo **uma sessão `control` ativa por vez**. Sessões adicionais podem ser aprovadas como `view`.

### Painel Admin separado e local

O painel administrativo usa outro servidor:

```text
http://127.0.0.1:8766
```

Ele nunca escuta em `0.0.0.0`. O token administrativo é gerado em memória a cada execução, é entregue no fragmento `#...` do endereço local e não é enviado ao servidor como parte da URL.

No painel é possível:

- aprovar/neg ar solicitações;
- escolher `CONTROL` ou `VIEW`;
- ver sessões ativas;
- desconectar uma sessão;
- ver estado da captura;
- desligar imediatamente todo input remoto;
- reabilitar o input localmente quando o launcher permitir controle.

### Parada de emergência local

No PC controlado:

```text
CTRL + ALT + F12
```

faz imediatamente:

```text
bloqueia input remoto
→ libera teclas/botões pressionados
→ revoga todas as sessões
→ fecha peers WebRTC ativos
```

O controle só pode voltar por ação local no painel Admin.

### Game Mode é o padrão

`GAME MODE` usa os módulos canônicos do PC Agent para localizar exatamente:

```text
Shinobi Story Online
```

O input exige que a janela exista, não esteja minimizada e esteja em foco. A captura reaproveita `pc_agent.game_capture.GameCapture`, mantendo a regra existente de capturar o alvo do jogo em vez de capturar aplicativos pessoais por acidente.

### Desktop Mode exige autorização explícita

O Host só aceita controle de desktop quando é iniciado simultaneamente com:

```text
--mode desktop --allow-control --allow-desktop-control
```

Essa combinação é intencionalmente usada apenas pelo launcher dedicado `START_REMOTE_DESKTOP_EXTERNAL.bat`.

### Cloudflare com exposição reduzida

No launcher externo, o servidor público fica em:

```text
127.0.0.1:8765
```

e o `cloudflared` cria o HTTPS externo para esse endereço. Não é necessário abrir uma porta pública no roteador.

`CF-Connecting-IP` só é confiado quando `--trust-cloudflare-proxy` está ativo **e** o servidor está preso a loopback.

O protótipo não baixa executáveis silenciosamente. Para Quick Tunnel ele procura um `cloudflared.exe` já preparado/verificado pelo fluxo oficial do KageLink ou disponível no `PATH`.

### TURN opcional

STUN é usado por padrão. Redes/NATs que não permitem conexão direta podem configurar TURN:

```text
KAGELINK_TURN_URL
KAGELINK_TURN_USERNAME
KAGELINK_TURN_CREDENTIAL
```

As credenciais TURN só são entregues depois de uma sessão autenticada solicitar um peer-grant.

### Watchdog de input

Se o DataChannel de uma sessão de controle ficar sem heartbeat por 5 segundos, o Host libera todas as teclas e botões. Após 15 segundos sem heartbeat, o peer é fechado.

### Frame queue = 1

`FrameHub` mantém apenas o frame mais recente. Se o consumidor estiver atrasado, frames antigos são descartados em vez de formar uma fila crescente de latência.

Isso prepara a v0.3.2 para captura/encode de baixa latência.

### Diagnóstico

Cliente:

- RTT;
- FPS recebido;
- bitrate recebido;
- packet loss.

Host:

- FPS de captura;
- tempo de captura;
- idade do frame;
- estado da captura.

### Mobile preservado

A v0.3.1 preserva as correções validadas nas hotfixes móveis:

- teclado nativo;
- texto Unicode;
- `autocapitalize="none"`;
- IME/composição ao vivo;
- reconciliação de alteração do sufixo durante autocorreção;
- Ctrl/Alt/Shift aderentes;
- Esc/Tab/Enter/Backspace/Delete/setas;
- toque = clique esquerdo;
- toque longo = clique direito;
- arraste = ponteiro;
- pinch/pan;
- zoom 100–400%;
- botão **Soltar**.

## O que deliberadamente NÃO existe

Esta revisão não implementa:

- shell remoto;
- PowerShell remoto;
- execução arbitrária de comandos;
- upload/download de arquivos;
- clipboard remoto;
- captura de credenciais;
- keylogging;
- gravação do texto digitado;
- áudio;
- inicialização oculta;
- persistência silenciosa;
- desativação de antivírus;
- controle do UAC Secure Desktop;
- Windows Service oculto.

O audit log registra **eventos de sessão**, nunca o conteúdo das teclas/textos.

## Instalação do protótipo

No PC Host:

1. Abra esta pasta.
2. Execute:

```text
SETUP.bat
```

3. Para o uso normal externo do jogo, execute:

```text
START_REMOTE_EXTERNAL.bat
```

4. O navegador do PC Host abrirá o painel Admin local.
5. No outro computador/celular, abra o endereço `https://....trycloudflare.com` mostrado pelo Host.
6. Clique/toque em **Solicitar conexão**.
7. No PC Host, aprove a solicitação como **Controle** ou **Visualização**.

O computador/celular cliente precisa somente de um navegador moderno.

## Launchers

### `START_REMOTE_EXTERNAL.bat`

Uso recomendado. `GAME MODE`, controle permitido após aprovação local, Cloudflare Quick Tunnel e servidor preso a loopback.

### `START_REMOTE_LOCAL_ONLY.bat`

Rede local somente, sem Cloudflare. O cliente usa:

```text
http://IP_DO_PC_HOST:8765
```

Pode ser necessário liberar a porta 8765 no Firewall do Windows **somente para rede privada**.

### `START_REMOTE_EXTERNAL_ADMIN.bat`

Executa o Host do `GAME MODE` elevado após um prompt UAC **local**. Útil somente quando o próprio jogo está elevado. O prompt UAC/Secure Desktop continua fora do alcance remoto.

### `START_REMOTE_DESKTOP_EXTERNAL.bat`

Autoriza explicitamente captura e controle do desktop selecionado. Não é o modo padrão.

## Testes

Localmente:

```text
RUN_TESTS.bat
```

O CI `Remote Control Prototype` verifica:

- sintaxe Python;
- autoridade de sessão;
- nonce de pareamento;
- token entregue uma única vez;
- sessão vinculada ao IP;
- somente um controlador;
- coexistência de `view`;
- peer-grant single-use;
- expiração;
- revogação total;
- rate limiting;
- ausência de segredos no hook de auditoria;
- sintaxe JavaScript;
- carregamento da camada de IME móvel.

## Limitações conhecidas da v0.3.1

- NVENC ainda **não** está integrado. Essa é a etapa planejada para v0.3.2.
- O pipeline de Game Mode ainda reaproveita a captura canônica JPEG do PC Agent antes de entregar o frame ao WebRTC; a fila de latência já foi eliminada, mas o caminho de captura/encode ainda pode melhorar muito.
- Quick Tunnel é apropriado para protótipo/beta; Named Tunnel fica para uma etapa posterior.
- TURN precisa ser fornecido pelo operador quando necessário.
- O comportamento Win32, BYOND, UAC, mobile e NAT precisa de validação física antes de merge.

## Próxima etapa planejada

```text
v0.3.2 — Low Latency Capture
```

Escopo pretendido:

- Windows Graphics Capture quando compatível;
- caminho de frame sem JPEG intermediário;
- H.264/NVENC na RTX 3060 quando suportado pelo stack escolhido;
- adaptação de bitrate/resolução;
- medição de capture → encode → network;
- manter `latest-frame only`.
