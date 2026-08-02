# Kage Combat Lab — contrato da PR #25

## Objetivo

Separar o raciocínio de combate do runtime real do KageLink e validá-lo em um ambiente determinístico executado pelo PowerShell.

## Regra indiscutível

```text
1 célula lógica = 64×64 pixels
```

A dimensão de 64 pixels é uma regra protegida do produto. Qualquer outro tamanho falha fechado com `KAGE_GRID_CELL_SIZE_IMMUTABLE`.

## Autoridade espacial

```text
pixel visual
→ âncora dos pés
→ célula 64px
→ hipótese espacial
→ Combat Target lógico
```

Track IDs são evidência descartável. A célula confirmada é a autoridade de identidade.

## Regras aprovadas

```text
D=0
→ pulso direcional de 50 ms na direção visual do alvo
→ H proibido
→ sem direção visual: HOLD

D=1
→ pulso direcional de 50 ms na direção do alvo
→ H proibido

D=2
→ mantém posição
→ mira no alvo
→ H por 50 ms somente com visão limpa e cooldown livre

D=3 até D=50
→ mira no alvo
→ H por 50 ms quando o cooldown estiver livre
→ depois aproxima por 100 ms rumo a D2

D>50
→ H proibido por alcance
→ aproxima por 100 ms com visão limpa
```

## Temporização e segurança

```text
Cooldown mínimo de H: 5,0 s
R key-down heartbeat: 250 ms
Nova observação após ação: 150 ms
Intervalo mínimo entre pulsos de movimento: 250 ms
Oclusão curta: até 1,0 s
Hard lost: 2,0 s
Primeiro teste em shadow mode: 10 s
Primeiro teste armado: máximo 45 s
Parada de emergência: F12
```

R permanece em estado lógico `pressed down` durante o combate e deve ser liberado em KO, F12, perda de foco, timeout, exceção ou encerramento do processo.

## Regras fail-closed

- H exige corpo limpo no frame atual e direção cardinal válida;
- atividade contaminada não atualiza identidade;
- blobs multicélula não adquirem nem reassumem o alvo;
- ausência de confirmação visual não autoriza H nem movimento;
- D0 sem direção visual válida não autoriza pulso;
- o primeiro alvo lógico permanece fixo até KO ou hard lost;
- o primeiro teste real aceita apenas um Trainer;
- KO remove toda autoridade e ignora novos candidatos até `reset_round`.

## Escopo atual

A PR #25 entrega o laboratório, a estratégia, o contrato físico neutro e os testes determinísticos. Ainda não envia teclas ao BYOND e não modifica o combate real da PR #23.

## Gate para adapter físico

A conexão ao jogo somente poderá começar quando:

1. todos os testes e cenários determinísticos passarem;
2. o cooldown de H nunca for menor que 5 segundos;
3. R for liberado em todos os caminhos de saída;
4. H nunca ocorrer sem visão limpa e mira cardinal;
5. D0–D50 permanecerem protegidos por testes;
6. blobs multicélula nunca adquirirem identidade;
7. o adapter preservar o grid imutável de 64px;
8. o primeiro estágio funcionar por 10 segundos em shadow mode antes de armar input.
