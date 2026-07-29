# Kage Pilot v0.3 — Target Guard

## Motivo

A validação real no BYOND mostrou que a memória `BACKGROUND_DYNAMIC` passou a aprender a água, mas algumas entidades ambientais ainda acumulavam `Enemy Score` alto e podiam virar `TARGET`, inclusive quando já estavam em estado `LOST`.

O `Target Guard` separa duas perguntas:

```text
isso é uma ENTITY rastreável?
        ↓
isso merece ser TARGET de combate?
```

## Regras atuais

- `LOST` nunca pode ser adquirido como novo TARGET;
- um TARGET recém-perdido pode permanecer acima de `target-keep` por aproximadamente 0,8 s para tolerar drop-outs curtos;
- depois dessa graça, um track `LOST` cai abaixo de `target-keep`;
- `OCCLUDED` permanece protegido, pois contato com `PLAYER #000` é forte evidência de combate;
- tracks muito novos não podem virar TARGET imediatamente;
- em região madura de `BACKGROUND_DYNAMIC`, um track distante do player fica abaixo do limiar de aquisição, a menos que mostre aproximação/movimento de combate coerente;
- a memória ambiental mínima passa a 30 s para reduzir reaprendizado da mesma água durante uma sessão.

## Objetivo da próxima validação

Na água, a telemetria deve deixar de mostrar novos alvos do tipo:

```text
target=#NNN/LOST/.../55%+
```

No combate, um alvo real deve continuar podendo apresentar:

```text
VISIBLE → OCCLUDED → breve LOST → VISIBLE
```

sem que `OCCLUDED` seja penalizado pelo filtro ambiental.
