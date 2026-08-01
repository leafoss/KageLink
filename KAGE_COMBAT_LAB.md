# Kage Combat Lab — contrato da PR #25

## Objetivo

Separar o raciocínio de combate do runtime real do KageLink e validá-lo em um ambiente determinístico executado pelo PowerShell.

## Regra indiscutível

```text
1 célula lógica = 64×64 pixels
```

A dimensão de 64 pixels é uma regra protegida do produto e não pode ser:

- configurada por JSON;
- alterada por argumento de linha de comando;
- inferida pelo tamanho do template do Trainer;
- herdada do modo 32;
- recalibrada por resolução;
- substituída por tamanho de bbox;
- modificada por testes, adapters ou integração futura.

O sistema deve falhar fechado quando receber qualquer outro tamanho.

## Autoridade espacial

```text
pixel visual
→ âncora dos pés
→ célula 64px
→ hipótese espacial
→ Combat Target lógico
```

Track IDs são evidência descartável. A célula confirmada é a autoridade de identidade.

## Regras de combate aprovadas

A distância usa Chebyshev entre a célula do jogador e a célula confirmada do alvo.

```text
D=0
→ exatamente um pulso direcional VERY_SHORT na direção visual do alvo
→ H proibido
→ sem direção visual dentro da célula, HOLD fail-closed

D=1
→ exatamente um pulso direcional VERY_SHORT na direção do alvo
→ H proibido

D=2
→ aguarda sem deslocamento
→ aperta H somente com confirmação visual limpa no frame atual

D=3
→ aperta H somente com confirmação visual limpa no frame atual
→ emite um pulso APPROACH para tentar chegar a D2

D>=4
→ regra ainda não definida
→ HOLD e H proibido
```

`VERY_SHORT` e `APPROACH` são perfis semânticos. A duração física em milissegundos pertence exclusivamente ao futuro adapter de teclado e não pode ser embutida na estratégia.

## Regras fail-closed

- atividade contaminada não atualiza identidade;
- blobs multicélula não adquirem nem reassumem o alvo;
- ausência de confirmação visual não autoriza H nem movimento;
- D0 sem direção visual válida não autoriza pulso;
- KO remove toda autoridade de combate;
- distâncias sem regra não herdam comportamento de outra distância.

## Escopo atual

A PR #25 entrega somente o laboratório independente, a estratégia experimental e os testes determinísticos. Não modifica o combate real da PR #23.

## Gate de integração

A integração com o KageLink somente poderá começar quando:

1. todos os cenários determinísticos passarem;
2. blobs multicélula nunca adquirirem identidade;
3. troca de track na mesma célula preservar o alvo lógico;
4. perda curta suspender o alvo sem movimento cego;
5. KO desativar toda autoridade de combate;
6. nenhuma configuração diferente de 64px for aceita;
7. as regras D0–D3 permanecerem protegidas por testes;
8. o adapter físico calibrar os perfis de pulso sem reescrever a estratégia.
