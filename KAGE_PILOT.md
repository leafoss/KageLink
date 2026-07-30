# Kage Pilot

[English](KAGE_PILOT.en.md) · [Bíblia do KageLink](AGENTS.md) · [Contrato normativo do Dojo](AGENTS_DOJO.md)

O **Kage Pilot** é o subsistema local de percepção, controle e treinamento no Dojo de **Shinobi Story Online**. Desde o KageLink 3.5.0, ele faz parte da distribuição Windows e pode ser controlado pelo Desktop ou pelo APK autenticado.

Este é o único documento técnico ativo do Kage Pilot em PT-BR. Registros antigos com nomes de versão, letras de hotfix ou datas permanecem preservados no histórico Git e nos Pull Requests que os validaram.

## Estado canônico

- **Versão de produto:** KageLink 3.5.0.
- **Comando público de desenvolvimento:** `KageLink Installer/pc_agent/kage_pilot.py`.
- **Comando do Dojo:** `python kage_pilot.py dojo`.
- **Configuração:** `KageLink Installer/pc_agent/config/kage_pilot_dojo.json`.
- **Serviço público:** `pc_agent.kage_pilot.DojoTrainingService`.
- **Workflow:** `.github/workflows/kage-pilot.yml`.
- **Executáveis instalados:** `KageLink.exe`, `KagePilotDojo.exe` e `KagePilotRound.exe`.
- **Templates do usuário:** `%LOCALAPPDATA%\KageLink\data\kage_pilot\templates`.

A baseline física registrada completou dez rodadas:

```text
DOJO_LOOP_FINISHED requested=10 processed=10 completed=10
finished_without_combat=0 failed=0 emergency_stopped=0
```

## Regra de organização

Existe uma única superfície pública humana:

```text
kage_pilot.py
```

Ela concentra os comandos:

```text
dojo
record
mark
train
train-v2
pilot
pilot-v2
capture-template
init-config
dojo-v2
```

O código interno continua modular por responsabilidade. Versões pertencem a commits, tags, releases e changelog; novas mudanças não devem criar outro entrypoint como `v03l`, `final2`, `new` ou `hotfix`.

A cadeia interna fisicamente validada ainda contém camadas de compatibilidade com nomes históricos. Elas não são superfícies públicas e só podem ser extraídas para nomes canônicos em uma mudança própria, com CI completo e nova validação no jogo.

## Arquitetura instalada

```text
Desktop ou APK
       ↓ API autenticada
KageLink.exe
       ↓ DojoTrainingService
KagePilotDojo.exe
       ↓ uma rodada isolada por vez
KagePilotRound.exe
       ↓
Shinobi Story Online
```

- O motor executa somente no Windows que possui o jogo.
- O APK não executa visão, teclado ou lógica de combate.
- Desktop e APK controlam o mesmo estado público.
- Durante treinamento, o Windows bloqueia comandos GAME concorrentes.
- A instalação não depende de Python externo nem de scripts soltos.

## Executar em desenvolvimento

Na pasta `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py dojo
```

Dez rodadas:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Mostrar a configuração efetiva:

```powershell
python kage_pilot.py dojo --show-config
```

`--rounds 0` executa continuamente até parada explícita ou F12.

## Templates 32×32 e 64×64

