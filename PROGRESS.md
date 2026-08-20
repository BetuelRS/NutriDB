# PROGRESS.md — estado, decisões pendentes, bloqueios

> Atualizado no fim de cada sessão (regra §17.1). Fonte da verdade operacional: `PLAN.md`; arquitetura: `docs/adr/`.

## Estado oficial (2026-08-20)

**Direção de produto aprovada:** o NutriDB é uma plataforma de dados de
composição alimentar. O dataset é o produto principal; o Explorer é a camada
de inspeção intuitiva; integrações e mais fontes seguem depois dos gates de
produção. Ver [`ADR-0010`](docs/adr/0010-direcao-produto.md).

| Área | Estado comprovado |
|---|---|
| Dataset | CIQUAL 2025 + INSA/TCA 7.1 integrados no canónico |
| Artefacto | SQLite schema 4 + Parquet; integrity check OK |
| Explorer | Build React/TypeScript funcional; comparação por fonte, cobertura global e locale pt/en; produto ainda inicial |
| Qualidade | QA real com 0 erros; warnings documentados |
| P1/P6/P9/P10 | Aquisição, gate de licença, fail-high e sync no build implementados |
| API | Artefactos read-only; rankings limitados a `per_100g_edible` |
| Golden/propriedades | Golden automático: 200 alimentos/943 células; Hypothesis ativo + merge idempotente |
| CI | `checks`, `explorer`, `qa` e `determinism` verdes; relatório QA e metadados de release publicados |
| Release verificável | Manifesto `release-1` + `SHA256SUMS` + SBOM CycloneDX 1.6 + atestação `attestation-1` (Ed25519) + `release verify` (ADR-0015) |
| Produção | Não fechada: 6 029 pares de identidade em review, revisão humana do golden e decisão operacional de custódia da chave |
| Testes | 230 testes verdes; ruff/mypy limpos |
| Próxima prioridade | rever conflitos 1:1 restantes, concluir golden 200 e preparar release assinada |

### Próximas ações

- Rever os 6 029 pares restantes com `nutridb link review`; 75 golden-true adiados permanecem explicitamente em review por conflito 1:1.
- Confirmar a custódia/backup de `NUTRIDB_SIGNING_KEY` e publicar uma release assinada.
- Só depois expandir fontes, API, bibliotecas e exports.

### Bloqueios

- Adjudicação humana dos pares de review (requer decisor humano; regra 17.6).
- Revisão humana do golden 200 (verificação à mão, critério 2 do F6).
- P3 ausência individual por motivo — requer evidência das fontes.
- Chave de assinatura: a chave foi gerada fora do repositório; falta confirmar a custódia humana antes de a tratar como âncora pública.

As secções seguintes são o histórico detalhado das fases e sessões. Quando uma
secção histórica disser “estado atual”, essa expressão refere-se ao snapshot
da data indicada, não ao estado oficial acima.

---

## Histórico: Fases 0-2 (snapshot 2026-08-17)

**Fase 0 — Fundações: concluída** (branch `f0/fundacoes`).
**Fase 1 — Vocabulário e primeira fonte:** **concluída** (branch `f1/ciqual-ponta-a-ponta`; F1.0–F1.10 + F1.8b; merge com CI verde).
**Fase 2 — Multi-fonte (INSA):** **concluída** (branch `f2/multi-fonte`; F2.0–F2.10; push + merge em `f0/fundacoes` — CI a confirmar).

| Tarefa | Estado | Nota |
|---|---|---|
| F2.0 ADR-0004 (licença/formato INSA) | ✅ | Licença `insa-tca-7.1` verificada na fonte oficial (custom não-SPDX, atribuição obrigatória, comercial ok; e-mail INSA 2026-07-28 como evidência); formato XLSX inspecionado; registry com `license_id` |
| F2.1 ADR-0005 (esquema comum) | ✅ | 4 tabelas por fonte (`food`, `food_group`, `constituent`, `value` na ordem fixada); canónico único; `source_nutrient_code` TEXT; conceitos (source, food); `mv_food_value` por (concept, nutrient, locale) com label/locale; schema 2; FTS por locale |
| F2.2 Registry + sync INSA | ✅ | Entrada `[sources.insa]` (URL oficial, SHA-256, `insa_tca.xlsx`); `sources sync` descarrega + verifica |
| F2.3 Extractor INSA | ✅ | `src/nutridb/sources/insa.py` (XLSX stdlib); 48 headers vs correspondência (fail high); chaves `<nome>_<unidade>` (µ→ug, α/β→a/b, NFKD); alias `alfa_tocoferol_mg`→`a_tocoferol_mg`; células vazias = não medido (P3); `per_100ml` só "Bebidas alcoólicas"; energia sem método → NULL (P2); record verbatim; report real 1376/48/66048; **8 testes unitários sintéticos** (workbook gerado no teste) |
| F2.4 Vocabulário aditivo | ✅ | +4 tagnames (OLSAC, VITA, CARTBEQ, NIATRP) → 161; freeze F1.1 mantido |
| F2.5 Mapeamentos INSA | ✅ | `mappings/nutrients/insa.csv` (48 linhas; FATRN ×1000 g→mg; `b_caroteno_total_ug`→CARTB e `sodio_mg`→NA documentados sem código INFOODS; energy_method `-`); `mappings/foodgroups/insa.csv` (22 L1 + overrides L2/L3) |
| F2.6 Transform multi-fonte | ✅ | Sem ramos por fonte; canónico único; report real: foods 4860, concepts 4860, source_records 328724, coverage 122, values 230601 (measured 208012 / trace 2514 / below_loq 20075), not_measured 93263, conversions 1376 (trans INSA ×1000), sources 2; dir ausente → TransformError (P9) |
| F2.7 i18n/package multi-fonte | ✅ | Labels nativas por fonte; `mv_food_value` 384 897 por locale; FTS `label_fts_{en,fr,pt,pt_PT}`; schema 2; `source_nutrient_code` TEXT |
| F2.8 Golden INSA | ✅ | `tests/golden/insa_10.csv` (35 células, 10 alimentos) — células nativas verbatim + coordenadas; 4 testes golden (forma/evidência, valores com fator do mapping, alimentos existem, proveniência no SQLite); 35/35 |
| F2.9 Explorer multi-fonte | ✅ | `foodValues(conceptId, locale)` com fallback (fr→en→pt; pt-PT→pt→en); vista de detalhe com rótulo resolvido; footer 2 fontes; `npm run build` verde |
| F2.10 Fecho da fase | ✅ | P10 real verificado (build completo com 2 fontes, counts idênticos); golden 96/96; suite 114 testes verdes; ruff/mypy limpos; PLAN/PROGRESS atualizados; CI cobre `f2/**`; **concluído 2026-08-17**: 12 commits atómicos + push `f2/multi-fonte` + merge em `f0/fundacoes` (e4fb3a9) |

