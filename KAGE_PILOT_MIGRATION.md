# Migração gradual dos módulos internos do Kage Pilot

[English](KAGE_PILOT_MIGRATION.en.md) · [Kage Pilot](KAGE_PILOT.md) · [Runtime](AGENTS_RUNTIME.md)

**Estado:** fase 1 — fronteiras canônicas e CI, sem remoção do motor validado  
**Base:** KageLink 3.5.0  
**Regra:** nenhum arquivo complexo `v03*` será removido antes da CI verde e de nova validação real no Windows/BYOND.

## Objetivo

Substituir nomes baseados em versões por nomes baseados em responsabilidade, preservando o comportamento fisicamente validado e mantendo rollback claro pelo Git.

## Superfície canônica interna

```text
pc_agent.kage_pilot.dojo_training_service
pc_agent.kage_pilot.dojo_request
pc_agent.kage_pilot.dojo_templates
pc_agent.kage_pilot.trainer_search
pc_agent.kage_pilot.ko_identity
pc_agent.kage_pilot.combat_control
pc_agent.kage_pilot.post_combat

kage_pilot.py
kage_pilot_loop.py
kage_pilot_round.py
```

Novos imports, specs, serviços e integrações devem usar esses nomes.

## Migração efetiva nesta fase

- `ko_identity.py` tornou-se a implementação canônica do gate de identidade de KO;
- `ko_identity_v03k.py` permanece apenas como wrapper de compatibilidade;
- `dojo_training_service.py` tornou-se a implementação canônica do serviço instalado/fonte;
- `dojo_training_v03k.py` permanece apenas como wrapper de compatibilidade;
- o serviço em modo fonte executa `kage_pilot_loop.py`;
- o loop em modo fonte executa `kage_pilot_round.py`;
- os specs do PyInstaller usam os dois entrypoints sem versão;
- API de templates e novos testes usam fronteiras canônicas;
- a CI possui um gate que impede referências versionadas nos consumidores públicos.

## Compatibilidade ainda preservada

A cadeia abaixo continua fornecendo o motor fisicamente validado:

```text
kage_pilot_loop_v03g.py
kage_pilot_loop_v03j.py
kage_pilot_live_v03.py
kage_pilot_live_v03e_round.py
kage_pilot_live_v03g_round.py
kage_pilot_live_v03h_round.py
kage_pilot_live_v03i_round.py
kage_pilot_live_v03j_round.py
kage_pilot_live_v03k_round.py
pc_agent/kage_pilot/*_v03*.py
```

Esses arquivos não são superfícies públicas novas. São fornecedores temporários de compatibilidade e não devem receber novas versões paralelas.

## Condições para a próxima extração

Um grupo de arquivos só pode ser convertido em implementação canônica e removido quando:

1. todos os seus consumidores oficiais usam o nome por responsabilidade;
2. existe teste canônico equivalente para cada comportamento protegido;
3. a suíte Python completa está verde;
4. os três executáveis compilam e passam smoke test;
5. Setup e APK compilam;
6. a validação física correspondente foi executada;
7. o resultado e os logs foram registrados neste documento ou no PR;
8. existe rollback identificável.

## Matriz de validação física obrigatória

Registrar para cada execução:

```text
commit testado
versão do Setup
Windows
versão BYOND/jogo
modo do template: 32 ou 64
configuração usada
caminho do log
resultado
anomalias
```

### A. Inicialização e empacotamento

- instalar/atualizar sem Python de sistema;
- abrir `KageLink.exe`;
- iniciar `KagePilotDojo.exe` pela UI/API;
- confirmar que `KagePilotRound.exe` é iniciado sem console órfão;
- encerrar e confirmar ausência de processos filhos órfãos.

### B. Templates

- testar template 32×32 isoladamente;
- testar template 64×64 isoladamente;
- testar os dois configurados simultaneamente;
- confirmar que update/reinstall preserva ambos;
- confirmar falha fechada sem template válido.

### C. Trainer e diálogo

- exatamente um clique no Trainer por rodada;
- diálogo encontrado na verificação 1;
- diálogo encontrado na verificação 2;
- diálogo encontrado na verificação 3;
- diálogo encontrado na verificação 4;
- diálogo nunca encontrado: rodada termina sem combate e a próxima começa;
- nenhum retry move, procura ou clica novamente no Trainer;
- HWND/PID inválido bloqueia o OK.

### D. Combate

- aproximação e facing em alvo visível;
- `R` mantido e setas/`H` usados somente como pulsos;
- particle burst bloqueia movimento e `H`;
- correção única de facing durante burst quando autorizada;
- map-save resync libera inputs e readquire percepção;
- perda de foco/janela bloqueia input.

### E. KO e identidade

- KO de oponente atual e diferente é aceito;
- KO repetido do oponente anterior é rejeitado;
- rejeição libera inputs, invalida o alvo e mantém combate;
- KO sem duas evidências visuais atuais não encerra a rodada;
- nome completo com rank, vírgula e espaços é preservado.

### F. Retorno e recuperação

- retorno visual ao Trainer;
- self-occlusion usa no máximo um pulso perpendicular;
- memória isolada nunca autoriza `V`;
- recuperação exige HP ≥ 90% e Chakra ≥ 50%;
- `Y` liga/desliga somente nas condições protegidas;
- cleanup desliga `Y` quando necessário.

### G. Parada e isolamento

- F12 durante busca do Trainer;
- F12 durante cada espera de diálogo;
- F12 durante combate;
- F12 durante retorno/recuperação;
- nenhuma tecla permanece pressionada;
- GAME manual permanece bloqueado durante treino;
- chat, histórico, STATS e LeafOS permanecem disponíveis.

## Decisão após validação

- **Aprovado:** extrair o próximo grupo de implementação para o módulo canônico e converter o arquivo antigo em wrapper fino.
- **Falhou:** manter o fornecedor antigo, corrigir em branch e repetir somente os cenários afetados mais a regressão completa.
- **Não testado:** proibir remoção.

## Ordem sugerida das próximas fases

1. serviço e identidade de KO — já migrados;
2. templates e busca do Trainer;
3. pedido/dialog gate;
4. controle de combate e particle safety;
5. pós-combate/retorno/recuperação;
6. composição final da rodada;
7. composição final do loop;
8. remoção dos wrappers sem consumidores.
