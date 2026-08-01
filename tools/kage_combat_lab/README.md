# Kage Combat Lab

Laboratório determinístico e independente do BYOND para desenvolver a mecânica de combate antes da integração com o KageLink.

## Contrato protegido do grid

**Cada célula lógica possui exatamente 64×64 pixels.**

```text
CELL_SIZE_PX = 64
```

Qualquer outro valor falha imediatamente com:

```text
KAGE_GRID_CELL_SIZE_IMMUTABLE
```

## Regras de combate aprovadas

A distância usa Chebyshev sobre o grid canônico de 64px.

| Distância | Regra |
|---|---|
| `D=0` | Pulso direcional de 50 ms na direção visual do alvo. H proibido. Sem direção visual, HOLD. |
| `D=1` | Pulso direcional de 50 ms na direção do alvo. H proibido. |
| `D=2` | Mantém posição, mira no alvo e toca H por 50 ms quando o cooldown estiver livre. |
| `D=3–50` | Mira, toca H por 50 ms quando disponível e depois aproxima por 100 ms rumo a D2. |
| `D>50` | Fora do alcance de H; aproxima por 100 ms com confirmação visual limpa. |

Regras globais:

- H exige confirmação visual limpa no frame atual;
- cooldown mínimo de H: 5 segundos;
- R permanece em `pressed down`, com heartbeat de key-down a cada 250 ms;
- após cada ação, observa novamente por 150 ms;
- dois frames limpos são necessários para o primeiro lock;
- oclusão curta preserva a identidade por até 1 segundo;
- 2 segundos sem visão limpa abandonam o alvo;
- o primeiro teste usa apenas um Trainer;
- KO, F12, perda de foco, timeout ou encerramento liberam todas as teclas.

## Execução

```powershell
cd tools\kage_combat_lab
.\run_kage_combat_lab.ps1 -Interactive
```

Executar todos os cenários:

```powershell
.\run_kage_combat_lab.ps1 -RunAll
```

Mostrar o contrato do primeiro teste real:

```powershell
.\run_kage_combat_lab.ps1 -LiveChecklist
```

## Primeiro teste físico

Defaults conservadores:

```text
Janela: Shinobi Story Online
Alvo: um único Trainer
Shadow mode inicial: 10 s
Duração armada máxima: 45 s
Parada de emergência: F12
```

O laboratório ainda não envia teclas ao jogo. O próximo estágio é criar um adapter físico separado que converta `CombatDecision` em comandos, sem alterar a estratégia ou o contrato de grid.

## Escopo

Incluído:

- aquisição e identidade lógica por célula;
- troca de track visual;
- direção, distância e cooldown;
- R persistente;
- pulso H e pulsos de aproximação;
- suspensão, hard lost e KO;
- rejeição de blobs multicélula;
- cenários e testes determinísticos.

Excluído deliberadamente nesta etapa:

- captura real do BYOND;
- OpenCV real;
- envio real de teclado e mouse;
- Trainer, meditação e retorno integrados;
- UI do KageLink.