**Entregáveis da fase**: ADR-0004/0005; extractor INSA + 8 testes unitários; +4 tagnames; mappings INSA; transform/i18n/package multi-fonte; golden INSA (35 células); explorer multi-fonte; artefacto `nutridb-core-0.1.0.sqlite` ~229,6 MB com 2 fontes (schema 2).

## Decisões em aberto

- Nenhuma (A1–A20 resolvidas; ADR-0001/0003 aprovados; ADR-0004/0005 aprovados por revisão humana — ainda não commitados).

## Bloqueios / pendências

- Nenhum. F2 fechada (push + merge); CI do `f0/fundacoes` a confirmar após o push.

## Histórico de sessões

- **2026-08-15**: arranque. SPEC lida, ADR-0001/0002, PLAN, ambiguidades resolvidas por aprovação humana; Fase 0 implementada e verificada (19 testes, lint e mypy verdes).
- **2026-08-15 (continuação)**: F1.0/F1.0b. Descarregados os 8 ficheiros CIQUAL 2025 do Dataverse; estruturas XML inspecionadas (74 const com `code_INFOODS`, matriz completa 257 816 pares, `source_code`/`code_confiance`/`min`/`max` por par); PDF lido via OCR (pypdf sem Unicode) → `doc_2025_11_19_ocr.txt`; etalab-2.0 (SPDX) confirmada na fonte oficial; MD5 locais = oficiais (8/8); **XML como formato primário** (ADR-0003, emenda A6); registry alargado (`files`), sync/audit validados.
- **2026-08-15 (continuação 2)**: F1.0 aprovado (ADR-0003 §7) e pushed; F1.1 — vocabulário canónico escrito e **congelado** (157 tagnames INFOODS/EuroFIR, 54 relações de agregação, 7 facetas), `nutridb vocab check` implementado com invariantes (tagname único, unidade única, grupos existem, tipos de ausência P3 obrigatórios, sem ciclos) e 12 testes novos; lint/mypy/pytest verdes (34 testes).
- **2026-08-15 (continuação 3)**: F1.2 — extractor CIQUAL escrito e **validado em dados reais**. Correções descobertas empiricamente: `facteur_Jones` com ponto decimal; alim_grp real usa `<ALIM_GRP>` (3 níveis desnormalizados por linha, placeholders all-zero `00`/`0000`/`000000`); `< N` com espaço → 20 075 `below_loq` (não 0 — **ADR-0003 §4.2 corrigido**); `code_confiance`/`source_code` ausentes só e sempre nas 83 246 células `-`; `1E-6` (notação científica) uma vez em `min`; group `'00'` usado por 1 alimento. Saída: 5 Parquet determinísticos (SHA-256 idêntico em 2 runs); report real 3 484/74/161/1 978/257 816; 46 testes verdes.
- **2026-08-15 (continuação 4)**: F1.3 — mapeamentos completos. `mappings/nutrients/ciqual.csv`: 74 códigos → 71 tagnames canónicos (ENERC ×4→ENERC_KJ/KCAL com método registado no CSV; PROCNT ×2; `FIB-`→FIBTG, `VITD-`→VITD, `VITE-`→VITE, `VITB6-`→VITB6A, `CHOL-`→CHOLE, `RAE`→VITA_RAE, `CLD`→CL, 10004 sem INFOODS→NACL; fator ×10 para AG g→mg; regras de ausência `-`/`traces`/`<N` por linha). `mappings/foodgroups/ciqual.csv`: 91 linhas (11 grp + 65 ssgrp + 15 ssssgrp) com convenções documentadas (alternativas vegetais/infantis→other; beurres→fats_oils; doces de cereais→cereals; algues→vegetables; grp `00`→other). `src/nutridb/mappings.py` (loaders + resolver por nível mais fino, mapping como autoridade). Testes: 10 novos — cobertura golden 74/74 e resolução de todos os 3 484 alimentos contra os intermediários reais, validade vs vocabulário (tagname/unidade/tipos ausência/food_group), gate `_unmapped/` vazio; 56 verdes; lint/mypy limpos.
- **2026-08-15 (continuação 5)**: F1.4+F1.5 — transformação canónica e identidade eterna. `src/nutridb/transform.py` (canónico Parquet: source, coverage, source_record, concept, concept_link, value, derivation vazia, tombstone vazia; ausência por cobertura D5; `acquisition_type` NULL documentado; `confidence_code` A–D em bruto; energia com método registado); `src/nutridb/identity/__init__.py` (ULID determinístico 26 chars base32 Crockford sem I/L/O/U, `nfx_`, SHA-256 do seed — P5/P10); `mappings/links.csv` stub; CLI `transform`. Real: values 174 570 (measured 151 981/trace 2 514/below_loq 20 075), not_measured 83 246 implícito, conversions ×10 39 414 (valor depois corrigido — ver 2026-08-16); determinístico (2 runs byte-idênticos); 71 testes verdes.
- **2026-08-15 (continuação 6)**: F1.6 — i18n F1-lite. `i18n/locales.toml` (fr/en/pt-PT/pt-BR ativas + pt/es/de/it→en), `vocab_pt_PT.csv` 11 labels curated; `src/nutridb/i18n/` (build de label.parquet com status native/official/curated; `normalize_label` ligaduras+NFKD+casefold; fail-high em rótulo vazio/tagname desconhecido); CLI `i18n build`. Real: labels 7 136 (fr 3 484 + en 3 484 + en vocab 157 + pt-PT 11); determinístico; 78 testes.
- **2026-08-15 (continuação 7)**: F1.7 — empacotamento `core`. `src/nutridb/package/` (SQLite §8 completo: tabelas centrais + vocabulário referenciado + FTS5 externo por locale + `mv_food_value` 174 570 + índices; page_size 8192, journal OFF, VACUUM/ANALYZE, user_version 1, `build_metadata` único bloco temporal); CLI `package --profile core`; fix de dados: vírgulas não-escapadas em acquisition_types/analytical_methods + gate `load_csv` (coluna extra → P9). Real: ~150 MB, integrity ok, determinístico (só `built_at` difere); smoke watermelon kcal 35,4; 85 testes.
- **2026-08-15 (continuação 8)**: F1.8 — motor de pesquisa. `src/nutridb/api/` (`search` público read-only; FTS5 em `text_normalized`; termos `"x"*` AND; fallback runtime; limit 1..100; locale desconhecida → ApiError; escape FTS5); fix `tomllib` (cadeias aninhadas). Real: pastis/eau de vie/pomme/milk/água OK; 'leite'/'gordura' vazios (sem rótulos pt-PT de alimentos em F1); 95 testes.
- **2026-08-16**: F1.9 — conjunto dourado + **correção de dados com evidência**. Ao gerar os goldens contra o XLSX oficial descobri (1) as colunas do XLS **não seguem a ordem da folha `codes INFOODS`** (casadas por cabeçalho normalizado) e (2) **erro de fator F1.3**: AG com fator ×10→"mg" mas a fonte (XML, XLS e folha INFOODS) declara `(g/100 g)` e a lista oficial INFOODS/FAO usa `FASAT(g)` — 0,97 g ≠ 9,7 mg. Corrigido: mapping AG ×1 + unidade g; vocab 38 tagnames AG mg→g; coluna `is_default` no mapping (327/328 Reg. UE 1169 e 25000 Jones default; 332/333 Jones-fibras e 25003 N×6,25 ficam no canónico `value` com `analytical_method` — P1) → `mv_food_value` único por (conceito, nutriente): real 164 433; fixture alargado (const 333); report real: conversions 0; determinismo real re-verificado (2 runs, 23 tabelas idênticas). Golden: `tests/golden/ciqual_20.csv` (61 células, expected = teneur verbatim do XML + célula XLS e coordenadas como cross-evidence) + `tests/golden/test_golden.py` (3 testes, tolerância 1e-9, skipif sem artefacto); 61/61 batem o artefacto; **98 testes verdes**; lint/mypy limpos (31 ficheiros).
- **2026-08-16 (continuação 9)**: F1.8b + fecho da fase. `explorer/` (Vite+React+TS) — página mínima de pesquisa (emenda A7) com **decisão com evidência**: o build pré-compilado do `sql.js` **não inclui FTS5** (`no such module: fts5`, verificado em node), trocado pelo **WASM oficial do SQLite** (`@sqlite.org/sqlite-wasm` 3.49.1-build3, pinado); `:memory:` + `sqlite3_deserialize` abre o artefacto de 147 MB (o construtor `oo1.DB` falha com bytes grandes — `RangeError: Too many properties to enumerate`; caminho capi); `sqlite3_bind_text` com string pura rebenta na wrapper (`pMem` undefined) — bind com `TextEncoder().encode(v).buffer`; pesquisa FTS5 real verificada (pomme/água em node); `npm run build` verde (tsc strict); dev server verificado: página 200, artefacto 200 (147 562 496 B), wasm 200, traversal `/artifacts/../` → 400; CLI `explorer dev`/`explorer build`; CI alargado (branches `f1/**` + job `explorer`); **proveniência ponta a ponta** no artefacto real (`test_golden_provenance_walk_on_sqlite`: label → `mv_food_value` → `source_record` com `teneur` verbatim, vírgula decimal, 61/61); critérios §16 F1 verificados; **99 testes verdes**; lint/mypy limpos; **fix CI**: `uv.lock` nunca incluiu as dev-dependencies (ruff/mypy/pytest) — o `uv sync` do CI instalava só runtime e falhava `Failed to spawn: ruff`; adicionado `[dependency-groups] dev` ao `pyproject.toml` + `uv lock` regenerado (nota de infra, não muda a stack); commits + push; CI verde (jobs `checks` + `explorer`); merge `f1/ciqual-ponta-a-ponta` → `f0/fundacoes`.
- **2026-08-16 (continuação 10)**: arranque F2. F2.0 — licença INSA verificada na fonte oficial (e-mail 2026-07-28 como evidência) → ADR-0004; formato XLSX inspecionado (folha de dados com group/column header e células nativas; folha "Componentes-Correspondência") → ADR-0005 (contrato de 4 tabelas por fonte, canónico único, `mv_food_value` por locale, schema 2). F2.1 — ADR-0005 aprovado. F2.2 — registry + sync INSA (SHA-256 verificado). F2.3 — extractor INSA com stdlib: `_shared_strings`/`_sheet_rows` (dict `{col_index: text}`), `_find_header_row`, 48 colunas de valores, correspondência com legendas numeradas/`NaN` ignoradas, `_KEY_ALIASES` (`alfa_tocoferol_mg`→`a_tocoferol_mg`), basis por grupo L1, record JSON verbatim; **correções descobertas nos dados reais**: cabeçalho "Cod | Nome do alimento" na row 2; alinhamento de colunas por índice (5..52) não por letra; unidades só na correspondência; células vazias `None`. F2.4 — +4 tagnames. F2.5 — mappings INSA (48 nutrientes; FATRN ×1000; energy_method `-`; 22 L1 + overrides). F2.6 — transform sem ramos por fonte; report real 4860/328724/230601 (conversions 1376). F2.7 — i18n/package: mv 384 897, FTS 4 locales, schema 2.
- **2026-08-16 (continuação 11)**: golden INSA + explorer + limpeza. Gerado `tests/golden/insa_10.csv` programaticamente do XLSX real (`%TEMP%\opencode\insa_golden_gen.py`): 10 alimentos, 35 células com coordenadas reais; **bugs do gerador corrigidos**: `_shared_strings` precisa do archive, rows como dicts `{col: text}`, header em rows[1], col = 5 + keys.index(key); células nativas sem aspas no expected; trans INSA em g com fator do mapping (×1000 → mg); energia INSA method NULL (P2). 4 testes golden INSA (incl. proveniência com `analytical_method` na tabela `value`). Explorer: `search.ts` com `label/locale` + `VALUE_LOCALE_FALLBACK`, `App.tsx` com prop locale e footer 2 fontes; `npm run build` verde. Fix 4 testes unit: foodgroups `("1","00")` excluído; `raw` do ciqual com `alim_nom_fr`/`alim_nom_eng`; TransformError sem intermediários; vocab_en 161. Ruff/mypy limpos (19 erros fixos). Build completo re-verificado (counts idênticos, artefacto 229 572 608 B); golden/integration/property verdes. CI: branches `f2/**`. **106 testes verdes**.
- **2026-08-17**: fecho do `test_extract_insa.py`. Escrito o ficheiro com workbook sintético gerado no teste (stdlib zipfile+xml.etree; 48 headers reais verbatim; correspondência com legendas/NaN/alias "Alfa-tocoferol"); **bugs da fixture corrigidos**: `sheet_xml` emitia um `<row>` por célula (→ 1 `<row>` por linha); linhas de dados sem colunas 0–4 (código/nome/níveis); legendas numeradas "1. " vs regra real `^\d+\s` ("1 Energia [kcal]" + linhas reais); `_read` sem `.parquet`; testes 2–4 sem chamar `extract`; null_count com `.item()`; esperado 83 calculado do FOODS (13 células preenchidas). Ruff/mypy no ficheiro (TYPE_CHECKING, `list[str | None]`, `\u03b1`). **114 testes verdes** (49 unit + 8 INSA + 8 golden + integração/property); format/lint/mypy limpos (33 ficheiros); PLAN.md F2.3 atualizado; PROGRESS.md atualizado. **Fecho da fase (F2.10)**: 12 commits atómicos (`docs(f2)` ADRs, `feat(f2)` registry/extractor/mappings/transform/i18n/golden/explorer, `ci(f2)`, `docs(f2)` PLAN/PROGRESS); push `f2/multi-fonte`; merge `--no-ff` em `f0/fundacoes` + push (e4fb3a9); PROGRESS/PLAN marcados concluídos.
## Histórico: Fase 3 (snapshot 2026-08-18)

