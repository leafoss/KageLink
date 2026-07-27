# Kage Pilot v0.3 — Live Control Gate 1 (PT-BR)

## Objetivo

Validar combate real com o menor conjunto possível de ações automáticas depois da validação do Entity Observer e Shadow Combat.

Nesta etapa o Kage Pilot **envia teclas reais**, mas somente:

- `R` como estado-base de combate, usando o padrão BYOND de repetição já validado;
- setas direcionais para aproximação/recuperação;
- pulsos curtos de direção para corrigir facing em melee.

`H` permanece **somente em Shadow Mode**. O console pode indicar `H_READY(SHADOW)`, mas nenhuma tecla H é enviada.

## Regras de movimento

- `d <= 1 célula`: MELEE. Mantém R e apenas corrige facing com pulso curto quando necessário.
- `d >= 2 células`: APPROACH/RECOVER somente com confirmação visual atual (`VISIBLE`/`OCCLUDED`). Mantém R e segura a seta na direção do TARGET.
- TARGET temporariamente ausente: mantém R, mas não anda às cegas.
- `CONTACT_MEMORY` preserva identidade/facing apenas no contato local (`d <= 1`). Nunca autoriza perseguição distante.
- Um alvo distante dentro de região com forte evidência `BACKGROUND_DYNAMIC` produz `BACKGROUND_HOLD`, não movimento.

A regra de recuperação é deliberadamente conservadora: após knockback, se o inimigo ainda não estiver visualmente confirmado, Leafos segura posição com R. Ele só corre novamente quando o adversário reaparece como `VISIBLE` ou `OCCLUDED`. Isso evita perseguir água/efeitos usando apenas memória prevista.

## Segurança

- Duração padrão: 25 segundos.
- `F12`: parada imediata global.
- Perda de foreground interrompe o controle; o processo não tenta roubar novamente o foco nesta etapa.
- `finally` sempre libera R e todas as setas.
- H não é enviado.
- Não existe ainda pós-combate automático com V.

## Comando

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 25 --log kage_pilot_live_test_1.jsonl
```

## Critérios de sucesso

1. R permanece atacando durante a luta.
2. Quando o inimigo cruza de lado, Leafos corrige o facing sem caminhar continuamente para dentro dele.
3. Após knockback, uma confirmação visual em `d >= 2` produz RECOVER/MOVE na direção correta.
4. `CONTACT_MEMORY d >= 2` nunca produz movimento.
5. Região fortemente `BACKGROUND_DYNAMIC` não autoriza perseguição.
6. Em perda curta do TARGET, Leafos segura posição em vez de perseguir ruído.
7. `H_READY(SHADOW)` pode aparecer, mas H não é executado nesta etapa.
