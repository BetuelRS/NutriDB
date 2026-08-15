# PROGRESS.md — estado, decisões pendentes, bloqueios

> Atualizado no fim de cada sessão (regra §17.1). Fonte da verdade operacional: `PLAN.md`; arquitetura: `docs/adr/`.

## Estado atual (2026-08-15)

**Fase 0 — Fundações: concluída** (branch `f0/fundacoes`).
**Fase 1 — Vocabulário e primeira fonte:** em curso (branch `f1/ciqual-ponta-a-ponta`).

| Tarefa | Estado | Nota |
|---|---|---|
| F1.0 ADR-0003 (licença/formato CIQUAL) | ✅ | Aprovado por revisão humana (2026-08-15) — registo no ADR §7; XML primário (emenda A6) |
| F1.0b pin SHA-256 no registry | ✅ | Modelo `files` (multi-ficheiro) novo no registry; 8 ficheiros fixados (5 XML + PDF + XLS + XLSX); `sources sync` re-descarcou 1 ficheiro do zero e validou por hash; audit `pinned=yes` |
| F1.1 Vocabulário canónico congelado | ✅ | 157 tagnames INFOODS (SPEC §5), 9 grupos, 6 unidades, 9 value_types (6 ausências P3), 8 acquisition (EuroFIR), 22 métodos (inicial), 18 food_groups, 7 facetas, 54 relações; `vocab check` real (invariantes + ciclos); 34 testes |
| F1.2 Extractor CIQUAL XML→Parquet | ✅ | Streaming iterparse (compo 69 MB); células tipadas (`-`→missing, `traces`→trace, `< N`→below_loq, vírgula/ponto/`1E-6`); Alim/grp placeholders all-zero; confiança A–D só em medidos; provenance JSON integral; determinístico byte-a-byte (P5); **validado em dados reais**: 3 484 / 74 / 161 grupos / 1 978 fontes / 257 816 valores; ADR-0003 §4.2 corrigido (`<N` na verdade 20 075) |
| F1.3 Mapeamentos completos | ✅ | `mappings/nutrients/ciqual.csv` (74/74 códigos → 71 tagnames; ENERC×4→2, PROCNT×2→1, `FIB-`→FIBTG, `VITD-`→VITD, `RAE`→VITA_RAE, `CLD`→CL, `CHOL-`→CHOLE, 10004→NACL; fator ×10 AG g→mg; métodos de energia pinados nas 4 ENERC); `mappings/foodgroups/ciqual.csv` (91 linhas: 11 grp + 65 ssgrp + 15 ssssgrp p/ split animal/vegetal; convenções documentadas em comentários); `src/nutridb/mappings.py` com resolver por nível mais fino; gate `_unmapped/` vazio em teste; cobertura golden vs intermediários reais; 56 testes verdes |
| F1.2–F1.10 | ☐ | próximas |

**Fallbacks de F0**: push `f0/fundacoes` feito; confirmar run do CI no GitHub (pendente de credenciais/remote).

## Decisões em aberto

- Nenhuma (A1–A20 resolvidas; ADR-0001 §7; ADR-0003 aprovado em F1.0).

## Bloqueios / pendências

- **CI no GitHub**: confirmar os runs `checks` de `f0/fundacoes` e `f1/ciqual-ponta-a-ponta` no Actions após push.

## Histórico de sessões

- **2026-08-15**: arranque. SPEC lida, ADR-0001/0002, PLAN, ambiguidades resolvidas por aprovação humana; Fase 0 implementada e verificada (19 testes, lint e mypy verdes).
- **2026-08-15 (continuação)**: F1.0/F1.0b. Descarregados os 8 ficheiros CIQUAL 2025 do Dataverse; estruturas XML inspecionadas (74 const com `code_INFOODS`, matriz completa 257 816 pares, `source_code`/`code_confiance`/`min`/`max` por par); PDF lido via OCR (pypdf sem Unicode) → `doc_2025_11_19_ocr.txt`; etalab-2.0 (SPDX) confirmada na fonte oficial; MD5 locais = oficiais (8/8); **XML como formato primário** (ADR-0003, emenda A6); registry alargado (`files`), sync/audit validados.
- **2026-08-15 (continuação 2)**: F1.0 aprovado (ADR-0003 §7) e pushed; F1.1 — vocabulário canónico escrito e **congelado** (157 tagnames INFOODS/EuroFIR, 54 relações de agregação, 7 facetas), `nutridb vocab check` implementado com invariantes (tagname único, unidade única, grupos existem, tipos de ausência P3 obrigatórios, sem ciclos) e 12 testes novos; lint/mypy/pytest verdes (34 testes).
- **2026-08-15 (continuação 3)**: F1.2 — extractor CIQUAL escrito e **validado em dados reais**. Correções descobertas empiricamente: `facteur_Jones` com ponto decimal; alim_grp real usa `<ALIM_GRP>` (3 níveis desnormalizados por linha, placeholders all-zero `00`/`0000`/`000000`); `< N` com espaço → 20 075 `below_loq` (não 0 — **ADR-0003 §4.2 corrigido**); `code_confiance`/`source_code` ausentes só e sempre nas 83 246 células `-`; `1E-6` (notação científica) uma vez em `min`; group `'00'` usado por 1 alimento. Saída: 5 Parquet determinísticos (SHA-256 idêntico em 2 runs); report real 3 484/74/161/1 978/257 816; 46 testes verdes.
- **2026-08-15 (continuação 4)**: F1.3 — mapeamentos completos. `mappings/nutrients/ciqual.csv`: 74 códigos → 71 tagnames canónicos (ENERC ×4→ENERC_KJ/KCAL com método registado no CSV; PROCNT ×2; `FIB-`→FIBTG, `VITD-`→VITD, `VITE-`→VITE, `VITB6-`→VITB6A, `CHOL-`→CHOLE, `RAE`→VITA_RAE, `CLD`→CL, 10004 sem INFOODS→NACL; fator ×10 para AG g→mg; regras de ausência `-`/`traces`/`<N` por linha). `mappings/foodgroups/ciqual.csv`: 91 linhas (11 grp + 65 ssgrp + 15 ssssgrp) com convenções documentadas (alternativas vegetais/infantis→other; beurres→fats_oils; doces de cereais→cereals; algues→vegetables; grp `00`→other). `src/nutridb/mappings.py` (loaders + resolver por nível mais fino, mapping como autoridade). Testes: 10 novos — cobertura golden 74/74 e resolução de todos os 3 484 alimentos contra os intermediários reais, validade vs vocabulário (tagname/unidade/tipos ausência/food_group), gate `_unmapped/` vazio; 56 verdes; lint/mypy limpos.