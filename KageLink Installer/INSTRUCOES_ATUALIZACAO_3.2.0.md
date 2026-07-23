# Instruções de atualização — KageLink 3.2.0

## 1. Gerar o APK Android

No computador Windows que já possui Flutter configurado:

1. Extraia o ZIP completo em uma pasta sem restrições de escrita.
2. Execute `COMPILAR_APK.bat`.
3. Aguarde as etapas de dependências, localização, análise e build release.
4. O resultado será criado na raiz como `KageLink-v3.2.0.apk`.
5. Instale o APK sobre o aplicativo anterior. Os perfis salvos pelo aplicativo devem permanecer, pois o identificador do projeto é mantido pelo script de build.

## 2. Gerar o instalador Windows

1. Abra a pasta `installer`.
2. Execute `CRIAR_INSTALADOR.bat`.
3. O script cria um ambiente isolado de compilação, empacota o agente e compila o Inno Setup.
4. O resultado será `installer\output\KageLink-PC-Agent-Setup-v3.2.0.exe`.

## 3. Atualizar uma instalação existente

1. Feche o KageLink PC Agent.
2. Execute `KageLink-PC-Agent-Setup-v3.2.0.exe` por cima da versão atual.
3. Não marque remoção de dados durante uma eventual desinstalação anterior.
4. Abra o agente. A migração de `config.json` e SQLite ocorrerá automaticamente.
5. Abra o Shinobi Story Online.
6. Conecte o APK atualizado ao mesmo endereço e token.

A atualização preserva, quando existentes:

- `config.json`;
- token de acesso;
- `data/chat_history.db`;
- logs;
- arquivos de conexão;
- preferência OOC anterior.

## 4. Confirmar o campo IC

1. No aplicativo, abra o menu do chat.
2. Entre em **Calibrar entrada**.
3. Localize o candidato exibido como `002` — o mesmo índice global do arquivo `002_hwnd-525946_Edit_sem_titulo` usado como referência.
4. Toque em **Usar como IC**.
5. Confirme que o indicador IC fica localizado.

O HWND não é salvo. A confirmação registra a geometria e a posição estáveis do controle.

## 5. Segurança de envio

- A aba OOC envia somente pelo campo OOC.
- A aba IC envia somente pelo campo IC.
- Se o campo selecionado não estiver disponível, a mensagem não é enviada pelo outro canal e o rascunho permanece no aplicativo.

## 6. Regra de leitura

- `(*` abre IC.
- O próximo `*)` fecha IC.
- O bloco completo vai para a aba IC.
- Todo o restante vai para OOC.
