# Kage Pilot

[English](KAGE_PILOT.en.md) · [Bíblia do KageLink](AGENTS.md)

O **Kage Pilot** é o subsistema local e experimental do KageLink para gravação de demonstrações, percepção visual, controle de combate e treinamento repetido no Dojo de **Shinobi Story Online**.

Este arquivo é a documentação canônica em PT-BR. Documentos antigos com nomes `V0_1`, `V0_2`, `V0_3`, `V03J`, datas ou nomes de hotfix pertencem ao histórico Git e não devem voltar a competir como documentação ativa.

## Estado atual

- **Entrada pública única:** `KageLink Installer/pc_agent/kage_pilot.py`.
- **Comando validado do Dojo:** `python kage_pilot.py dojo`.
- **Configuração oficial:** `KageLink Installer/pc_agent/config/kage_pilot_dojo.json`.
- **Serviço público:** `pc_agent.kage_pilot.DojoTrainingService`.
- **Workflow:** `.github/workflows/kage-pilot.yml`.
- **Status:** baseline do Dojo validada fisicamente e mergeada no PR #16 em 29/07/2026.

A execução longa registrada completou:

```text
DOJO_LOOP_FINISHED requested=10 processed=10 completed=10
finished_without_combat=0 failed=0 emergency_stopped=0
```

## Regra de organização

O Kage Pilot possui **uma única superfície pública**, mas continua modular internamente.

```text
kage_pilot.py
    ├── dojo                         # fluxo canônico validado
    ├── record / mark                # dataset
    ├── train / train-v2             # treinamento
    ├── pilot / pilot-v2             # execução de política
    ├── capture-template
    ├── init-config
    └── dojo-v2                      # ferramenta experimental anterior
```

Módulos internos devem ser nomeados pela responsabilidade, não pela versão. Novas versões pertencem a commits, tags, releases e changelog — não a novos arquivos como `final2`, `v03l` ou `hotfix_new`.

## Arquitetura funcional

```text
captura HWND específica do jogo
        ↓
percepção visual e estado temporal
        ↓
seleção de alvo e decisão de combate
        ↓
planejador seguro de teclas
        ↓
controle Windows validado
        ↓
KO confirmado pelo chat
        ↓
retorno ao treinador e recuperação
        ↓
próxima rodada
```

O aprendizado pode escolher políticas ou parâmetros permitidos, mas não pode enfraquecer os gates de segurança.

## Executar o Dojo

Na pasta `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py dojo
```

Exemplo com dez rodadas:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Mostrar a configuração efetiva sem iniciar:

```powershell
python kage_pilot.py dojo --show-config
```

`--rounds 0` executa continuamente até parada explícita ou F12.

## State machine protegida

```text
ROUND_START
→ SEARCH_TRAINER
→ CONFIRM_TRAINER
→ CLICK_TRAINER_ONCE
→ WAIT_DIALOG
→ CHECK_DIALOG
→ CLICK_DIALOG_OK
→ WAIT_SPAWN
→ COMBAT_ACTIVE
→ KO_CONFIRMED
→ RETURN_TO_TRAINER
→ RECOVERY
→ ROUND_COMPLETE
```

Saídas alternativas:

```text
falha recuperável
→ encerrar somente a tentativa ou rodada
→ preservar loop superior quando seguro

F12
→ EMERGENCY_STOP
→ liberar todos os inputs
→ encerrar o loop
```

## Contrato absoluto do treinador

```text
trainer_clicks_per_round <= 1
```

Depois de `TRAINER_CLICK_ONCE`, nenhuma espera ou retry de diálogo pode:

- clicar novamente no treinador;
- procurar outro treinador para repetir o pedido;
- mover o personagem para reiniciar a interação;
- abrir uma segunda solicitação de spar.

O gate de diálogo usa:

```text
1 clique no treinador
→ 1 verificação inicial
→ até 3 verificações adicionais
→ nenhuma repetição do clique
```

Se o diálogo não aparecer após quatro verificações, a rodada é marcada como `FINISHED_WITHOUT_COMBAT` e a próxima rodada pode começar.

## Aquisição visual do treinador

A percepção visual gera um candidato; ela não autoriza diretamente o clique.

O fluxo validado exige:

1. scan inicial;
2. confirmação visual estável;
3. manobra lateral curta quando o próprio personagem possivelmente oculta o treinador;
4. nova confirmação visual;
5. clique único.

Memória antiga de posição nunca autoriza `V` sozinha.

## Combate

Regras permanentes:

- `R` é a única tecla normalmente mantida;
- setas e `H` são pulsos curtos;
- `V` e `Y` são toggles por toque e são proibidos durante combate;
- perda de alvo, foco ou autoridade visual deve reduzir a ação, não aumentar a agressividade;
- `MAP_SAVE_RESYNC` e `H_SETTLE_HOLD` permanecem holds absolutos;
- correção de facing durante partículas é limitada a alvo visual atual, adjacente e confirmado;
- qualquer erro ou transição deve liberar teclas pendentes.

