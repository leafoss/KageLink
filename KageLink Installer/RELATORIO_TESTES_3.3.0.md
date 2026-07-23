# Relatório de testes — KageLink 3.3.0

## Resultado automatizado

Comando executado:

```text
cd pc_agent
PYTHONPATH=. python -m unittest discover -s tests -v
```

Resultado: **26 testes aprovados**.

- 17 testes anteriores de chat, parser, histórico e migração continuam aprovados.
- 7 testes do protocolo GAME validam whitelist, rejeição de teclas arbitrárias, estado multitouch, heartbeat e os dois modos permitidos.
- 2 testes de imagem validam saída 960×540, letterbox sem distorção e recorte central aproximado.

Também foram executados:

- `python -m compileall -q .`: aprovado.
- leitura JSON dos quatro ARBs: aprovado;
- igualdade das 178 chaves traduzíveis nos quatro ARBs: aprovado;
- referências `l10n.*` presentes nos ARBs: aprovado;
- imports Dart relativos: aprovado, ignorando somente o arquivo gerado pelo `flutter gen-l10n`;
- varredura lexical de parênteses, colchetes e chaves Dart: aprovado;
- alinhamento de versão Flutter 3.3.0+17, agente 3.3.0 e instalador 3.3.0: aprovado.

## Limites do ambiente

Este ambiente é Linux e não possui Flutter, Android SDK, Windows, pywin32 funcional, Shinobi Story Online, PyInstaller Windows ou Inno Setup. Portanto, não foram declarados como executados:

- `flutter analyze` real;
- compilação do APK;
- compilação do EXE/instalador;
- captura HWND real;
- envio SendInput real;
- teste por Cloudflare com vídeo;
- FPS e latência reais no Galaxy S24.

## Homologação obrigatória

No Windows, validar:

1. janela normal, maximizada e tela cheia;
2. jogo ausente, minimizado, fechado e reaberto;
3. seleção correta da área útil;
4. 8–12 FPS e ausência de atraso crescente;
5. Tela inteira e Aproximado;
6. quatro setas e quatro diagonais;
7. A=E, B=Espaço, C=G, D=V;
8. tap, hold e multitouch;
9. saída da aba, background e desconexão durante hold;
10. nenhuma tecla presa;
11. chat OOC/IC intacto durante falhas do GAME;
12. instalação sobre a versão anterior preservando token e histórico.
