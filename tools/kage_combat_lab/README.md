# Kage Combat Lab

Laboratório determinístico, adapter de combate real e loop completo do Dojo da PR #25.

## Contratos protegidos

```text
1 célula lógica = 64×64 pixels
posição desejada = D0
R = postura básica contínua, heartbeat de 250 ms durante o combate
H = toque de 50 ms, cooldown mínimo de 5 s e autoridade estrita de alvo/orientação
F12 = parada imediata e liberação de todas as teclas
```

## Início da luta

```text
DOJO_DIALOG_OK_CLICKED
→ refocar jogo
→ RIGHT sozinho por 90 ms
→ aguardar spawn
→ iniciar processo da luta
→ R_BASELINE_STARTED
```

O pulso RIGHT ocorre uma única vez depois do OK. O processo filho herda `confirmed_facing=RIGHT`, não repete o pulso e inicia imediatamente o heartbeat básico de R.

## Separação de autoridades

R e H não representam a mesma permissão:

```text
SEARCH / ATTENTION / REID_LOCAL
    R básico ativo
    H bloqueado
    movimento direcional bloqueado

TURN_ALIGN
    R temporariamente liberado
    direção exclusiva por 80 ms
    H bloqueado

LOCKED_ALIGNED / CONTACT_LOCK
    R ativo
    chase autorizado
    H autorizado conforme alcance e cooldown

KO / ENDED
    todas as teclas liberadas
```

Isso evita o personagem permanecer imóvel enquanto o detector ainda está adquirindo o inimigo, sem voltar a permitir H ou perseguição cega.

## Aquisição tolerante a ruído

A aquisição continua exigindo duas evidências, mas elas não precisam mais ser perfeitamente consecutivas.

```text
primeiro CLEAN_BODY
→ ATTENTION por até 1,60 s
→ um frame ruim não apaga a hipótese
→ segundo CLEAN_BODY confirma o lock
```

O mesmo raw track também pode completar a segunda evidência quando estiver:

- visível;
- na mesma região local;
- com movimento independente suficiente;
- abaixo do limite de background;
- fora da classe multicell;
- com confiança mínima.

Tracks estáticos, regiões de fundo e tracks diferentes não recebem essa promoção.

## Perda visual e ReID

```text
LOCKED
→ OCCLUDED_COAST por até 1,25 s
→ REID_LOCAL por até 6 s
→ SEARCH somente após hard lost
```

O valor de 1,25 s cobre uma captura ausente no FPS físico observado. Durante o coast:

- R permanece ativo;
- apenas uma microcorreção de 50 ms na última direção é permitida;
- H permanece proibido.

Durante `REID_LOCAL`, R básico permanece ativo, mas não há movimento nem H.

## CHASE_ALWAYS_ON

| Distância | Perseguição | H |
|---|---|---|
| `D=0` | Contact Lock com deadzone de 16 px | Somente com facing confirmado |
| `D>=1` | Aproximação de 100 ms em frame confiável | Permitido até D50 |
| `D>50` | Continua perseguindo | Bloqueado por alcance |

## Target Capsule por rodada

O `track_id` do OpenCV é descartável. A rodada mantém um `logical_target_id` e salva memória visual temporária em:

```text
kage_pilot_loop_logs\target_cache\round_001\
```

A Target Capsule, o ReID e a memória negativa do ambiente permanecem ativos.

## Trainer dia/noite

As referências `day-64` e `night-64` continuam ativas na busca inicial, no retorno pós-combate e na autorização visual da meditação.

## Diagnóstico

Logs:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\round_001.jsonl
```

Campos adicionais desta correção:

```text
r_baseline_active
engagement_policy
```

Ações esperadas durante aquisição:

```text
R_BASELINE,H_BLOCKED_WAITING_FOR_TARGET_OR_ALIGNMENT
```

Quando alinhado:

```text
R_AUTHORIZED
MOVE_<DIRECTION>_100MS
H_50MS
```

Vídeos de evento:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\event_videos\round_001\
```

## Testes

```powershell
cd "C:\Users\Rafael\Desktop\Powershell\Kagelink2\tools\kage_combat_lab"
.\run_kage_combat_lab.ps1 -RunAll
```

## Teste físico inicial

Comece com uma rodada:

```powershell
.\run_kage_combat_lab.ps1 -FullLoop -Rounds 1
```

Depois de confirmar `R_BASELINE_STARTED`, aquisição e chase, avance para três rodadas.

O loop completo continua:

```text
Trainer
→ diálogo e OK
→ RIGHT
→ spawn
→ R baseline
→ aquisição
→ alinhamento
→ combate
→ KO pelo chat
→ retorno
→ meditação protegida por 5,25 s
→ recuperação
→ READY
```

Use F12 diante de qualquer sequência inesperada.
