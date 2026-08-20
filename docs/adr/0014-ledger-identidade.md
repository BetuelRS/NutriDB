# ADR-0014 - Ledger persistente de identidade (P4)

- **Estado**: Aprovado
- **Data**: 2026-08-20
- **Fase**: P4/F6 - IDs eternos

---

## 1. Contexto

Os IDs `nfx_` são ULIDs determinísticos derivados do seed
`(kind, source, code)` (F1.5). Isso garante estabilidade entre builds, mas a
atribuição "uma vez" (SPEC §1 P4) é apenas por convenção: nenhum mecanismo
impede que uma mudança de algoritmo, uma colisão de seed ou a reutilização de
um código pela fonte produza um ID diferente para a mesma identidade — ou o
mesmo ID para uma identidade nova — em silêncio.

## 2. Decisão

O transform passa a manter **`mappings/id_ledger.csv`** — um registo de
atribuição, revisível em diff (P8), com colunas:

```
source,source_code,concept_id,seed_sha256
```

- `seed_sha256` = SHA-256 do registo cru do alimento (o `record` JSON do
  `source_record`).
- O ledger cobre **concepts** (identidades eternas expostas ao exterior);
  `source_record`/`value`/`derivation`/`tombstone` continuam derivados sem
  estado (são internos, sem contrato externo).
- Regras no transform (fail high, P9):
  - `(source, code)` já registado com `concept_id` diferente do recomputado
    → `TransformError` (mudança de algoritmo/seed deve ser deliberada e
    regenerar o ledger).
  - `(source, code)` já registado com `seed_sha256` diferente → o ID é
    **mantido** (eterno); a linha é atualizada e contada em `identity_drift`
    (revisão humana no diff; tipicamente uma edição nova da fonte).
  - código novo → atribuição determinística como hoje, contada em
    `identity_new`.

O ficheiro é lido e escrito pelo transform, ordenado por `(source, code)`,
determinístico e parte do fingerprint da cache (está em `mappings/`).

## 3. Consequências

- "Atribuído uma vez" passa de convenção a enforcement; reutilização de
  códigos e mudanças de algoritmo tornam-se visíveis e falham alto.
- Edições de fonte produzem diffs `identity_drift` revisíveis em vez de IDs
  novos silenciosos.
- O primeiro run real cria o ledger com as 4 860 atribuições atuais; diffs
  posteriores são pequenos e revisíveis.
- O ficheiro é estado no git (como `links.csv`), não configuração editada à
  mão; a regeneração total exige apagá-lo deliberadamente.