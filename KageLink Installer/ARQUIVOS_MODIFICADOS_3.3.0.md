# Arquivos alterados — KageLink 3.3.0

## Flutter

- `lib/main.dart`: orientação inicial em retrato.
- `lib/screens/chat_screen.dart`: terceira aba, troca de orientação e navegação compacta em GAME.
- `lib/screens/game_screen.dart`: stream, status e overlay final.
- `lib/services/game_connection.dart`: WebSockets independentes, heartbeat, FPS, latência e sincronização de teclas.
- `lib/widgets/game_joystick.dart`: joystick de oito direções.
- `lib/widgets/game_action_button.dart`: botões multitouch tap/hold.
- `lib/l10n/*.arb`: textos GAME em quatro catálogos equivalentes.
- `pubspec.yaml`: versão 3.3.0+17.

## PC Agent

- `pc_agent/app.py`: novos endpoints e WebSockets isolados.
- `pc_agent/pc_agent/game_protocol.py`: whitelist e validação do protocolo.
- `pc_agent/pc_agent/game_window.py`: localização exata e área de captura.
- `pc_agent/pc_agent/game_image.py`: Tela inteira e Aproximado.
- `pc_agent/pc_agent/game_capture.py`: captura específica por PrintWindow, fallback MSS com foco confirmado e JPEG 960×540.
- `pc_agent/pc_agent/game_control.py`: SendInput, foco e estado das teclas.
- `pc_agent/pc_agent/game_runtime.py`: fachada isolada e carregamento seguro.
- `pc_agent/requirements.txt`: MSS e Pillow.
- `pc_agent/tests/test_game_protocol.py`: protocolo e segurança.
- `pc_agent/tests/test_game_image.py`: transformação e recorte.

## Build e documentação

- `COMPILAR_APK.bat`
- `installer/CRIAR_INSTALADOR.bat`
- `installer/KageLink.spec`
- `installer/KageLink_PC_Agent.iss`
- `README_pt-BR.md`
- `README_en-US.md`
- `CHANGELOG.md`
- `docs/Idea.png`
- `INSTRUCOES_ATUALIZACAO_3.3.0.md`
- `RELATORIO_TESTES_3.3.0.md`
- `VALIDACAO_AUTOMATICA_3.3.0.txt`
- `ENTREGA_3.3.0.txt`
- `docs/ESPECIFICACAO_GAME_V1.txt`
