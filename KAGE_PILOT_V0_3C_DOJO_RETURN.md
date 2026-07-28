# Kage Pilot v0.3c — Retorno ao líder do Dojo (PT-BR)

## Problema validado

O pós-combate v0.3b funciona quando o líder está visível ou quando já existe memória visual. Porém, se o teste começa com o líder fora da tela e sem memória, o sistema permanece parado em `SEEK_LEADER`.

## Estratégia v0.3c

A política de combate não foi alterada. A v0.3c adiciona somente percepção auxiliar e navegação pós-combate.

### 1. Âncora persistente durante a luta

Em cada quadro do combate, o template local do líder é procurado de forma somente leitura. Depois da primeira confirmação visual, a posição é mantida durante a luta e deslocada pelo `global_flow` da câmera.

```text
posição visual confirmada do líder
+ deslocamento global da câmera por quadro
= posição prevista atual
```

A memória dura até 180 segundos nesta revisão.

### 2. Retorno por memória

Depois da mensagem autoritativa `has been Knocked-Out`, todas as teclas de combate são liberadas. Se existe âncora, Leafos retorna por pulsos curtos até o líder reaparecer.

Estado de log:

```text
RETURN_TO_LEADER
```

A memória pode orientar caminhada, mas nunca pode apertar `V`.

### 3. Busca limitada sem âncora

Se o líder nunca foi visto no processo atual, começa uma busca em quadrado expansivo:

```text
UP 1
RIGHT 1
DOWN 2
LEFT 2
UP 3
RIGHT 3
...
```

Cada unidade é composta por pulsos dead-man. Setas nunca são mantidas. A busca para imediatamente quando o template visual reaparece e tem limite de tempo e raio.

Estados:

- `SEARCH_WAIT`: pequena espera antes de iniciar a busca;
- `SEARCH_LEADER`: pulso da busca limitada;
- `SEARCH_HOLD`: limite atingido; nenhuma tecla enviada.

### 4. Meditação continua visualmente protegida

Mesmo que a memória indique distância `d <= 1`, o sistema espera o líder reaparecer e exige duas confirmações visuais antes de tocar `V`.

```text
visual confirmado + adjacente
→ V uma vez
→ HP >= 90% e Chakra >= 50%
→ V uma vez
→ READY
```

## Segurança

- `R` e `H` nunca são usados durante o retorno;
- setas são somente pulsos curtos;
- `F12` interrompe imediatamente;
- perda de foreground interrompe o controle;
- a busca é limitada e não deve ser testada fora da área segura do Dojo.

## Teste isolado

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_postcombat_live_test_v03c.py --seconds 60
```

## Ciclo completo

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03c.py --seconds 90 --log kage_pilot_live_test_7.jsonl
```
