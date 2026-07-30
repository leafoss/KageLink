# Kage Pilot — documentação canônica

[English](KAGE_PILOT.en.md) · [Bíblia do KageLink](AGENTS.md) · [Addendum 3.5](AGENTS_3_5.md) · [Runtime](AGENTS_RUNTIME.md) · [Dojo](AGENTS_DOJO.md)

O **Kage Pilot** é o subsistema do KageLink 3.5.0 responsável por percepção visual, controle seguro e treinamento repetido no Dojo de **Shinobi Story Online**.

Este é o único documento ativo do Kage Pilot em PT-BR. Documentos com nomes de versões, datas, hotfixes ou marcos pertencem ao histórico Git e não devem competir como documentação operacional.

## Superfície canônica

```text
Fonte pública: KageLink Installer/pc_agent/kage_pilot.py
Comando Dojo: python kage_pilot.py dojo
Loop público: KageLink Installer/pc_agent/kage_pilot_loop.py
Configuração: KageLink Installer/pc_agent/config/kage_pilot_dojo.json
Serviço: pc_agent.kage_pilot.DojoTrainingService
```

O instalador 3.5.0 distribui `KageLink.exe`, `KagePilotDojo.exe` e `KagePilotRound.exe`. Os executáveis auxiliares são fronteiras de isolamento e compatibilidade; devem encaminhar para a superfície canônica e não constituem implementações concorrentes.

## Organização

- uma responsabilidade possui um nome canônico sem versão;
- versões pertencem a commits, tags, releases e changelog;
- não criar novos arquivos `v03x`, `final2`, `new`, `hotfix` ou equivalentes;
- módulos internos versionados ainda usados pelo motor validado permanecem temporariamente como compatibilidade;
- remover esses módulos exige migração de imports/specs/testes, CI verde e nova validação real.

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

## Templates do treinador

O 3.5.0 aceita templates independentes para 32×32 e 64×64 em:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Atualizações normais preservam os templates. O treinamento falha fechado sem template válido. Cada modo possui arquivo e metadados independentes, e somente uma correspondência visual estável autoriza a continuidade.

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

Contrato absoluto:

```text
trainer_clicks_per_round <= 1
```

Depois de `TRAINER_CLICK_ONCE`, retries de diálogo nunca podem procurar, mover até ou clicar novamente no treinador.

Fluxo padrão:

```text
1 clique
→ 1 espera/verificação inicial
→ até 3 esperas/verificações adicionais
→ falha final encerra somente a rodada
```

Uma rodada sem diálogo consome seu número e não cria compensação silenciosa.

## Segurança

- F12 é parada global imediata;
- toda falha, timeout ou transição libera inputs;
- `R` é a única tecla normalmente mantida em combate;
- setas e `H` são pulsos curtos;
- `V` e `Y` são proibidos durante combate;
- GAME manual fica bloqueado durante treino autônomo;
- perda de foco, HWND, PID ou autoridade visual reduz ação;
- vitória continua dependente da linha real `has been Knocked-Out` e dos gates de identidade;
- recuperação exige HP ≥ 90% e Chakra ≥ 50%.

## Testes mínimos

```powershell
python -m py_compile kage_pilot.py kage_pilot_dojo.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python kage_pilot.py dojo --show-config
```

Também validar build e smoke de `KageLink.exe`, `KagePilotDojo.exe`, `KagePilotRound.exe`, Setup e APK. Mudanças em captura, detecção, foco, input, KO, retorno ou recuperação exigem Windows + BYOND real antes do merge funcional.
