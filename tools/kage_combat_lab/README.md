# Kage Combat Lab

Laboratório determinístico, adapter de combate real e loop completo do Dojo da PR #25.

## Contratos protegidos

```text
1 célula lógica = 64×64 pixels
posição desejada = D0
R = key-down renovado a cada 250 ms
H = toque de 50 ms, cooldown mínimo de 5 s
F12 = parada imediata e liberação de todas as teclas
```

## CHASE_ALWAYS_ON

| Distância | Perseguição | H |
|---|---|---|
| `D=0` | Microcorreção de 50 ms com deadzone e histerese | Somente após confirmação fechada da direção |
| `D>=1` | Aproximação de 100 ms em todo frame confiável | Permitido até D50 |
| `D>50` | Continua perseguindo | Bloqueado por alcance |

## Target Capsule por rodada

O `track_id` do OpenCV é descartável. A rodada mantém um `logical_target_id` e salva uma memória visual temporária do inimigo:

```text
kage_pilot_loop_logs\target_cache\round_001\
├── target_session.json
├── exemplar_001.png
├── descriptor_001.npz
└── ...
```

Somente frames limpos e confiáveis alimentam a cápsula. Cada candidato posterior recebe um score híbrido:

```text
35% aparência
25% posição prevista
15% tamanho e formato
15% movimento independente da câmera
10% evidência de foreground
```

Um novo `track_id` pode ser religado ao mesmo alvo lógico quando aparência, posição e forma forem compatíveis.

## Memória negativa do ambiente

Regiões rejeitadas repetidamente e alinhadas pelo movimento global da câmera tornam-se evidência de fundo. Isso reduz a chance de chão, água, decoração animada e partículas serem promovidos a inimigo.

A memória negativa nunca é aprendida sobre o alvo confirmado e não classifica algo como chão por apenas um frame parado.

## Perda visual e ReID

```text
LOCKED
→ OCCLUDED_COAST por até 0,45 s
→ REID_LOCAL por até 6 s
→ SEARCH somente após hard lost
```

- `OCCLUDED_COAST`: preserva identidade, permite somente microchase previsto e proíbe H.
- `REID_LOCAL`: procura perto da posição prevista usando a Target Capsule; não persegue nem ataca às cegas.
- Um ReID bem-sucedido mantém o mesmo `logical_target_id`, mesmo que o raw `track_id` mude.

## Controle fechado de orientação

H não é mais enviado imediatamente após o comando direcional:

```text
calcular direção atual
→ pulso direcional de 50 ms
→ aguardar 75 ms
→ capturar um novo frame
→ confirmar/corrigir a direção
→ H somente quando confirmado
```

São permitidas no máximo duas correções. Se a confirmação falhar, H é cancelado e o cooldown de cinco segundos não é consumido.

Em D0:

```text
deadzone = 12 px
mudança de direção/eixo = 2 frames consistentes
margem para trocar de eixo = 6 px
```

Isso reduz oscilações `LEFT ↔ RIGHT` e trocas horizontais/verticais causadas por ruído do bounding box.

## Vídeos de eventos críticos

O loop não grava continuamente. Ele mantém um buffer circular e salva clipes com aproximadamente cinco segundos antes e cinco depois de:

```text
TARGET_HARD_LOST
REID_SUCCESS
DIRECTION_FLIP
AIM_UNCONFIRMED
```

Local:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\event_videos\round_001\
```

Os vídeos possuem overlay com estado, alvo lógico, raw track, D, direção, scores e inputs enviados.

## Trainer dia/noite

As referências oficiais `day-64` e `night-64` continuam ativas na busca inicial, retorno pós-combate e autorização visual da meditação:

```text
final_score = max(score_day_64, score_night_64, demais_templates_configurados)
```

## Testes

```powershell
cd "C:\Users\Rafael\Desktop\Powershell\Kagelink2\tools\kage_combat_lab"
.\run_kage_combat_lab.ps1 -RunAll
```

## Loop completo

```powershell
.\run_kage_combat_lab.ps1 -FullLoop -Rounds 10
```

Fluxo:

```text
buscar Trainer
→ diálogo e OK
→ spawn
→ combate com Target Capsule e CHASE_ALWAYS_ON
→ KO pelo chat
→ retorno ao Trainer
→ meditação e recuperação
→ READY
→ próxima rodada
```

Defaults:

```text
Combate máximo: 120 s por rodada
Retorno/recuperação: 240 s
Busca do Trainer: 90 s
HP para READY: 90%
Chakra para READY: 50%
Meditação mínima antes do segundo V: 5,25 s
```

Logs:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\round_001.jsonl
```

Use F12 se o sistema perseguir um objeto incorreto, continuar atacando depois do KO ou apresentar qualquer sequência de input inesperada.
