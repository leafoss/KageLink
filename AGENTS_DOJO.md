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
GET  /api/dojo/status
POST /api/dojo/start
POST /api/dojo/stop
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
- Parar precisa liberar inputs mesmo quando o motor já terminou.

## 4. Interlock de controle

Durante `running=true`:

- controles manuais GAME ficam bloqueados;
- ativação manual do input fica bloqueada;
- clique remoto no centro do jogo fica bloqueado;
- chat e STATUS permanecem independentes;
- F12 permanece parada de emergência local.

O objetivo é impedir que APK, Desktop e agente autônomo enviem comandos concorrentes.

## 5. Contratos preservados do Kage Pilot v0.3j

- `R` é a única tecla normalmente mantida durante combate.
- setas e `H` são pulsos curtos e condicionados;
- `V` e `Y` são toggles por toque e proibidos durante combate;
- toda vitória exige KO aceito pelo gate de identidade;
- KO repetido do adversário anterior invalida o alvo e mantém o combate;
- memória nunca autoriza `V` sem confirmação visual atual;
- timeout de combate interrompe o loop;
- toda saída, erro, stop e shutdown precisa liberar teclas.

Alterações nesses contratos exigem branch própria, testes de regressão e validação física no jogo.

## 6. Internacionalização

Toda superfície nova deve existir em PT-BR e EN-US:

- Desktop;
- APK;
- mensagens controladas da API;
- documentação;
- estados e instruções de segurança.

Identificadores técnicos de telemetria podem permanecer estáveis em inglês para diagnóstico.

## 7. Gate obrigatório de distribuição

Antes de uma Release com Dojo:

1. suíte Python completa;
2. suíte Kage Pilot direcionada;
3. compilação dos três executáveis;
4. `--help` funcional nos dois helpers;
5. smoke launch do `KageLink.exe`;
6. Setup contendo os três executáveis;
7. `flutter gen-l10n`, analyze e testes;
8. APK release;
9. validação real do Setup instalado;
10. validação real do APK conectado ao Setup;
11. aprovação explícita de Rafael antes do merge.

Artifacts temporários de PR não substituem a Release oficial. A Release é construída novamente da `main` e publicada pelos nomes estáveis:

```text
KageLink-Windows-Setup.exe
KageLink-Android.apk
SHA256SUMS.txt
```

## 8. Validação física mínima 3.5.0

A versão não pode ser marcada pronta apenas porque os builds passaram. É obrigatório confirmar no Windows instalado:

```text
Setup instala os 3 executáveis
→ Desktop mostra Motor: Instalado
→ iniciar 1 rodada
→ diálogo, combate, KO, retorno e recuperação
→ parar pelo Desktop
→ iniciar pelo APK
→ status e contador sincronizados
→ controles GAME bloqueados durante o treino
→ F12 interrompe e libera inputs
```

Nenhum merge ou publicação final deve ocorrer sem esse gate real.
