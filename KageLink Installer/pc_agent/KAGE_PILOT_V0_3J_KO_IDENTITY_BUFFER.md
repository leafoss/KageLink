# Kage Pilot v0.3j — Buffer de identidade do adversário nocauteado

**Data:** 29/07/2026  
**Status:** implementação e testes automatizados em andamento; validação física pendente  
**Escopo:** autoridade de vitória por chat entre rodadas consecutivas

## Falha real observada

Em uma execução longa, `Jounin: Matsuda, Al` foi derrotado e a rodada terminou corretamente. Na rodada seguinte, o corpo de Matsuda ainda estava presente. Ele se levantou, foi selecionado novamente como alvo e recebeu um segundo nocaute enquanto o novo adversário, `Jounin: Aoki, Ian`, continuava atacando o jogador.

A segunda linha válida:

```text
Jounin: Matsuda, Al has been Knocked-Out
```

foi interpretada como vitória da nova rodada. O pós-combate começou com Aoki ainda vivo, contaminando a rodada seguinte.

## Solução

O orquestrador mantém um buffer com a última identidade de KO aceita:

```text
last_accepted_ko_name = "Jounin: Matsuda, Al"
```

A identidade é tudo que aparece antes de:

```text
has been Knocked-Out
```

A normalização usa:

- espaços internos condensados;
- remoção de espaços externos;
- comparação `casefold()`;
- preservação do texto original para telemetria.

## Regra de aceitação

Uma linha de KO só encerra a rodada quando:

```text
nome atual != último nome aceito
+ pelo menos duas observações de inimigo com autoridade visual atual nesta rodada
```

Autoridades visuais aceitas:

```text
VISIBLE
OCCLUDED
CONTACT_REBIND
```

`CONTACT_MEMORY` isolado não conta como prova de um inimigo atual.

## KO repetido

Exemplo:

```text
buffer: Jounin: Matsuda, Al
linha:  Jounin: Matsuda, Al has been Knocked-Out
```

Resultado:

```text
KO_CANDIDATE name="Jounin: Matsuda, Al"
KO_REJECTED reason=REPEATED_PREVIOUS_OPPONENT
TARGET_INVALIDATED reason=KO_IDENTITY_REJECTED
COMBAT_CONTINUES
```

A rejeição:

1. libera todos os inputs imediatamente;
2. não inicia o pós-combate;
3. não altera o buffer;
4. limpa identidade, contato, facing, movimento e burst ligados ao alvo rejeitado;
5. preserva a memória de cenário dinâmico;
6. exige nova evidência visual do inimigo correto;
7. continua o combate.

## KO de adversário diferente

Exemplo:

```text
buffer: Jounin: Matsuda, Al
linha:  Jounin: Aoki, Ian has been Knocked-Out
```

Com inimigo atual validado:

```text
KO_CANDIDATE name="Jounin: Aoki, Ian"
KO_ACCEPTED reason=NEW_OPPONENT_KO
VICTORY_CHAT / VITORIA_CHAT: Jounin: Aoki, Ian has been Knocked-Out
```

Depois de `READY`, o pai atualiza:

```text
KO_BUFFER_UPDATE previous=Jounin: Matsuda, Al current=Jounin: Aoki, Ian
```

A rodada seguinte recebe Aoki como identidade anterior.

## Nome diferente sem inimigo atual validado

Uma linha com nome diferente não basta quando a rodada não registrou duas observações visuais atuais:

```text
KO_REJECTED reason=NO_CURRENT_ROUND_ENEMY
```

Isso protege contra histórico reexibido, controles de chat recriados e mensagens fora de contexto.

## Persistência

O buffer vive no processo pai do loop e é passado para cada runtime filho por argumento interno:

```text
--previous-ko-name "Jounin: Matsuda, Al"
```

Ele persiste durante toda a execução de 20 rodadas, mas não é gravado como estado permanente entre execuções independentes.

## Fonte canônica

```text
kage_pilot_dojo.py
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
→ kage_pilot_live_v03k_round.py
→ RoundKOIdentityGate
```

A camada `v03k` é um hotfix interno do runtime. O entrypoint público continua sendo `kage_pilot_dojo.py` e a baseline externa continua identificada como v0.3j enquanto o PR permanece em release candidate.

## Arquivos

```text
pc_agent/kage_pilot/ko_identity_v03k.py
kage_pilot_live_v03k_round.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_v03k_ko_identity.py
.github/workflows/kage-pilot-v03.yml
```

## Testes obrigatórios

- extração de tudo antes da frase de KO;
- normalização de espaços e caixa;
- Matsuda repetido é rejeitado mesmo com alvo visual;
- Aoki diferente sem inimigo atual é rejeitado;
- `CONTACT_MEMORY` não valida inimigo atual;
- Aoki diferente com duas observações atuais é aceito;
- rejeição libera inputs;
- rejeição incrementa a geração de invalidação e limpa evidência;
- processo pai passa o nome anterior ao filho;
- buffer é substituído somente após vitória e `READY`.

## Limitação deliberada

Duas rodadas legítimas consecutivas com exatamente o mesmo nome serão tratadas como suspeitas. Essa política é deliberadamente conservadora para o release candidate e evita repetir o erro real do corpo reanimado. Uma futura identidade mais rica poderá combinar nome, spawn e assinatura visual.

## Gate físico restante

Executar várias rodadas e procurar a sequência real:

```text
Matsuda KO aceito
→ Matsuda reaparece e é nocauteado
→ KO_REJECTED
→ COMBAT_CONTINUES
→ Aoki KO aceito
→ buffer atualizado para Aoki
```

O PR continua em draft e sem merge.