**Fase 0**: concluida (`f0/fundacoes`). **Fase 1**: concluida (`f1/ciqual-ponta-a-ponta`). **Fase 2**: concluida (`f2/multi-fonte`; merge e4fb3a9).

**Fase 3 - Identidade: concluida** (branch `f3/identidade`; F3.0-F3.8).

| Tarefa | Estado | Nota |
|---|---|---|
| F3.0 Matcher (blocking + sinais + veto + adjudicacao) | done | 111 267 candidatos; AUTO_THRESHOLD 0.84 (subiu de 0.72 apos 42 FALSE nos autos), REVIEW 0.50; tie-break 1:1 (-score, -sim, insa, ciqual); veto de nutrientes (>= 2 divergentes de 6 nucleares); conflito distintivo/numerico demove para review; single-term sim >= 0.65; `evaluate()` com precision/recall/food_recall (recall conta TRUEs do golden em review = adjudicados) |
| F3.1 Dicionario | done | `food_terms.csv` 466+ linhas + 27 queijos (brie..bleu); correcao: celulas pt so com o token (frases "queijo X" colapsavam as keys e impediam partilha de termo) |
| F3.2 Golden 633 pares | done | 281 true / 352 false; 42 FALSE nos 238 autos a 0.72; 1 FP final aceite (60100015->T130, 411 reclama 9532 primeiro); 15 FN de par = colaterais 1:1 (irmaos TRUE); 4 missed-TRUE (Brie, Purée, chevre, Mascarpone); 2 familia-not-identity (1234 pastagem, 1900000018 cenoura baby); 817 carapau->Chinchard maigre e 820 cavala->Maquereau espagnol adicionados como TRUE |
| F3.3 CLI link | done | Escreve links.csv (123 finais x 2 + 6237 review x 2 = 12 720 linhas); metricas golden 0.9919/0.9037/0.9956; exit 1 se gates falharem |
| F3.4 Transform consome links.csv | done | 123 tombstones identity_link_f3; concept_link 4983 (cross com status da decisao); valores do absorvido reassignados ao survivor; review ignorado; fail high em codigo desconhecido/duplicado; comentarios `#` do gate F1 tolerados |
| F3.5 i18n fundido | done | by_concept agrega todos os registos do conceito (primeiro nome nao-vazio por locale, deterministico); status automatic+adjudicated; labels reais 8700 |
| F3.6 mv dedup | done | sort (concept, nutrient, locale, source_id, source_record_id) + unique keep=first; 390 323 linhas reais, 0 duplicados |
| F3.7 Testes | done | +9 testes (evaluate, _status, write_links_csv roundtrip, _apply_identity_links merge/tombstone/fail-high); sandbox root (mappings/sources/vocab/i18n sem links.csv) em toda a suite - testes ja nao tocam o registo de adjudicacao real; 119 testes verdes |
| F3.8 Fecho | done | CI `f3/**`; PLAN/PROGRESS; commits atomicos `(f3)`; push; merge `--no-ff` em `f0/fundacoes` |