A instalação não usa uma imagem incorporada do Dojo Trainer como autoridade principal. O usuário cadastra recortes independentes para os modos reais do jogo:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates\
├── dojo_trainer_32.png
├── dojo_trainer_64.png
└── templates.json
```

Regras:

- cada modo é persistido e removido independentemente;
- atualizações normais preservam os arquivos;
- PNG, JPEG, WebP e BMP podem ser enviados pela UI e são normalizados;
- os dois templates podem ser carregados simultaneamente;
- o detector escolhe somente uma correspondência estável;
- ambiguidade forte deve falhar fechado;
- o runtime instalado não inicia sem ao menos um template válido;
- a calibração de código-fonte é apenas compatibilidade de desenvolvimento.

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

Falha recuperável termina somente a tentativa ou a rodada. F12 executa `EMERGENCY_STOP`, libera inputs e encerra o loop.

## Contrato absoluto do treinador

```text
trainer_clicks_per_round <= 1
```

Depois de `TRAINER_CLICK_ONCE`, retries de diálogo não podem:

- clicar novamente no Trainer;
- procurar outro Trainer para repetir a solicitação;
- mover o personagem para reiniciar a interação;
- iniciar uma segunda solicitação de spar.

Fluxo padrão:

```text
1 clique no Trainer
→ espera inicial
→ check 1
→ retry wait + check 2
→ retry wait + check 3
→ retry wait + check 4
```

Quatro falhas encerram somente a rodada como `FINISHED_WITHOUT_COMBAT`. A rodada consome seu número e o loop segue quando for seguro.

## Aquisição visual

A visão cria candidatos; ela não autoriza input sozinha. A aquisição exige confirmação atual e estável. Quando o personagem pode estar ocultando o Trainer, uma manobra lateral curta pode ser usada antes da confirmação final.

Nenhuma memória antiga de posição autoriza clique, `V` ou recuperação sem evidência visual atual.

## Combate

Contratos permanentes:

- `R` é a única tecla normalmente mantida;
- setas e `H` são pulsos curtos;
- `V` e `Y` são toggles por toque e são proibidos durante combate;
- perda de alvo, foco ou autoridade visual reduz a ação;
- `MAP_SAVE_RESYNC` e `H_SETTLE_HOLD` são bloqueios absolutos;
- facing durante partículas exige alvo atual, adjacente e confirmado;
- erro, timeout, stop e shutdown liberam todos os inputs.

## Autoridade de KO

A frase real continua sendo a autoridade de término:

```text
has been Knocked-Out
```

O nome do último oponente aceito é carregado para a rodada seguinte. Um KO repetido do adversário anterior é rejeitado, o alvo é invalidado e o combate continua. Vitória só é aceita para um oponente diferente com evidência visual atual suficiente.

## Retorno e recuperação

Pisos protegidos:

```text
HP >= 90%
Chakra >= 50%
```

- `V` exige confirmação visual atual do Trainer.
- `Y` só pode permanecer ligado durante meditação e deve ser desligado ao alcançar o limiar.
- timeout de recuperação não pode ser registrado como sucesso.

## Contadores

```text
requested
processed
completed
finished_without_combat
failed
emergency_stopped
```

`--rounds 10` processa as rodadas numeradas de 1 a 10. Não existe rodada 11 de compensação silenciosa.

## API autenticada

```text
GET    /api/dojo/status
POST   /api/dojo/start
POST   /api/dojo/stop
GET    /api/dojo/templates
GET    /api/dojo/templates/{mode}/image
POST   /api/dojo/templates/{mode}
DELETE /api/dojo/templates/{mode}
```

Todos os endpoints usam o mesmo Bearer Token do KageLink. Iniciar sem runtime ou template válido deve falhar fechado. Parar deve liberar inputs mesmo quando o processo já terminou.

## Interlock com GAME

Enquanto `running=true`:

- ativação manual GAME é rejeitada;
- estado manual de teclas GAME é rejeitado;
- clique remoto no centro do jogo é rejeitado;
- troca ou remoção de template é bloqueada;
- chat e STATUS permanecem independentes;
- F12 continua sendo parada local de emergência.

## Dados locais

Não versionar:

```text
.venv-kage-pilot/
data/kage_pilot/
kage_pilot_loop_logs/
kage_pilot_*.jsonl
config.json
```

Templates, calibração, frames e logs pertencem à instalação do usuário.

## Treinamento adaptativo futuro

Evolução aceitável:

```text
telemetria passiva
→ análise offline
→ challenger em shadow mode
→ política pré-aprovada
→ promoção humana explícita
```

Nunca podem ser aprendidos automaticamente:

- autoridade de KO;
- clique único;
- pisos de recuperação;
- target/focus gates;
- whitelist de teclas;
- F12;
- liberação de inputs;
- proibição de `V` e `Y` em combate;
- proteções de partículas, água e perseguição cega.

## Validação

Comandos principais do CI:

```powershell
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python -m compileall .
python kage_pilot.py dojo --show-config
```

A distribuição também precisa validar:

- build dos três executáveis;
- `--help` dos dois helpers;
- smoke launch do Desktop;
- Setup contendo os três executáveis;
- upload, persistência e remoção dos templates;
- Flutter localization, analyze e testes;
- APK release;
- uma rodada real instalada nos modos aplicáveis;
- Desktop/APK start, stop e status;
- interlock GAME;
- F12 e liberação de inputs.

Testes automatizados não substituem a validação real Windows + BYOND.
