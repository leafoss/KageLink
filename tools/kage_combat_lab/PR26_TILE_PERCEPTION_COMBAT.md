# PR26.11 — Guaranteed combat replay evidence

A PR26 permanece empilhada sobre a PR25 e mantém a continuidade de alvo da PR26.9, a grade imutável de 64 px, os contratos de movimento, facing, R, pulso H, F12, KO por chat e recuperação pós-combate.

## Falha física corrigida

Mesmo após a PR26.10, uma execução real processou 46 frames e terminou normalmente, mas nenhum `full_combat_replay.mp4` foi criado. Isso demonstra que o `cv2.VideoWriter` local não conseguiu abrir o codec `mp4v` e falhou silenciosamente.

## Contrato da PR26.11

O gravador não depende mais de um único codec nem de dimensões pares já fornecidas pela captura.

Ordem de tentativa:

```text
mp4v -> .mp4
avc1 -> .mp4
XVID -> .avi
MJPG -> .avi
```

Antes de abrir o writer, o frame é normalizado para `uint8 BGR`, memória contígua e largura/altura pares. Dimensões ímpares recebem um pixel preto de padding na direita ou embaixo.

## Fallback obrigatório

Se nenhum codec abrir, a rodada ainda gera evidência visual:

```text
full_combat_replay_frames/
  frame_000000.png
  frame_000001.png
  ...
  replay_manifest.json
```

O manifesto contém FPS, quantidade de frames, padrão dos nomes e todos os erros dos codecs tentados.

## Telemetria explícita

A primeira gravação imprime uma destas linhas:

```text
FULL_REPLAY_RECORDER_OPEN mode=VIDEO codec=... path=...
```

ou:

```text
FULL_REPLAY_VIDEO_WRITER_FAILED fallback=PNG_SEQUENCE path=...
```

No encerramento sempre aparece:

```text
FULL_REPLAY_SAVED mode=... codec=... frames=... path=...
```

Se nem um frame chegar ao gravador, aparece `FULL_REPLAY_NOT_CREATED` com a razão.

## Validação automática

GitHub Actions está verde no head `ec36471`:

- 168 testes pytest aprovados;
- todos os 15 cenários determinísticos da PR25 aprovados;
- ambos os launchers PowerShell analisados com sucesso.

Novos testes cobrem:

- fallback de MP4 para AVI/XVID;
- fallback total para sequência PNG;
- padding automático de dimensões ímpares;
- manifesto JSON com os erros de codec;
- replay de rodada limpa sem evento diagnóstico.

A PR permanece Draft e não deve ser mesclada antes do teste físico em Windows.
