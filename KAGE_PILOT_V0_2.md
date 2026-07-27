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
UP/DOWN/              H /
LEFT/RIGHT        configuráveis
   ↓                 ↓
   └────────┬────────┘
            ↓
          + R

vitória
   ↓
V = meditação / pós-combate
```

A navegação e os jutsus são aprendidos separadamente. `R` permanece como estado-base de combate. `V` **não é uma skill de combate**: por padrão ele marca o início da cauda pós-luta e não entra no treinamento de combate.

## O que mudou em relação à v0.1

- usa pares de frames para capturar mudança visual e movimento;
- `R` é uma tecla-base permanente por padrão e não uma ação a ser classificada;
- `UP`, `DOWN`, `LEFT` e `RIGHT` formam uma política exclusiva de navegação;
- `H` é a skill de combate padrão inicial; outras podem ser configuradas;
- `V` é pós-combate/meditação por padrão;
- ao encontrar `V` em uma demonstração, o treinador descarta `V` e o restante daquela cauda do treino de combate;
- a política compara cada classe com exemplos reais de blocos de ação, em vez de depender apenas de uma imagem média por classe;
- a quantidade de exemplos `idle` não funciona como votação contra `LEFT/RIGHT`;
- após disparar um jutsu, a política precisa voltar a `idle` antes que outro disparo do mesmo estado seja permitido;
- jutsus também possuem cooldown;
- o Pilot tem modo `--debug` mostrando decisão, confiança, rearme e teclas aplicadas;
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

Defaults atuais:

```text
base key: R
combat skills: H
post-combat key: V
history: 2 frames
somente vitórias
```

Para adicionar outra skill de combate:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json --skill-key h --skill-key g
```

Para alterar a tecla de pós-combate:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json --post-combat-key v
```

## Primeiro teste recomendado

Entre manualmente em uma luta e execute:

```powershell
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --seconds 15 --debug
```

O comando aguarda 3 segundos antes de assumir o controle. O log mostra linhas como:

```text
V0.2 nav=right:0.143 skill=idle:0.091 fire=- armed=yes keys=r+right
V0.2 nav=idle:0.112 skill=h:0.084 fire=h armed=no keys=h+r
```

O objetivo inicial não é vencer. Primeiro confirme que:

1. `R` permanece ativo;
2. movimento ocorre quando necessário;
3. o personagem para de se mover quando o modelo decide `idle`;
4. `V` nunca é usado durante o combate;
5. `H` não é repetido continuamente;
6. as decisões mudam quando a posição relativa muda.

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

O Dojo Manager continua determinístico. A IA controla apenas o combate. A meditação `V` pertence à sequência pós-resultado, não à política de jutsus.

## Limite atual

A v0.2 possui memória visual temporal e agora usa exemplos reais por classe, mas ainda não possui um detector supervisionado explícito que desenhe caixas em `Leafos` e no inimigo. Esta etapa verifica se essas correções já são suficientes para aprender perseguição/reposicionamento no ambiente controlado do Dojo. Se a navegação ainda permanecer em `idle` diante de separações claras, o próximo passo é adicionar calibração visual explícita de player/inimigo sobre esta arquitetura, sem descartar o dataset atual.
