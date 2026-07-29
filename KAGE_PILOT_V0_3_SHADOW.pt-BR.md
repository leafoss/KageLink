# Kage Pilot v0.3 — Shadow Combat

O Shadow Combat é a etapa intermediária entre percepção e controle automático.

Ele reutiliza o Entity Observer validado no Dojo, com GRID lógica de 32×32 px, `BACKGROUND_DYNAMIC`, `CONTACT_MEMORY`, `OCCLUDED` e reacquisition. Nenhuma tecla é enviada ao Shinobi Story Online.

A camada transforma o TARGET validado em uma decisão hipotética:

```text
sem TARGET      -> SEARCH / HOLD
TARGET distante -> MOVE_LEFT/RIGHT/UP/DOWN
TARGET contato  -> FACE_* / R_ON
contato estável e visualmente confirmado -> H_READY
```

`H_READY` é deliberadamente proibido quando o alvo existe apenas em `CONTACT_MEMORY`; é necessário `VISIBLE` ou `OCCLUDED` com estabilidade temporal e cooldown.

O objetivo é comparar as decisões do sistema com a luta manual antes de conectar qualquer saída ao `GameInputController`.

## Execução

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_shadow.py --telemetry-seconds 1
```

Opcionalmente, grave um JSONL de cada decisão:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_shadow.py --telemetry-seconds 1 --log kage_pilot_shadow_test.jsonl
```

A GRID padrão deste modo é 32×32 px, conforme validação visual no Dojo em julho de 2026.