**Entregaveis da fase**: matching.py; food_terms.csv; golden 633; links.csv 12 720 linhas; CLI link; transform/i18n/package F3; testes sandbox; CI.

## Histórico: Fase 4 (snapshot 2026-08-18)

**Fase 4 - Multilinguismo: concluida** (branch `f4/multilinguismo`; F4.0-F4.8; F4.9 em fecho).

| Tarefa | Estado | Nota |
|---|---|---|
| F4.0 ADR-0006 | done | Ambio F4: composicao por prioridade (reviewed > native > glossario > divergences); gates P7/161/95%/divergencias; fallback nunca congelado; composicao facetada gramatical adiada (F5+) |
| F4.1 Glossarios | done | 7 locales x 161 tagnames (fr, pt, pt-PT, pt-BR, es, de, it), status curated, evidence "terminologia INFOODS/EuroFIR, verificada a mao 2026-08-18"; 11 curados F1 migrados para pt-PT; `i18n/labels/vocab_pt_PT.csv` apagado (substituido) |
| F4.2 Facetas | done | `vocab/facets/*.csv` 9 colunas (139 linhas); mojibake cp1252 do name_pt reparado (Pao, Maca, Acucar, Salmao, Feijao, ...); `vocab check` valida header + celulas nao-vazias (removeu codigo morto do check) |
| F4.3 Divergencias | done | `i18n/divergences.csv` 67 linhas (53 nutrientes + 14 alimentos: 10 CIQUAL + 4 INSA); drift-check vs glossarios; conceito desconhecido falha; pares en-GB/en-US registados sem gate |
| F4.4 i18n build F4 | done | Gates: mt_unreviewed aborta; cobertura 161 por locale (pt: 108, generic forbidden nos 53 divergentes); >= 95% status; `reviewed_<locale>.csv` como override topo (curated); sorted deterministico; counts por locale + status |
| F4.5 Package | done | 8 tabelas `label_fts_*` (9775 linhas cada no artefacto real) |
| F4.6 Pesquisa cruzada | done | `api.search` resolve o rotulo pela cadeia do locale pedido + dedupe por conceito; golden real: "zucchini" em pt-PT -> "Curgete, polpa e pele, cozida"; "abacaxi" em pt-BR -> "Abacaxi, polpa sem casca, cru" |
| F4.7 CLI i18n review | done | Lista `i18n/review_queue/<locale>.csv`, `--apply` grava aprovados em `i18n/labels/reviewed_<locale>.csv`; fila vazia no real (P7: tudo nasce native/official/curated); `i18n/untranslatable.csv` com header |
| F4.8 Testes | done | test_i18n F4 (gates P7/divergencias/cobertura/drift/reviewed); sandbox com divergences sintetico derivado dos glossarios (sem concept_ids reais); FTS 8 locales; pesquisa cruzada + dedupe; golden i18n real (amostra por locale, gates, search no sqlite); 136 testes verdes; ruff/mypy limpos (35 ficheiros) |
| F4.9 Fecho | done | CI `f4/**`; commits atomicos `(f4)` (9); push; merge `--no-ff` em `f0/fundacoes` (8649801) + push; CI verde (checks+explorer) |

