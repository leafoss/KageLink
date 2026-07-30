# Kage Pilot — documentação canônica

[English](KAGE_PILOT.en.md) · [Bíblia do KageLink](AGENTS.md) · [Runtime](AGENTS_RUNTIME.md) · [Dojo](AGENTS_DOJO.md)

O **Kage Pilot** é o subsistema do KageLink 3.5.0 responsável por percepção visual, controle seguro e treinamento repetido no Dojo de **Shinobi Story Online**.

Este é o único documento ativo do Kage Pilot em PT-BR. Documentos com nomes de versões, datas, hotfixes ou marcos permanecem apenas como histórico Git e não devem voltar a competir como documentação operacional.

## Superfície canônica

```text
Fonte pública: KageLink Installer/pc_agent/kage_pilot.py
Comando Dojo: python kage_pilot.py dojo
Loop público: KageLink Installer/pc_agent/kage_pilot_loop.py
Configuração: KageLink Installer/pc_agent/config/kage_pilot_dojo.json
Serviço: pc_agent.kage_pilot.DojoTrainingService
```

O instalador 3.5.0 distribui:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

Os executáveis auxiliares são fronteiras de isolamento e compatibilidade. Eles não constituem implementações concorrentes: devem encaminhar para a superfície canônica.

## Organização do código

- Uma responsabilidade possui um nome canônico sem versão.
- Versões pertencem a commits, tags, releases e changelog.
- Não criar novos arquivos `v03x`, `final2`, `new`, `hotfix` ou equivalentes.
- Módulos internos históricos ainda usados pelo motor validado permanecem temporariamente como compatibilidade.
- A remoção desses módulos exige extração semântica, suíte verde e nova validação real no jogo.

## Executar

Na pasta `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Mostrar configuração:

```powershell
python kage_pilot.py dojo --show-config
```

## Templates do treinador no 3.5.0

O KageLink aceita templates independentes para os modos 32×32 e 64×64. Eles pertencem à instalação do usuário e ficam fora de `Program Files`:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Regras:

- atualização normal deve preservar os templates;
- o treinamento falha fechado sem template válido;
- cada modo possui arquivo e metadados independentes;
- a detecção escolhe apenas uma correspondência visual estável;
- template antigo, coordenada antiga ou memória isolada não autorizam clique.

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

### Clique único

```text
trainer_clicks_per_round <= 1
```

Depois de `TRAINER_CLICK_ONCE`, retries de diálogo nunca podem procurar, mover até ou clicar novamente no treinador.

O fluxo padrão é:

```text
1 clique
→ 1 espera/verificação inicial
→ até 3 esperas/verificações adicionais
→ falha final encerra somente a rodada
```

Uma rodada sem diálogo consome seu número e não cria compensação silenciosa.

## Segurança

- F12 é parada global imediata.
- Toda falha, timeout ou transição libera inputs.
- `R` é a única tecla normalmente mantida em combate.
- Setas e `H` são pulsos curtos.
- `V` e `Y` são proibidos durante combate.
- Manual GAME input fica bloqueado enquanto o treinamento autônomo está ativo.
- Perda de foco, HWND, PID ou autoridade visual reduz ação e nunca aumenta agressividade.
- A autoridade de vitória continua sendo a linha real `has been Knocked-Out` com os gates de identidade atuais.
- Recuperação não pode ser declarada antes de HP ≥ 90% e Chakra ≥ 50%.

## Resultados

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

`NOT_FOUND`, `TIMEOUT` ou `FAILED` não são automaticamente fatais. A política da etapa deve declarar se encerra tentativa, rodada, módulo ou processo.

## Testes mínimos

```powershell
python -m py_compile kage_pilot.py kage_pilot_dojo.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python kage_pilot.py dojo --show-config
```

Também validar build e smoke de `KageLink.exe`, `KagePilotDojo.exe`, `KagePilotRound.exe`, Setup e APK.

Mudanças em captura, detecção, foco, input, KO, retorno ou recuperação exigem validação real em Windows + BYOND antes do merge funcional.

## Definição de pronto

- uma superfície pública canônica;
- compatibilidade externa preservada;
- nenhum novo nome versionado ativo;
- contratos de segurança preservados;
- testes e limitações registrados honestamente;
- PT-BR e EN-US equivalentes;
- arquivos pessoais e templates fora do Git;
- branch e PR rastreáveis;
- nenhuma versão correta somente em ZIP ou Desktop.
