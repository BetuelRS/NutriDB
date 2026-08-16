# PLAN.md — plano vivo do NUTRIDB

> Plano atualizado a cada sessão. Nunca dependas do contexto sobreviver (regra §17.1).
> Estado atual: **Fase 0 concluída (2026-08-15)** — CLI, registry, audit/sync, CI e ADR aprovados; 19 testes verdes. **Próximo: Fase 1** (vocabulário + CIQUAL ponta a ponta), aguardando ADR-0003 (URL/hash do ficheiro).

## Convenções

- Uma fase por branch: `f0/fundacoes`, `f1/ciqual-ponta-a-ponta`, …
- Commits atómicos, mensagens convencionais (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- Qualquer decisão cara de reverter → ADR numerado (contexto, opções, decisão, consequências).
- Testes primeiro em tudo o que envolve correção numérica.
- Legendas: `[ ]` pendente · `[x]` feito · DoD = definição de feito · Verificação = comando concreto que prova o DoD.

---

## Fase 0 — Fundações (branch `f0/fundacoes`)

**Objetivo**: repositório, CI, lint, tipos, CLI esqueleto, registo de fontes, ADR-0001/0002 aprovados.

**Decisões registadas (ADR-0001 §7)**: Apache-2.0; remote `https://github.com/BetuelRS/NutriDB.git`; CIQUAL 2025 em `core`; XLS via engine com fallback XML; **F1 inclui página mínima de pesquisa (emenda)**: motor FTS5 no SQLite **+** bootstrap `explorer/` (Vite+React+TS, sql.js/WASM, sem HTTP-range — essa otimização é F8); docs pt-PT / código EN.

**Critérios de aceitação da spec (§16 F0)**:
1. `nutridb --help` funciona
2. CI verde
3. ADR de arquitetura aprovado

| # | Tarefa | DoD | Verificação |
|---|---|---|---|
| F0.1 | Preparação do repo: renomear `NUTRIDB-SPEC.md` → `SPEC.md`, `git init`, remote `origin` → `https://github.com/BetuelRS/NutriDB.git`, `.gitignore` (`build/`, `sources/cache/`, `.venv/`, `__pycache__/`, `.pytest_cache/`), `.gitattributes` (LF, `*.xls` binário), `README.md` mínimo, `LICENSE` (Apache-2.0) e `NOTICE` | Nenhum ficheiro de dados no repo; git limpo; remote aponta ao destino | `git status` vazio; `git remote -v`; `Test-Path SPEC.md` |
| F0.2 | Scaffold de diretórios: `src/nutridb/{sources,vocab,identity,i18n,merge,derive,quality,package,api}`, `vocab/`, `mappings/{nutrients,foodgroups,_unmapped}`, `i18n/{glossary,labels,review_queue}`, `reference/`, `derivations/`, `tests/{unit,property,golden,integration}`, `docs/adr`, `explorer/`; dirs de dados com README de conteúdo esperado | Estrutura espelha §3 | `tree` (ou `Get-ChildItem -Recurse`) |
| F0.3 | Projeto `uv` + `pyproject.toml`: Python 3.12, pacote `nutridb`, script `nutridb`, deps fixadas (`uv add` + lock): typer, rich, structlog, pydantic v2, duckdb, polars, pytest, hypothesis; dev deps: ruff, mypy. Config `ruff` e `mypy --strict` | `uv.lock`; `pyproject` validado | `uv run python -c "import nutridb"` |
| F0.4 | CLI esqueleto `nutridb`: subcomandos registados com help e exit codes corretos — `sources sync`, `sources audit`, `extract`, `vocab check`, `link`, `i18n build`, `i18n review`, `merge`, `derive`, `qa`, `package`, `build`, `diff`, `serve`, `explorer dev`, `--version` | Cada subcomando aparece no help | `uv run nutridb --help` (exit 0); `uv run nutridb --version` |
| F0.5 | `sources/registry.toml` + modelo pydantic + validação: campo `ciqual` com URL, versão, licença, hash, atribuição, share-alike, uso comercial, artefacto de destino | Schema validado por testes (registry malformado falha) | `uv run pytest tests/unit/test_registry.py` |
| F0.6 | `nutridb sources audit`: lê registry, imprime relatório de licenças (tabela rich) e reproduz o gate por-artefacto (ciqual → core) | Relatório coerente com registry | `uv run nutridb sources audit` |
| F0.7 | `nutridb sources sync`: download genérico para `sources/cache/` + verificação SHA-256 contra registry (primeiro alvo: CIQUAL) | Hash verificado ou falha alta se divergir | `uv run nutridb sources sync` (rede necessária) |
| F0.8 | CI: `.github/workflows/ci.yml` (install uv, ruff format --check, ruff check, mypy, pytest) | Workflow sintaticamente válido; verde quando houver remote | `uv run ruff check .`; `uv run mypy src`; `uv run pytest` |
| F0.9 | ADR-0001 aprovado (feito — §7 regista as decisões); ADR-0002 (Apache-2.0, feito); `PROGRESS.md` criado | Estado do ADR-0001 e 0002 = Aprovado | leitura dos ficheiros |

**Entregáveis da fase**: SPEC.md, repo git, CLI funcional, registry validado, CI file, ADR-0001/0002, PROGRESS.md.

**Riscos/bloqueios**: sem remote GitHub o CI só roda local; licença do código (A2) bloqueia F0.9; rede necessária para F0.7.

---

## Fase 1 — Vocabulário e primeira fonte, ponta a ponta (branch `f1/ciqual-ponta-a-ponta`)

**Objetivo**: `vocab/nutrients.csv` completo e congelado; CIQUAL extraída, mapeada, empacotada em `core`; SQLite com pesquisa.

**Critérios de aceitação da spec (§16 F1)**:
1. Consultas ao SQLite devolvem alimentos com nutrientes corretos e proveniência
2. `mappings/_unmapped/` vazio
3. 20 alimentos verificados à mão passam

| # | Tarefa | DoD | Verificação |
|---|---|---|---|
| F1.0 | **ADR-0003 — licença e formato da CIQUAL**: ✅ 2026-08-15 (aprovado): 8 ficheiros baixados do Dataverse (DOI 10.57745/RDMHWY), MD5 = oficiais, etalab-2.0/SPDX confirmada; **XML como formato primário** (proveniência por valor; XLS sem fontes — doc oficial §3.1.1); semântica `-`/`traces`/`<N`/confiança A–D verificada (doc §3.2/§5.5); AMENDADO ADR-0001 A6 | ADR aprovado; registry coincide | `nutridb sources audit` ✓ |
| F1.0b | **Versão fixada: CIQUAL 2025** ✅ 2026-08-15: SHA-256 dos 8 ficheiros no registry (modelo `files`); `sources sync` re-descarcou `alim_grp` e validou por hash | Hash no registry | `uv run nutridb sources sync` ✓ |
| F1.1 | **Vocabulário canónico completo e congelado** ✅ 2026-08-15: **157 tagnames INFOODS/EuroFIR** (SPEC §5: energia ×2, proximados, hidratos, lípidos + AGs `FnnDnnNn` 35, minerais, vitaminas, aminoácidos, outros), `nutrient_groups` 9, `units` 6, `value_types` 9 (6 ausências P3), `acquisition_types` 8 (EuroFIR), `analytical_methods` 22 (inicial), `food_groups` 18, `facets/` 7 ficheiros; `nutrient_relation` 54 agregações; `vocab check` implementado (`src/nutridb/vocab/`); nota: ~250 do SPEC é alvo de projeto — expansão posterior é **aditiva**, não quebra o freeze | Parse limpo; invariantes (tagname único, unidade única, grupos existem, sem ciclos, ausências P3 obrigatórias) | `uv run nutridb vocab check` → 0 erros ✓; `pytest tests/unit/test_vocab.py` ✓ |
| F1.2 | **Extractor CIQUAL** (`src/nutridb/sources/ciqual.py`): lê os 5 XML oficiais do cache (ADR-0003, streaming `compo` 69 MB) → intermediário canónico em Parquet com `source_record` JSON integral (nome original, grupo original, células cruas `-`/`traces`/`<N`, unidades das colunas) | ✅ 2026-08-15: 100% das células processadas sem descarte silencioso; reprodutível — 2 execuções → hashes idênticos (P5); teste unit com fixture sintética; report real 3 484/74/161/1 978/257 816 | `uv run nutridb extract`; `pytest tests/unit/test_extract_ciqual.py` |
| F1.3 | **Mapeamentos completos**: `mappings/nutrients/ciqual.csv` (código constituinte → tagname canónico + fator + método de energia + regra de value_type p/ `-`/`traces`/`<N` + unidade destino + `is_default`), mapeamento grupos CIQUAL → `food_groups`, preenchimento de `_unmapped/` como artefacto do build | ✅ 2026-08-15 (fator AG corrigido 2026-08-16, ver F1.9): 74/74 códigos mapeados (71 tagnames únicos; ENERC×4→2, PROCNT×2→1, hífens→canónicos, RAE/CLD/10004); 91 linhas de grupos (11 grp + 65 ssgrp + 15 ssssgrp p/ split animal/vegetal); `_unmapped/` **vazio** (gate em teste); cobertura golden contra os intermediários reais | `pytest tests/unit/test_mappings.py`; leitura de `_unmapped/` |
| F1.4 | **Transformação de valores** ✅ 2026-08-15: `src/nutridb/transform.py` — leitura intermediários + mappings + vocab + registry → **dataset canónico** em `build/canonical/ciqual/` (1 Parquet por tabela §8: `source`, `coverage`, `source_record`, `concept`, `concept_link`, `value`, `derivation`, `tombstone`); CIQUAL já é por 100 g (`basis=per_100g_edible`); conversão por fator do mapping (AG ×10 → mg); ausência **por cobertura + flags explícitas** (ADR-0001 D5, nunca cross-product): `-` = `not_measured` implícito (coverage ∧ sem linha em `value`), `traces`→`trace`, `<N`→`below_loq` com `below_loq_threshold`; `value` com proveniência completa (concept_id, source_id, source_record_id, source_nutrient_code), `confidence_code` A–D preservado em bruto, `acquisition_type` NULL (ranking de confiança ≠ tipo de aquisição; documentado); `ENERC_*` com método registado em `analytical_method`; `derivation` vazia (P2, nada derivado em F1); report real: **values 174 570, measured 151 981, trace 2 514, below_loq 20 075, not_measured 83 246 (implícito), coverage 74, concepts 3 484, conversions ×10 39 414→**0** (corrigido 2026-08-16: AG são g na fonte, INFOODS/FAO — ver F1.9)** — 0 células perdidas | Verificado em dados reais + fixtures; determinístico (2 execuções byte-idênticas) | `pytest tests/unit/test_transform.py`; `uv run nutridb transform` |
| F1.5 | **Identidade F1-lite** ✅ 2026-08-15: `src/nutridb/identity/` — IDs eternos `nfx_` + ULID (26 chars Crockford, sem I/L/O/U) **determinísticos por seed** (P5: timestamp+randomness derivados de SHA-256 do seed, sem estado — P10); `source_record` imutável (261 300: foods + células compo, JSON cru integral com NaN→null), concept 1:1 por alimento, `concept_link` estatuto `automatic` (3 484), `tombstone` vazia com esquema; `mappings/links.csv` stub — linhas reais só na adjudicação (F3) | Todos os concepts com link; IDs estáveis entre builds | `pytest tests/unit/test_identity.py`; hashes reais 2 runs idênticos |
| F1.6 | **i18n F1-lite** ✅ 2026-08-15: `i18n/locales.toml` (8 locales: fr/en base, pt→en, pt-PT/pt-BR→pt→en, es/de/it→en; ativas fr/en/pt-PT/pt-BR; validação de cadeias/ ciclos); `i18n/labels/vocab_pt_PT.csv` (11 rótulos mínimos, estatuto `curated`); `src/nutridb/i18n/` — `nutridb i18n build` → tabela `label` (ref_kind food/nutrient, ref, locale, status native/official/curated, text, text_normalized); normalização NFKD + transliteração de ligaduras (œ→oe, æ→ae, ß→ss) + minúsculas (acentos-insensível); rótulo vazio falha o build (P7/P9); tagname desconhecido no curated falha; real: **labels 7 136 (fr 3 484 native + en 3 484 native + en vocab 157 official + pt-PT 11 curated)**; fallback nunca congelado na tabela (resolvido em consulta) | `i18n build` gera `label`; falha em vazio; determinístico | `pytest tests/unit/test_i18n.py`; `uv run nutridb i18n build` |
| F1.7 | **Empacotamento `core`** ✅ 2026-08-15: `src/nutridb/package/` — `nutridb package --profile core` → `build/artifacts/nutridb-core-0.1.0.sqlite` (150 MB) com esquema §8 completo: 19 tabelas centrais (as vazias de F1 mantêm esquema tipado: classification/facet/portion/density/reference_value) + vocabulário congelado referenciado (nutrient/relation/food_group/unit/value_type/acquisition_type/analytical_method) + FTS5 externo `content='label'` por locale (fr/en/pt-PT) + `mv_food_value` (tabela larga pré-calculada 164 433 — só códigos `is_default` do mapping; os métodos não-default ficam no canónico `value` com `analytical_method`, P1; correção 2026-08-16) + índices de leitura + `page_size=8192` + `VACUUM`/`ANALYZE` + `user_version=1`, journal não-WAL; `build_metadata` isolado (único bloco temporal, P5); artefacto real verificado: 2 execuções → todas as tabelas byte-idênticas, só `built_at` difere; `integrity_check ok`; **fix de dados**: 2 células do vocabulário com vírgula não-escapada (`acquisition_types` R, `analytical_methods` enzymatic) agora quotadas + gate no `load_csv` (coluna extra → erro duro, P9) | Ficheiro gerado; verificação acima | `pytest tests/unit/test_package.py tests/property/test_determinism.py`; `uv run nutridb package --profile core` |
| F1.8 | **Motor de pesquisa** ✅ 2026-08-15 (emenda A7): `src/nutridb/api/` — `search(db, query, locale, limit)` público e read-only sobre o artefacto: FTS5 por locale (coluna `text_normalized`, insensível a acentos), cadeia de fallback do `locales.toml` resolvida em runtime (primeira locale com hits vence; nunca congelada), frase multi-termo (`"term"*` AND), escape de carateres FTS5, `limit` 1..100, locale desconhecida → erro; resultados `SearchResult` (ref_kind, ref, locale, status, text, score). Real: pastis/eau de vie/pomme/milk/água verificados; **fix**: `tomllib` aninha `[locale.en]` — loader corrigido (testes de cadeias passam agora a valer) | Consultas de exemplo devolvem o esperado (dígito sem acento encontra rótulo com acento) | `pytest tests/integration/test_search.py` (9 testes) |
| F1.8b | **Página mínima de pesquisa** (emenda A7): bootstrap do `explorer/` — Vite+React+TS, uma vista de pesquisa que carrega o SQLite do build via sql.js/WASM (fetch integral do ficheiro; **sem** HTTP-range, otimização reservada à F8) e mostra resultados com proveniência | `npm run build` verde; página consulta o `nutridb-core-0.1.0.sqlite`; pesquisa sem acentos funciona | `uv run nutridb explorer dev` e consulta manual; `pytest` não se aplica (verificação manual + build CI) |
| F1.9 | **Conjunto dourado — 20 alimentos** ✅ 2026-08-16: `tests/golden/ciqual_20.csv` (61 células: 20 alimentos conhecidos × 2–4 constituintes) gerado por script efémero (`uv run --with pandas`) diretamente dos ficheiros oficiais: `expected` = célula `teneur` **verbatim do XML primário** (compo_2025_11_03.xml, alim+const referenciados) e célula XLS legado registada como cross-evidence com coordenadas (linha/col; o XLS diverge em células que o formato legado perdeu — ex. cálcio da água 7,13 vs 0, documentado); colunas XLS casadas por cabeçalho normalizado (não por posição — a folha `codes INFOODS` não está na ordem das colunas do XLS); `tests/golden/test_golden.py` (3 testes) cruza com `mv_food_value` do artefacto real (ou canónico, sem SQLite) com tolerância 1e-9, `skipif` sem artefacto (CI); **correção de dados F1.3/F1.4/F1.7** (evidência INFOODS/FAO: `FASAT(g)`, `FAMS(g)`, `FAPU(g)` — todos os AG em g): mapping AG fator ×10→×1 e unidade mg→g (0,97 g ≠ 9,7 mg); vocab 38 tagnames AG mg→g; coluna `is_default` no mapping (327/328 Reg. UE 1169 e 25000 Jones = default; 332/333 e 25003 ficam no canónico `value` com método registado, P1) → `mv_food_value` único por (conceito, nutriente) e report real corrigido: values 174 570 (canónico preserva tudo), mv 164 433, conversions 0 | Golden 61/61 batem o artefacto real; determinismo real re-verificado (2 runs, 23 tabelas idênticas) | `uv run pytest tests/golden/`; `uv run pytest` (98 testes) |
| F1.10 | **Fechar a fase** ✅ 2026-08-16: `uv run nutridb build` (SPEC §16/P10) encadeia extract→transform→i18n build→package core e falha alto em qualquer etapa (P9); provado do zero: `build/{intermediates,canonical,artifacts}` removidos e reconstruídos com um comando (extract 257 816 células → transform 174 570 → artefacto 147,5 MB, integrity ok); report consolidado por etapa; falta: página mínima de pesquisa (emenda A7) fica para F1.8b/explorer; critérios de aceitação §16 F1 revistos; branch mergeada só com CI verde | P10 verificado em dados reais (reconstrução completa) | `uv run nutridb build`; `pytest tests/unit/test_cli.py` (99 testes) |

**Entregáveis da fase**: ADR-0003; vocabulário congelado; extractor CIQUAL; mappings completos; esquema SQLite fino (documento de esquema + migração); `nutridb-core-0.1.0.sqlite` com proveniência e pesquisa; página mínima de pesquisa; 20 dourados; teste de determinismo.

**Riscos/bloqueios**: rede (CIQUAL 2025 no cache de cache); formato XLS legado (leitura via `duckdb`/`pandas` com engine xls — alternativas: converter XML como fallback); i18n mínimo (A10); seleção dos dourados (A13, auditada).

---

## Próximas fases (referência — só desdobradas quando F1 fechar)

- **F2** Multi-fonte: USDA (4 sub-conjuntos), INSA (autorização!), CoFID, Frida, Fineli + 3 à escolha; 1 ADR de licença por fonte. **Ponto de paragem obrigatório: contacto humano para INSA (§17.6).**
- **F3** Identidade: blocking, sinais, adjudicação, dourado de 500 pares (precisão ≥ 0,98 / recall ≥ 0,90).
- **F4** Multilinguismo: facetas, glossários, composição, divergências (8 locales, ≥ 95% native/official/curated).
- **F5** Fusão e derivações. **F6** Qualidade (suite + 200 dourados). **F7** Empacotamento (gate de licenças automático; lite < 25 MB).
- **F8** Explorador (13 vistas). **F9** API e clientes. **F10** 1.0 (reprodutibilidade externa).

## Decisões em aberto (pendentes de aprovação)

Resolvidas em 2026-08-15 (ADR-0001 §7): A1–A20 fechadas — remote GitHub, Apache-2.0, pt-PT/EN, CIQUAL 2025 em `core`, XLS+fallback XML, página mínima de pesquisa em F1, cobertura+flags, método de energia, INFOODS + i18n mínimo, dourados/Fixtures, esquema fino, semver 0.1.0, links 1:1, `_unmapped`/READMEs, registry oficial+Zenodo, divergences só F4. Sem decisões em aberto para arrancar F0.