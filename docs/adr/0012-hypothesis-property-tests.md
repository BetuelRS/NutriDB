# ADR-0012 - Hypothesis para propriedades do pipeline

- **Estado**: Aprovado
- **Data**: 2026-08-20
- **Fase**: P2 - release verificável

---

## 1. Contexto

O SPEC §11 exige propriedades para conversões reversíveis, fusão idempotente
e invariância à ordem de processamento. A suite existente testa determinismo
com uma fixture fixa, mas não explora sistematicamente os limites numéricos e
as permutações de entrada.

## 2. Decisão

Adicionar `hypothesis` apenas ao grupo de dependências de desenvolvimento. Os
testes devem usar estratégias sintéticas, não valores nutricionais reais, e
devem testar propriedades sem alterar fontes, registry ou artefactos reais.

Primeiras propriedades:

- roundtrip de conversões positivas e finitas;
- divergência simétrica e limitada a `[0, 1]`;
- ordenação determinística de candidatos independentemente da ordem de entrada.

As propriedades que exigem o pipeline completo serão adicionadas depois de o
contrato canónico P1/P3 estar fechado.

## 3. Consequências

- A suite cobre classes de entradas, não apenas exemplos escolhidos.
- A dependência não entra no runtime nem altera a API de consumidores.
- Fixtures continuam isoladas e explicitamente sintéticas (P2).
