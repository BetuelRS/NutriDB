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
| F1.2 | **Extractor CIQUAL** (`src/nutridb/sources/ciqual.py`): lê ficheiro oficial (XLS ou XML) do cache → intermediário canónico em Parquet com `source_record` JSON integral (nome original, grupo original, células cruas `-`/`traces`/`<N`, unidades das colunas) | 100% das células processadas sem descarte silencioso; reprodutível (2 execuções → mesmos ficheiros); teste unit com fixture sintética pequena (`tests/fixtures/synthetic_ciqual.xls`) | `uv run nutridb extract --source ciqual`; `pytest tests/unit/test_extract_ciqual.py` |
| F1.3 | **Mapeamentos completos**: `mappings/nutrients/ciqual.csv` (código constituinte → tagname canónico + fator + método de energia + regra de value_type p/ `-`/`traces`/`<N` + unidade destino), mapeamento grupos CIQUAL → `food_groups`, preenchimento de `_unmapped/` como artefacto do build | `_unmapped/` **vazio** (gate); conversões cobertas por testes | `uv run nutridb vocab check`; leitura de `_unmapped/` |
| F1.4 | **Transformação de valores**: normalização a 100 g (já é a base da CIQUAL), conversão unidades via fatores do mapping, tipagem de ausência (P3): `-` → `not_measured`, `traces` → `trace`, `<N` → `below_loq` com limiar `N` guardado; `value` completa com proveniência (source_id, source_record_id, source_nutrient_code); `ENERC_*` com método registado; tabela `derivation` criada (vazia, mecanismo pronto) | Tabela `value` normalizada; contagem por `value_type` documentada no relatório; 0 células perdidas | `uv run pytest tests/unit/test_transform.py`; `uv run pytest tests/unit/test_absence.py` |
| F1.5 | **Identidade F1-lite**: `source_record` imutável (tabela + camada), concept 1:1 por registo com ULID `nfx_`, `concept_link` com estatuto `automatic` (1 fonte), `tombstone` implementado mas sem casos reais, `mappings/links.csv` criado (cabeçalho) | Todos os concepts com link registado; IDs estáveis entre builds | consulta SQLite (ver F1.7) |
| F1.6 | **i18n F1-lite**: `locales.toml` (fallback chains 8 locales; ativos: fr, en, pt-PT/pt-BR mínimos), `labels/` com nomes nativos (`fr`, `native`) e rótulos do vocabulário (`en` `pt-PT` `curated`/`official`), normalização sem acentos por locale | `uv run nutridb i18n build` gera a tabela `label`; falha em rótulo vazio; divergências (`divergences.csv`) não exigidas em F1 | `uv run nutridb i18n build` |
| F1.7 | **Empacotamento `core`**: `nutridb package --profile core` → `nutridb-core-0.1.0.sqlite` com esquema §8 completo (tabelas centrais + vistas materializadas + `build_metadata` temporal isolado + FTS5 externo por locale + índices cobertos + `page_size` + `VACUUM`/`ANALYZE`, sem WAL) | Ficheiro gerado; duas execuções → byte-idênticos exceto `build_metadata` | `uv run nutridb package --profile core`; `pytest tests/property/test_determinism.py` |
| F1.8 | **Motor de pesquisa** (emenda aprovada: A7): FTS5 por locale + busca insensível a acentos (coluna normalizada) via consulta pública no pacote | Consultas de exemplo devolvem resultados esperados (ex.: dígito sem acento encontra rótulo com acento) | `pytest tests/integration/test_search.py` |
| F1.8b | **Página mínima de pesquisa** (emenda A7): bootstrap do `explorer/` — Vite+React+TS, uma vista de pesquisa que carrega o SQLite do build via sql.js/WASM (fetch integral do ficheiro; **sem** HTTP-range, otimização reservada à F8) e mostra resultados com proveniência | `npm run build` verde; página consulta o `nutridb-core-0.1.0.sqlite`; pesquisa sem acentos funciona | `uv run nutridb explorer dev` e consulta manual; `pytest` não se aplica (verificação manual + build CI) |
| F1.9 | **Conjunto dourado — 20 alimentos**: `tests/golden/ciqual_20.csv` (alimento, constituinte, valor, unidade, referência à linha/coluna da tabela oficial) verificado à mão contra a fonte; teste compara o SQLite gerado com o fixture | 20/20 passam; valores provêm da fonte oficial (nunca inventados) | `uv run pytest tests/golden/` |
| F1.10 | **Fechar a fase**: `nutridb build` completo ponta a ponta do zero a partir de cache vazio (inclui sync); página mínima de pesquisa a funcionar (emenda A7); critérios de aceitação §16 F1 verificados um a um; `PLAN.md`/`PROGRESS.md` atualizados; branch mergeada só com CI verde | Tudo acima verde | `uv run nutridb build`; `pytest` completo; checklist de aceitação |

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