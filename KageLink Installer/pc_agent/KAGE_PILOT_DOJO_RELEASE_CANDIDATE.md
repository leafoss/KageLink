# Kage Pilot Dojo — Release Candidate v0.3j

**Data:** 28/07/2026  
**Status:** preparado para nova validação física pré-merge; ainda sem merge  
**Baseline funcional:** `kage_pilot_loop_v03j.py`  
**Entrada pública:** `kage_pilot_dojo.py`

## Marco validado no jogo

A v0.3j completou rodadas reais em Shinobi Story Online com:

1. localização visual do Dojo Trainer;
2. exatamente um clique no treinador;
3. seleção de `Taijutsu Dojo Spar` pelo botão `OK` real;
4. detecção, orientação, ataque base e `H` guardado;
5. reconhecimento de `has been Knocked-Out` no chat;
6. liberação imediata de todas as teclas;
7. retorno ao treinador;
8. meditação por toggle de `V`;
9. recuperação até HP >= 90% e Chakra >= 50%;
10. `Y` ligado e desligado exatamente uma vez quando necessário;
11. conclusão em `READY` e `ROUND COMPLETE`.

O combate da v0.3j foi avaliado pelo usuário como excelente.

## Falha encontrada na validação longa

Em uma execução solicitada com dez rodadas, as rodadas 1 e 2 foram concluídas. Na rodada 3, o treinador foi localizado e clicado uma única vez, mas o diálogo não apareceu dentro da primeira janela de observação:

```text
ROUND 3: TRAINER_CLICK_ONCE
ROUND 3: DOJO_REQUEST_FAILED: DOJO_DIALOG_NOT_FOUND
DOJO_LOOP_STOPPED completed=2
```

O problema era o tratamento fatal de uma falha temporária do diálogo. A política foi corrigida sem alterar visão, combate, facing, KO, retorno ou recuperação.

Documentação detalhada:

```text
KAGE_PILOT_V0_3J_DIALOG_RETRY.md
KAGE_PILOT_V0_3J_DIALOG_RETRY.en.md
```

## Gate robusto treinador → diálogo

A política atual é:

```text
1 clique no treinador
→ espera inicial
→ verificação 1/4
→ espera adicional → verificação 2/4
→ espera adicional → verificação 3/4
→ espera adicional → verificação 4/4
```

Com os padrões:

```text
--dialog-delay 5
--dialog-retries 3
```

A conta é:

```text
1 verificação inicial + 3 retries = 4 verificações totais
```

Regras:

- depois de `TRAINER_CLICK_ONCE`, nunca pesquisar, mover-se até ou clicar novamente no treinador;
- todos os retries atuam apenas sobre o diálogo já solicitado;
- o diálogo e o controle `OK` são reenumerados e revalidados antes do clique;
- não reutilizar HWND ou coordenada de tentativa anterior;
- manter todos os inputs liberados durante as esperas;
- F12 interrompe as esperas;
- combate começa somente após `DOJO_DIALOG_CONFIRMED` e `DOJO_DIALOG_OK_CLICKED`;
- quatro falhas encerram apenas a rodada atual em `FINISHED_WITHOUT_COMBAT`;
- a próxima rodada usa o número seguinte, sem criar rodada compensatória.

## Política de segurança preservada

- `R` é a única tecla normalmente mantida durante combate.
- Setas e `H` são pulsos curtos.
- `V` e `Y` são toggles acionados somente por toque.
- Uma nova linha de KO é a única autoridade para encerrar o combate.
- Vitória libera todas as teclas antes do pós-combate.
- O treinador recebe no máximo um clique por rodada.
- O botão `OK` é acionado diretamente no diálogo atual validado.
- `V` exige confirmação visual do treinador.
- `V` e `Y` são proibidos durante combate.
- `MAP_SAVE_RESYNC` continua liberando todas as teclas.
- `H_SETTLE_HOLD` continua absoluto.
- F12 continua sendo a parada de emergência local.

## Orientação durante partículas

A v0.3j preserva o `MotionBurstGuard`, mas possui uma exceção estreita para impedir que o personagem permaneça olhando para o lado errado no corpo a corpo:

