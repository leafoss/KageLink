# Kage Pilot v0.3b — Pós-combate calibrado (PT-BR)

## Objetivo

Preservar integralmente o combate validado da v0.3 e tornar o fluxo pós-vitória confiável em cada computador.

## Vitória

A vitória continua sendo autoritativa pelo chat novo:

```text
has been Knocked-Out
```

Ao receber a frase, todas as teclas de combate são liberadas imediatamente.

## Calibração local do líder

A imagem de referência enviada anteriormente não correspondeu com score suficiente à captura real. A v0.3b permite ensinar o sprite diretamente da janela do jogo:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_leader_calibrate.py
```

Na janela de calibração, selecione o líder completo com uma pequena margem do piso e confirme com Enter/Espaço. O arquivo local é salvo em:

```text
data/kage_pilot/dojo_leader_template.png
```

Essa pasta é ignorada pelo Git.

## Memória de câmera

Depois de uma confirmação visual, a posição prevista do líder é deslocada pelo `global_flow` da câmera. A memória pode orientar pulsos de caminhada quando o sprite fica oculto ou sai temporariamente da tela.

A memória nunca autoriza meditação. `V` só é enviado quando o líder reaparece visualmente e está confirmado em uma célula adjacente.

## Recursos

Calibração observada no PC Micro:

```text
HP cheio     = 47 px
Chakra cheio = 40 px
```

A saída da meditação exige HP >= 90% e Chakra >= 50% por leituras consecutivas.

## Probe

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_postcombat_probe_v2.py --seconds 20
```

O probe é somente leitura e mostra a origem do template, score, bbox, HP e Chakra.

## Live v0.3b

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03b.py --seconds 90 --log kage_pilot_live_test_6.jsonl
```

A v0.3b reutiliza o mesmo combate validado e substitui somente o detector/estado pós-combate.
