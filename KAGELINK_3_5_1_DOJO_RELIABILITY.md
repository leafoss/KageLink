# KageLink 3.5.1 — Confiabilidade do Dojo Trainer

[English](KAGELINK_3_5_1_DOJO_RELIABILITY.en.md)

## Escopo

A versão 3.5.1 preserva o pipeline RAW, a geometria do clique, o diálogo, o combate, o retorno visual, a recuperação, F12, Stop e os demais controles de segurança do Dojo.

A aba **Dojo Trainer → Imagens** agora é a fonte absoluta de verdade dos templates usados para localizar o Trainer.

## Regra RAW correta

RAW imutável significa que o PNG escolhido pelo usuário é armazenado e utilizado sem tratamento visual.

O template ativo não recebe:

- resize, upscale, downscale ou interpolação;
- recorte automático ou padding;
- grayscale, CLAHE, equalização, brilho ou contraste;
- threshold, binarização ou máscara reconstruída;
- blur, sharpen, denoise ou morphology;
- Canny ou edge detection;
- regravação, recompressão ou conversão de formato;
- geração de escalas intermediárias.

RAW imutável não impede substituir ou remover a imagem.

## Autoridade da aba Imagens

Fluxo canônico:

```text
usuário escolhe PNG
→ backend valida somente PNG/decodificação
→ bytes exatos são persistidos
→ arquivo é associado ao modo 32 ou 64
→ interface mostra o arquivo ativo
→ detector carrega exatamente o mesmo arquivo
→ matching ocorre em escala 1.000
```

Os valores 32 e 64 representam o modo de célula do jogo, não a dimensão obrigatória do recorte. Um PNG 72×73 pode ser associado ao modo 64 e permanece 72×73 no matcher.

## Substituição, remoção e padrão

- `POST /api/dojo/templates/{mode}` aceita qualquer PNG válido e preserva os bytes exatos;
- `DELETE /api/dojo/templates/{mode}` remove a imagem, registra `removed_by_user=true` e não restaura o padrão;
- `POST /api/dojo/templates/{mode}/restore-default` restaura o padrão somente por ação explícita;
- conflito HTTP 409 permanece apenas quando o treinamento está ativo;
- erros de PNG são apresentados em PT-BR e EN-US sem expor apenas o código HTTP genérico.

Templates incorporados são usados somente na primeira inicialização de um modo sem estado persistido. Diferença de hash nunca autoriza sobrescrever uma imagem do usuário.

## Persistência

Local:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Metadados por modo incluem origem `user/default/none`, dimensões reais, modo da célula, SHA-256, nome original, data, estado ativo e remoção explícita.

## Detector preservado

Continuam obrigatórios:

- captura da área cliente original do BYOND;
- transporte PNG sem perdas;
- busca no frame cliente completo;
- escala 1.000;
- pixels nativos do template;
- bbox no frame cliente original;
- conversão validada do bbox para coordenada de clique.

KageLink.exe, KagePilotDojo.exe, KagePilotRound.exe, Anchor Monitor, API e Desktop usam o mesmo armazenamento persistente.

## Telemetria

```text
DOJO_USER_TEMPLATE_SAVED
DOJO_ACTIVE_TEMPLATE_LOADED
DOJO_USER_TEMPLATE_REMOVED
DOJO_DEFAULT_TEMPLATE_RESTORED
DOJO_RAW_MATCH_CANDIDATE
DOJO_RAW_MATCH_CONFIRMED
```

`DOJO_RAW_TEMPLATE_MATERIALIZED reason=hash-mismatch` não pertence mais ao caminho operacional de templates personalizados.

## Validação automatizada

Head validado antes desta atualização documental: `db10b7ef1ca45bc39203fbbcfed640bcb8c8a9b0`.

- Kage Pilot / KageLink 3.5 — run 181: sucesso;
- KageLink Unified LeafOS CI — run 677: sucesso;
- Publish KageLink Release — run 233: sucesso;
- suíte Python completa e compilação: sucesso;
- KageLink.exe, KagePilotDojo.exe e KagePilotRound.exe: build e smoke tests concluídos;
- smoke launch do Desktop: sucesso;
- Setup Windows, Flutter e APK: sucesso.

## Teste físico obrigatório

1. instalar o preview atual;
2. abrir Dojo → Imagens;
3. substituir o template 64 por um PNG válido, inclusive 72×73;
4. confirmar ausência de HTTP 400;
5. confirmar origem Usuário, dimensões e hash na interface;
6. iniciar o Trainer e confirmar o mesmo hash no log;
7. confirmar match em escala 1.000 e tentativa de clique na célula correta;
8. reiniciar o KageLink e confirmar persistência;
9. remover a imagem e confirmar ausência de HTTP 409 por imutabilidade;
10. reiniciar e confirmar que o padrão não reaparece;
11. restaurar o padrão somente pelo botão explícito;
12. repetir para o modo 32.

A PR permanece Draft e não pode ser mesclada sem autorização explícita de Rafael.
