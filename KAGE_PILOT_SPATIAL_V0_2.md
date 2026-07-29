# Kage Pilot v0.2 — Experimento Espacial

Este modo é uma revisão experimental da percepção do Kage Pilot v0.2. Ele **não substitui** ainda o modelo temporal principal.

## Por que existe

Nos testes reais do Dojo, o controle de teclado foi validado e o `R` passou a funcionar corretamente usando o padrão de repetição de `KEYDOWN` exigido pelo BYOND. Porém, o modelo visual original continuou classificando praticamente todas as situações como `idle`, com confiança próxima de zero.

Isso impediu o Pilot de:

- corrigir `LEFT/RIGHT` após knockback ou separação do inimigo;
- reconhecer situações em que `H` deveria ser usado;
- diferenciar suficientemente estados de combate visualmente parecidos.

## Nova representação

O experimento espacial usa:

- recorte da região principal da arena;
- bordas/alta frequência da imagem atual para destacar sprites e formas;
- diferença temporal assinada e amplificada;
- grade grosseira de energia de movimento por região;
- normalização por feature antes da comparação;
- comparação balanceada por classe usando os exemplos reais das demonstrações.

As regras de combate continuam iguais:

- `R`: estado base de combate, executado fisicamente com repetição BYOND;
- `LEFT/RIGHT/UP/DOWN`: navegação aprendida;
- `H`: habilidade de combate aprendida separadamente;
- `V`: meditação pós-combate, excluída do aprendizado de combate.

## Comandos

Treinar com as demonstrações existentes:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_spatial.py train --model kage_pilot_v02_spatial.json
```

Executar um teste real:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_spatial.py pilot --model kage_pilot_v02_spatial.json --seconds 20 --debug
```

O objetivo desta etapa não é vencer automaticamente. O primeiro critério de sucesso é observar decisões reais `nav=left/right` após separação e eventualmente `skill=h`, em vez de `idle` permanente.
