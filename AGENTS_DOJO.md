# Bíblia normativa — KageLink Dojo Trainer

Este documento é uma extensão normativa da `AGENTS.md`. Em caso de divergência, deve ser aplicada a regra mais conservadora para segurança do personagem, integridade do GitHub e rastreabilidade da distribuição.

[English](AGENTS_DOJO.en.md)

## 1. Autoridade e separação de responsabilidades

```text
Shinobi Story Online
        ↑
Windows PC Agent — autoridade de visão, decisão e input
        ↑
Desktop / API autenticada
        ↑
APK Android — controle remoto e observação
```

- O motor do Dojo executa somente no Windows que contém o jogo.
- O APK nunca executa visão computacional, teclado ou lógica de combate.
- Desktop e APK usam o mesmo serviço público e o mesmo estado.
- Nenhuma UI pode implementar uma segunda regra de combate.

## 2. Runtime instalado

A distribuição Windows oficial precisa instalar, lado a lado:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

- `KageLink.exe` hospeda Desktop, API e estado público.
- `KagePilotDojo.exe` executa o loop isolado entre rodadas.
- `KagePilotRound.exe` executa uma rodada isolada.
- A instalação oficial não pode depender de Python instalado nem de scripts `.py` soltos.
- Em desenvolvimento, a execução por Python permanece válida para diagnóstico e regressão.

## 3. API pública e autenticação

Endpoints oficiais:

```text
GET    /api/dojo/status
POST   /api/dojo/start
POST   /api/dojo/stop
GET    /api/dojo/logs/latest
GET    /api/dojo/templates
GET    /api/dojo/templates/{mode}/image
POST   /api/dojo/templates/{mode}
DELETE /api/dojo/templates/{mode}
```

Todos exigem o mesmo Bearer Token do KageLink. O status deve expor, no mínimo:

```text
available
running
phase
current_round
completed_rounds
last_line
last_error
return_code
position_state
position_x
position_y
position_confidence
recent_actions
last_log
```

- Iniciar quando já estiver ativo retorna conflito.
- Iniciar sem runtime instalado opera fail-closed.
- Iniciar sem ao menos um template personalizado válido opera fail-closed com `DOJO_TRAINER_TEMPLATE_REQUIRED`.
- Parar precisa liberar inputs mesmo quando o motor já terminou.
- O endpoint de logs expõe somente metadados e caminho do último diagnóstico; nunca transmite um console contínuo.

## 4. Templates externos 32×32 e 64×64 — REGRA PROTEGIDA

O KageLink não deve depender de uma imagem do Dojo Trainer incorporada ao executável ou ao Setup como fonte principal de visão.

O usuário pode fornecer templates independentes para:

```text
modo do jogo 32×32
modo do jogo 64×64
```

Regras permanentes:

- as imagens são propriedade da instalação do usuário;
- devem ser persistidas fora de `Program Files`, fora do executável e fora da pasta temporária do PyInstaller;
- o local canônico é `%LOCALAPPDATA%\KageLink\data\kage_pilot\templates`;
- atualização ou reinstalação normal deve preservar os templates;
- cada modo possui arquivo e metadados independentes;
- o detector pode carregar os dois modos simultaneamente e deve escolher somente uma correspondência visual estável;
- o upload precisa validar decodificação, limites de tamanho e dimensões;
- remover um template não pode remover o outro;
- o treinamento instalado não pode iniciar sem pelo menos um template personalizado válido;
- a calibração local do código-fonte pode permanecer como compatibilidade exclusiva de desenvolvimento;
- nenhum fallback incompatível pode autorizar clique, `V` ou movimento de recuperação.

## 5. Regra canônica de navegação Desktop

A ordem canônica da barra lateral do KageLink Desktop é:

```text
Visão geral / Overview
Memória / Memory
Conexão / Connection
Dojo Trainer
Configurações / Settings
```

**Configurações / Settings deve ser sempre o último item do menu lateral.**

