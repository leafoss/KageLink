# Kage Pilot v0.3 — Live Control Gate 3 (PT-BR)

## Objetivo

Fechar o primeiro ciclo autônomo do Dojo sem alterar o núcleo de combate já validado:

```text
COMBAT
→ vitória autoritativa pelo chat
→ R OFF
→ localizar líder do Dojo
→ ficar adjacente
→ V ON
→ recuperar HP/Chakra
→ V OFF
→ READY
```

## Combate preservado

A v0.3 já validou em jogo real:

- GRID lógica 32×32;
- TARGET híbrido com memória de contato;
- filtro de água/background;
- proteção contra partículas de impacto;
- `R` como estado-base de combate BYOND;
- movimento por pulsos dead-man;
- recuperação após knockback;
- correção explícita de facing;
- `H` real protegido;
- primeira vitória autônoma.

Durante combate:

- `R` é a única tecla que pode permanecer logicamente ativa;
- setas são pulsos curtos, nunca estado sustentado;
- `H` é sempre um tap curto e só pode disparar em melee validado;
- antes de `H`, o Pilot força um pulso de facing para o TARGET;
- depois de `H`, existe `H_SETTLE_HOLD`;
- `MOTION_BURST_HOLD` bloqueia movimento/facing/H durante picos de vento/partículas, mantendo apenas R.

## Vitória autoritativa pelo chat

A vitória **não** é inferida por `target=none` ou desaparecimento visual do inimigo.

O Kage Pilot lê diretamente o chat do Shinobi Story Online e observa somente texto novo depois do início da luta.

A família autoritativa é:

```text
<qualquer nome/rank> has been Knocked-Out
```

Exemplo real informado:

```text
Jounin: Tamura, Seijun has been Knocked-Out
```

O matcher tolera também `has been knocked out`, mas não aceita apenas `knocked down` nem desaparecimento do TARGET.

Ao receber a mensagem:

```text
VICTORY_CHAT
→ release_all()
→ R OFF imediatamente
→ encerra COMBAT
→ inicia POST_COMBAT
```

Tudo que já estava no chat antes da luta é baseline e não pode gerar vitória retroativa.

## Pós-combate — líder do Dojo

O pós-combate usa como template o sprite real do líder do Dojo fornecido pelo usuário.

Estado:

```text
SEEK_DOJO_LEADER
```

Regras:

- busca o sprite dentro da arena capturada;
- exige confirmação em múltiplos frames;
- enquanto o NPC não estiver visível, não anda às cegas;
- navega com pulsos curtos de seta, **sem R**;
- converte PLAYER e líder para a GRID 32×32;
- qualquer uma das oito células adjacentes é válida;
- distância Chebyshev `<= 1` significa que chegou ao lado do NPC.

## Meditação com V

`V` é um **toggle**, nunca uma tecla mantida.

Ao chegar ao lado do líder:

```text
V TAP
→ entra em meditação
→ nenhuma tecla é mantida
```

Durante meditação o Kage Pilot lê as barras de HP e Chakra do HUD do GAME.

Critério atual:

```text
HP >= 90%
E
Chakra >= 50%
```

Os dois limites precisam permanecer válidos em múltiplas leituras consecutivas.

Quando ambos forem alcançados:

```text
V TAP
→ sai da meditação
→ READY
```

Não existe `V HOLD`.

## Movimento dead-man

Um `MOVE_RIGHT`, por exemplo:

```text
estado-base
↓
RIGHT por ~90 ms
↓
RIGHT OFF obrigatoriamente
↓
nova percepção necessária para outro passo
```

Uma decisão ruim não pode deixar uma seta permanentemente pressionada.

## Confirmação e watchdog de perseguição

- alvo/direção distante precisa permanecer coerente antes do primeiro pulso;
- troca de `ENTITY ID` distante reinicia confirmação;
- falta de progresso na GRID produz `NO_PROGRESS_HOLD`;
- `CONTACT_MEMORY` distante nunca autoriza perseguição;
- background dinâmico forte bloqueia perseguição;
- partículas pequenas não possuem autoridade para navegação distante.

## Segurança

- `F12`: parada imediata global;
- perda de foreground interrompe controle;
- `finally` libera R/H/setas;
- vitória pelo chat libera todas as teclas antes do pós-combate;
- pós-combate nunca reativa R;
- se o líder não for localizado, o personagem fica parado;
- timeout de pós-combate não inventa sucesso de recuperação;
- se o runtime iniciou meditação e o pós-combate expira normalmente, V é tocado uma vez para não deixar o personagem preso em meditação;
- F12 não envia ação adicional depois da parada de emergência.

## Comando atual

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 60 --log kage_pilot_live_test_5.jsonl
```

Defaults do pós-combate:

```text
chat poll:               0,25 s
leader threshold:        0,72
leader confirm:          2 frames
HP target:               90%
Chakra target:           50%
recovery confirmation:   3 frames
post-combat timeout:     120 s
V pulse:                 0,08 s
```

## Estados úteis no log

Combate:

- `MOVE_CONFIRM`
- `MOVE_PULSE`
- `FACE_RECOVER`
- `H_FIRE`
- `H_SETTLE_HOLD`
- `MOTION_BURST_HOLD`
- `NO_PROGRESS_HOLD`
- `MOVE_COOLDOWN`
- `MEMORY_HOLD`
- `BACKGROUND_HOLD`

Pós-combate:

- `VICTORY_CHAT`
- `SEEK_DOJO_LEADER`
- `START_MEDITATION`
- `MEDITATING`
- `READY`