**Entregaveis da fase**: ADR-0006; glossarios 7 locales (1127 rotulos); facetas 8 locales; divergences.csv 67 linhas; i18n build F4 com gates; 8 tabelas FTS; pesquisa cruzada; CLI `i18n review`; testes + golden i18n. **Artefacto real**: 9 775 labels (fr 3706 native+curated, en 3706 native+official, pt 1542 native+curated, pt-PT/pt-BR 169 curated, es/de/it 161 curated), 8 FTS, 231 243 776 bytes.

## Decisoes em aberto

- Nenhuma.

## Bloqueios / pendencia

- Nenhum. F5 em curso: F5.0-F5.7 done, F5.8 (fecho) pendente — commits atomicos, merge, push, CI.

## Historico de sessoes

- **2026-08-18**: F4 (multilinguismo). ADR-0006 aprovado (ambito, gates, composicao honesta). Glossarios 7 locales x 161 tagnames autorados e validados (161/161). Facetas expandidas para 8 locales (139 linhas, 9 colunas) com mojibake reparado. `divergences.csv` 67 linhas (53 nutrientes + 14 alimentos). i18n build F4 reescrito: prioridade reviewed > native > glossario > divergences; gates P7 (mt_unreviewed aborta), cobertura 161 por locale com excecao pt (108: generic proibido nos 53 divergentes), >= 95% status, drift-check, conceito desconhecido falha; 1a corrida do build falhou no gate pt (53 tagnames divergentes) e foi corrigida; `locales.toml` com 8 ativas; `vocab_pt_PT.csv` apagado (substituido pelo glossario pt-PT). `api.search` F4: resolve rotulo pela cadeia do locale pedido + dedupe por conceito; CLI `i18n review` + `untranslatable.csv`. Testes: test_i18n reescrito (11 testes F4), sandbox com divergences sintetico, FTS 8 locales, pesquisa cruzada/dedupe, golden i18n real (labels por locale, gates, search "zucchini"->Curgete pt-PT no sqlite); 136 testes verdes; ruff/mypy limpos. Artefacto real reconstruido (P10): 9775 labels, 8 FTS, 231 243 776 bytes.

