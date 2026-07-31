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

## Execução

```powershell
cd tools\kage_combat_lab
.\run_kage_combat_lab.ps1 -Interactive
```

Executar todos os cenários:

```powershell
.\run_kage_combat_lab.ps1 -RunAll
```

## Escopo

Incluído:

- aquisição de alvo;
- identidade lógica por célula;
- troca de track visual;
- previsão limitada a célula adjacente;
- contato diagonal por distância de Chebyshev;
- suspensão e recuperação local;
- rejeição de blobs multicélula;
- encerramento por KO;
- decisões neutras de face, movimento e ataque.

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
