# Kage Combat Lab

Laboratório determinístico e independente do BYOND para desenvolver a mecânica de combate antes da integração com o KageLink.

## Contrato protegido do grid

**Cada célula lógica possui exatamente 64×64 pixels.**

Isso não é uma configuração, preferência ou valor calibrável. É uma invariável do domínio:

```text
CELL_SIZE_PX = 64
```

Qualquer tentativa de iniciar, configurar, importar ou integrar o laboratório com 16, 32, 48, 96, 128 ou qualquer outro valor deve falhar imediatamente com:

```text
KAGE_GRID_CELL_SIZE_IMMUTABLE
```

## Regras de combate aprovadas

A distância usa Chebyshev sobre o grid canônico de 64px.

| Distância | Regra |
|---|---|
| `D=0` | Um único pulso direcional `VERY_SHORT` na direção visual do alvo. H proibido. Sem direção visual, segura tudo. |
| `D=1` | Um único pulso direcional `VERY_SHORT` na direção do alvo. H proibido. |
| `D=2` | Aguarda e pressiona H somente com confirmação visual limpa no frame atual. |
| `D=3` | Pressiona H com confirmação visual limpa e emite pulso `APPROACH` para tentar chegar a D2. |
| `D>=4` | Regra ainda não definida; segura tudo de forma fail-closed. |

Os perfis `VERY_SHORT` e `APPROACH` são semânticos. A duração física em milissegundos será calibrada somente no futuro adapter de teclado; a estratégia não controla teclado diretamente.

## Execução

```powershell
cd tools\kage_combat_lab
.\run_kage_combat_lab.ps1 -Interactive
```

Executar todos os cenários:

```powershell
.\run_kage_combat_lab.ps1 -RunAll
```

Cenários individuais:

```powershell
.\run_kage_combat_lab.ps1 -Interactive -Scenario distance_0_overlap
.\run_kage_combat_lab.ps1 -Interactive -Scenario distance_1_adjacent
.\run_kage_combat_lab.ps1 -Interactive -Scenario distance_2_hold_h
.\run_kage_combat_lab.ps1 -Interactive -Scenario distance_3_h_approach
```

## Escopo

Incluído:

- aquisição de alvo;
- identidade lógica por célula;
- troca de track visual;
- previsão limitada a célula adjacente;
- contato diagonal por distância de Chebyshev;
- regras D0, D1, D2 e D3;
- direção visual interna para sobreposição D0;
- suspensão e recuperação local;
- rejeição de blobs multicélula;
- encerramento por KO;
- decisões neutras de direção, perfil de pulso e tecla H.

Excluído deliberadamente:

- captura do BYOND;
- OpenCV real;
- teclado e mouse;
- Trainer;
- HP/chakra;
- meditação;
- navegação de retorno;
- UI do KageLink.

## Regra de integração futura

O KageLink deverá adaptar dados visuais reais para `CombatFrame`. A estratégia não poderá importar módulos de captura ou controle. A saída `CombatDecision` será convertida em teclas por outro adapter.