- **2026-08-18**: F3 completa. Matcher afinado (0.84), golden 633 gerado e revisto (42 FALSE, 15 FN colaterais 1:1, food_recall 0.9956), `nutridb link` + transform/i18n/package integrados, sandbox root nos testes (correcao de mojibake via `git checkout` + reaplicacao com edit tool), suite 119 testes verdes, lint/mypy limpos, pipeline real verificado ponta a ponta (123 tombstones, 390 323 mv rows, 0 duplicados).

## Histórico: Fase 5 (snapshot 2026-08-19)

**Fases 0-4: concluidas** (`f0/fundacoes`).

**Fase 5 - Fusao e derivacoes: em curso** (branch `f5/fusao`; F5.0-F5.7 em progresso, F5.8 fecho pendente).

| Tarefa | Estado | Nota |
|---|---|---|
| F5.0 ADR-0007 | done | Prioridades como dados (`mappings/source_priority.csv`, 8 regras: pt/pt-PT/pt-BR -> insa>ciqual; fr/en/es/de/it -> ciqual>insa); resolucao por especificidade (l,g,n) > (l,g,*) > (l,*,n) > (l,*,*); nunca medias entre fontes (SPEC §9/P2); divergencia rel = \|a-b\|/max(\|a\|,\|b\|) >= 0.30 so measured vs measured; overrides com justificacao obrigatoria (acquisition declared); derivacoes reais = 0 (fontes ja medem 100g/100ml); tabelas de fatores com headers a aguardar fonte publicada; schema 2 -> 3 |
| F5.1 Sondagens | done | 123 conceitos 2+ fontes; 4090 pares medidos por ambas; 1597 pares rel >= 0.30 (36 nutrientes, 122 conceitos); INSA 1461 linhas per_100ml (84 bebidas); basis per_100g_edible/per_100ml; measured 208012/trace 2514/below_loq 20075 |
| F5.2 Merge stage | done | `src/nutridb/merge/` — `mv_food_value.parquet` por (concept, nutrient, locale, basis) com preferred por prioridade (tie-break measured > trace > below_loq > source_record_id), alternatives JSON, divergence_flag/divergence_max, acquisition_type, derivation_id, override_justification; filtro `is_default` dos codigos movido do package para o merge; falla alto: locale sem regra, fonte desconhecida, override sem justificacao/conceito desconhecido; 10 testes unit |
| F5.3 Dados | done | `mappings/source_priority.csv` (8 regras), `mappings/overrides.csv` (header), `derivations/{retention_factors,yield_factors,densities,portions}.csv` (headers + evidencias a preencher) + README |
| F5.4 Derive stage | done | `src/nutridb/derive/` — por-volume (100ml = 100g x densidade), confeccao (x retencao x rendimento, helpers testados), tabelas validadas (header, chave unica, fator numerico, evidencia obrigatoria, conceito/grupo/nutriente conhecidos); sem fatores = falha alta; cada valor calculado com derivation_id + formula + inputs + fatores (chain registada, P2); escreve portion.parquet/density.parquet; 9 testes unit |
| F5.5 CLI | done | `nutridb merge`/`nutridb derive` reais (substituem _not_implemented); `nutridb build` encadeia transform -> derive -> i18n -> merge -> package |
| F5.6 Package schema 3 | done | mv_food_value +7 colunas (acquisition_type, alternatives, divergence_flag, divergence_max, derivation_id, override_justification); portion/density com evidence; PRAGMA user_version 3; package carrega mv_food_value.parquet (removido `_build_mv_food_value`); sandbox com `derivations/` |
| F5.7 Testes | done | test_merge (10) + test_derive (9) + test_cli + test_package schema 3 + golden com basis na chave; fixes empiricos: `resolve_priority` wildcard generico `(*,*)`, nutrients.csv lido via csv.DictReader (polars falha no ficheiro), derive com schema explicito + `vertical_relaxed` (Null-type das fixtures); **155 testes verdes**; ruff/mypy limpos (37 ficheiros) |
| F5.8 Fecho | pending | CI `f5/**` (ja adicionado ao ci.yml); commits atomicos `(f5)`; PLAN/PROGRESS; merge `--no-ff` em `f0/fundacoes` + push; CI verde |

**Entregaveis da fase**: ADR-0007; source_priority.csv; overrides.csv; 4 tabelas de fatores; merge stage; derive stage; CLI; package schema 3; 19 testes unit novos. **Artefacto real (2026-08-19)**: mv 391 101 linhas, divergence_flag 4 542, locales 5, derive 0 derivacoes (fatores vazios — report explicito), 236 380 160 bytes, integrity ok.

## Histórico: emenda A8 (snapshot 2026-08-19)

**Fases 0-5: concluidas** (`f0/fundacoes`; F5 merge `4af00b7`).

**Emenda A8 - Performance e escavabilidade: concluida** (branch `f5b/perf-busca`; ADR-0008).

