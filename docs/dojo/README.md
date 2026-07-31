# KageLink Dojo Trainer Documentation

[Português do Brasil](README.pt-BR.md)

This folder centralizes Dojo Trainer-specific documentation without changing operational code paths.

## Normative authority

The Bibles remain at the repository root for maximum visibility:

- [`AGENTS.en.md`](../../AGENTS.en.md) — general KageLink Development Bible;
- [`AGENTS_DOJO.en.md`](../../AGENTS_DOJO.en.md) — normative Dojo Trainer extension;
- [`AGENTS.md`](../../AGENTS.md) and [`AGENTS_DOJO.md`](../../AGENTS_DOJO.md) — PT-BR equivalents.

## Versioned documentation

### KageLink 3.5.1 / PR #23

- [`KAGELINK_3_5_1_DOJO_PLAN.md`](3.5.1/KAGELINK_3_5_1_DOJO_PLAN.md) — plan and scope boundaries;
- [`KAGELINK_3_5_1_DOJO_RELIABILITY.en.md`](3.5.1/KAGELINK_3_5_1_DOJO_RELIABILITY.en.md) — EN-US reliability contract;
- [`KAGELINK_3_5_1_DOJO_RELIABILITY.md`](3.5.1/KAGELINK_3_5_1_DOJO_RELIABILITY.md) — equivalent PT-BR contract;
- [`KAGELINK_3_5_1_COMBAT_TARGET.en.md`](3.5.1/KAGELINK_3_5_1_COMBAT_TARGET.en.md) — persistent logical target, local rebind and combat stability;
- [`KAGELINK_3_5_1_COMBAT_TARGET.md`](3.5.1/KAGELINK_3_5_1_COMBAT_TARGET.md) — equivalent PT-BR documentation.

## Operational file map

PR #23 code files remain in their canonical paths so imports, tests, specs and packaging are not broken:

```text
KageLink Installer/pc_agent/
├── kage_pilot_*.py
│   └── canonical helper and round entrypoints
├── unified_dojo_*.py
│   └── Desktop UI composition and API integration
├── pc_agent/kage_pilot/
│   └── dojo_*_v351.py, bridges, guards and vision/position/combat subsystems
├── tests/
│   └── test_dojo_*.py and packaging/regression tests
└── config/
    └── kage_pilot_dojo.json

KageLink Installer/installer/
├── KageLink.spec
├── KagePilotRound.spec
├── KageLink_PC_Agent.iss
└── CRIAR_INSTALADOR.bat
```

Documentation organization does not change operational paths. Functional PR changes remain isolated in canonical modules with tests and bilingual documentation.
