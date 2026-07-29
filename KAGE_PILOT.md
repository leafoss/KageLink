# Kage Pilot — documentação canônica

[English](KAGE_PILOT.en.md) · [Bíblia do KageLink](AGENTS.md) · [Runtime e organização](AGENTS_RUNTIME.md)

Este arquivo é a **única documentação operacional canônica do Kage Pilot**. Os documentos `KAGE_PILOT_V0_3*` registraram etapas de desenvolvimento e continuam recuperáveis pelo histórico Git, mas não devem ser usados como instrução ativa.

## Estado validado

- Linha fisicamente validada: Dojo v0.3j com runtime de round v0.3k.
- Merge de referência: PR #16, commit `3c819d346d044a0c71650fcf182d3815385b7672`.
- Validação real: 10 rodadas solicitadas, 10 processadas e 10 concluídas, sem falhas nem parada de emergência.
- GitHub é a única fonte oficial; ZIPs, Desktop, ambientes virtuais, logs e configurações locais não são fonte canônica.

## Superfície pública

```text
kage_pilot.py             CLI geral estável do subsistema
kage_pilot_dojo.py        entrada estável do treinamento no Dojo
pc_agent/kage_pilot/      implementação interna modular
config/kage_pilot_dojo.json
```

Novas evoluções não devem criar outro entrypoint com sufixo de versão. A implementação por trás dos nomes estáveis deve ser substituída somente após testes.

## Comando recomendado para o Dojo

A partir de `KageLink Installer/pc_agent`:

```powershell
.\.venv-kage-pilot\Scripts\python.exe .\kage_pilot_dojo.py `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

## Máquina de estados protegida

```text
ROUND_START
→ SEARCH_TRAINER
→ CONFIRM_TRAINER
→ CLICK_TRAINER_ONCE
→ WAIT_DIALOG
→ CLICK_DIALOG_OK
→ WAIT_SPAWN
→ COMBAT_ACTIVE
→ KO_CONFIRMED
→ RETURN_TO_TRAINER
→ RECOVERY
→ ROUND_COMPLETE
```

Falhas recuperáveis encerram somente a etapa ou a rodada. Somente falha fatal comprovada ou F12 encerra todo o loop.

## Contratos permanentes

### Clique único no treinador

```text
trainer_clicks_per_round <= 1
```

Retries de diálogo nunca repetem o clique nem iniciam nova busca do treinador.

### Gate do diálogo

- uma verificação inicial;
- até três retries adicionais;
- nenhuma repetição da ação one-shot;
- após a falha final, a rodada é `FINISHED_WITHOUT_COMBAT` e o loop pode seguir.

### Identidade de KO

- o último adversário aceito é preservado entre rodadas;
- repetição do mesmo nome pode ser rejeitada quando o corpo anterior ainda está visível;
- KO rejeitado libera inputs, invalida o alvo e continua o combate;
- vitória exige identidade e evidência visual atual compatíveis.

### Segurança de input

- `R` pode permanecer pressionado apenas durante o contrato de combate;
- setas e `H` são pulsos curtos;
- `V` e `Y` são toggles por toque e proibidos durante combate;
- toda falha, timeout, cancelamento e transição crítica libera inputs;
- F12 permanece parada de emergência e todas as esperas devem ser interrompíveis.

### Recuperação

Pisos validados:

```text
HP >= 90%
Chakra >= 50%
```

A rodada não conclui antes dos thresholds configurados.

## Organização de código

“Um Kage Pilot” significa **uma superfície canônica**, não um arquivo monolítico misturando visão, combate, pós-combate, configuração e serviço.

Regras:

1. um entrypoint público estável por função;
2. módulos internos nomeados por responsabilidade, não por tentativa (`v03a`, `v03b`...);
3. experimentos não são importados pelo runtime oficial;
4. snapshots deixam a árvore ativa quando o equivalente canônico possui testes;
5. o histórico Git substitui arquivos mantidos apenas como arquivo morto;
6. testes permanentes descrevem contratos, não versões transitórias.

## Configuração

Fonte padrão:

```text
config/kage_pilot_dojo.json
```

A configuração rejeita chaves desconhecidas e permite overrides por CLI.

## Telemetria

Logs devem identificar:

```text
round
state
operation
attempt
result
error_code
recoverability
elapsed
```

`completed=N` só atualiza o número público de rodadas em resumos autoritativos:

```text
DOJO_LOOP_FINISHED
DOJO_LOOP_STOPPED
DOJO_FINAL
```

## Testes obrigatórios

Preservar cobertura para:

- clique único;
- diálogo em cada tentativa e diálogo ausente;
- treinador ocluído e revelação lateral;
- troca de HWND e perda de foreground;
- KO repetido rejeitado e KO correto aceito;
- subprocesso com nonzero/timeout;
- recuperação;
- round abortado sem encerrar o loop;
- F12 durante esperas;
- nenhuma tecla presa.

## Definição de pronto

Uma alteração só está pronta quando:

- usa a superfície canônica;
- não cria novo arquivo versionado para substituir a implementação anterior;
- possui testes proporcionais ao risco;
- preserva F12 e cleanup;
- registra quando depende de validação Windows/BYOND real;
- mantém documentação equivalente PT-BR/EN-US;
- não deixa a versão correta somente em ZIP, log ou pasta local.
