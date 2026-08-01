# Kage Combat Lab

Laboratório determinístico, input real e loop completo do Dojo da PR #25.

## Contratos protegidos

```text
1 célula lógica = 64×64 pixels
posição desejada = D0
R = key-down renovado a cada 250 ms, somente com autoridade
H = toque de 50 ms, cooldown mínimo de 5 s
F12 = parada imediata e liberação de todas as teclas
```

## Início obrigatório virado para a direita

O pulso inicial ocorre exatamente depois do OK/refoco e antes da espera de spawn:

```text
DOJO_DIALOG_OK_CLICKED
→ refocar a janela do jogo
→ liberar todas as teclas
→ aguardar 300 ms
→ RIGHT sozinho por 90 ms
→ liberar RIGHT
→ aguardar 120 ms
→ WAITING_FOR_SPAWN
```

O processo filho recebe `--pr25-post-ok`, herda `confirmed_facing=RIGHT` e não envia um segundo pulso.

## Autoridade explícita de orientação

São mantidos separadamente:

```text
raw_target_bearing
stable_target_bearing
commanded_facing
confirmed_facing
```

Enviar uma direção não confirma automaticamente a orientação.

Estados de orientação:

```text
SEARCH
ATTENTION
OCCLUDED_COAST
REID_LOCAL
LOCKED_UNALIGNED
TURN_ALIGN
LOCKED_ALIGNED
CONTACT_LOCK
ENDED
```

Autoridade:

```text
SEARCH / ATTENTION / OCCLUDED_COAST / REID_LOCAL → R OFF, H OFF
TURN_ALIGN / LOCKED_UNALIGNED                   → R OFF, H OFF
LOCKED_ALIGNED / CONTACT_LOCK                   → R autorizado
ENDED / KO                                      → todas as teclas liberadas
```

## Giro e ataque em frames separados

```text
Frame A — TURN_ALIGN
liberar R e direcionais
→ aguardar 30 ms
→ direção sozinha por 80 ms
→ liberar direção
→ aguardar 90 ms

Frame B — confirmação
reobservar o alvo
→ aceitar ou rejeitar o giro
→ manter R/H desligados durante o frame de confirmação

Frame C — ataque
alvo ainda visível e bearing compatível
→ R autorizado
→ H autorizado quando cooldown e alcance permitirem
```

Máximo de duas tentativas. Giro falho não consome o cooldown de H.

## Contact Lock em D0

```text
deadzone = 16 px
troca de lado = pelo menos 20 px
confirmação da troca = 2 frames
margem para trocar de eixo = 6 px
```

Dentro da deadzone, não há microchase nem inversão de facing. Pequenas variações do bounding box deixam de produzir `LEFT → RIGHT → LEFT`.

## Invalidação por empurrão

A orientação aceita é invalidada quando houver evidência de:

```text
KNOCKBACK
TARGET_CROSSED_PLAYER
BEARING_JUMP
AIM_UNCONFIRMED
```

Após invalidação, R e H são desligados e o sistema retorna ao `TURN_ALIGN`.

## Target Capsule e ReID

O raw `track_id` continua descartável. A rodada preserva um `logical_target_id` e memória visual temporária:

```text
kage_pilot_loop_logs\target_cache\round_001\
├── target_session.json
├── exemplar_001.png
├── descriptor_001.npz
└── ...
```

Score de ReID:

```text
35% aparência
25% posição prevista
15% tamanho e formato
15% movimento independente da câmera
10% foreground
```

Perda visual:

```text
LOCKED
→ OCCLUDED_COAST por até 0,45 s, com R/H desligados
→ REID_LOCAL por até 6 s, sem perseguição cega
→ SEARCH somente após hard lost
```

A memória negativa do ambiente continua reduzindo falsas aquisições de chão, água, decoração e partículas.

## Dataset futuro de orientação do jogador

Após giros exclusivos confirmados, recortes confiáveis de 64×64 são salvos em:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\player_facing_dataset\
├── right\
├── left\
├── up\
└── down\
```

Cada PNG possui JSON associado com round, frame, direção, fonte, confiança e contaminação. Recortes com baixa confiança, muito movimento ou sobreposição do inimigo são rejeitados.

## Vídeos de diagnóstico

Clipes com aproximadamente cinco segundos antes e cinco depois são criados para:

```text
STARTUP_RIGHT_PULSE
TURN_ALIGN_STARTED
TURN_ALIGN_CONFIRMED
TURN_ALIGN_FAILED
AIM_UNCONFIRMED
FACING_INVALIDATED
R_AUTHORITY_CHANGED
CONTACT_SIDE_SWITCH
TARGET_HARD_LOST
REID_SUCCESS
DIRECTION_FLIP
```

Local:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\event_videos\round_001\
```

O overlay mostra estado, alvo lógico, raw track, D, raw/stable bearing, commanded/confirmed facing, confiança, tentativa de giro, autoridade de R/H e causa da invalidação.

## Trainer e recuperação

`day-64` e `night-64` continuam ativos na busca inicial, retorno pós-combate e confirmação visual da meditação.

Preservado:

```text
KO autoritativo pelo chat
retorno ao Trainer
meditação V/Y
HP >= 90%
Chakra >= 50%
intervalo mínimo de 5,25 s antes do segundo V
```

## Testes determinísticos

```powershell
cd "C:\Users\Rafael\Desktop\Powershell\Kagelink2\tools\kage_combat_lab"
.\run_kage_combat_lab.ps1 -RunAll
```

## Teste físico inicial

```powershell
.\run_kage_combat_lab.ps1 -FullLoop -Rounds 3
```

Fluxo:

```text
Trainer
→ diálogo/OK
→ RIGHT antes do spawn
→ aquisição com R desligado
→ alinhamento exclusivo
→ combate autorizado
→ KO
→ retorno
→ meditação
→ recuperação
→ próxima rodada
```

Logs:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\round_001.jsonl
```

Use F12 diante de alvo incorreto, input inesperado, ataque após KO ou falha de retorno/meditação.
