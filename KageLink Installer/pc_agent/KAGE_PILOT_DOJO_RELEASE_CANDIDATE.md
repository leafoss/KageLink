# Kage Pilot Dojo — Release Candidate

**Data:** 28/07/2026  
**Status:** candidato a release; ainda sem merge  
**Baseline funcional validada:** `kage_pilot_loop_v03i.py`

## Marco validado no jogo

A primeira rodada completa foi executada em Shinobi Story Online com sucesso:

1. localizar visualmente o Dojo Trainer;
2. clicar exatamente uma vez no treinador;
3. aguardar 5 segundos;
4. selecionar `Taijutsu Dojo Spar` e clicar diretamente no botão `OK`;
5. aguardar 5 segundos pelo adversário;
6. detectar, enfrentar e derrotar o inimigo;
7. reconhecer uma nova linha de chat contendo `has been Knocked-Out`;
8. liberar todas as teclas imediatamente;
9. procurar e retornar ao Dojo Trainer;
10. iniciar meditação com um toque em `V`;
11. aguardar HP >= 90% e Chakra >= 50%;
12. desligar modos persistentes e encerrar em `READY`;
13. registrar `ROUND 1: COMPLETE`.

A mesma execução também atravessou uma ressincronização causada por um salvamento/travamento do mapa, descartou o alvo e o facing antigos e readquiriu o inimigo.

## Política de segurança preservada

- `R` é a única tecla mantida durante combate normal.
- Setas e `H` são pulsos curtos.
- `V` e `Y` são toggles acionados somente por toque.
- Uma linha nova de KO é a única autoridade para encerrar o combate.
- Vitória libera todas as teclas antes do pós-combate.
- Memória do treinador pode orientar movimento, mas somente confirmação visual autoriza `V`.
- O treinador recebe exatamente um clique por solicitação.
- Falha ao abrir o diálogo encerra a solicitação com segurança; não há segundo clique automático.
- `F12` continua sendo a parada de emergência local.

## Comportamento conservador conhecido

Em alguns momentos o agente permanece parado aguardando o adversário se aproximar. Isso ocorre quando não existe alvo visual validado ou quando o MotionBurstGuard bloqueia temporariamente movimento e habilidade por excesso de partículas/movimento na tela.

Esse comportamento é atualmente preferível à perseguição cega. Ele poderá ser refinado depois de uma série maior de rodadas reais, sem enfraquecer a proteção contra água, partículas, salvamento do mapa e identidades antigas.

## Entrada pública estável

Use:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --rounds 1
```

O script público chama o motor v0.3i em processo isolado. Os scripts `v03a` até `v03i` devem ser tratados como implementação histórica/interna durante o release candidate.

## API para integração futura

```python
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService

service = DojoTrainingService()
service.start(DojoTrainingConfig(rounds=0))  # contínuo até desligar o toggle
status = service.snapshot()
service.stop()
```

Contrato público:

- `DojoTrainingConfig`: parâmetros normalizados do treinamento;
- `DojoTrainingService.start()`: inicia somente uma instância;
- `DojoTrainingService.stop()`: solicita encerramento do grupo de processos;
- `DojoTrainingService.snapshot()`: estado imutável para UI;
- `DojoTrainingPhase`: `idle`, `starting`, `requesting`, `combat`, `victory`, `recovery`, `ready`, `stopping`, `stopped`, `error`.

## Futuro toggle na aba Game

A integração visual não faz parte deste release candidate. Quando for implementada:

- toggle `Dojo` ligado: `start(DojoTrainingConfig(rounds=0))`;
- toggle desligado: `stop()`;
- status e mensagens devem usar o sistema de internacionalização PT-BR/EN-US;
- a UI não deve importar módulos versionados nem reproduzir lógica de combate;
- somente `DojoTrainingService` deve atravessar a fronteira entre app e Kage Pilot.

## Checklist antes do merge

- [ ] suíte completa `test_kage_pilot*.py` finaliza em `OK`;
- [ ] testes do serviço público finalizam em `OK`;
- [ ] comando canônico `kage_pilot_dojo.py --rounds 1` completa uma rodada real;
- [ ] executar pelo menos 3 rodadas consecutivas sem teclas vazando para o PowerShell;
- [ ] confirmar clique único no treinador em todas as rodadas;
- [ ] confirmar KO -> liberação imediata -> pós-combate em todas as rodadas;
- [ ] confirmar que `Y`, quando usado, liga e desliga exatamente uma vez;
- [ ] revisar arquivos não rastreados e manter modelos/templates locais fora do Git;
- [ ] revisar o diff e a documentação PT-BR/EN-US;
- [ ] retirar o PR de draft somente após revisão;
- [ ] merge somente após aprovação explícita de Rafael.

## Decisão arquitetural

Durante o polimento, a implementação v0.3i validada permanece intacta. A consolidação física dos módulos versionados será considerada somente depois da validação do ponto de entrada público. Isso evita introduzir uma regressão em um loop que já funcionou no jogo.
