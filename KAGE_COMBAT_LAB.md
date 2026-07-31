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

## Escopo inicial

A PR #25 entrega somente o laboratório independente, a estratégia experimental e os testes determinísticos. Não modifica o combate real da PR #23.

## Gate de integração

A integração com o KageLink somente poderá começar quando:

1. todos os cenários determinísticos passarem;
2. blobs multicélula nunca adquirirem identidade;
3. troca de track na mesma célula preservar o alvo lógico;
4. perda curta suspender o alvo sem movimento cego;
5. KO desativar toda autoridade de combate;
6. nenhuma configuração diferente de 64px for aceita.
