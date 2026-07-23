# Validação e inventário — KageLink 3.3.0

A versão 3.3.0 foi construída diretamente sobre o ZIP funcional KageLink 3.2.0 recebido. Os módulos existentes de chat, parsing, histórico, autenticação, envio OOC/IC e calibração foram preservados. A nova função GAME foi adicionada por arquivos e rotas separados.

## Inventário funcional

### Chat preservado

- API e WebSocket antigos mantidos;
- parser OOC/IC mantido;
- SQLite e migrações mantidos;
- calibração OOC/IC mantida;
- perfil, token e Cloudflare mantidos.

### GAME adicionado

- janela exata `Shinobi Story Online`;
- captura específica por PrintWindow, com fallback MSS somente após foco confirmado;
- saída JPEG 960×540 a 10 FPS alvo;
- Tela inteira e Aproximado;
- joystick de oito direções;
- A=E, B=Espaço, C=G, D=V;
- whitelist rígida;
- heartbeat e soltura automática;
- landscape somente na aba GAME.

## Arquivos de referência

- `docs/Idea.png`
- `ARQUIVOS_MODIFICADOS_3.3.0.md`
- `INSTRUCOES_ATUALIZACAO_3.3.0.md`
- `RELATORIO_TESTES_3.3.0.md`
- `HASHES_ARQUIVOS_PRESERVADOS.txt`

## Limitação declarada

O ambiente utilizado para produzir o fonte não possui Windows, Flutter/Android SDK ou a janela real do jogo. Os binários não são incluídos como se tivessem sido compilados. A homologação prática deve seguir o checklist do relatório de testes.
