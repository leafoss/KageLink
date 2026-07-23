# KageLink 3.3.0 — Chat + Game V1

O KageLink 3.3.0 preserva o sistema de chat validado da versão 3.2.0 e adiciona um módulo independente chamado **GAME**. A conexão, o token, o domínio e o túnel seguro continuam sendo os mesmos. A falha ou ausência do jogo não interrompe leitura, parsing, histórico nem envio de mensagens OOC/IC.

## O que foi adicionado

A tela principal agora possui três abas:

- **OOC**
- **IC / RP**
- **GAME**

Ao abrir GAME, o Android muda para paisagem e conecta dois WebSockets novos e separados:

- `/ws/game/stream`: recebe somente os quadros do jogo;
- `/ws/game/control`: envia exclusivamente o estado das teclas autorizadas.

Ao voltar para OOC ou IC/RP, o app retorna ao retrato, solta automaticamente todas as teclas e mantém mensagens, rascunhos e conexão do chat.

A referência visual aprovada está em `docs/Idea.png`.

## Captura do jogo

O PC Agent procura uma janela com o título exato:

```text
Shinobi Story Online
```

O módulo tenta selecionar o maior controle de renderização útil dentro da janela. Quando não encontra um controle interno adequado, usa a área cliente da janela como fallback. A área de trabalho completa não é transmitida.

Configuração da V1:

- saída fixa em `960 × 540`;
- objetivo de 10 FPS, dentro da faixa de 8–12 FPS;
- JPEG binário;
- sem áudio;
- quadro mais recente, sem fila intencional de imagens;
- estado claro quando o jogo está ausente ou minimizado.

### Modos de visualização

- **Tela inteira:** preserva a proporção e usa letterbox quando necessário.
- **Aproximado:** recorte central 16:9 com aproximação fixa de aproximadamente 2×. Não há detecção do personagem nesta V1.

## Controles

O joystick transparente trabalha em oito direções e envia as setas do teclado:

- cima, baixo, esquerda e direita;
- diagonais por duas setas simultâneas.

Mapeamento fixo dos botões:

| Botão | Tecla |
|---|---|
| A | E |
| B | Espaço |
| C | G |
| D | V |

Todos aceitam toque rápido e pressionamento contínuo. Não existe toggle. O protocolo envia o estado completo das teclas pressionadas, permitindo multitouch, como andar em diagonal enquanto mantém E pressionado.

## Segurança

O agente aceita somente esta whitelist:

```text
up, down, left, right, e, space, g, v
```

Comandos arbitrários, Alt+F4, tecla Windows, Ctrl+Esc, texto, mouse e macros não fazem parte do protocolo.

Todas as teclas são soltas automaticamente quando:

- a aba GAME é fechada;
- o aplicativo vai para segundo plano;
- o WebSocket fecha;
- o heartbeat expira;
- o jogo fecha ou é minimizado;
- o stream ou controle apresenta erro;
- o PC Agent é encerrado.

O controle usa `SendInput` somente após localizar e confirmar a janela do jogo e obter o foco dela. O estado interno evita key-down duplicado e key-up perdido.

## Arquitetura preservada

Os endpoints e o WebSocket anteriores continuam existentes sem mudança de contrato:

- `/api/auth`
- `/api/status`
- `/api/history`
- `/api/send`
- `/api/input-candidates`
- `/api/input-preference`
- `/ws`

O módulo GAME adiciona:

- `/api/game/status`
- `/ws/game/stream`
- `/ws/game/control`

As dependências exclusivas de captura são carregadas de forma isolada. Se não puderem iniciar, o servidor de chat continua disponível.

## Compilar o APK

Requisitos de desenvolvimento:

- Windows;
- Flutter configurado no PATH;
- Android SDK configurado.

Execute na raiz:

```text
COMPILAR_APK.bat
```

O script cria uma base Android limpa, copia os fontes, gera localizações, executa `flutter analyze` e compila:

```text
KageLink-v3.3.0.apk
```

## Criar o instalador do PC Agent

Execute:

```text
installer\CRIAR_INSTALADOR.bat
```

O processo instala ferramentas de compilação apenas no computador do desenvolvedor, empacota Python e dependências com PyInstaller e gera:

```text
installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe
```

O usuário final não precisa instalar Python, Pillow, MSS, Visual C++, pip ou bibliotecas manualmente. O instalador preserva `config.json`, token, histórico, logs e arquivos de conexão existentes.

## Homologação necessária no Windows

Este pacote passou por testes unitários e validações estáticas no ambiente de desenvolvimento disponível. A homologação real precisa ser feita em um Windows com o Shinobi Story Online aberto:

1. Abrir o jogo em janela normal, maximizada e tela cheia.
2. Confirmar que somente o conteúdo útil do jogo aparece.
3. Testar Tela inteira e Aproximado.
4. Testar todas as direções e diagonais.
5. Testar tap e hold de A/B/C/D.
6. Testar joystick e botões simultaneamente.
7. Sair da aba durante um hold e confirmar que a tecla é solta.
8. Fechar o jogo e confirmar que o chat continua funcionando.
9. Reabrir o jogo e confirmar reconexão automática.
10. Validar a latência pelo domínio externo usado no KageLink.

Consulte `RELATORIO_TESTES_3.3.0.md` para saber exatamente o que foi e não foi executado neste ambiente.
