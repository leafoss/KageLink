# Relatório de testes — KageLink 3.2.0

## Resultado geral

A lógica do agente passou em **17 testes automatizados**. A base Python também passou por compilação sintática completa. Os arquivos Flutter passaram por validações estruturais e de localização executadas no ambiente disponível.

## Testes automatizados do agente

Comando:

```text
cd pc_agent
PYTHONPATH=. python -m unittest discover -s tests -v
```

Cenários aprovados:

1. OOC simples.
2. IC simples delimitado por `(* ... *)`.
3. IC multilinha preservado como uma única mensagem.
4. IC fragmentado aguardando o fechamento.
5. Conteúdo misto OOC + IC + OOC.
6. Dois blocos IC na mesma captura.
7. Delimitador de abertura dividido entre leituras.
8. Preservação exata de novas linhas na captura incremental.
9. Preservação do separador após truncamento do RichEdit.
10. Preservação de parágrafos em IC fragmentado.
11. Recuperação de sufixo IC incompleto durante atualização.
12. Retomada de IC pendente após reinicialização.
13. Remoção somente do prefixo reproduzido em ressincronização.
14. Preservação de mensagens novas e não relacionadas em ressincronização.
15. Migração do SQLite legado sem perda de linhas.
16. Persistência do snapshot e do buffer do monitor.
17. Migração da preferência OOC antiga e criação da referência IC `002`.

## Outras validações executadas

- `python -m compileall -q .`: aprovado.
- Quatro arquivos ARB lidos como JSON: aprovado.
- As quatro traduções possuem as mesmas **161 chaves**: aprovado.
- Metadados dos novos placeholders `channel`, `left`, `top`, `width` e `height`: aprovados.
- **140 referências** `l10n.*` no código foram encontradas nos ARBs: aprovado.
- Imports Dart relativos existentes: aprovado; o arquivo gerado `app_localizations.dart` foi corretamente tratado como saída do `flutter gen-l10n`.
- Varredura lexical de delimitadores Dart, ignorando strings e comentários: aprovado.
- Verificação de versão: Flutter `3.2.0+16`, agente `3.2.0` e instalador `3.2.0` alinhados.
- Verificação de ausência de HWND fixo `525946` no código: aprovado.

## Testes que dependem do computador Windows do jogo

A execução real de envio para os controles BYOND, a geração do APK release e a compilação do instalador EXE exigem, respectivamente, a janela do Shinobi Story Online no Windows, Flutter/Android SDK e PyInstaller/Inno Setup no Windows. Essas ferramentas e a janela do jogo não existem neste ambiente Linux; por isso, nenhum binário foi falsamente declarado como compilado.

Os scripts entregues realizam essas etapas no computador Windows:

- `COMPILAR_APK.bat`
- `installer\CRIAR_INSTALADOR.bat`

## Checklist de homologação no Windows

- Abrir o Shinobi e confirmar que o candidato global `002` corresponde ao campo Roleplay.
- Salvar o candidato como IC e confirmar os indicadores OOC/IC.
- Enviar uma mensagem curta por cada aba.
- Enviar um IC multilinha e conferir um único bloco na aba IC.
- Fechar e reabrir agente/app durante um bloco incompleto e confirmar a retomada.
- Instalar a versão 3.2.0 sobre a anterior e confirmar token, histórico e configurações preservados.
