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