| Tarefa | Estado | Nota |
|---|---|---|
| A8.1 Investigar ULID | done | Perfil pyinstrument inflava `_to_crockford` 3x; formula translates byte-identica (100k seeds, 0 mismatches) verificada mas **mais lenta** (1,83 vs 1,67 s/600k); modulo revertido ao loop original (alteracao liquida zero) |
| A8.2 Golden ULIDs | done | `test_ulid_golden_values`: `ciqual:food:24999` → `5CGDNX7JVCE01C6NZFGNC5GPFJ`; ananas `13002` → `nfx_5WAXNCVY3238REJ2NWP012390F`; courgette `20021` → `nfx_43XVY2CS429HC4KK3WZHM6R7H6` (seeds do artefacto real, P4) |
| A8.3 VACUUM removido | done | No-op de ~9 s em ficheiro novo; build real 36,7 → 18,3-18,7 s; ANALYZE fica |
| A8.4 Cache de estagios | done | `src/nutridb/cache.py`: fingerprint sha256 deterministico (version + registry + cache de fontes + codigo sources + intermediarios + mappings + vocab + identity); `build/cache/{extract,transform}/<fp>`; `refresh_from_cache` limpa e copia (P10); `--full` ignora; **determinismo P5 verificado**: artefacto full vs cached byte-identico exceto `build_metadata`; cached 18,4 s (poupa ~16 s por build) |
| A8.5 Schema 4 trigram | done | `label_fts_<locale>_tri` (tokenize='trigram') por locale ativo, content='label'; user_version 4; artefacto 240 730 112 B; integrity ok |
| A8.6 API alargada | done | `search(kind=, food_group=)` (trigram quando todos os termos >= 3 chars, senao prefixo); `foods_for_nutrient()` ranking por valor; real: "polpa" pt-PT → Ananas/Curgete; "vitamina c" pt-PT → VITC; top VITC fr = acerola 2850 mg |
| A8.7 Explorer | done | IndexedDB (chave `<artefacto>@v<schema>` — schema novo invalida); modo nutrientes (pesquisa + ranking com abertura do alimento); chips de grupo (faceta); trigramas espelhados; `npm run build` verde; dev server: pagina/artefacto(240 730 112 B)/wasm 200 |
| A8.8 ADR-0008 | done | Aprovado: contexto (36,7 s, so-prefixo, re-descarga explorer), opcoes com evidencia (VACUUM, ULID translate vs loop, cache, trigram vs LIKE, IDB), decisao, consequencias |
| A8.9 Fecho | done | 176 testes verdes; ruff/mypy limpos; commits atomicos `(f5b)` (9); merge `--no-ff` em `f0/fundacoes` (98576d5) + push; CI verde (checks + explorer) |

**Entregaveis da emenda**: ADR-0008; cache.py + testes (6); CLI `build --full`; schema 4 (16 tabelas FTS = 8 prefixo + 8 trigram); API kind/food_group/foods_for_nutrient (+9 testes integracao); explorer F2/A8; golden ULID.

## Decisoes em aberto

- Nenhuma.

## Bloqueios / pendencia

- Nenhum. Emenda A8 fechada (merge `98576d5` em `f0/fundacoes`, push, CI verde).

## Historico de sessoes

