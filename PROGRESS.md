# PROGRESS.md — estado, decisões pendentes, bloqueios

> Atualizado no fim de cada sessão (regra §17.1). Fonte da verdade operacional: `PLAN.md`; arquitetura: `docs/adr/`.

## Estado atual (2026-08-15)

**Fase 0 — Fundações: concluída** (branch `f0/fundacoes`).
**Fase 1 — Vocabulário e primeira fonte:** em curso (branch `f1/ciqual-ponta-a-ponta`).

| Tarefa | Estado | Nota |
|---|---|---|
| F1.0 ADR-0003 (licença/formato CIQUAL) | 🔧 proposto | Evidência completa; **aguarda revisão humana** (questionário/PR). Registado em `docs/adr/0003-fonte-ciqual-2025.md` |
| F1.0b pin SHA-256 no registry | ✅ | Modelo `files` (multi-ficheiro) novo no registry; 8 ficheiros fixados (5 XML + PDF + XLS + XLSX); `sources sync` re-descarcou 1 ficheiro do zero e validou por hash; audit `pinned=yes` |
| F1.1–F1.10 | ☐ | próximas |

**Fallbacks de F0**: push `f0/fundacoes` feito; confirmar run do CI no GitHub (pendente de credenciais/remote).

## Decisões em aberto

- **ADR-0003** (momentaneamente em `Proposto`): a leitura humana deve confirmar (1) XML como formato primário — emenda à A6, (2) semântica `-`/`traces`/`<N`/confiança A–D (§4.1), (3) volume §4.2 (3484×74; 83 246 ausentes; 1 978 fontes), (4) artefacto `core` com etalab-2.0.
- A1–A20 resolvidas (ADR-0001 §7).

## Bloqueios / pendências

- **Aprovação humana do ADR-0003** (gate da F1.0) — pode ser feita por PR ou questionário.
- **CI no GitHub**: confirmar o run `checks` de `f0/fundacoes` no Actions (o CI de `f1/...` só corre após push).

## Histórico de sessões

- **2026-08-15**: arranque. SPEC lida, ADR-0001/0002, PLAN, ambiguidades resolvidas por aprovação humana; Fase 0 implementada e verificada (19 testes, lint e mypy verdes).
- **2026-08-15 (continuação)**: F1.0/F1.0b. Descarregados os 8 ficheiros CIQUAL 2025 do Dataverse (interface `/api/access/datafile`); estrutura dos 5 XML inspecionada (74 const com `code_INFOODS` oficial, matriz completa 257 816 pares, `source_code`/`code_confiance`/`min`/`max` por par); PDF oficial extraído por **OCR** (pypdf não extrai texto — fontes sem mapeamento Unicode) para `sources/cache/ciqual/doc_2025_11_19_ocr.txt`; licença etalab-2.0 confirmada na página oficial (SPDX) e no doc (Licence Ouverte, p.4); MD5 locais batem com os MD5 oficiais do Dataverse (8/8); **XML escolhido como formato primário** (ADR-0003; emenda A6); registry extendido (`files`), 22 testes verdes, `sources sync`/`audit` como gate validado.