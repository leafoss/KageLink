# KageLink — Dream Daemon Observer

[English](README.md)

Ferramenta **passiva e somente leitura** para visualizar o tráfego TCP que chega do Dream Daemon ao processo `dreamseeker.exe`.

Ela não injeta código, não altera memória, não modifica pacotes, não envia comandos ao jogo e não tenta adivinhar que um byte representa automaticamente um inimigo. O objetivo é registrar evidências repetíveis para descobrir padrões do protocolo.

## O que a ferramenta mostra

- processo e conexão TCP ativa do Dream Seeker;
- direção `IN` — Dream Daemon → Dream Seeker;
- direção `OUT` — Dream Seeker → Dream Daemon;
- horário, tamanho, sequência TCP, ACK e stream;
- payload em hexadecimal e ASCII;
- entropia do payload;
- percentual de bytes imprimíveis;
- assinatura SHA-256 curta;
- percentual de mudança em relação ao pacote anterior;
- offsets alterados em relação ao último payload do mesmo tamanho;
- strings ASCII encontradas;
- correlação por marcadores de eventos;
- captura bruta `capture.pcapng` para análise posterior no Wireshark.

## Marcadores

Durante o teste, pressione um marcador imediatamente quando o evento acontecer:

- **Inimigo apareceu**;
- **Inimigo se moveu**;
- **Jogador se moveu**;
- **Golpe / ataque**;
- **Mapa mudou**;
- marcador personalizado.

O analisador compara uma janela antes e depois do marcador e mostra principalmente os pacotes de entrada:

- tamanhos mais frequentes;
- assinaturas que não apareciam na linha de base;
- offsets que mudaram repetidamente;
- strings ASCII visíveis;
- quantidade de pacotes e bytes em cada direção.

## Pré-requisitos

1. Windows 10 ou 11.
2. Python 3.11.
3. Wireshark instalado com:
   - TShark;
   - Dumpcap;
   - Npcap.
4. Dream Seeker aberto e conectado ao jogo.

A captura pode exigir PowerShell executado como **Administrador**, dependendo da configuração do Npcap.

## Como executar

Abra PowerShell como Administrador dentro desta pasta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\run_dream_daemon_observer.ps1
```

O script cria um ambiente Python isolado, instala apenas `psutil` e abre a interface.

## Primeiro teste recomendado

1. Abra o Shinobi Story Online e fique parado em uma área segura.
2. Abra o Observer.
3. Clique em **Atualizar conexões**.
4. Selecione a conexão cujo endpoint remoto corresponde ao servidor do jogo.
5. Selecione a interface de rede ativa, normalmente Ethernet ou Wi-Fi.
6. Clique em **Iniciar captura**.
7. Aguarde 5 segundos parado para criar uma linha de base.
8. Faça apenas uma ação por vez: caminhar uma célula, deixar um NPC entrar na tela, receber um ataque ou trocar de mapa.
9. Pressione o marcador correspondente no instante do evento.
10. Repita o mesmo evento pelo menos 10 vezes.
11. Clique em **Parar** e abra a pasta da sessão.

## Dados gravados

Por padrão:

```text
%LocalAppData%\KageLink PC Agent\data\dream_daemon_observer\YYYYMMDD_HHMMSS\
```

Arquivos:

```text
session.json
packets.jsonl
packets.csv
markers.jsonl
event_analysis.jsonl
capture.pcapng
```

`packets.jsonl` guarda os payloads em hexadecimal e Base64. `capture.pcapng` preserva a captura para abrir no Wireshark e usar **Analyze → Follow → TCP Stream**.

## Como interpretar corretamente

Um pacote TCP não é necessariamente uma mensagem completa do jogo. Uma mensagem pode ser dividida, agrupada com outras, retransmitida, comprimida, codificada, cifrada ou baseada em deltas.

Por isso, a primeira meta não é encontrar texto como `enemy=true`. A meta é descobrir padrões reproduzíveis, por exemplo:

```text
Inimigo entra na tela
→ sempre surge um payload IN de 48 bytes
→ bytes 0x0C–0x0F mudam
→ assinatura começa a formar uma família estável
```

Depois disso, podemos criar um decodificador experimental isolado para testar hipóteses sem afetar o Dream Seeker.

## Protocolo de coleta recomendado

Grave sessões separadas para:

- linha de base parada por 30 segundos;
- dez movimentos para cada direção;
- inimigo entrando, parando, aproximando e saindo da tela;
- ataque do jogador;
- ataque do inimigo;
- dano recebido;
- KO e fim da rodada;
- transição de mapa.

Evite combinar ações no mesmo instante. Quanto mais isolado o evento, mais útil será a correlação.

## Testes

```powershell
.\run_tests.ps1
```

Os testes verificam métricas de payload, offsets alterados, comparação entre pacotes do mesmo tamanho, classificação de direção e detecção de assinaturas exclusivas na janela do evento.

## Limites da primeira versão

- ainda não decodifica o protocolo do BYOND;
- não afirma que um payload representa uma entidade;
- a tabela mostra segmentos TCP individuais;
- a reconstrução completa deve ser feita pelo `capture.pcapng` no Wireshark;
- a captura depende de TShark/Npcap e das permissões do Windows.
