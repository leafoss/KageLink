# KageLink — Bíblia de Runtime, Persistência e Organização

[English](AGENTS_RUNTIME.en.md) · [Bíblia principal](AGENTS.md) · [Kage Pilot](KAGE_PILOT.md)

Este documento complementa `AGENTS.md` e governa a composição real do executável, workers, persistência, automação Windows, falhas, retries, versionamento e organização da árvore.

## 1. Composição oficial do executável

O runtime empacotado segue:

```text
KageLink.spec
→ unified_entry.py
→ unified_launcher.py
→ kagelink_launcher.py
→ unified_app.py
→ app.py
```

A rota inclui herança, substituição de módulo e seleção runtime do Interpreter. Antes de alterar o PC Agent, identificar:

1. entrypoint empacotado;
2. classe efetivamente instanciada;
3. backend efetivamente importado;
4. monkeypatch ou substituição aplicável;
5. teste que percorre a mesma rota;
6. módulo legado preservado apenas por compatibilidade.

Uma correção não está pronta quando foi aplicada somente a uma camada que o executável oficial não usa.

## 2. Fonte de versão

`RELEASE_VERSION` é a única fonte humana editável da versão de release.

CI deve verificar coerência entre:

- `RELEASE_VERSION`;
- `pubspec.yaml`;
- Inno Setup;
- backend e `/api/health`;
- labels Android;
- nomes de artefatos;
- workflows;
- READMEs e documentação de release.

Evitar números de versão hardcoded em texto de UI.

## 3. Classes de falha

Todo resultado operacional deve pertencer a uma classe:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

- falha recuperável encerra somente a tentativa;
- aborto encerra somente a operação ou rodada;
- indisponibilidade de módulo não derruba módulos independentes;
- somente falha fatal encerra o processo automaticamente;
- emergency stop libera inputs e encerra imediatamente;
- `NOT_FOUND`, `TIMEOUT` e `FAILED` não são automaticamente fatais.

## 4. Retry e ação one-shot

Retries repetem somente a etapa que falhou.

Depois que uma ação one-shot foi executada com sucesso, polling da resposta não pode repeti-la.

Toda política de retry deve declarar:

- espera inicial;
- número de retries e verificações totais;
- intervalo;
- condição de sucesso;
- condição de aborto;
- efeito sobre o loop superior;
- possibilidade de interrupção.

## 5. Gate obrigatório de janela e input

Antes de qualquer clique, key-down, texto ou captura fallback:

1. localizar novamente o alvo;
2. validar HWND;
3. validar título e classe;
4. validar PID/processo;
5. validar relação root/child;
6. validar visibilidade;
7. rejeitar minimizado;
8. confirmar foreground quando necessário;
9. revalidar imediatamente antes do input;
10. validar coordenadas dentro do client;
11. executar;
12. garantir mouse-up/key-up e cleanup.

Nunca confiar cegamente em HWND ou coordenadas de frame antigo.

## 6. Ownership de workers

Toda thread, task, timer, watcher e subprocesso deve declarar:

- owner;
- nome;
- condição de início;
- condição de parada;
- timeout;
- cancelamento;
- cleanup;
- resultado;
- política de retry;
- impacto de falha.

`daemon=True` não substitui lifecycle explícito.

Um monitor temporariamente cancelado para uma transação deve ser retomado em `finally`, salvo shutdown definitivo.

## 7. Integridade de estado

Cada arquivo persistente deve declarar uma política.

### Fail closed

Para RAW, sessões, Reviewer, Canonical Memory, cursores de evidência e estado de identidade.

### Quarentena e reconstrução

Somente para estado comprovadamente regenerável a partir de fontes íntegras.

### Backup e defaults

Para configuração recuperável, com aviso explícito.

Estado existente porém inválido de cursor, sessão ou identidade nunca deve ser tratado silenciosamente como vazio.

## 8. IDs de evidência

IDs de mensagens são identidade.

Novos IDs devem ser maiores que qualquer ID já existente em:

- SQLite;
- RAW;
- Processor;
- Vault.

Migração ou reinstalação não pode reiniciar IDs abaixo do `last_processed_id`.

## 9. Protocolos e localização

API e WebSocket retornam códigos estáveis, por exemplo:

```text
INVALID_TOKEN
GAME_NOT_FOUND
FOREGROUND_FAILED
IC_INPUT_NOT_FOUND
STATS_WINDOW_CHANGED
```

A UI converte códigos para PT-BR ou EN-US.

É proibido:

- usar frase localizada como contrato de protocolo;
- criar prosa visível em controller/service quando existe localização;
- exibir traceback ou detalhe interno diretamente ao usuário;
- traduzir IDs, campos JSON ou códigos técnicos.

## 10. Segurança de logs

Nunca registrar:

- access token;
- token em query string;
- conteúdo de secure storage;
- URL privada completa contendo segredo;
- RAW pessoal desnecessário;
- título de janela não relacionada;
- payload sensível integral.

Preferir campos estruturados:

```text
component
operation
error_code
recoverability
attempt
session_id/round_id
elapsed
```

## 11. Organização da árvore

A árvore ativa contém somente:

- entrypoints canônicos;
- módulos importados pelo runtime;
- testes permanentes;
- configuração exemplo/canônica;
- documentação vigente.

Não manter na árvore ativa:

- cópias `v03a`, `v03b`, `v03c` que já foram substituídas;
- probes descartáveis;
- scripts manuais já absorvidos por teste automatizado;
- relatórios de milestone usados como manual atual;
- arquivos duplicados PT/EN sem uma relação canônica clara.

O histórico Git é o arquivo de versões antigas. Quando uma implementação é consolidada:

1. criar nome canônico sem versão;
2. atualizar imports, subprocessos, workflows, testes e documentação;
3. validar a suíte;
4. remover snapshots substituídos;
5. registrar migração e rollback no PR.

Não transformar módulos com responsabilidades diferentes em um monólito apenas para reduzir contagem de arquivos.

## 12. Contrato de release

CI deve falhar quando houver divergência de versão, documentação, backend, Android, installer ou artefatos.

Workflows devem ler `RELEASE_VERSION` em vez de hardcodar a versão corrente.

Mudanças em `AGENTS*.md`, protocolos, estado persistente, entrypoints, workflows, installer ou localização devem acionar os jobs pertinentes.

## 13. Testes mínimos adicionais

Preservar ou adicionar testes para:

- sincronização de versão;
- rota empacotada;
- corrupção de cada estado persistente;
- cleanup de task/thread/subprocesso;
- janela substituída entre detecção e clique;
- PID incorreto;
- perda de foreground;
- retry sem repetir ação one-shot;
- falha de operação sem encerrar loop;
- localização de erros de controller/service;
- reconexão e fallback HTTP Flutter;
- liberação de controles GAME/STATS em dispose/desconexão.

## 14. Definição de pronto

Uma mudança de runtime ou organização só está pronta quando:

- a fonte ativa foi identificada;
- o entrypoint empacotado foi considerado;
- a classe de falha foi definida;
- cleanup foi demonstrado;
- estado persistente afetado possui política de corrupção;
- protocolos permanecem estáveis;
- PT-BR e EN-US foram verificados;
- testes cobrem sucesso, ausência, timeout, retry, cancelamento e shutdown conforme o risco;
- versão e artefatos estão sincronizados;
- validação real necessária foi registrada;
- não existe implementação correta somente em ZIP, Desktop ou build local.
