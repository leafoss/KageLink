# Kage Pilot v0.3 — Live Control Gate 2 (PT-BR)

## Objetivo

Validar combate real completo preservando as proteções que impediram runaway e adicionando o primeiro uso real da habilidade `H`.

Nesta etapa o Kage Pilot envia:

- `R` como estado-base de combate;
- pulsos curtos de setas para aproximação/recuperação;
- pulsos curtos de direção para corrigir facing em melee;
- `H` como tap curto, somente em janela validada de habilidade.

## Regra dead-man para movimento

Setas nunca permanecem em estado sustentado. Toda iteração retorna explicitamente para `R` antes de qualquer pulso direcional.

```text
R
↓
R + RIGHT por ~90 ms
↓
R novamente
```

Continuar andando exige nova autorização da percepção em ciclos seguintes.

## Correção de facing após impacto/knockback

Golpes do inimigo podem empurrar Leafos e também virar fisicamente o personagem para o lado errado. A posição do TARGET pode continuar correta mesmo quando o facing físico mudou.

Agora qualquer uma destas situações arma uma correção obrigatória:

- APPROACH/RECOVER;
- `MOTION_BURST_HOLD` causado por impacto/partículas.

Quando o sistema volta para `d <= 1`, o primeiro frame de melee força exatamente um novo pulso para a direção do inimigo, mesmo que essa direção seja igual ao último facing memorizado.

O estado aparece como:

```text
FACE_RECOVER
```

## H real protegido

`H` é liberado apenas quando:

- TARGET está em melee (`d <= 1`);
- há confirmação visual atual (`VISIBLE`/`OCCLUDED`);
- não é somente `CONTACT_MEMORY`;
- Enemy Score atende o mínimo;
- engagement estável atende o tempo mínimo;
- cooldown terminou;
- não existe `MOTION_BURST_HOLD` nem `H_SETTLE_HOLD`.

Antes de cada H real, o controlador força um pulso fresco para a direção do TARGET. A sequência física é:

```text
R
↓
R + direção por ~55 ms
↓
R
↓
R + H por ~65 ms
↓
R
```

O log mostra:

```text
H_FIRE
```

O H pode ser desabilitado para regressão com `--disable-h`.

## H_SETTLE_HOLD

O próprio jutsu pode produzir animação/partículas. Após cada H existe uma janela padrão de aproximadamente `0,55 s`:

```text
H_SETTLE_HOLD
→ R continua
→ nenhuma seta
→ nenhum novo facing
→ nenhum novo H
```

Isso evita reagir ao efeito visual produzido pela própria habilidade.

## Confirmação e watchdog de perseguição

- alvo/direção distante precisa aparecer em pelo menos 2 decisões consecutivas antes do primeiro pulso;
- troca de `ENTITY ID` distante reinicia a confirmação;
- se a distância na GRID não melhorar por aproximadamente 1,15 s, ocorre `NO_PROGRESS_HOLD`;
- `CONTACT_MEMORY d >= 2` nunca autoriza perseguição;
- alvo distante em região `BACKGROUND_DYNAMIC` forte gera `BACKGROUND_HOLD`.

## Guarda de impacto/partículas

`MotionBurstGuard` monitora células ativas e população de entidades. Um pico súbito gera `MOTION_BURST_HOLD` por aproximadamente `0,75 s`, mantendo apenas R.

Esse estado também arma uma correção obrigatória de facing assim que o melee volta a ser confiável.

## Segurança

- Duração padrão: 25 segundos.
- `F12`: parada imediata global.
- Perda de foreground interrompe o controle.
- `finally` libera R, setas e H.
- setas e H são sempre pulsos curtos, nunca estados mantidos.
- pós-combate automático com V ainda não está habilitado.

## Comando

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 45 --log kage_pilot_live_test_4.jsonl
```

## Estados úteis no log

- `MOVE_CONFIRM`: aguardando confirmação antes de andar.
- `MOVE_PULSE`: pulso de recuperação/aproximação.
- `FACE_RECOVER`: facing obrigatório após knockback/impacto.
- `H_FIRE`: H realmente enviado.
- `H_SETTLE_HOLD`: pausa de percepção/controle depois do próprio H.
- `MOTION_BURST_HOLD`: impacto/partículas; ações bloqueadas exceto R.
- `NO_PROGRESS_HOLD`: distância não melhorou.
- `MOVE_COOLDOWN`: pausa antes de reconsiderar perseguição.
- `MEMORY_HOLD`: memória sem visão suficiente para perseguir.
- `BACKGROUND_HOLD`: candidato em região ambiental dinâmica forte.
