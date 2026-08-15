# mappings/ — o trabalho real. Tudo revisível em diff.

- `nutrients/<fonte>.csv` — (código fonte) → (nutriente canónico, fator)
- `foodgroups/` — mapeamento de grupos por fonte para a taxonomia canónica
- `source_priority.csv` — prioridade por (locale, grupo, nutriente)
- `overrides.csv` — correções manuais, cada uma com justificação obrigatória
- `links.csv` — concept_id ↔ (fonte, id_fonte), adjudicado
- `tombstones.csv`
- `_unmapped/` — **gerado pelo build** (conteúdo gitignored); esvaziar é obrigatório

Regra: se a decisão não está num CSV do git, não aconteceu.