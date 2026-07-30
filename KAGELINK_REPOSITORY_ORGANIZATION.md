# Organização do repositório KageLink 3.5

[English](KAGELINK_REPOSITORY_ORGANIZATION.en.md) · [Migração do Kage Pilot](KAGE_PILOT_MIGRATION.md)

## Objetivo

Reduzir superfícies concorrentes sem quebrar o motor do Kage Pilot validado fisicamente.

## Superfície ativa canônica

```text
AGENTS.md + AGENTS_3_5.md + capítulos especializados
KAGE_PILOT.md / KAGE_PILOT.en.md
KageLink Installer/pc_agent/kage_pilot.py
KageLink Installer/pc_agent/kage_pilot_loop.py
KageLink Installer/pc_agent/kage_pilot_round.py
KageLink Installer/pc_agent/kage_pilot_dojo.py  # wrapper do helper instalado
.github/workflows/kage-pilot.yml
```

Módulos internos canônicos:

```text
pc_agent.kage_pilot.dojo_training_service
pc_agent.kage_pilot.dojo_request
pc_agent.kage_pilot.dojo_templates
pc_agent.kage_pilot.trainer_search
pc_agent.kage_pilot.ko_identity
pc_agent.kage_pilot.combat_control
pc_agent.kage_pilot.post_combat
```

## Compatibilidade externa preservada

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

Esses nomes são contratos de distribuição do 3.5.0 e não devem ser removidos incidentalmente.

## Estado da migração

A fase 1 migra consumidores oficiais, specs, serviço, API e CI para nomes sem versão. `ko_identity.py` e `dojo_training_service.py` já são implementações canônicas; os equivalentes versionados permanecem wrappers temporários.

A cadeia complexa ainda depende de famílias como:

```text
kage_pilot_loop_v03*
kage_pilot_live_v03*
pc_agent/kage_pilot/*_v03*
tests/test_kage_pilot_v03*
```

Esses arquivos não são superfícies públicas. Eles fornecem temporariamente a composição de patches validada e não podem receber novos snapshots paralelos.

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

A remoção física exige:

- inventário automático de imports e referências;
- nomes canônicos internos por responsabilidade;
- atualização de PyInstaller specs;
- atualização de workflows;
- migração dos testes sem perda de cenários;
- suíte Python completa verde;
- builds/smokes dos três EXEs;
- Setup e APK verdes;
- validação real de clique único, diálogo, combate, KO, retorno, recuperação, F12 e interlock GAME;
- evidência conforme `KAGE_PILOT_MIGRATION.md`;
- rollback por PR identificável.

Até esse gate, os arquivos internos permanecem como compatibilidade e não como padrão arquitetural. Um wrapper só pode ser apagado quando não possuir consumidores e a validação física correspondente estiver registrada.
