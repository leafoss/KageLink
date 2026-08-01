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

## Política atual: CHASE_ALWAYS_ON

O objetivo espacial deixou de ser D2. Enquanto existir um corpo limpo confirmado, o jogador tenta permanecer em **D=0** do alvo.

| Distância | Perseguição | H |
|---|---|---|
| `D=0` | Microcorreção de 50 ms pela posição interna atual do alvo | Usa H quando visão, direção e cooldown permitem |
| `D>=1` | Pulso de aproximação de 100 ms em todo frame limpo rumo a D0 | Usa H entre D0 e D50 quando o cooldown permite |
| `D>50` | Continua perseguindo rumo a D0 | H bloqueado por alcance |

Regras centrais:

- não existe mais espera em D1 ou D2;
- H não interrompe a perseguição;
- cada H recebe uma orientação cardinal nova antes do disparo;
- alvo abaixo gera `DOWN`, acima `UP`, à esquerda `LEFT` e à direita `RIGHT`;
- cooldown de H: 5 segundos;
- R usa key-down repetido a cada 250 ms;
- dois frames limpos são necessários para o lock inicial;
- mudança de uma célula adjacente mantém identidade e chase;
- perda visual apaga direção, movimento e autoridade de H;
- oclusão curta preserva somente a identidade por 1 segundo;
- hard lost após 2 segundos;
- F12, KO, timeout, perda de foco ou exceção liberam todas as teclas.

A sequência física em um frame com H é:

```text
R mantido
→ direção atual por 50 ms
→ H por 50 ms
→ chase rumo a D0
→ nova observação
```

Sem H disponível:

```text
R mantido
→ chase rumo a D0
→ nova observação
```

## Testes determinísticos

```powershell
cd tools\kage_combat_lab
.\run_kage_combat_lab.ps1 -RunAll
```

## Combate real com input

`-LiveInput` envia teclas reais para **Shinobi Story Online**.

```powershell
cd "C:\Users\Rafael\Desktop\Powershell\Kagelink2\tools\kage_combat_lab"
.\run_kage_combat_lab.ps1 -LiveInput -MaxSeconds 80 -NoPreview
```

Defaults e segurança:

```text
Contagem para armar: 3 s
Duração máxima: 80 s
Frequência de visão: 8 FPS
Parada de emergência: F12
```

Cada decisão é registrada em:

```text
tools\kage_combat_lab\reports\live_input_*.jsonl
```

## Dependências

O modo `-LiveInput` precisa do checkout completo do KageLink e do ambiente Python que já executa o Kage Pilot, incluindo OpenCV, NumPy e pywin32. Os testes determinísticos continuam independentes dessas dependências.
