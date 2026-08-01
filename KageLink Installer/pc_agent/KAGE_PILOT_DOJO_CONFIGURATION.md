# Kage Pilot Dojo — Configuração

**Status:** contrato público do release candidate v0.3j  
**Arquivo canônico:** `config/kage_pilot_dojo.json`

## Objetivo

Manter as configurações básicas do treinamento em um único local fácil de editar, revisar e apresentar na aba Dojo do KageLink.

O arquivo JSON controla:

- quantidade de rodadas;
- esperas entre etapas;
- timeouts de busca, combate e recuperação;
- percentuais de HP e Chakra necessários para `READY`;
- uso de `H`;
- threshold visual do treinador;
- pasta de logs.

A lógica de segurança não é configurável por esse arquivo.

## Arquivo padrão

```json
{
  "schema_version": 1,
  "rounds": 1,
  "timing": {
    "after_trainer_click_seconds": 5.0,
    "dialog_find_timeout_seconds": 6.0,
    "after_dialog_ok_seconds": 5.0,
    "combat_timeout_seconds": 120.0,
    "post_combat_timeout_seconds": 240.0,
    "trainer_search_timeout_seconds": 90.0,
    "round_startup_delay_seconds": 1.0,
    "chat_poll_seconds": 0.15
  },
  "recovery": {
    "hp_percent": 90.0,
    "chakra_percent": 40.0
  },
  "combat": {
    "h_enabled": true
  },
  "detection": {
    "leader_threshold": 0.88
  },
  "logging": {
    "directory": "kage_pilot_loop_logs"
  }
}
```

## Campos

### Controle geral

| Campo | Significado |
|---|---|
| `rounds` | `1` executa uma rodada; `0` repete até desligamento/F12. |

### Tempos

| Campo | Significado |
|---|---|
| `after_trainer_click_seconds` | Espera entre o clique único no treinador e a confirmação do diálogo. |
| `dialog_find_timeout_seconds` | Tempo máximo para localizar o diálogo e o botão `OK`. |
| `after_dialog_ok_seconds` | Espera depois do botão `OK` para o adversário aparecer. |
| `combat_timeout_seconds` | Limite máximo da fase de combate; o KO pode encerrá-la antes. |
| `post_combat_timeout_seconds` | Limite para retornar, meditar e alcançar `READY`. |
| `trainer_search_timeout_seconds` | Limite para localizar o treinador antes da luta. |
| `round_startup_delay_seconds` | Pequena espera depois de focar a janela antes do controle. |
| `chat_poll_seconds` | Intervalo de leitura do chat para detectar o KO. |

### Recuperação

| Campo | Faixa permitida | Padrão |
|---|---:|---:|
| `hp_percent` | `90` a `100` | `90` |
| `chakra_percent` | `40` a `100` | `40` |

Os pisos são `HP >= 90%` e `Chakra >= 40%`. A configuração pode aumentar esses valores, mas não reduzi-los.

### Combate e detecção

| Campo | Significado |
|---|---|
| `h_enabled` | `true` permite o uso guardado de `H`; `false` mantém somente ataque base/orientação. Deve ser booleano JSON real, sem aspas. |
| `leader_threshold` | Confiança mínima do template visual do treinador. |

## Integração com a aba Dojo

Ao abrir a aba, o Desktop busca os valores atuais no backend e preenche os campos. Enquanto o usuário estiver editando um campo, as atualizações periódicas de status não podem restaurar o valor anterior.

Os valores editados são aplicados quando **Iniciar** é clicado:

```text
backend preenche a interface
→ usuário altera localmente
→ polling preserva o campo alterado
→ Iniciar envia todos os valores visíveis
→ backend salva o debug e inicia o runtime com a configuração enviada
```

A opacidade é mostrada como percentual inteiro de `10` a `100` e convertida na fronteira da API:

```text
85 → 0,85
10 → 0,10
```

## Uso

Mostrar a configuração efetiva sem iniciar o jogo:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --show-config
```

Executar com o arquivo padrão:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py
```

Usar outro arquivo:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py `
  --config ".\config\meu_dojo.json"
```

Sobrescrever temporariamente valores sem editar o JSON:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py `
  --rounds 3 `
  --dialog-delay 4 `
  --spawn-delay 5 `
  --recovery-hp-percent 95 `
  --recovery-chakra-percent 40
```

A precedência é:

```text
valor enviado pela interface ou argumento do PowerShell
→ arquivo JSON
→ padrão interno do DojoTrainingConfig
```

## Validação fail-closed

O programa não inicia quando encontra:

- JSON inválido;
- seção com formato incorreto;
- chave desconhecida;
- versão de schema não suportada;
- `h_enabled` que não seja `true` ou `false` real;
- HP abaixo de 90% ou acima de 100%;
- Chakra abaixo de 40% ou acima de 100%;
- opacidade do overlay abaixo de 10% ou acima de 100%.

Erros de configuração terminam com código `2` e uma mensagem `DOJO_CONFIG_ERROR / ERRO_CONFIG_DOJO`.

## Regras que permanecem fixas

O JSON não pode alterar:

- `has been Knocked-Out` como autoridade de fim do combate;
- liberação imediata de todas as teclas após KO;
- clique único no treinador;
- botão `OK` acionado diretamente;
- proibição de `V` e `Y` durante combate;
- `V` somente após confirmação visual do treinador;
- `R` como única tecla normalmente mantida;
- setas e `H` como pulsos;
- `MAP_SAVE_RESYNC`, `H_SETTLE_HOLD` e demais gates de segurança;
- F12 como parada de emergência.

O app não deve ler o JSON e reproduzir a lógica por conta própria. A aba Dojo constrói um `DojoTrainingConfig` e chama exclusivamente `DojoTrainingService`.

Todos os textos visíveis devem passar pelo sistema de internacionalização PT-BR/EN-US; nomes de campos JSON são identificadores técnicos estáveis.