- somente alvo visual atual;
- somente `MELEE` com `d <= 1`;
- duas confirmações do mesmo alvo/direção;
- no máximo um pulso por episódio;
- sem liberar movimento, perseguição ou `H`;
- nunca por `CONTACT_MEMORY` isolado;
- nunca durante `MAP_SAVE_RESYNC` ou `H_SETTLE_HOLD`.

Detalhes:

```text
KAGE_PILOT_V0_3J_BURST_FACING.md
KAGE_PILOT_V0_3J_BURST_FACING.en.md
```

## Configuração pública

As configurações básicas ficam em:

```text
config/kage_pilot_dojo.json
```

Documentação:

```text
KAGE_PILOT_DOJO_CONFIGURATION.md
KAGE_PILOT_DOJO_CONFIGURATION.en.md
```

O arquivo controla rodadas, esperas, timeouts, recuperação, uso de `H`, threshold visual e logs. Os percentuais podem ser aumentados, mas não reduzidos abaixo de `90% HP / 50% Chakra`.

Mostrar a configuração efetiva:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --show-config
```

Executar com a configuração padrão:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py
```

## API para integração futura

```python
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService

service = DojoTrainingService()
service.start(DojoTrainingConfig(rounds=0))
status = service.snapshot()
service.stop()
```

A futura aba Game usará somente essa API. Ela não deverá importar módulos versionados nem duplicar lógica de combate. Textos visíveis deverão usar o sistema de internacionalização PT-BR/EN-US.

## Testes realizados

Workflow dedicado:

```text
.github/workflows/kage-pilot-v03.yml
```

No runner oficial Windows Server 2025 com Python 3.11, após a correção do diálogo:

```text
41 testes direcionados: OK
164 testes Kage Pilot: OK
292 testes completos PC Agent: OK
compilação: OK
configuração canônica: OK
```

Os nove testes novos cobrem sucesso nas verificações 1, 2, 3 e 4, diálogo ausente, clique único, F12, HWND desaparecido e falha da rodada 3 sem interromper uma execução de dez rodadas.

O CI valida código e configuração, mas não substitui a execução física em Windows/BYOND com a janela real do jogo.

## Conformidade com a Bíblia

- GitHub permanece como fonte técnica canônica.
- Toda mudança termina em commit identificável.
- Documentação relevante existe em PT-BR e EN-US.
- A política foi centralizada no caminho canônico do release candidate.
- Nenhuma lógica de combate foi duplicada na futura fronteira do app.
- Um gate Windows automatizado protege o merge.
- Nenhum merge ocorre sem aprovação explícita de Rafael.

## Próximo marco: treinamento adaptativo

Permanece documentado separadamente em:

```text
KAGE_PILOT_DOJO_ADAPTIVE_TRAINING.md
KAGE_PILOT_DOJO_ADAPTIVE_TRAINING.en.md
```

A primeira etapa futura será telemetria passiva. Aprendizado online não faz parte deste release candidate.

## Checklist final antes do merge

- [x] primeiro loop completo validado no jogo;
- [x] v0.3j aprovada em rodada real;
- [x] clique único no treinador confirmado;
- [x] KO → liberação → pós-combate confirmado;
- [x] `Y` ligado e desligado exatamente uma vez quando necessário;
- [x] falha de diálogo da rodada 3 diagnosticada;
- [x] uma espera inicial + três retries implementados;
- [x] rodada sem diálogo continua para a próxima;
- [x] nove testes de regressão do diálogo adicionados;
- [x] 41 testes direcionados em `OK`;
- [x] 164 testes Kage Pilot em `OK`;
- [x] 292 testes completos do PC Agent em `OK`;
- [ ] validar fisicamente o retry do diálogo no jogo;
- [ ] executar novamente várias rodadas consecutivas pelo comando canônico;
- [ ] confirmar ausência de segundo clique no treinador;
- [ ] confirmar ausência de teclas vazando ao PowerShell;
- [ ] revisar `git status` e arquivos não rastreados;
- [ ] retirar PR de draft após os gates reais;
- [ ] merge somente após aprovação explícita de Rafael.

## Decisão arquitetural

Os scripts `v03a` até `v03j` permanecem como histórico interno durante este release candidate. O contrato estável continua:

```text
kage_pilot_dojo.py
→ DojoTrainingConfig
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
```

A consolidação física dos módulos históricos poderá ocorrer depois do merge, em PR separado, para não arriscar regressão na baseline que já funciona no jogo.
