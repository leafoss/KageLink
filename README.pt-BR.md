# KageLink 3.4.2

[English](README.md) · [Bíblia de desenvolvimento](AGENTS.md) · [Kage Pilot](KAGE_PILOT.md) · [Downloads](DOWNLOAD.md)

<!-- kagelink-downloads-start -->

## ⬇️ Download

**Versão estável atual: KageLink 3.4.2**

| Windows | Android |
| --- | --- |
| **[Baixar KageLink para Windows](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Windows-Setup.exe)** | **[Baixar KageLink para Android](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Android.apk)** |

[Release mais recente e SHA-256](https://github.com/leafoss/KageLink/releases/latest)

<!-- kagelink-downloads-end -->

O **KageLink** conecta o **Shinobi Story Online** executado no Windows a um aplicativo Android para chat OOC/IC, controle remoto do jogo, visualização de `Status | Inventory` e integração opcional com LeafOS/Obsidian.

Versões:

```text
KageLink: 3.4.2
Flutter: 3.4.2+22
```

> O Android é uma interface remota. O jogo precisa permanecer aberto no computador que executa o PC Agent.

## Componentes

### PC Agent — Windows

Responsável por:

- localizar `Shinobi Story Online`;
- ler o chat BYOND;
- classificar OOC e IC/RP;
- persistir histórico SQLite e estado do parser;
- localizar separadamente os campos OOC e IC;
- enviar mensagens ao campo correto;
- expor API HTTP e WebSockets autenticados;
- iniciar rede local e Cloudflare Quick Tunnel;
- transmitir GAME e controlar teclas permitidas;
- transmitir e controlar `Status | Inventory` em STATS;
- exportar RAW e executar o pipeline LeafOS quando habilitado;
- oferecer o Kage Pilot local e experimental.

### Aplicativo Android

Oferece:

- perfis de conexão;
- token em armazenamento seguro;
- rotas interna, externa e personalizada;
- abas OOC, IC/RP, GAME e STATS;
- histórico sincronizado e reconexão;
- calibração independente OOC/IC;
- joystick e bancos `ABCD`/`ZXVU`;
- PT-BR e EN-US.

## Instalação

### Windows

1. Baixe `KageLink-Windows-Setup.exe`.
2. Feche uma instância antiga.
3. Execute o instalador.
4. Abra o KageLink.
5. Na primeira execução, escolha PT-BR ou EN-US e mantenha a porta `8765`, salvo necessidade específica.

Atualizações normais preservam configuração, chave, histórico e calibrações. Não apague `config.json` ou `chat_history.db` como procedimento normal de atualização.

### Android

1. Baixe `KageLink-Android.apk`.
2. Abra o APK e autorize somente a origem usada para instalação.
3. Instale o aplicativo.
4. No PC Agent, copie o endereço e a chave.
5. Crie um perfil no Android.

O APK e o PC Agent devem preferencialmente pertencer à mesma release.

## Primeira execução do PC Agent

O assistente solicita:

- idioma;
- porta;
- ativação opcional do LeafOS;
- caminho da Vault, quando aplicável;
- personagem principal, quando o LeafOS estiver ativo.

O Agent cria automaticamente uma chave aleatória e segura. Trate-a como senha.

A tela principal apresenta:

- estado do Agent, jogo, chat, entradas e conexão externa;
- endereço externo recomendado;
- endereço local;
- chave de acesso;
- personagem e sessão LeafOS;
- controles do Ollama/Interpreter/Reviewer quando configurados.

As informações de conexão também ficam em:

```text
%LocalAppData%\KageLink PC Agent\KAGELINK_CONNECTION.txt
```

## Criar uma conexão Android

Informe:

- nome da rota;
- endereço local, URL HTTPS ou endereço personalizado;
- chave de acesso mostrada no PC Agent.

Exemplos:

```text
192.168.0.25:8765
https://exemplo.trycloudflare.com
```

A URL `trycloudflare.com` pode mudar quando o túnel reinicia.

## Chat OOC e IC/RP

OOC e IC são canais independentes na leitura e no envio.

### Regra IC de roleplay

Todo bloco iniciado por:

```text
(*
```

e encerrado pelo próximo:

```text
*)
```

é IC/RP. Blocos fragmentados ficam pendentes até o fechamento.

### Regra literal `Says:`

O marcador oficial é exatamente:

```text
Says:
```

Exemplos IC:

```text
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Não ativam essa regra:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: Hello
```

A regra é deliberadamente case-sensitive.

### Envio

Endpoints dedicados:

```text
/api/send/ooc
/api/send/ic
```

O Agent nunca deve usar silenciosamente o campo do outro canal.

Limite configurado:

```text
32000 caracteres
```

Quebras de linha são normalizadas antes do envio ao campo do jogo.

### Histórico

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

## Calibração OOC / IC

O BYOND pode recriar HWNDs. A calibração salva geometria e identidade suficiente para relocalizar os campos.

1. Abra o jogo.
2. No Android, abra a calibração.
3. Selecione um candidato para OOC.
4. Selecione outro candidato para IC.
5. Confirme os dois estados.

Um mesmo HWND nunca representa OOC e IC ao mesmo tempo.

## GAME

Contrato atual:

```text
janela: Shinobi Story Online
JPEG: 960 × 540
qualidade: 70
alvo: ~10 FPS
áudio: não
modos: Full | Zoom
```

Controles:

- joystick de oito direções;
- diagonais;
- toque, hold e multitouch;
- bancos `ABCD` e `ZXVU`;
- mapeamentos persistidos no Android;
- liberação automática de teclas ao sair, desconectar ou perder condições seguras.

Padrões:

| Botão | Tecla |
| --- | --- |
| A | E |
| B | Space |
| C | G |
| D | V |
| Z | Z |
| X | X |
| V | V |
| U | U |

O Agent aceita apenas a whitelist documentada na Bíblia. GAME não executa comandos genéricos do sistema.

## STATS

Alvo exclusivo:

```text
Título: Status | Inventory
Classe: #32770
Processo: o mesmo do Shinobi Story Online
```

Recursos:

- stream JPEG independente a 5 FPS;
- tentativa de abertura da janela;
- toque simples → clique esquerdo;
- toque longo → clique direito;
- coordenadas normalizadas;
- validação de PID, HWND e último frame.

STATS não é controle genérico do desktop.

## LeafOS / Obsidian

A integração é opcional e desativada por padrão.

Fluxo:

```text
histórico classificado
→ RAW append-only
→ Processor
→ sessão fechada
→ Interpreter
→ pending_review
→ Memory Reviewer
→ aprovação humana
→ Canonical Memory
```

Regras:

- RAW não reclassifica OOC/IC;
- IDs são a identidade dos registros;
- o Processor não reprocessa IDs;
- o Interpreter cria candidatos, não verdade canônica;
- o Reviewer é gate humano obrigatório;
- `memory.json` é a fonte canônica;
- `MEMORY.md` é projeção regenerável;
- falhas LeafOS permanecem isoladas do restante do Agent.

Nunca publique RAW, Vault, banco, token, URL privada ou logs sensíveis.

## Kage Pilot

O Kage Pilot possui uma única entrada pública:

```powershell
python kage_pilot.py dojo
```

Exemplo de dez rodadas:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Também preserva os comandos de gravação e treinamento por `kage_pilot.py`.

A baseline mergeada foi validada com 10/10 rodadas e mantém:

- um clique no treinador por rodada;
- retry de diálogo sem novo clique;
- F12 como emergência;
- proteção contra KO repetido;
- retorno e recuperação obrigatórios;
- pisos HP ≥ 90% e Chakra ≥ 50%;
- liberação de inputs em falha/transição.

Leia [KAGE_PILOT.md](KAGE_PILOT.md) antes de alterar esse subsistema.

## Rede e segurança

### Rede interna

Use o endereço local quando PC e celular estiverem na mesma rede alcançável.

### Rede externa

O Quick Tunnel fornece HTTPS sem exigir exposição manual normal da porta no roteador.

### Chave

Rotas sensíveis usam a chave KageLink. Nunca a publique.

### Limites de controle

- GAME usa apenas teclas permitidas;
- STATS usa apenas cliques normalizados no alvo validado;
- Kage Pilot atua somente no jogo validado;
- captura fallback exige a janela exata em foreground.

## Diagnóstico

### O Agent não encontra o jogo

- abra o Shinobi Story Online;
- restaure a janela;
- use a nova tentativa;
- consulte `logs\kagelink.log`.

### O Android não conecta

Verifique Agent, endereço, porta, chave, alcance da rede e URL externa atual.

### OOC ou IC não envia

Refaça a calibração e confirme os dois campos separadamente.

### `**Anbu** Says: test` aparece em OOC

Isso indica build antigo ou regressão. A regra oficial classifica como IC.

### RAW não aparece

Verifique integração ativa, caminhos, canal habilitado, permissões e logs.

### STATS não aparece

Abra/restaure `Status | Inventory` e tente novamente.

### Diagnóstico de startup

```text
KageLink Installer\DIAGNOSTICAR_KAGELINK.bat
```

## Build para desenvolvedores

### Android

```text
KageLink Installer\COMPILAR_APK.bat
```

Saída de release publicada:

```text
KageLink-Android.apk
```

### Windows

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

Saída de release publicada:

```text
KageLink-Windows-Setup.exe
```

O usuário final não precisa instalar Python para executar o Setup.

## Desenvolvimento

Leia [AGENTS.md](AGENTS.md) antes de alterar o projeto.

Princípios:

- GitHub é a fonte oficial;
- branch e PR para mudanças significativas;
- uma fonte canônica por responsabilidade;
- versões históricas ficam no Git;
- testes e documentação acompanham contratos;
- PT-BR e EN-US são obrigatórios;
- validação real é registrada quando Windows/BYOND exigir;
- nunca afirmar que um teste passou sem execução.

## Licença

Copyright © 2026 Rafael Demari Dib.

Uso, modificação e compilação para uso pessoal do proprietário são permitidos. Redistribuição ou publicação comercial requer autorização. Dependências de terceiros mantêm suas licenças próprias.
