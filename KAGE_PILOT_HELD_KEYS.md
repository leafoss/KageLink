# Kage Pilot — teclas mantidas

[English](KAGE_PILOT_HELD_KEYS.en.md)

O Combat Learner deve distinguir entre uma **tecla-base mantida** e as decisões variáveis do combate.

Exemplo observado no Dojo: `R` permanece pressionado durante boa parte da luta enquanto `LEFT`, `RIGHT`, `H`, `V` e outras teclas representam decisões momentâneas.

A partir desta revisão, o treino usa `actions.jsonl` por padrão: cada bloco contínuo de ação conta como um exemplo, independentemente de durar 100 ms ou vários segundos. Isso evita que uma tecla mantida domine o dataset apenas porque o Recorder captura aproximadamente 10 frames por segundo.

Para tratar `R` como tecla-base:

```powershell
python kage_pilot.py train --model kage_pilot_model_r.json --exclude-key r --no-idle
```

Para testar o Pilot mantendo `R` pressionado enquanto executa as ações aprendidas:

```powershell
python kage_pilot.py pilot --model kage_pilot_model_r.json --hold-key r --confidence 0 --seconds 10
```

Depois do primeiro teste, volte a usar um limite de confiança progressivamente maior.

O modo legado frame a frame continua disponível apenas para diagnóstico:

```powershell
python kage_pilot.py train --model legacy.json --frame-samples
```
