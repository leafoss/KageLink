# Kage Pilot Dojo — Release Candidate v0.3j

**Data:** 28/07/2026  
**Status:** preparado para validação final pré-merge; ainda sem merge  
**Baseline funcional validada:** `kage_pilot_loop_v03j.py`  
**Entrada pública:** `kage_pilot_dojo.py`

## Marco validado no jogo

A v0.3j completou uma rodada real em Shinobi Story Online:

1. localizou visualmente o Dojo Trainer;
2. clicou exatamente uma vez no treinador;
3. aguardou o tempo configurado;
4. selecionou `Taijutsu Dojo Spar` e acionou diretamente o botão `OK`;
5. aguardou o adversário;
6. detectou, orientou-se, usou ataque base e `H` guardado;
7. reconheceu `has been Knocked-Out` no chat;
8. liberou todas as teclas;
9. retornou ao treinador de `d=10` até `d=1`;
10. iniciou meditação com um toque em `V`;
11. ligou `Y` quando HP chegou a 96% e Chakra permanecia em 32%;
12. desligou `Y` quando Chakra chegou a 52%;
13. alcançou `READY`;
14. encerrou com `ROUND 1: COMPLETE` e código de saída `0`.

O usuário avaliou o combate da v0.3j como excelente e aprovou o comportamento para promoção ao ponto de entrada público.

## Política de segurança preservada

- `R` é a única tecla normalmente mantida durante combate.
- Setas e `H` são pulsos curtos.
- `V` e `Y` são toggles acionados somente por toque.
- Uma nova linha de KO é a única autoridade para encerrar o combate.
- Vitória libera todas as teclas antes do pós-combate.
- O treinador recebe exatamente um clique por solicitação.
- O botão `OK` é acionado diretamente no diálogo correto.
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

O arquivo controla:

- rodadas;
- espera após clicar no treinador;
- timeout do diálogo;
- espera após o botão `OK`;
- timeout de combate;
- timeout de pós-combate;
- timeout de busca do treinador;
- HP e Chakra desejados;
- uso de `H`;
- threshold visual;
- pasta de logs.

Os percentuais podem ser aumentados, mas não reduzidos abaixo de `90% HP / 50% Chakra`.

Mostrar a configuração efetiva:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --show-config
```

Executar com a configuração padrão:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py
```

Argumentos do PowerShell sobrescrevem temporariamente o JSON.

## API para integração futura

```python
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService

service = DojoTrainingService()
service.start(DojoTrainingConfig(rounds=0))
status = service.snapshot()
service.stop()
```

A futura aba Game usará somente essa API. Ela não deverá importar módulos versionados nem duplicar lógica de combate. Textos visíveis deverão usar o sistema de internacionalização PT-BR/EN-US.

## Testes realizados nesta revisão

Foi adicionado o workflow dedicado:

```text
.github/workflows/kage-pilot-v03.yml
```

No runner oficial Windows Server 2025 com Python 3.11, foram aprovados:

- instalação das dependências;
- compilação de todos os módulos do Kage Pilot;
- testes direcionados do release candidate;
- suíte completa `test_kage_pilot*.py`;
- validação de `kage_pilot_dojo.py --show-config`;
- suíte completa do PC Agent: **283 testes, todos em `OK`**.

A primeira execução da suíte completa revelou um teste antigo do LeafOS preso à data literal `2026-07-26`. O comportamento estava correto, mas o teste falhava quando executado em `2026-07-28`. A asserção foi corrigida para validar o contrato estável `YYYY-MM-DD_001`, e a suíte seguinte terminou integralmente em `OK`.

O CI valida código, configuração e empacotamento, mas não substitui a execução física em Windows/BYOND com a janela real do jogo.

## Conformidade com a Bíblia

- GitHub permanece como fonte técnica canônica.
- Toda mudança termina em commit identificável.
- Documentação relevante existe em PT-BR e EN-US.
- A configuração pertence ao domínio/serviço, não à futura UI.
- O app terá uma fronteira pública pequena e estável.
- Mudanças comportamentais foram aditivas e validadas no jogo.
- Um gate Windows automatizado passa a proteger o merge.
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
- [x] KO -> liberação -> pós-combate confirmado;
- [x] `Y` ligado e desligado exatamente uma vez quando necessário;
- [x] entrada pública promovida para v0.3j;
- [x] configuração JSON canônica adicionada;
- [x] documentação PT-BR/EN-US revisada;
- [x] testes direcionados no Windows em `OK`;
- [x] suíte completa `test_kage_pilot*.py` no Windows em `OK`;
- [x] suíte completa do PC Agent: 283 testes em `OK`;
- [x] `kage_pilot_dojo.py --show-config` validado no Windows CI;
- [x] compilação e empacotamento do PC Agent em `OK`;
- [ ] executar 3 rodadas consecutivas pelo comando canônico no jogo real;
- [ ] confirmar ausência de teclas vazando ao PowerShell nessas três rodadas;
- [ ] revisar `git status` e arquivos não rastreados no computador do usuário;
- [ ] retirar PR de draft após os gates reais acima;
- [ ] merge somente após aprovação explícita de Rafael.

## Decisão arquitetural

Os scripts `v03a` até `v03j` permanecem como histórico interno durante este release candidate. O contrato estável é:

```text
kage_pilot_dojo.py
→ DojoTrainingConfig
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
```

A consolidação física dos módulos históricos poderá ocorrer depois do merge, em PR separado, para não arriscar regressão na baseline que já funciona no jogo.
