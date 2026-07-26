# KageLink — Bíblia de Desenvolvimento — Capítulo LeafOS Interpreter

[English](AGENTS_INTERPRETER.en.md) · [Bíblia principal](AGENTS.md) · [Interpreter v3.2.1](LEAFOS_INTERPRETER_V3_2_1.md)

Este arquivo é uma **extensão normativa de `AGENTS.md`** para mudanças no LeafOS Interpreter, Memory Reviewer e contratos diretamente ligados ao pipeline de memória do KageLink.

Em caso de conflito, `AGENTS.md` continua sendo a fonte operacional superior. Para tarefas no Interpreter, ambos devem ser lidos antes de alterar código.

## 1. Pipeline protegido

```text
RAW imutável
   ↓
Processor
   ↓
sessão fechada
   ↓
Interpreter
   ↓
Interpretation Bundle / pending_review
   ↓
Memory Reviewer
   ↓
aprovação humana explícita
   ↓
Canonical Memory
```

Regras permanentes:

- RAW não é reescrito pelo Interpreter;
- sessões do Processor não são alteradas pelo Interpreter;
- Interpretation Bundle não é memória canônica;
- o Memory Reviewer continua sendo gate humano obrigatório;
- Canonical Memory não pode ser criada automaticamente pelo Interpreter;
- evidência deve permanecer rastreável por `source_message_ids` até Processor e RAW.

## 2. Interpreter v3 — sessões longas

Sessões grandes devem usar chunking ordenado em vez de uma única requisição gigante.

Contrato atual:

```text
chunk aproximado: 9000 caracteres
sobreposição padrão: 2 mensagens
timeout: por chunk
```

Nenhuma mensagem do meio pode ser descartada pelo fluxo normal. Chunks concluídos podem ser persistidos em checkpoint e reutilizados em retry parcial.

Checkpoint obsoleto não deve ser reutilizado quando sessão, prompt ou configuração de chunk mudar.

## 3. Grounding v3.1

O modelo interpreta somente a evidência fornecida.

É proibido inventar ou completar com conhecimento externo:

- identidade;
- intenção;
- treinamento;
- preparação de missão;
- definição de item;
- rank;
- facção;
- relação;
- localização;
- consequência.

A identidade visível `Anbu` nunca prova automaticamente `Anbu = Leafos`.

## 4. Category Discipline + Salience v3.2

Depois do grounding, gates determinísticos podem impedir que fatos grounded porém transitórios ou mal categorizados poluam o Reviewer.

Candidatos suprimidos não devem ser apagados silenciosamente: permanecem auditáveis em `suppressed_candidates`.

A supressão não equivale a rejeição canônica. Ela apenas controla a fila normal do Reviewer.

## 5. Durable System Revelations v3.2.1

Formatos explícitos e duráveis do sistema podem possuir extratores determinísticos **somente após a sintaxe real ser observada e coberta por regressão**.

Primeiro contrato aprovado:

```text
Your primary Element is: <valor>
Your secondary Element is: <valor>
```

A sintaxe real observada pelo Processor também pode vir envelopada:

```text
(***<identidade visível>** Your primary Element is: <valor>*)
(***<identidade visível>** Your secondary Element is: <valor>*)
```

O wrapper de identidade é apresentação/transporte e **não autoriza atribuir ownership** do resultado.

Saída reviewable deve permanecer neutra:

```text
The system reported the primary Element as Fire.
The system reported the secondary Element as Earth.
```

Não produzir automaticamente:

```text
Leafos has Fire/Earth
Anbu has Fire/Earth
```

## 6. Conflito entre LLM e extrator determinístico

Quando o LLM cria uma versão redundante da mesma revelação, por exemplo:

```text
Anbu revealed the primary element as Fire.
```

com o mesmo `source_message_id`, campo e valor do formato determinístico:

1. a versão do LLM não deve permanecer na fila normal do Reviewer;
2. a versão original deve ser preservada para auditoria em `suppressed_candidates`;
3. o Reviewer deve receber a versão determinística neutra;
4. nenhuma resolução de identidade deve ser inferida nesse processo.

## 7. Caso de regressão canônico

Sessão real usada como contrato de regressão:

```text
session_id: 2026-07-26_011
13863: (***Anbu** Your primary Element is: Fire*)
13864: (***Anbu** Your secondary Element is: Earth*)
```

Na execução real, o Reviewer mostrou que o LLM havia entendido os dois elementos, mas os publicou como eventos atribuídos ao `Anbu` visível:

```text
Revealing Primary Element
Anbu revealed the primary element as Fire.

Revealing Secondary Element
Anbu revealed the secondary element as Earth.
```

Esse resultado foi usado para endurecer o contrato antes do merge. A regressão automatizada usa exatamente a sintaxe e os IDs observados e exige como pós-processamento final:

- dois candidatos `facts` neutros;
- IDs `13863` e `13864` preservados separadamente;
- nenhuma atribuição `Leafos`/`Anbu` nos statements finais;
- versões redundantes do modelo apenas em auditoria;
- ruído mecânico de pickup/drop continua fora da fila normal.

A validação manual comprova a entrada real e a capacidade do pipeline de detectar o conteúdo; a forma neutra final adicionada depois desse log é coberta pela regressão automatizada correspondente.

## 8. Como adicionar novos formatos do sistema

Rank, clã, vila, habilidade, atributo ou qualquer novo formato só pode receber extração determinística depois de:

1. capturar a linha real do RAW/Processor;
2. registrar o comportamento esperado;
3. adicionar teste de regressão com a sintaxe real;
4. manter `source_message_ids` exatos;
5. definir explicitamente se ownership é comprovado ou não;
6. validar que não quebra v3/v3.1/v3.2;
7. atualizar documentação PT-BR e EN-US.

Não criar um parser genérico de mensagens de sistema por conveniência.

## 9. Definição de pronto para mudanças no Interpreter

Uma mudança no Interpreter só está pronta quando:

- testes Python passam;
- `compileall` passa;
- build empacotado continua válido quando afetado;
- evidência permanece rastreável;
- Reviewer continua sendo gate humano;
- identidade não é inferida sem prova;
- regressões reais pertinentes estão cobertas;
- documentação PT-BR e EN-US está atualizada;
- limitações de validação manual são registradas honestamente.
