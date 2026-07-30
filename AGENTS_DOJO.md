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
```

- Iniciar quando já estiver ativo retorna conflito.
- Iniciar sem runtime instalado opera fail-closed.
- Iniciar sem ao menos um template personalizado válido opera fail-closed com `DOJO_TRAINER_TEMPLATE_REQUIRED`.
- Parar precisa liberar inputs mesmo quando o motor já terminou.

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

## 8. Internacionalização

Toda superfície nova deve existir em PT-BR e EN-US:

- Desktop;
- APK;
- mensagens controladas da API;
- documentação;
- estados e instruções de segurança.

Identificadores técnicos de telemetria podem permanecer estáveis em inglês para diagnóstico.

## 9. Gate obrigatório de distribuição

Antes de uma Release com Dojo:

1. suíte Python completa;
2. suíte Kage Pilot direcionada;
3. compilação dos três executáveis;
4. `--help` funcional nos dois helpers;
5. smoke launch do `KageLink.exe`;
6. Setup contendo os três executáveis;
7. upload, persistência, remoção e recarga dos templates 32×32 e 64×64;
8. `flutter gen-l10n`, analyze e testes;
9. APK release;
10. validação real do Setup instalado;
11. validação real do APK conectado ao Setup;
12. aprovação explícita de Rafael antes do merge.

Artifacts temporários de PR não substituem a Release oficial. A Release é construída novamente da `main` e publicada pelos nomes estáveis:

```text
KageLink-Windows-Setup.exe
KageLink-Android.apk
SHA256SUMS.txt
```

## 10. Validação física mínima 3.5.0

A versão não pode ser marcada pronta apenas porque os builds passaram. É obrigatório confirmar no Windows instalado:

```text
Setup instala os 3 executáveis
→ Desktop mostra Motor: Instalado
→ Settings aparece como último item do menu
→ upload do template 32×32 persiste após reiniciar
→ upload do template 64×64 persiste após reiniciar
→ iniciar 1 rodada em modo 32×32
→ iniciar 1 rodada em modo 64×64
→ diálogo, combate, KO, retorno e recuperação
→ parar pelo Desktop
→ iniciar pelo APK
→ status e contador sincronizados
→ controles GAME bloqueados durante o treino
→ F12 interrompe e libera inputs
```

Nenhum merge ou publicação final deve ocorrer sem esse gate real.