## Autoridade de KO

A autoridade de término de combate continua sendo a linha real:

```text
has been Knocked-Out
```

A proteção entre rodadas mantém o último oponente aceito. Um KO com o mesmo nome do oponente anterior é rejeitado até existir evidência visual suficiente de um oponente atual diferente.

Fluxo validado:

```text
KO repetido do oponente anterior
→ release_all
→ invalidar alvo atual
→ continuar combate
→ readquirir alvo

novo nome + evidência visual atual
→ aceitar vitória
→ release_all
→ iniciar pós-combate
```

## Retorno e recuperação

A rodada só termina quando o personagem volta ao estado seguro de recuperação.

Pisos que não podem ser reduzidos por configuração:

```text
HP >= 90%
Chakra >= 50%
```

- `V` só pode ser acionado após confirmação visual atual do treinador.
- `Y` só pode permanecer ligado durante meditação e deve ser desligado ao atingir o limiar.
- timeout de recuperação não deve fingir sucesso.

## Contadores de rodada

```text
requested
processed
completed
finished_without_combat
failed
emergency_stopped
```

Uma rodada sem combate consome seu número. `--rounds 10` processa no máximo as rodadas numeradas de 1 a 10; não cria rodada 11 para compensação silenciosa.

## Configuração

O JSON oficial expõe somente valores seguros e compreensíveis:

- rodadas;
- tempos de espera e timeout;
- limiares de recuperação acima dos pisos protegidos;
- ativação de H;
- threshold do treinador;
- diretório de logs.

Configuração inválida deve falhar fechado com erro identificável. Chaves desconhecidas não são ignoradas silenciosamente.

Invariantes de segurança não são configuráveis.

## Dataset e ferramentas anteriores

A entrada única preserva os comandos de gravação e aprendizado:

```powershell
python kage_pilot.py record
python kage_pilot.py mark
python kage_pilot.py train --model kage_pilot_model.json
python kage_pilot.py train-v2 --model kage_pilot_temporal.json
python kage_pilot.py pilot --model kage_pilot_model.json --seconds 60
python kage_pilot.py pilot-v2 --model kage_pilot_temporal.json --seconds 60
```

Dados pessoais e artefatos de runtime permanecem fora do Git:

```text
.venv-kage-pilot/
data/kage_pilot/
kage_pilot_loop_logs/
kage_pilot_live_test_*.jsonl
kage_pilot_shadow_test_*.jsonl
config.json
```

## Treinamento adaptativo futuro

A camada adaptativa permanece proposta, não ativa por padrão.

Evolução autorizável:

```text
telemetria passiva
→ análise offline
→ challenger em shadow mode
→ bandit contextual entre políticas pré-aprovadas
→ promoção humana explícita
```

A função objetivo correta é completar rodadas seguras por unidade de tempo, considerando combate, retorno e recuperação — não apenas vencer a luta rapidamente.

Nunca podem ser aprendidos automaticamente:

- a autoridade de KO;
- clique único no treinador;
- pisos de recuperação;
- gates de foco/janela;
- whitelist de teclas;
- F12;
- proibição de `V`/`Y` em combate;
- liberação de inputs;
- proteções de água, partículas e perseguição cega.

## Testes

Workflow canônico:

```text
.github/workflows/kage-pilot.yml
```

Validação mínima:

```powershell
python -m compileall -q pc_agent/kage_pilot
python -m py_compile kage_pilot.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python kage_pilot.py dojo --show-config
```

Também devem existir testes para:

- um único clique por rodada;
- diálogo encontrado em cada tentativa possível;
- diálogo ausente sem encerrar o loop;
- F12 durante toda espera importante;
- subprocesso com erro/timeout;
- KO repetido rejeitado;
- KO correto aceito;
- alvo/janela alterados antes do input;
- nenhuma tecla presa após falha;
- contadores de rodadas;
- configuração fail-closed.

## Limite de validação

Testes automatizados não substituem Windows + BYOND + jogo real. Mudanças em captura, detecção, foco, input, KO, retorno ou recuperação exigem registrar a validação física necessária.

## Definição de pronto

Uma mudança do Kage Pilot está pronta quando:

- existe apenas uma entrada pública estável;
- nomes ativos não usam sufixos de versão;
- contratos de segurança foram preservados;
- testes automatizados pertinentes passaram;
- limitações reais foram registradas;
- PT-BR e EN-US permanecem equivalentes;
- runtime/config/logs pessoais não foram versionados;
- a mudança está em branch e PR rastreáveis;
- nenhuma “versão correta” existe somente em ZIP ou Desktop.
