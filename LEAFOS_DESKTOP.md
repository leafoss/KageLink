# KageLink · LeafOS Desktop

[English](LEAFOS_DESKTOP.en.md) · [README](README.pt-BR.md) · [Bíblia](AGENTS.md)

O **KageLink · LeafOS Desktop** reúne no mesmo `KageLink.exe` o Agent do Shinobi Story Online e o fluxo de memória LeafOS. O usuário final não precisa abrir PowerShell, executar módulos Python nem iniciar manualmente o Memory Reviewer.

## Fluxo normal do usuário

```text
Abrir KageLink.exe
        ↓
confirmar Personagem Principal
        ↓
abrir Shinobi Story Online
        ↓
jogar normalmente
        ↓
KageLink registra chat + histórico + RAW
        ↓
Processor organiza a sessão
        ↓
Finalizar sessão e revisar
        ↓
Interpreter local (Ollama / qwen3:14b)
        ↓
Memory Reviewer
        ↓
Aprovar / Editar + aprovar / Rejeitar
        ↓
Canonical Memory
```

O Android continua opcional. Ele permanece como interface remota para OOC, IC/RP, GAME, STATS e configuração do personagem, mas o LeafOS não depende mais de abrir o app Android para descobrir quem é o personagem principal.

## Uma aplicação, módulos separados

Para o usuário existe um programa:

```text
KageLink.exe
```

Internamente continuam separados:

```text
Chat Reader / Parser
HistoryStore
RAW Exporter
Processor
Interpreter
Memory Reviewer
Canonical Memory
GAME
STATS
Tunnel
```

A unificação é de **experiência de usuário**, não uma fusão das responsabilidades de domínio. Isso preserva isolamento, testes e rastreabilidade.

## Personagem Principal

Quando LeafOS está habilitado, a tela Desktop mostra o personagem atual. Se nenhum personagem estiver configurado, o KageLink solicita a escolha e o Processor não inicia uma nova sessão ambígua.

Cada nova sessão recebe seu próprio `primary_character`.

Trocar de personagem executa primeiro:

```text
sincronizar RAW
    ↓
processar mensagens pendentes
    ↓
finalizar sessão anterior
    ↓
registrar character_changed
    ↓
ativar novo personagem
```

Isso impede que duas identidades controladas pelo usuário sejam misturadas na mesma sessão.

## Encerramento de sessão

Os 15 minutos de inatividade continuam existindo, mas são um **fallback automático**, não a forma principal de terminar uma sessão.

Uma sessão pode terminar por:

- botão **Finalizar sessão e revisar**;
- troca de Personagem Principal;
- encerramento normal do KageLink, inclusive X/Alt+F4;
- fechamento persistente da janela do Shinobi Story Online;
- timeout de inatividade;
- recuperação de uma sessão deixada aberta após encerramento anormal.

Sessões fechadas registram:

```text
close_reason
closed_cleanly
closed_at
primary_character
```

Razões atuais:

```text
manual
character_changed
agent_shutdown
game_closed
idle_timeout
unclean_shutdown_recovery
```

## Ordem de fechamento do KageLink

No encerramento normal, a prioridade é preservar a sessão antes de desmontar a infraestrutura:

```text
última leitura do chat
        ↓
histórico
        ↓
RAW sync
        ↓
Processor
        ↓
fechar sessão
        ↓
salvar estado
        ↓
encerrar backend/túnel
        ↓
fechar KageLink
```

Se a finalização segura falhar, a interface informa o erro antes da saída forçada.

## Recuperação após queda abrupta

Nenhum processo consegue executar rotina de shutdown depois de perda de energia, BSOD ou `taskkill /F`.

Por isso, no próximo início o KageLink verifica se o Processor deixou `open_session`. Quando encontra uma sessão órfã, ela é fechada como:

```text
close_reason: unclean_shutdown_recovery
closed_cleanly: false
```

Antes disso, o exporter tenta sincronizar qualquer histórico já persistido.

## Shinobi Story fechado

O Desktop monitora o estado já produzido pelo Agent. Depois que o jogo esteve online, uma ausência contínua de aproximadamente 10 segundos é tratada como encerramento do jogo e pode fechar a sessão LeafOS aberta com `game_closed`.

A janela curta evita transformar oscilações momentâneas de detecção em fronteiras de sessão.

## Interpreter dentro do KageLink

O Interpreter continua sendo a mesma camada semântica e mantém o mesmo contrato:

```text
sessão fechada
    ↓
LeafOSInterpreter
    ↓
Interpretation Bundle
status: pending_review
```

Ele continua proibido de criar memória canônica automaticamente.

A diferença é que o usuário pode executar pela tela **Memória** ou pelo botão **Finalizar sessão e revisar**. A CLI permanece disponível apenas como ferramenta de desenvolvimento/diagnóstico.

## Ollama

O modelo padrão continua:

```text
qwen3:14b
http://127.0.0.1:11434
```

A tela Memória informa:

- Ollama instalado ou ausente;
- servidor online/offline;
- `qwen3:14b` disponível ou não.

A própria interface oferece ações para:

- instalar Ollama via `winget`, quando disponível;
- iniciar `ollama serve` sem PowerShell;
- executar `ollama pull qwen3:14b` sem PowerShell.

O modelo não é embutido dentro do `KageLink.exe`, evitando transformar o instalador em um pacote de muitos gigabytes.

## Memory Reviewer

O Reviewer continua preservando o gate humano:

```text
Interpreter candidate
        ↓
validar evidência até RAW
        ↓
Aprovar
Editar + aprovar
Rejeitar
        ↓
Canonical Memory somente após aprovação humana
```

No pacote final, o botão **Abrir Memory Reviewer** inicia o Reviewer usando o mesmo `KageLink.exe`. O usuário não precisa localizar Python nem executar comandos.

## Canonical Memory

A fonte oficial permanece:

```text
<Vault>/60 - Canonical Memory/memory.json
```

A projeção humana permanece:

```text
<Vault>/60 - Canonical Memory/MEMORY.md
```

`MEMORY.md` continua derivado e não é uma segunda fonte canônica.

## Tela Desktop

A navegação principal é:

```text
Visão geral
Memória
Conexão
Configurações
```

**Visão geral** mostra serviços, personagem, sessão atual e ações de finalização.

**Memória** mostra Ollama, modelo, sessões fechadas, interpretações e pendências do Reviewer.

**Conexão** mantém endereço externo, endereço local, chave e controles do túnel.

**Configurações** mantém idioma, porta e integração LeafOS.

A identidade visual segue a linguagem aprovada do LeafOS Memory Reviewer: verde escuro, superfícies discretas, destaque de folha e suporte PT-BR/en-US.

## Contrato de segurança

A unificação não altera estes princípios:

1. RAW é evidência append-only.
2. Processor organiza e não interpreta narrativa.
3. Interpreter produz candidatos, nunca verdade canônica.
4. Reviewer exige evidência válida.
5. Memória permanente exige ação humana explícita.
6. GAME/STATS/chat/túnel continuam isolados de falhas LeafOS.
7. OOC não vira sessão semântica de RP pelo Processor atual.
8. Nenhum fluxo normal do usuário exige PowerShell.

## Build

O PyInstaller agora usa `unified_launcher.py` como entrypoint e inclui os assets do Reviewer/LeafOS no `KageLink.exe`.

A CI executa:

```text
Python unittest completo
compileall
Flutter analyze
Flutter test
PyInstaller build smoke test
verificação do KageLink.exe gerado
```

O artefato de preview é publicado pelo workflow como:

```text
KageLink-unified-preview
```
