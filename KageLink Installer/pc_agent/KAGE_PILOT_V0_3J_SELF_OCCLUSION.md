# Kage Pilot v0.3j — Desoclusão do treinador pelo próprio jogador

**Data:** 29/07/2026  
**Status:** implementação e testes automatizados em validação; teste físico pendente  
**Escopo:** pós-combate, imediatamente antes da autorização de meditação

## Evidência visual

Uma captura real mostrou Leafos exatamente abaixo do Dojo Trainer. Nessa posição, o sprite do jogador cobre parte das pernas, do assento e da região inferior usada pelo template do treinador.

Isso explica o log observado:

```text
visual do treinador em d=1
→ Leafos chega exatamente abaixo
→ template fica parcialmente encoberto
→ detector retorna apenas memória em d=0/d=1
→ V permanece bloqueado por segurança
→ pós-combate fica aguardando nova visão
```

A regra `memória nunca autoriza V` continua correta e foi preservada.

## Nova política

Quando a busca visual já entrou em modo de readquisição e todas as condições abaixo são verdadeiras:

1. o último visual real do treinador é recente;
2. a memória ainda indica distância `d <= 1`;
3. `V` ainda não foi autorizado;
4. nenhuma manobra de desoclusão foi enviada nesta recuperação;
5. existe uma direção perpendicular que não está temporariamente bloqueada;

então o motor produz:

```text
SELF_OCCLUSION_ESCAPE
```

com exatamente um pulso cardinal curto.

Depois:

```text
SELF_OCCLUSION_WAIT
```

sem movimento e sem `V`, enquanto o detector tenta obter uma visão atual novamente.

## Escolha da direção

A direção é perpendicular à linha jogador → treinador:

```text
Treinador acima ou abaixo
→ testar direita/esquerda

Treinador à esquerda ou direita
→ testar baixo/cima
```

A primeira opção é a direção com mais espaço disponível dentro da arena. Se essa direção estiver temporariamente bloqueada, a segunda perpendicular é tentada. Se ambas estiverem bloqueadas, nenhuma movimentação é forçada e a busca visual limitada existente continua.

No cenário da captura:

```text
Treinador
    ↑
Leafos
```

`up` é explicitamente proibido como pulso de desoclusão. O resultado deve ser `left` ou `right`.

## Invariantes de segurança

A mudança não permite:

- `V` por memória;
- mais de um pulso de desoclusão na mesma recuperação;
- direção mantida;
- mouse pressionado;
- clique adicional no treinador;
- alteração de combate;
- `H`, `R` ou qualquer ação ofensiva no pós-combate;
- movimento forçado quando as duas direções perpendiculares estão bloqueadas.

A autorização de meditação continua exigindo:

```text
2 confirmações visuais atuais e adjacentes
→ START_MEDITATION
→ V_TAP
```

## Telemetria esperada

```text
POST SELF_OCCLUSION_ESCAPE leader_score=... d=0 move_pulse=left V_WAIT ...
reason=POSSIBLE_SELF_OCCLUSION...

POST SELF_OCCLUSION_WAIT leader_score=... d=0 move_pulse=- V_WAIT ...

POST SEEK_LEADER ... confirming adjacent trainer visual
POST START_MEDITATION ... V_TAP
```

Caso a visão não retorne após a espera curta:

```text
REACQUIRE_VISUAL_WAIT
→ REACQUIRE_LEADER_VISUAL
```

A busca visual anterior continua como fallback.

## Arquivos

```text
kage_pilot_live_v03j_round.py
tests/test_kage_pilot_v03j_self_occlusion.py
.github/workflows/kage-pilot-v03.yml
```

## Testes de regressão

- jogador abaixo do treinador recebe pulso lateral, nunca `up`;
- apenas um `SELF_OCCLUSION_ESCAPE` por recuperação;
- depois do pulso, `SELF_OCCLUSION_WAIT` não move e não toca `V`;
- duas visões atuais após a desoclusão autorizam meditação;
- treinador à direita/esquerda gera escape vertical;
- memória sem visual recente usa a busca limitada anterior;
- duas direções perpendiculares bloqueadas não forçam movimento.

## Gate físico

A validação real deve confirmar:

- [ ] o estado `SELF_OCCLUSION_ESCAPE` aparece quando Leafos encobre o treinador;
- [ ] o pulso é lateral no cenário abaixo do treinador;
- [ ] o personagem não caminha para dentro do treinador;
- [ ] ocorre no máximo um pulso;
- [ ] `V` só acontece após duas confirmações visuais;
- [ ] a recuperação termina em `READY`;
- [ ] o loop continua para a próxima rodada;
- [ ] nenhuma tecla vaza para o PowerShell.

O PR continua em draft e sem merge.
