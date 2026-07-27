# Kage Pilot v0.3 — Live Control Gate 1 (PT-BR)

## Objetivo

Validar combate real com o menor conjunto possível de ações automáticas depois da validação do Entity Observer e Shadow Combat.

Nesta etapa o Kage Pilot envia teclas reais, mas somente:

- `R` como estado-base de combate, usando o padrão BYOND de repetição já validado;
- pulsos curtos de setas para aproximação/recuperação;
- pulsos curtos de direção para corrigir facing em melee.

`H` permanece somente em Shadow Mode. O console pode indicar `H_READY(SHADOW)`, mas nenhuma tecla H é enviada.

## Regra dead-man para movimento

Setas não permanecem mais em estado sustentado. Toda iteração retorna explicitamente para o estado-base `R` antes de qualquer comando direcional.

Um `MOVE_RIGHT`, por exemplo, é executado como:

```text
R
↓
R + RIGHT por ~90 ms
↓
R novamente
```

Portanto uma decisão ruim não pode deixar uma seta permanentemente pressionada. Para continuar andando, a percepção precisa renovar a autorização em novos ciclos.

## Confirmação e watchdog de perseguição

- um alvo/direção distante precisa aparecer em pelo menos 2 decisões consecutivas antes do primeiro pulso de movimento;
- troca de `ENTITY ID` distante reinicia essa confirmação;
- se a distância na GRID não melhorar por aproximadamente 1,15 s, o movimento é interrompido (`NO_PROGRESS_HOLD`);
- após a interrupção há uma pequena janela de cooldown antes de nova perseguição.

Isso limita a distância que Leafos pode percorrer atrás de um falso alvo persistente.

## Guarda de impacto/partículas

Golpes fortes podem gerar vento/partículas que criam dezenas de regiões móveis simultâneas. O `MotionBurstGuard` mantém uma linha-base recente de:

- células ativas na GRID;
- quantidade de entidades/contornos.

Um aumento súbito muito acima da linha-base produz:

```text
MOTION_BURST_HOLD
→ R permanece
→ nenhuma seta
→ nenhum pulso de facing
→ aguarda a cena estabilizar (~0,75 s)
```

O pico não é incorporado imediatamente à linha-base, evitando ensinar a explosão visual como comportamento normal.

## Regras de alvo

- `d <= 1 célula`: MELEE. Mantém R e apenas corrige facing com pulso curto quando necessário.
- `d >= 2 células`: APPROACH/RECOVER somente com confirmação visual atual (`VISIBLE`/`OCCLUDED`).
- TARGET temporariamente ausente: mantém R, mas não anda às cegas.
- `CONTACT_MEMORY` preserva identidade/facing apenas no contato local (`d <= 1`). Nunca autoriza perseguição distante.
- alvo distante dentro de região com forte evidência `BACKGROUND_DYNAMIC` produz `BACKGROUND_HOLD`, não movimento.

## Segurança

- Duração padrão: 25 segundos.
- `F12`: parada imediata global.
- Perda de foreground interrompe o controle.
- `finally` libera R e todas as setas.
- cada ciclo também volta explicitamente para R antes de um novo pulso direcional.
- H não é enviado.
- Não existe ainda pós-combate automático com V.

## Comando

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 25 --log kage_pilot_live_test_3.jsonl
```

## Estados de segurança úteis no log

- `MOVE_CONFIRM`: alvo/direção ainda aguardando confirmação.
- `MOVE_PULSE`: pulso direcional autorizado.
- `MOTION_BURST_HOLD`: provável impacto/partículas; movimento bloqueado.
- `NO_PROGRESS_HOLD`: perseguia, mas a distância não melhorou.
- `MOVE_COOLDOWN`: pequena pausa antes de reconsiderar perseguição.
- `MEMORY_HOLD`: memória existe, mas não há visão suficiente para perseguir.
- `BACKGROUND_HOLD`: candidato em região ambiental dinâmica forte.