- **2026-08-19**: emenda A8 (f5b). Investigacao ULID: paridade byte-identica (100k seeds) com formula translates, mas mais lenta que o loop (1,83 vs 1,67 s/600k — pyinstrument inflava 3x) → **modulo revertido**, golden P4 como regressao. VACUUM removido do package (36,7 → 18,3 s). `cache.py` content-addressed (fingerprint sha256; hit → copia; fail-high) + `build --full`; determinismo full vs cached provado (todas as tabelas iguais exceto build_metadata). Schema 4: FTS trigram por locale; API `kind`/`food_group`/`foods_for_nutrient` (trigram quando >= 3 chars, senao prefixo). Explorer: IndexedDB (chave com schema_version), modo nutrientes, chips de grupo. **176 testes verdes**; ruff/mypy limpos; artefacto real 240 730 112 B (user_version 4, integrity ok); ADR-0008 aprovado; 7 commits `(f5b)` (perf VACUUM, test ULIDs golden, ci f5b/**, test cache, perf cache, feat schema 4, feat explorer, docs ADR).

## Histórico: Fase 6 inicial (snapshot 2026-08-19)

**Fases 0-5 + emenda A8: concluidas** (`f0/fundacoes`).

**Fase 6 - Qualidade: em curso** (branch `f6/qualidade`; F6.0-F6.4 done, F6.5-F6.8 pendentes).

| Tarefa | Estado | Nota |
|---|---|---|
| F6.0 ADR-0009 | done | Severidades por origem da incoerencia (fonte → warning/revisao; contrato do pipeline → error); energia Atwater UE 1169/2011 (POLYL opcional 2,4) ±5% com piso absoluto 5 kcal; divergencia em pares nao ordenados >= 30% (info); coerencia por (conceito, fonte) |
| F6.1 Suite quality | done | `src/nutridb/quality/` 20 checks (SPEC §11); `_per_source_g` normaliza mg/ug → g; energia so com metodo registado (1485 sem metodo contados, P2); z-score |z|>4 n>=10 por (nutriente, grupo); integridade/órfaos/derivation/unmapped/mt_unreviewed como error |
| F6.2 CLI qa | done | Tabela rich + `build/qa/report.html` + `metrics.json` (schema qa-1); exit 1 com erros; stdout UTF-8 (isinstance guard) |
| F6.3 Testes unit 22 | done | Sinteticos por check; per-source (mistura nao dispara), FATRN 16500 mg→g, NA 200 mg, POLYL opcional, z-score n>=10, órfaos FK, mt_unreviewed; ruff/mypy limpos; **198 testes verdes** (22 novos) |
| F6.4 Triagem real | done | `nutridb qa` real: **0 erros**; warnings proximados 222 (3702 completos, mediana 99,99; Isolat de soja 107,64 CIQUAL, Farine de seigle T85 110,80 INSA), energia 33, AG 44, açucares 2, sal 937 (4259 pares, mediana 1,00 exato; vinhos), RAE 2, z-score 1893; info: divergencia 1200 pares >= 30%, resto 0 |
| F6.5 Golden 200 | pending | Estratificado ~18/grupo CIQUAL (11 grupos, seed fixa); celulas ENERC_KCAL/PROCNT/FAT/CHOAVL/WATER; skip ausentes; tolerancia 1e-9; script efemero dos XMLs oficiais |
| F6.6 Property tests | pending | Hypothesis: shuffle invariante (merge/transform), roundtrip conversao, propriedades da divergencia |
| F6.7 CI f6 | pending | Trigger `f6/**` + job `qa` (fixtures → suite → upload-artifact do relatorio) |
| F6.8 Fecho | pending | PLAN/PROGRESS; commits atomicos `(f6)`; merge `--no-ff` em `f0/fundacoes`; push; CI verde |

**Entregaveis da fase (em curso)**: ADR-0009; suite quality 20 checks; CLI qa + relatorio; 22 testes; triagem real documentada.

## Decisoes em aberto

- Nenhuma.

## Bloqueios / pendencia

- Nenhum. F6 em curso: golden 200, property tests, CI, fecho.

## Sessão 2026-08-20

- Direção de produto publicada no GitHub e registada em ADR-0010: dataset como núcleo, Explorer intuitivo e workspace neutro sem aconselhamento.
- SPEC alinhada com o workspace neutro (`0d03227`).
- ADR-0011 e contrato de aquisição: `declared` para células publicadas, `calculated` para derivações; package rejeita nulos/tipos desconhecidos (`c567de4`).
- Gate P6 de compatibilidade de fontes por perfil (`086b8ed`).
- Build verifica sources/hash e inclui registry no fingerprint (`6fb27c2`).
- Fail-high para fonte sem extractor, SQLite inválido e survivor de identidade desconhecido (`56a3340`, `56f45e6`).
- API read-only e ranking por 100 g (`27f2dd9`, `78970d7`).
- Golden automático CIQUAL: 200 alimentos e 943 células; Hypothesis adicionado em ADR-0012.
- CI `f6/**` com `checks`, `explorer`, build real, QA e upload do relatório; execução verde.
- `nutridb build --full` passou a executar `vocab check` e QA internamente; último build: `qa_errors=0`, `qa_warnings=7` (`ea1d256`).
- Manifesto `release-1` e `SHA256SUMS` gerados pelo build, com fontes, licenças, hashes e counts QA (`458b54d`).
- CI: job `determinism` prova byte-identidade de dois builds completos (P5, `6095a3d` + `78f04c3`); `qa` faz upload do relatório e dos metadados de release; execução 32407054962 verde.
- Explorer: locales derivadas de `i18n/locales.toml` no build (fonte única, P8), padrão `pt-PT`, locales disponíveis descobertas do artefacto (`ba34256`).
- Identidade honesta: `recall` de cobertura (0.9537) separado de `recall_confirmed` (0.4342); `review_golden_true` 146 pares aguardam adjudicação (`dbc5810`).
- Ledger de IDs (ADR-0014, `b0a47b7`): `mappings/id_ledger.csv` com 4 860 atribuições eternas; mudança de algoritmo falha alto; `identity_drift` sinaliza edições da fonte mantendo o ID; escritas LF para determinismo entre plataformas (`2c5837a`).
- F6.5/F6.6/F6.7 fechados no PLAN: golden 200 automático; property tests (roundtrip, divergência simétrica/limitada, ordem de fontes invariante) + merge idempotente (re-run byte-idêntico, `test_merge.py`); CI com jobs `checks`/`explorer`/`qa`/`determinism`.
- Explorer: vista "valores por fonte" — comparação lado a lado por nutriente/fonte com deteção de divergência >= 30% (espelho da regra de fusão), incluindo tipo, aquisição, confiança e licença (`b13157b`).
- Explorer: chips de cobertura por fonte — nutrientes medidos vs vocabulário total (161 tagnames) por conceito (`coverageBySource`; real: 66/161 CIQUAL, 40/161 INSA).
- **F6 fechado**: merge `--no-ff` `9457d52` em `f0/fundacoes`; CI verde (32409215939); pendências humanas documentadas como pós-F6.
- Explorer: vista de cobertura global por fonte e grupo (`coverageGlobal`; real: 4 860 conceitos, 230 601 células, ciqual 3 484/71, insa 1 376/48); interface com locale `pt`/`en` (`i18n.ts`, toggle no header; números formatados por locale).
- `link review` (F6.9): grupo typer com `invoke_without_command` (typer 0.27.1 sem click), listagem com contexto dos proposals e `--apply` CSV determinístico; `_queue_index` corrigido para produto cartesiano por survivor — **listagem real corrigida de 1 719 para 6 237 pares** (1 008 survivors multi-par, 1 008 linhas partilhadas; regra: linha só sai quando todos os pares que a usam estão decididos; 2 testes de regressão).
- **Release verificável (ADR-0015, F7)**: `sbom.py` (CycloneDX 1.6, UUID5 do hash, sem timestamp, licenças honestas); `signing.py` (Ed25519 PEM/base64, fail-high); `write_attestation` (schema `attestation-1`, digests, bloco temporal, assinatura opcional); `nutridb release verify` (hashes + assinatura); `cryptography>=44` adicionado ao pyproject (decisão do ADR); SHA256SUMS cobre só determinísticos; gate de determinismo compara também manifesto/SBOM/checksums; CI faz upload dos novos ficheiros. **E2E real**: build com chave → `signature: verified`; 15 testes novos; suite **230 testes verdes**.
- Suite: **230 testes verdes**, ruff/mypy limpos; build real e QA com 0 erros.
- Adjudicação de identidade aplicada no commit `d431959`: 95 aceites, 112 rejeitados, 6 029 pares restantes; build real com 218 tombstones, 5 078 concept links e QA com 0 erros.
- Os 75 golden-true adiados são conflitos 1:1, principalmente múltiplos alimentos específicos contra CIQUAL `aliment moyen`; não foram fabricadas fusões.
- Chave Ed25519 gerada fora do repositório; `docs/keys/nutridb-signing.pub.pem` contém a pública. Build com `NUTRIDB_SIGNING_KEY` e `release verify --public-key` retornaram `signature: verified`.
- ADR-0016 fecha P3: CIQUAL publica `-`, `<N` e `traces`; INSA não publica motivos por célula; razões adicionais não são inferidas.
- ADR-0017 documenta USDA Retention Factors Release 6 como proposta não integrada; falta pin do artefacto, SHA-256 e confirmação de licença na fonte oficial.
- Análise autónoma dos restantes 6 029 pares não aplicou novas decisões: os 3 candidatos exclusivos colidem com links automáticos existentes.
