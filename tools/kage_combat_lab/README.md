# Kage Combat Lab

Laboratório determinístico e adapter de combate real da PR #25.

## Contrato protegido do grid

**Cada célula lógica possui exatamente 64×64 pixels.**

```text
CELL_SIZE_PX = 64
```

Qualquer outro valor falha imediatamente com:

```text
KAGE_GRID_CELL_SIZE_IMMUTABLE
```

## Regras de combate

A distância usa Chebyshev sobre o grid canônico de 64px.

| Distância | Regra |
|---|---|
| `D=0` | Pulso direcional de 50 ms na direção visual do alvo. H proibido. |
| `D=1` | Pulso direcional de 50 ms na direção do alvo. H proibido. |
| `D=2` | Mira e toca H por 50 ms quando o cooldown estiver livre. |
| `D=3–50` | Mira, toca H quando disponível e aproxima por 100 ms rumo a D2. |
| `D>50` | Fora do alcance de H; aproxima por 100 ms com visão limpa. |

Regras globais:

- H exige corpo limpo no frame atual e direção cardinal;
- cooldown mínimo de H: 5 segundos;
- R usa o padrão BYOND de key-down repetido a cada 250 ms;
- dois frames limpos são necessários para o primeiro lock;
- oclusão curta preserva identidade por 1 segundo;
- hard lost após 2 segundos;
- F12, KO, timeout, perda de foco ou exceção liberam todas as teclas.

## Testes determinísticos

```powershell
cd tools\kage_combat_lab
.\run_kage_combat_lab.ps1 -RunAll
```

## Combate real com input

O shadow mode foi removido por decisão explícita do usuário. `-LiveInput` envia teclas reais para **Shinobi Story Online**.

Antes de executar:

1. abra o jogo;
2. deixe o personagem já no combate contra um único Trainer;
3. mantenha a janela visível e sem menus sobrepostos;
4. deixe a mão preparada sobre F12.

Execute:

```powershell
cd "C:\Users\Rafael\Desktop\Powershell\Kagelink2\tools\kage_combat_lab"
.\run_kage_combat_lab.ps1 -LiveInput
```

Defaults:

```text
Contagem para armar: 3 s
Duração máxima: 80 s
Frequência de visão: 8 FPS
Preview OpenCV: ligado
Parada de emergência: F12
```

Para executar o teste completo de 80 segundos:

```powershell
.\run_kage_combat_lab.ps1 -LiveInput -MaxSeconds 80
```

Sem janela de preview:

```powershell
.\run_kage_combat_lab.ps1 -LiveInput -MaxSeconds 80 -NoPreview
```

O modo real:

- reutiliza `WindowsGameController` e o padrão de R já validado no KageLink;
- captura exclusivamente a janela do jogo;
- converte os pés de cada corpo visual para uma célula 64px;
- mantém a identidade lógica na `GridFocusStrategy`;
- mira antes de H;
- mantém R durante as ações;
- registra cada decisão em `tools\kage_combat_lab\reports\live_input_*.jsonl`.

## Dependências

O modo `-LiveInput` precisa do checkout completo do KageLink e do ambiente Python que já executa o Kage Pilot, incluindo OpenCV, NumPy e pywin32. Os testes determinísticos continuam independentes dessas dependências.
