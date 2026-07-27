# Kage Pilot v0.2

[English](KAGE_PILOT_V0_2.en.md)

O **Kage Pilot v0.2** substitui o conceito de "uma imagem → uma tecla" por um modelo temporal de combate adaptado ao Dojo de Shinobi Story Online.

## Modelo de combate

```text
R mantido = estado base / auto-ataque corpo a corpo

frame anterior + frame atual
            ↓
     contexto temporal
            ↓
   ┌────────┴────────┐
   ↓                 ↓
Navegação          Jutsus
UP/DOWN/          H / V /
LEFT/RIGHT        configuráveis
   ↓                 ↓
   └────────┬────────┘
            ↓
          + R
```

A navegação e os jutsus são aprendidos separadamente. Isso evita que um jutsu frequente seja confundido com movimento e permite manter `R` pressionado durante todo o combate.

## O que mudou em relação à v0.1

- usa pares de frames para capturar mudança visual e movimento;
- `R` é uma tecla-base permanente por padrão e não uma ação a ser classificada;
- `UP`, `DOWN`, `LEFT` e `RIGHT` formam uma política exclusiva de navegação;
- `H` e `V` são as skills padrão da primeira calibração e podem ser alteradas;
- jutsus possuem cooldown para impedir spam a cada frame;
- o Pilot tem modo `--debug` mostrando decisão, confiança e teclas aplicadas;
- há atraso de inicialização configurável para evitar disputa de foco com o PowerShell;
- o controlador força o foco do `Shinobi Story Online` antes de iniciar;
- a memória temporal é reiniciada a cada luta do Dojo;
- os comandos legados v0.1 continuam disponíveis para comparação.

## Dados existentes

As sessões gravadas na v0.1 continuam válidas. A v0.2 usa os mesmos:

```text
sessions/<fight>/
├── manifest.json
├── samples.jsonl
├── actions.jsonl
└── frames/
```

O treino v0.2 usa os blocos de `actions.jsonl`, portanto uma tecla mantida por vários segundos não recebe dezenas de votos apenas por causa do FPS do Recorder.

## Treinar v0.2

No diretório `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json
```

Defaults iniciais:

```text
base key: R
skills: H, V
history: 2 frames
somente vitórias
```

Para adicionar outra skill:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json --skill-key h --skill-key v --skill-key g
```

## Primeiro teste recomendado

Entre manualmente em uma luta e execute:

```powershell
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --seconds 15 --debug
```

O comando aguarda 3 segundos antes de assumir o controle. O log mostra linhas como:

```text
V0.2 nav=right:0.143 skill=idle:0.091 fire=- keys=r+right
V0.2 nav=idle:0.112 skill=h:0.084 fire=h keys=h+r
```

O objetivo inicial não é vencer. Primeiro confirme que:

1. `R` permanece ativo;
2. movimento ocorre quando necessário;
3. o personagem para de se mover quando o modelo decide `idle`;
4. jutsus não são repetidos continuamente;
5. as decisões mudam quando a posição relativa muda.

## Ajustes úteis

```powershell
# mais conservador com jutsus
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --skill-confidence 0.05 --seconds 15 --debug

# cooldown maior
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --skill-cooldown 2.0 --seconds 15 --debug

# sem atraso inicial
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --startup-delay 0 --seconds 15 --debug
```

## Dojo Manager v0.2

Depois de calibrar templates e sequências do Dojo:

```powershell
python kage_pilot.py dojo-v2 --model kage_pilot_v02.json --config dojo_config.json --cycles 10 --debug
```

O Dojo Manager continua determinístico. A IA controla apenas o combate.

## Limite atual

A v0.2 possui memória visual temporal, mas ainda não possui um detector supervisionado explícito que desenhe caixas em `Leafos` e no inimigo. O objetivo desta etapa é verificar se a informação temporal das demonstrações já é suficiente para aprender perseguição/reposicionamento no ambiente controlado do Dojo. Se não for, o próximo passo é adicionar calibração visual explícita de player/inimigo sobre esta arquitetura, sem descartar o dataset atual.
