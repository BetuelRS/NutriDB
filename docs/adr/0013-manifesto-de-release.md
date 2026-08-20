# ADR-0013 - Manifesto e checksums de release

- **Estado**: Aprovado
- **Data**: 2026-08-20
- **Fase**: P2/F7 - release verificável

---

## 1. Contexto

O SQLite é reproduzível localmente, mas um consumidor externo precisa de
receber também a identidade do artefacto, o hash do ficheiro, as fontes que o
compõem, as licenças e o resultado QA. O `sources/registry.toml` já contém os
hashes dos dumps; essa informação ainda não acompanha o artefacto distribuído.

## 2. Decisão

Cada package produzido pelo pipeline terá, no mesmo diretório:

- `<artefacto>.manifest.json`, schema `release-1`;
- `SHA256SUMS`, com o SHA-256 do artefacto SQLite e do manifesto.

O manifesto contém versão NutriDB, nome do artefacto, perfil, SHA-256 do
SQLite, fontes ordenadas por id, versões, licenças, atribuições, destinos de
artefacto e os hashes fixados dos ficheiros de origem. Quando o build executa
QA, o manifesto inclui também os counts por severidade.

O manifesto não inclui dumps nem valores nutricionais adicionais. Não possui
timestamps próprios; o bloco temporal continua isolado em `build_metadata`.

## 3. Consequências

- Um consumidor pode verificar integridade e composição legal sem abrir o código.
- O manifesto é determinístico para o mesmo artefacto e registry.
- Alterações à registry ou ao artefacto mudam os hashes observáveis.
- A publicação ainda precisa de SBOM e atestação próprios, que permanecem
  fases posteriores.
