# PR26.17 — Retenção do alvo corporal provisório

A PR26 permanece empilhada sobre a PR25 e mantém a grade imutável de `64x64`, comparação individual por célula, Target Capsule, replay integral, diagnósticos, facing, R, pulso H, F12, KO por chat e recuperação pós-combate.

## O raio de esperança da rodada física

A PR26.16 finalmente encontrou o inimigo real:

```text
frame 6
PR26_CELL_BODY_SELECTION id=3 raw_ids=[7]
PR26_MOBILE_DANGER id=3 cells={(7,2)}
reason=raw body and changed 64px cell are geometrically bound
```

Isso confirmou que a baseline `84/84`, a máscara de diferença da célula e a associação corpo↔pixels funcionaram em conjunto.

A aquisição, porém, foi descartada antes dos dois votos necessários para `COMBAT_LOCK`:

```text
frame 6: corpo real id=3/raw=7 selecionado
frame 7: detector bruto perde momentaneamente o corpo
frame 7: seletor troca para id=2, componente vertical raw-less
frame 8: correlação de câmera fica incerta
frame 8: exact_baselines passa de 84 para 0 naquele frame
```

Depois disso surgiram estimativas periódicas como `-64`, `-96` e `-32` pixels, embora o viewport permanecesse visualmente parado. O piso repetitivo do dojo e a estrutura de 32/64 px estavam criando aliases da correlação de fase.

## Alvo corporal provisório

A primeira associação válida entre corpo bruto e pixels alterados da baseline exata agora cria um alvo **provisório**, ainda sem autoridade ofensiva:

```text
EXACT_CELL_BASELINE
+
raw body visível
+
bbox/pé sobre os pixels do componente
-> PR26_PROVISIONAL_BODY_LATCH
```

Esse alvo permanece selecionado por até `3.0 s` durante uma falha curta do detector bruto.

```text
corpo bruto desaparece por um ou dois frames
-> mesma identidade provisória permanece selecionada
-> challenger raw-less é bloqueado
-> MOVE/H continuam bloqueados
-> sistema espera o próximo voto do mesmo corpo
```

Telemetria:

```text
PR26_PROVISIONAL_BODY_LATCH
PR26_PROVISIONAL_BODY_COAST
PR26_PROVISIONAL_BODY_RELEASED
```

A retenção provisória não equivale a `ROUND_TARGET_LATCHED`. Para liberar combate continua obrigatório:

```text
mesmo corpo confirmado em contato 2-de-3 frames
-> HOSTILE_CONFIRMED
-> COMBAT_LOCK
-> ROUND_TARGET_LATCHED
```

## Câmera fixa antes do latch

Antes de um latch hostil legítimo, a camada física permite somente pulsos isolados de orientação. Chase e H estão bloqueados; portanto, não existe movimento de câmera legítimo produzido pelo agente nessa fase.

A PR26.17 mantém a transformação aceita da baseline durante toda a aquisição pré-latch:

```text
sem ROUND_TARGET_LATCHED válido
-> PRELATCH_STATIC_VIEWPORT_HOLD
-> transformação aceita preservada
-> exact_baselines permanecem carregadas
-> estimativas -64/-96/-32 não cegam a percepção
```

Após um latch válido, movimento de câmera volta a exigir confirmação temporal. Aliases periódicos de `32 px` são desembrulhados para a posição equivalente mais próxima da tradução aceita.

## Segurança preservada

A correção não permite combate por memória provisória:

- `MOVE/H` continuam bloqueados até `COMBAT_LOCK`;
- componente raw-less não pode substituir o corpo provisório;
- mesma célula sem sobreposição de pixels continua inválida;
- track centrado no jogador continua bloqueado;
- campos `43x64`, `64x23`, células saturadas e faixas de UI continuam terreno;
- cluster continua sendo somente dica de busca;
- ReID continua impossível antes de um latch legítimo;
- depois do latch, geometria visual ainda exige corpo atual ou Target Capsule confirmado.

## JSON dos eventos

Os arquivos `FACE_ONLY_LOCK_CHANGED` e `DANGER_MOVED` da rodada chegaram com `CLIP_CLOSE_FALLBACK`, porque o wrapper de fechamento sobrescrevia o snapshot do gatilho.

A ordem dos gravadores foi corrigida e um wrapper final restaura os payloads congelados depois de todos os hooks de fechamento:

```text
snapshot no frame do evento
-> OccupancyEventRecorder
-> fechamento dos clips
-> restauração final do payload
-> snapshot_timing=EVENT_TRIGGER_FRAME
```

Telemetria:

```text
PR26_EVENT_TRIGGER_JSON_RESTORED
```

## Baseline e aquisição mantidas

Continuam válidas as correções da PR26.16:

- baseline pré-spawn por mediana temporal robusta;
- silhueta completa do jogador removida somente durante a captura;
- cobertura exata obrigatória em todas as células disponíveis de `D<=3`;
- promoção de track bruto fraco somente quando há sobreposição real com pixels alterados da baseline exata;
- referências genéricas de classe sem autoridade de aquisição.

## Validação automática

A suíte cobre:

- aliases `-64` e `-96` sendo normalizados para o viewport aceito;
- deslocamentos pequenos comuns permanecendo inalterados;
- retenção provisória durante falhas curtas do detector;
- expiração obrigatória após `3.0 s`;
- impossibilidade de a retenção provisória substituir um latch legítimo;
- ordem correta dos wrappers de snapshot, ocupação e fechamento;
- todos os contratos anteriores da PR26;
- os 15 cenários determinísticos da PR25;
- parsing dos launchers PowerShell.

No head automatizado, `200` testes pytest, os `15` cenários determinísticos e os dois launchers PowerShell passaram. A PR permanece Draft e não deve ser mesclada antes de uma nova rodada física no Windows confirmar a passagem:

```text
PR26_PROVISIONAL_BODY_LATCH
-> PR26_CELL_BODY_COMBAT_LOCK
-> PR26_ROUND_TARGET_LATCHED
```