Esta é uma regra permanente de produto, não apenas um detalhe da tela Dojo. Novas páginas devem ser inseridas antes de `Settings`. Testes de UI ou constantes canônicas devem impedir regressão dessa ordem.

A página Dojo possui a hierarquia canônica:

```text
Resumo
Configurações
Imagens
Logs
```

- `Resumo` contém estado, progresso, localização resumida, controle e últimas ações.
- `Configurações` mostra somente parâmetros que já existirem no contrato do produto.
- `Imagens` contém os templates 64×64 e 32×32, nesta ordem.
- `Logs` mostra somente o último diagnóstico de falha e ações para abrir arquivo/pasta.
- A página precisa abrir corretamente no primeiro frame; maximizar/minimizar artificialmente é proibido como correção de layout.

## 6. Interlock de controle

Durante `running=true`:

- controles manuais GAME ficam bloqueados;
- ativação manual do input fica bloqueada;
- clique remoto no centro do jogo fica bloqueado;
- chat e STATUS permanecem independentes;
- F12 permanece parada de emergência local.

O objetivo é impedir que APK, Desktop e agente autônomo enviem comandos concorrentes.

## 7. Contratos preservados do Kage Pilot v0.3j

- `R` é a única tecla normalmente mantida durante combate.
- setas e `H` são pulsos curtos e condicionados;
- `V` e `Y` são toggles por toque e proibidos durante combate;
- toda vitória exige KO aceito pelo gate de identidade;
- KO repetido do adversário anterior invalida o alvo e mantém o combate;
- memória nunca autoriza `V` sem confirmação visual atual;
- timeout de combate interrompe o loop;
- toda saída, erro, stop e shutdown precisa liberar teclas.

Alterações nesses contratos exigem branch própria, testes de regressão e validação física no jogo.

## 8. Journal de sessão do Dojo — REGRA 3.5.1

O journal do Dojo é exclusivo da sessão e não pode poluir o Kage Agent ou o log geral.

Local canônico:

```text
%LOCALAPPDATA%\KageLink\logs\dojo
```

Contrato:

1. o início cria `dojo_session_<timestamp>_<id>.active` em UTF-8;
2. eventos importantes recebem timestamp, categoria e flush imediato;
3. conclusão normal remove o `.active` e não deixa log permanente;
4. erro transforma o arquivo em `dojo_error_<timestamp>_<id>.txt`;
5. um `.active` abandonado é convertido em `dojo_incomplete_<timestamp>_<id>.txt` na próxima inicialização;
6. falha ao escrever o journal nunca pode quebrar F12, stop ou liberação de teclas;
7. traceback completo deve ser preservado quando houver exceção;
8. o arquivo deve conter configuração, templates, fases, visão, posição, retorno, fallback, código de saída e resumo final.

O Desktop mostra apenas o último erro, horário, resumo, caminho e botões para abrir o arquivo ou a pasta.

## 9. Posição visual canônica — REGRA PROTEGIDA 3.5.1

A posição do personagem não pode ser inferida apenas pelas teclas enviadas. Empurrões, teleports, jutsus, colisões, movimento de inimigos e câmera podem deslocá-lo sem comando do KageLink.

Hierarquia de autoridade:

```text
1. coordenadas reais comprovadamente acessíveis, se existirem
2. relocalização visual por keyframes
3. odometria visual contínua
4. comandos enviados, apenas como intenção auxiliar
```

Estados obrigatórios:

```text
KNOWN
UNCERTAIN
LOST
```

A origem `(0,0)` só pode ser definida ou redefinida após confirmação visual válida do Trainer. Ela representa a região do mundo onde o Trainer foi confirmado, não o início do macro nem o centro da tela.

A relação conceitual é:

```text
movimento_no_mundo = movimento_do_jogador_na_tela - movimento_do_cenário_na_tela
```

Regras permanentes:

- movimento observado sem comando atualiza X/Y como deslocamento externo;
- comando sem movimento visual não altera X/Y;
- deslocamento abrupto sem continuidade visual muda o estado para `LOST`;
- o sistema jamais pode inventar coordenadas depois de perder continuidade;
- HUD, chat e elementos fixos devem ser excluídos da medição sempre que possível;
- a estimativa precisa carregar confiança e rejeitar valores inconsistentes;
- valores em pixels são convertidos pelo modo de célula 32×32 ou 64×64.

## 10. Keyframes, relocalização e retorno em malha fechada

Enquanto a posição estiver `KNOWN`, o motor pode guardar keyframes limitados e associados a X/Y. Não é permitido guardar todo frame.

A relocalização exige:

- personagem parado e teclas liberadas;
- comparação com keyframes conhecidos;
- score mínimo;
- margem suficiente sobre o segundo melhor candidato;
- restauração de X/Y somente com evidência confiável.

O retorno ao Trainer é um controlador em malha fechada:

```text
parar
→ validar/relocalizar posição
→ calcular erro até (0,0)
→ enviar um pulso
→ medir movimento real
→ atualizar X/Y
→ recalcular
→ repetir com limites
→ scan estacionário na origem
→ busca local curta
→ busca em anéis existente, apenas como fallback final
```

- Uma rota histórica pode ajudar a evitar obstáculos, mas nunca substitui a posição atual observada.
- Empurrão durante o retorno precisa causar replanejamento imediato.
- Movimento bloqueado não pode gerar progresso falso.
- Todo retorno possui timeout, limite de passos e detecção de ausência de progresso.
- Posição `LOST` proíbe retorno vetorial longo.
- F12 e Stop interrompem odometria, relocalização e retorno imediatamente.

## 11. Internacionalização

Toda superfície nova deve existir em PT-BR e EN-US:

- Desktop;
- APK;
- mensagens controladas da API;
- documentação;
- estados e instruções de segurança.

Identificadores técnicos de telemetria podem permanecer estáveis em inglês para diagnóstico.

## 12. Gate obrigatório de distribuição

Antes de uma Release com Dojo:

1. suíte Python completa;
2. suíte Kage Pilot direcionada;
3. compilação dos três executáveis;
4. `--help` funcional nos dois helpers;
5. smoke launch do `KageLink.exe`;
6. Setup contendo os três executáveis;
7. upload, persistência, remoção e recarga dos templates 32×32 e 64×64;
8. journal normal, erro e recuperação de `.active` validados;
9. odometria, keyframes, relocalização e retorno cobertos por testes;
10. `flutter gen-l10n`, analyze e testes;
11. APK release;
12. validação real do Setup instalado;
13. validação real do APK conectado ao Setup;
14. aprovação explícita de Rafael antes do merge.

Artifacts temporários de PR não substituem a Release oficial. A Release é construída novamente da `main` e publicada pelos nomes estáveis:

```text
KageLink-Windows-Setup.exe
KageLink-Android.apk
SHA256SUMS.txt
```

## 13. Validação física mínima 3.5.1

A versão não pode ser marcada pronta apenas porque os builds passaram. É obrigatório confirmar no Windows instalado:

```text
Setup instala os 3 executáveis
→ Desktop abre organizado sem maximizar/restaurar
→ Settings aparece como último item do menu
→ abas Resumo, Configurações, Imagens e Logs funcionam
→ templates 32×32 e 64×64 persistem
→ sessão normal não deixa log de erro
→ erro controlado produz .txt e aparece na aba Logs
→ iniciar rodada em 32×32 e 64×64
→ posição muda ao andar e ao sofrer deslocamento externo
→ posição perdida não inventa X/Y
→ relocalização reconhece região já mapeada
→ retorno compensa empurrão e busca (0,0)
→ scan estacionário precede busca local e anéis
→ parar pelo Desktop
→ iniciar pelo APK e observar status sincronizado
→ controles GAME ficam bloqueados
→ F12 interrompe e libera inputs
```

Nenhum merge ou publicação final deve ocorrer sem esse gate real.
