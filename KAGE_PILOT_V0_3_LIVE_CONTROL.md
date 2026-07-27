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
- `d >= 2 células`: APPROACH/RECOVER. Mantém R e segura a seta na direção do TARGET.
- TARGET temporariamente ausente: mantém R, mas não anda às cegas.
- CONTACT_MEMORY preserva a última direção visual confirmada.

A regra `d >= 2 => RECOVER` é deliberada: evita repetir o problema da v0.2 em que Leafos era empurrado e continuava atacando o vazio.

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
3. Após knockback, `d >= 2` produz RECOVER/MOVE na direção correta.
4. Em perda curta do TARGET, Leafos segura posição em vez de perseguir ruído.
5. `H_READY(SHADOW)` pode aparecer, mas H não é executado nesta etapa.
