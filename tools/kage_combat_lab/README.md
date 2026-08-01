# Kage Combat Lab

Laboratório determinístico, adapter de combate real e teste completo do Dojo da PR #25.

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

## Testes determinísticos

```powershell
cd tools\kage_combat_lab
.\run_kage_combat_lab.ps1 -RunAll
```

## Combate isolado com input

`-LiveInput` inicia somente o combate contra um Trainer já invocado.

```powershell
cd "C:\Users\Rafael\Desktop\Powershell\Kagelink2\tools\kage_combat_lab"
.\run_kage_combat_lab.ps1 -LiveInput -MaxSeconds 80 -NoPreview
```

## Loop completo do Dojo

`-FullLoop` reutiliza o loop validado do Kage Pilot e substitui somente a rodada de combate pelo `CHASE_ALWAYS_ON`.

Fluxo executado:

```text
buscar o Dojo Trainer
→ confirmar visualmente
→ clicar uma única vez
→ aguardar e confirmar o diálogo
→ clicar OK
→ aguardar o adversário nascer
→ combater com CHASE_ALWAYS_ON
→ aceitar KO autoritativo pelo chat
→ liberar R, H e direcionais
→ localizar/retornar ao Trainer
→ iniciar meditação com V
→ usar Y rápido quando o motor validado autorizar
→ atingir HP >= 90% e Chakra >= 50%
→ aguardar no mínimo 5,25 s desde a entrada na meditação
→ sair da meditação com V
→ emitir READY
```

Para o primeiro teste, comece recuperado, dentro do Dojo e sem estar meditando. Execute apenas uma rodada:

```powershell
cd "C:\Users\Rafael\Desktop\Powershell\Kagelink2\tools\kage_combat_lab"
.\run_kage_combat_lab.ps1 -FullLoop -Rounds 1
```

Parâmetros padrão do primeiro teste:

```text
Rodadas: 1
Combate máximo por rodada: 120 s
Retorno + recuperação: 240 s
Espera do diálogo: 5 s
Espera de nascimento: 5 s
Busca do Trainer: 90 s
HP para READY: 90%
Chakra para READY: 50%
Meditação mínima antes do segundo V: 5,25 s
Parada de emergência: F12
```

Comando explícito equivalente:

```powershell
.\run_kage_combat_lab.ps1 `
  -FullLoop `
  -Rounds 1 `
  -CombatSeconds 120 `
  -PostCombatTimeout 240 `
  -DialogDelay 5 `
  -SpawnDelay 5 `
  -TrainerSearchTimeout 90
```

Sinais esperados no terminal:

```text
DOJO_REQUEST_ACCEPTED
PR25_FULL_ROUND=CHASE_ALWAYS_ON
FULL ROUND COMBAT ARMED
VICTORY_CHAT / VITORIA_CHAT
POST_COMBAT / POS-COMBATE
POST V_TAP state=START_MEDITATION
READY / PRONTO
result=ready
ROUND 1: COMPLETE / CONCLUIDA
DOJO_LOOP_FINISHED ... completed=1 ... failed=0
```

Use F12 imediatamente se ocorrer qualquer uma destas condições:

- perseguir um objeto que não seja o adversário;
- caminhar sem corpo limpo visível;
- continuar enviando R ou H depois do KO;
- não retornar ao Trainer;
- tentar sair da meditação antes do prazo físico;
- iniciar uma nova luta ainda meditando.

Os logs da rodada completa são gravados em:

```text
KageLink Installer\pc_agent\kage_pilot_loop_logs\round_001.jsonl
```

## Dependências

Os modos `-LiveInput` e `-FullLoop` exigem o checkout completo do KageLink e o ambiente Python que já executa o Kage Pilot, incluindo OpenCV, NumPy e pywin32. O modo `-FullLoop` é intencionalmente restrito ao checkout fonte e não tenta alterar o executável instalado.
