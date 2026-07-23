# KageLink 3.3.0 — GAME V1

- Preservado o protocolo e o comportamento do chat OOC/IC da versão 3.2.0.
- Adicionada a terceira aba **GAME**, com paisagem automática e retorno ao retrato nas abas de chat.
- Adicionado stream autenticado e independente em JPEG 960×540, objetivo de 10 FPS e sem áudio.
- Adicionados modos **Tela inteira** e **Aproximado** com recorte central fixo.
- Adicionado joystick transparente de oito direções mapeado para as setas.
- Adicionados botões A=E, B=Espaço, C=G e D=V com tap, hold e multitouch.
- Adicionada whitelist rígida de comandos e sincronização do estado completo das teclas.
- Implementado `SendInput` com a estrutura nativa completa de 32/64 bits, incluindo setas estendidas.
- Adicionados heartbeat, soltura automática e proteção contra teclas presas.
- Adicionada localização exata da janela `Shinobi Story Online` e captura de área cliente/controle de renderização.
- Adicionados `/api/game/status`, `/ws/game/stream` e `/ws/game/control`, separados do WebSocket do chat.
- Adicionadas dependências `mss` e `Pillow` ao empacotamento PyInstaller.
- Atualizados Flutter, PC Agent, scripts e instalador para 3.3.0.
- Adicionados testes de protocolo, whitelist, multitouch lógico e transformação de imagem.

# KageLink 3.2.0 — Chats OOC e IC

- Adicionadas duas abas independentes no aplicativo Android: **OOC** e **IC / RP**.
- Implementada classificação determinística: todo bloco iniciado por `(*` e encerrado pelo próximo `*)` é IC; todo o restante é OOC.
- Mensagens IC multilinha, fragmentadas entre leituras e múltiplos blocos na mesma captura são reconstruídos sem perder formatação.
- O estado do parser e o último snapshot do chat são preservados no SQLite para continuar blocos incompletos após reinicialização.
- Ressincronizações com o histórico visível removem somente o prefixo já gravado, evitando duplicação sem descartar mensagens novas.
- Cada aba mantém rolagem, contador de não lidas e rascunho próprios.
- O canal ativo determina o destino do envio.
- O campo OOC existente foi preservado.
- O campo IC usa o índice global zero-based `002` apenas como referência inicial e passa a ser reconhecido por geometria, posição relativa, classe do pai e índice calibrado, sem fixar o HWND temporário.
- Envios são bloqueados quando o campo do canal solicitado não é localizado; não existe fallback silencioso para o outro canal.
- Adicionado `channel` ao histórico, API, WebSocket e modelos Flutter, com migração automática das bases antigas.
- Atualizados o número de versão para `3.2.0+16`, o script de APK e o projeto do instalador Windows.
- Adicionados testes automatizados para parser, fragmentação, migração, configuração e retomada após reinicialização.

# KageLink 3.1.1 — Uvicorn GUI Logging Fix

- Corrigido `sys.stdout is None` em builds PyInstaller sem console.
- Adicionados streams seguros para `stdout` e `stderr`.
- Desativada a configuração padrão de logging do Uvicorn.
- Desativadas cores ANSI do Uvicorn.
- Mantido o sistema próprio de logs do KageLink.
- Nenhuma alteração no token, API, WebSocket ou detecção BYOND.

# KageLink 3.1.0 — Agent State and Game Detection Fix

- Separados os estados do agente interno e do Cloudflare Tunnel.
- Corrigido o apagamento da mensagem de erro pelo túnel.
- Tornado o startup/retry idempotente.
- Adicionada verificação contínua de `/api/health`.
- Adicionada detecção por título normalizado e controles BYOND.
- Adicionado snapshot de janelas em `logs/kagelink.log`.
- Nenhuma alteração no protocolo móvel, token ou WebSocket.

# KageLink 3.0.4 — Temporary Executable Fix

- Temporário alterado para `cloudflared.download.exe`.
- Corrigida a validação `cloudflared --version`.
- Adicionada limpeza dos temporários antigo e novo.
- Mantidas as verificações de SHA-256, cabeçalho MZ e versão.

# KageLink 3.0.3 — Cloudflared Hash Fix

- Corrigido o SHA-256 de `cloudflared-windows-amd64.exe` 2026.7.2.
- Hash esperado atualizado para `cdb5d4432f6ae1595654a692a51308b69d2bf7af961f5578d9391837cf072df9`.
- Adicionada validação do cabeçalho executável `MZ`.
- Adicionada validação de `cloudflared --version`.
- Adicionado `cloudflared.sha256` ao instalador.
- Nenhuma alteração no token, endpoints, WebSocket ou protocolo móvel.

# KageLink 3.0.2 — Backend and Tunnel Startup Fix

- Adicionado ajuste automático quando a porta configurada está ocupada.
- Adicionado endpoint interno `/api/health`.
- Tornada explícita a inclusão do backend no PyInstaller.
- Adicionado painel de diagnóstico visível na interface.
- Adicionados os botões **Tentar novamente** e **Abrir logs**.
- Corrigido o estado do túnel após falha do servidor.
- `cloudflared.exe` agora é incluído no instalador final.
- Preservados token, endpoints móveis, WebSocket e design do aplicativo.

# KageLink 3.0.1 — Startup Visibility Fix

- Corrigido o assistente de primeira execução invisível no Windows.
- Removida a dependência `transient` de uma janela principal oculta.
- Adicionado posicionamento central, `lift` e foco temporário.
- Adicionado `logs/startup_error.log` para falhas anteriores à interface.
- Adicionada caixa de erro nativa do Windows em falhas fatais.
- Garantida a liberação do mutex em encerramentos e exceções.
- Ajustada a execução pós-instalação para o usuário original.
- Nenhuma alteração nos endpoints, token, WebSocket ou protocolo do aplicativo.

# KageLink 3.0.0 — Final Single-Agent Model

- Preservado o design Chakra Night e toda a arquitetura do aplicativo.
- Alterada somente a regra de habilitação do composer: depende da conexão, não do foco do jogo.
- Adicionadas mensagens localizadas para jogo ausente e falha ao obter foco.
- Criada `ensure_game_window_foreground()` com restauração, `SetForegroundWindow`, pulso ALT e `AttachThreadInput` controlado.
- O campo `Edit` é localizado novamente depois que a janela é restaurada.
- Mantidos `WM_SETTEXT`, clique físico e Enter físico.
- Criado agente único com interface Tkinter, servidor FastAPI e túnel Cloudflare gerenciados pelo mesmo processo.
- `config.json` e chave segura são criados automaticamente na primeira execução.
- O endereço externo e a chave são gravados em `KAGELINK_CONNECTION.txt`.
- Implementada instância única por mutex.
- Logs organizados e com mascaramento de tokens.
- Instalador final contém somente `KageLink.exe` e cria apenas um atalho principal.
- Removidos patches, agentes duplicados, BATs de uso final e ambiente Python instalado.
