# Documentação do KageLink Dojo Trainer

[English](README.md)

Esta pasta centraliza a documentação específica do Dojo Trainer sem alterar os caminhos operacionais do código.

## Autoridade normativa

As Bíblias permanecem na raiz do repositório para máxima visibilidade:

- [`AGENTS.md`](../../AGENTS.md) — Bíblia geral do KageLink;
- [`AGENTS_DOJO.md`](../../AGENTS_DOJO.md) — extensão normativa do Dojo Trainer;
- [`AGENTS.en.md`](../../AGENTS.en.md) e [`AGENTS_DOJO.en.md`](../../AGENTS_DOJO.en.md) — equivalentes EN-US.

## Documentação por versão

### KageLink 3.5.1 / PR #23

- [`KAGELINK_3_5_1_DOJO_PLAN.md`](3.5.1/KAGELINK_3_5_1_DOJO_PLAN.md) — plano e limites de escopo;
- [`KAGELINK_3_5_1_DOJO_RELIABILITY.md`](3.5.1/KAGELINK_3_5_1_DOJO_RELIABILITY.md) — contrato de confiabilidade em PT-BR;
- [`KAGELINK_3_5_1_DOJO_RELIABILITY.en.md`](3.5.1/KAGELINK_3_5_1_DOJO_RELIABILITY.en.md) — contrato equivalente em EN-US;
- [`KAGELINK_3_5_1_COMBAT_TARGET.md`](3.5.1/KAGELINK_3_5_1_COMBAT_TARGET.md) — alvo lógico persistente, rebind local e estabilidade do combate;
- [`KAGELINK_3_5_1_COMBAT_TARGET.en.md`](3.5.1/KAGELINK_3_5_1_COMBAT_TARGET.en.md) — documentação equivalente em EN-US.

## Mapa dos arquivos operacionais

Os arquivos de código da PR #23 permanecem em seus caminhos canônicos para não quebrar imports, testes, specs ou empacotamento:

```text
KageLink Installer/pc_agent/
├── kage_pilot_*.py
│   └── entrypoints canônicos dos helpers e da rodada
├── unified_dojo_*.py
│   └── composição da interface Desktop e integração da API
├── pc_agent/kage_pilot/
│   └── dojo_*_v351.py, bridges, guards e subsistemas de visão/posição/combate
├── tests/
│   └── test_dojo_*.py e testes de empacotamento/regressão
└── config/
    └── kage_pilot_dojo.json

KageLink Installer/installer/
├── KageLink.spec
├── KagePilotRound.spec
├── KageLink_PC_Agent.iss
└── CRIAR_INSTALADOR.bat
```

A organização documental não altera caminhos operacionais. Mudanças funcionais da PR permanecem isoladas nos módulos canônicos, com testes e documentação bilíngue.
