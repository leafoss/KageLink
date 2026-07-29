# KageLink 3.5.0 RC1 — Falha de empacotamento do template do treinador

**Data:** 29/07/2026  
**PR:** #18  
**RC afetado:** commit `1f3e608406f0dc6006adb433a244a7109afc31f4`

## Resultado físico

O Setup, o Desktop, a API, o APK e o início remoto do Dojo funcionaram. Porém, durante a aquisição inicial do treinador, o personagem permaneceu na busca limitada e não confirmou visualmente o sprite.

## Causa confirmada

A v0.3b registrou que a referência antiga embutida não obtinha score suficiente na captura real. O detector confiável passou a usar uma calibração local salva em:

```text
data/kage_pilot/dojo_leader_template.png
```

Essa pasta é ignorada pelo Git. Portanto, o arquivo calibrado que existia no computador usado nos testes por código-fonte não entrou no GitHub.

Os specs `KagePilotDojo.spec` e `KagePilotRound.spec` coletam dependências Python/OpenCV, mas não incluem `data/kage_pilot/dojo_leader_template.png` em `datas`. No executável instalado, `CalibratedDojoLeaderDetector` não encontra o template local e recorre silenciosamente à referência embutida antiga.

A busca então nunca recebe duas confirmações visuais acima do threshold e continua emitindo pulsos de procura até timeout.

## Correção obrigatória para RC2

1. recuperar o template calibrado original do computador de validação;
2. versionar uma cópia canônica adequada para distribuição;
3. incluir o arquivo em ambos os helpers PyInstaller;
4. preservar suporte a override local futuro;
5. emitir telemetria explícita da origem do template;
6. falhar fechado antes de caminhar quando apenas a referência incompatível estiver disponível;
7. adicionar gate que execute os helpers empacotados e confirme a presença/decodificação do template distribuído;
8. gerar novo Setup RC2 e repetir o teste físico.

## Estado

O RC1 não está aprovado para merge. As demais funcionalidades validadas permanecem aproveitáveis, mas a aquisição do treinador deve ser corrigida antes de nova Release Candidate.
