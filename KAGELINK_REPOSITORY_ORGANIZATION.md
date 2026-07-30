# Organização do repositório KageLink 3.5

[English](KAGELINK_REPOSITORY_ORGANIZATION.en.md)

## Objetivo

Reduzir superfícies concorrentes sem quebrar o motor do Kage Pilot validado fisicamente.

## Superfície ativa canônica

```text
AGENTS.md + AGENTS_3_5.md + capítulos especializados
KAGE_PILOT.md / KAGE_PILOT.en.md
KageLink Installer/pc_agent/kage_pilot.py
KageLink Installer/pc_agent/kage_pilot_loop.py
KageLink Installer/pc_agent/kage_pilot_dojo.py  # wrapper do helper instalado
```

## Compatibilidade externa preservada

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

Esses nomes são contratos de distribuição do 3.5.0 e não devem ser removidos incidentalmente.

## Dívida interna versionada

O motor validado ainda depende de famílias como:

```text
kage_pilot_loop_v03*
kage_pilot_live_v03*
pc_agent/kage_pilot/*_v03*
tests/test_kage_pilot_v03*
.github/workflows/kage-pilot-v03.yml
```

Esses arquivos não são novas superfícies públicas. Eles formam uma cadeia de compatibilidade histórica que deve ser extraída para nomes por responsabilidade em uma PR funcional separada.

## Política de novos arquivos

Proibido criar novas implementações permanentes usando:

```text
v03x
final/final2
new/new2
hotfix
fix_latest
copy/copy2
```

Durante uma grande atualização:

1. atualizar o arquivo canônico do subsistema;
2. atualizar changelog/release/PR;
3. adicionar testes no conjunto canônico;
4. não criar uma nova cópia completa apenas para representar a versão.

## Gate para remoção dos snapshots

A fase de remoção física exige:

- inventário automático de imports e referências;
- nomes canônicos internos por responsabilidade;
- atualização de PyInstaller specs;
- atualização de workflows;
- migração dos testes sem perda de cenários;
- suíte Python completa verde;
- builds/smokes dos três EXEs;
- Setup e APK verdes;
- validação real de clique único, diálogo, combate, KO, retorno, recuperação, F12 e interlock GAME;
- rollback por PR identificável.

Até esse gate, os arquivos internos permanecem, mas são marcados como compatibilidade e não como padrão arquitetural.
