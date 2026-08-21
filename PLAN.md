# PLAN.md — plano vivo do NUTRIDB

> Plano atualizado a cada sessão. Nunca dependas do contexto sobreviver (regra §17.1).
> **Estado oficial:** direção de produto aprovada em 2026-08-19. O dataset é o produto principal; o Explorer é a interface de inspeção; integrações e expansão de fontes seguem depois dos gates de produção.

## Convenções

- Uma fase por branch: `f0/fundacoes`, `f1/ciqual-ponta-a-ponta`, …
- Commits atómicos, mensagens convencionais (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- Qualquer decisão cara de reverter → ADR numerado (contexto, opções, decisão, consequências).
- Testes primeiro em tudo o que envolve correção numérica.
- Legendas: `[ ]` pendente · `[x]` feito · DoD = definição de feito · Verificação = comando concreto que prova o DoD.

## Direção confirmada

O NutriDB será uma plataforma aberta e versionada de dados de composição
alimentar para desenvolvedores, investigadores e consulta pública. O núcleo é
o dataset; o Explorer torna a informação intuitiva sem esconder proveniência,
ausências ou divergências. A direção está registada no
[`ADR-0010`](docs/adr/0010-direcao-produto.md).

### Produto

- Dataset canónico, auditável e reutilizável como primeira prioridade.
- Explorer web com pesquisa, fichas, comparação de fontes, proveniência e cobertura.
- Workspace neutro futuro para selecionar alimentos/quantidades e calcular totais com inputs visíveis; sem aconselhamento clínico.
- API, bibliotecas e exports adicionais apenas depois da release confiável do dataset.

### Escopo inicial

- Fontes: CIQUAL 2025 + INSA/TCA 7.1.
- Idiomas: `pt-PT` primeiro, `en` depois; outras variantes por prioridade e cobertura.
- Saídas: SQLite + Parquet + Explorer.
- Fora do core: diário, tracking, contas, recomendações clínicas e imputação de valores.

### Plano atual orientado à produção

| Prioridade | Objetivo | Critério verificável |
|---|---|---|
| P0 | Fechar o contrato do produto e emendar a SPEC sobre o workspace neutro | ADR-0010 aprovado; fronteiras documentadas |
| P1 | Fechar P1/P3/P4/P6/P9/P10 | aquisição e ausência tipadas; IDs auditáveis; gate de licenças; build único; CI sem falhas |
| P2 | Publicar um dataset verificável | golden 200; Hypothesis; QA no CI; manifesto e checksums; rebuild externo |
| P3 | Explorer v1 | `pt-PT`/`en`, pesquisa, ficha, proveniência, comparação e cobertura testadas |
| P4 | Expandir catálogo com segurança | cada fonte com ADR, hash, extractor, mapping, golden e QA |
| P5 | Integrar consumidores | API, bibliotecas, exports e publicação só após P2/P3 |

### Bloqueadores atuais

- A adjudicação inicial fechou 95 pares (73 golden-true + 22 exclusivos) e rejeitou 112 golden-false; permanecem 6 029 pares em review. 75 golden-true foram adiados por conflitos 1:1, sobretudo contra entradas compostas `aliment moyen`.
- O golden 200 automático existe; falta a revisão humana final das células selecionadas.
- P3 está fechado por ADR-0016: `coverage` + ausência de linha, `trace`/`below_loq` quando publicados e nenhum motivo adicional inferido.
- A chave privada Ed25519 está fora do repositório em `C:\Users\Betuel\.nutridb\signing\`; a chave pública está em `docs/keys/nutridb-signing.pub.pem`. Falta apenas a decisão operacional de custódia/backup para uma release pública.

### Progresso confirmado desde a auditoria

- `acquisition_type` controlado: fontes publicadas usam `declared`, cálculos usam `calculated` e o package falha em nulos/tipos desconhecidos.
- Gate de compatibilidade de licença aplicado no package por perfil.
- `build` verifica a registry e os hashes antes de extrair; a registry entra no fingerprint do transform.
- Fonte registada sem extractor, survivor de identidade desconhecido e SQLite inválido falham alto.
- API abre artefactos existentes em modo somente leitura e rankings filtram `per_100g_edible`.
- Golden automático CIQUAL: 200 alimentos e 943 células do XML primário.
- Hypothesis cobre conversões, divergência e ordem determinística de identidade.
- CI `f6/**` executa checks, Explorer, build real, QA e upload do relatório.
- `nutridb build --full` executa `vocab check` e QA internamente e falha com qualquer `error`.
- O build gera manifesto `release-1`, `SHA256SUMS`, SBOM CycloneDX 1.6 e atestação `attestation-1` (Ed25519 se `NUTRIDB_SIGNING_KEY`; ADR-0015); `nutridb release verify` valida tudo, incluindo a assinatura.
- CI: job `determinism` constrói duas vezes e prova byte-identidade (P5) — agora compara também manifesto, SBOM e `SHA256SUMS`; `qa` faz upload do relatório e dos metadados de release.
- Explorer deriva locales de `i18n/locales.toml` no build; `pt-PT` é o padrão; locales disponíveis descobertas do artefacto.
- Métricas de identidade honestas: `recall` (cobertura do matcher 0.954) separada de `recall_confirmed` (0.434, antes da adjudicação); 95 links adjudicados estão aplicados e 6 029 pares continuam em review.
- Ledger de IDs (ADR-0014): `mappings/id_ledger.csv` com 4 860 atribuições; mudança de algoritmo falha alto, `identity_drift` sinaliza edições da fonte sem trocar o ID.
- Suite atual: **230 testes verdes**, ruff/mypy limpos; build real e QA passam com 0 erros.
- `nutridb link review`: fila de adjudicação humana com contexto (nomes, similaridade, score), `--apply` determinístico em `mappings/links.csv` (P8); após a primeira vaga restam 6 029 pares, com a restrição 1:1 preservada.
- Explorer: vista de cobertura global do dataset (por fonte e por grupo) e interface com locale `pt`/`en` (toggle).
- ADR-0016 fecha P3 com evidência CIQUAL/INSA e mantém razões de ausência não publicadas fora do modelo.
- ADR-0017 regista USDA Retention Factors Release 6 como proposta; integração bloqueada até descarregar artefacto oficial, fixar SHA-256 e confirmar licença na fonte.
- Análise da fila restante não encontrou aceites seguros: os 3 candidatos exclusivos colidem com links automáticos existentes; permanecem em review.
- PR #2 integrado em `f0/fundacoes` (`4a53ca3`) com CI verde no PR e pós-merge; README em release candidate; `release verify` é passo do CI.
- Release `v0.1.0` etiquetada e publicada com artefacto assinado e metadados verificáveis.

As secções seguintes preservam o histórico detalhado das fases já executadas.
Não devem ser interpretadas como o estado oficial atual quando divergirem deste
bloco.

---

## Histórico detalhado de implementação

As tabelas abaixo registam decisões e entregáveis por fase. O estado oficial e
as próximas ações estão na secção anterior.

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
1. Consultas ao SQLite devolvem alimentos com nutrientes corretos e proveniência — ✅ testado ponta a ponta (F1.9 golden 61/61 + **F1.8b proveniência** `test_golden_provenance_walk_on_sqlite`: concept → `mv_food_value` → `source_record` com `teneur` verbatim do XML oficial)
2. `mappings/_unmapped/` vazio — ✅ gate em teste (F1.3)
3. 20 alimentos verificados à mão passam — ✅ F1.9 (61 células vs ficheiros oficiais; célula XLS como cross-evidence)

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
| F1.8b | **Página mínima de pesquisa** ✅ 2026-08-16 (emenda A7): bootstrap do `explorer/` — Vite+React+TS, uma vista de pesquisa que carrega o SQLite do build **por fetch integral** (sem HTTP-range, otimização reservada à F8) e mostra resultados com proveniência; **decisão com evidência**: mecanismo é o **WASM oficial do SQLite** (`@sqlite.org/sqlite-wasm` 3.49.1-build3 pinado) porque o build pré-compilado do `sql.js` **não inclui FTS5** (`no such module: fts5` — verificado empiricamente 2026-08-16; FTS5 é o motor da F1, emenda A7); `:memory:` + `sqlite3_deserialize` (147 MB OK); semântica de pesquisa espelhada de `src/nutridb/api/` (normalização ligaduras+NFKD+minúsculas, `"term"*` AND, cadeias de fallback do `locales.toml` em `src/search.ts`); vista de detalhe: `mv_food_value` + proveniência (`source` + `source_record` JSON cru); CLI `nutridb explorer dev` (dev server vite com middleware `/artifacts/*` do `build/`, `NUTRIDB_ROOT` respeitado, traversal bloqueado) e `nutridb explorer build`; `scripts/copy-wasm.mjs` (binário não vai para o git); CI: job `explorer` (npm ci + build, Node 22) | `npm run build` verde (tsc strict + vite); dev server verificado: página 200, artefacto 200 (147 562 496 bytes), wasm 200, traversal 400 | `uv run nutridb explorer dev` / `explorer build`; job `explorer` no CI |
| F1.9 | **Conjunto dourado — 20 alimentos** ✅ 2026-08-16: `tests/golden/ciqual_20.csv` (61 células: 20 alimentos conhecidos × 2–4 constituintes) gerado por script efémero (`uv run --with pandas`) diretamente dos ficheiros oficiais: `expected` = célula `teneur` **verbatim do XML primário** (compo_2025_11_03.xml, alim+const referenciados) e célula XLS legado registada como cross-evidence com coordenadas (linha/col; o XLS diverge em células que o formato legado perdeu — ex. cálcio da água 7,13 vs 0, documentado); colunas XLS casadas por cabeçalho normalizado (não por posição — a folha `codes INFOODS` não está na ordem das colunas do XLS); `tests/golden/test_golden.py` (3 testes) cruza com `mv_food_value` do artefacto real (ou canónico, sem SQLite) com tolerância 1e-9, `skipif` sem artefacto (CI); **correção de dados F1.3/F1.4/F1.7** (evidência INFOODS/FAO: `FASAT(g)`, `FAMS(g)`, `FAPU(g)` — todos os AG em g): mapping AG fator ×10→×1 e unidade mg→g (0,97 g ≠ 9,7 mg); vocab 38 tagnames AG mg→g; coluna `is_default` no mapping (327/328 Reg. UE 1169 e 25000 Jones = default; 332/333 e 25003 ficam no canónico `value` com método registado, P1) → `mv_food_value` único por (conceito, nutriente) e report real corrigido: values 174 570 (canónico preserva tudo), mv 164 433, conversions 0 | Golden 61/61 batem o artefacto real; determinismo real re-verificado (2 runs, 23 tabelas idênticas) | `uv run pytest tests/golden/`; `uv run pytest` (98 testes) |
| F1.10 | **Fechar a fase** ✅ 2026-08-16: `uv run nutridb build` (SPEC §16/P10) encadeia extract→transform→i18n build→package core e falha alto em qualquer etapa (P9); provado do zero: `build/{intermediates,canonical,artifacts}` removidos e reconstruídos com um comando (extract 257 816 células → transform 174 570 → artefacto 147,5 MB, integrity ok); report consolidado por etapa; F1.8b fechada (explorer mínimo — ver linha); critérios de aceitação §16 F1 verificados um a um; **merge com CI verde** | P10 verificado em dados reais (reconstrução completa) | `uv run nutridb build`; `pytest tests/unit/test_cli.py` (99 testes) |

**Entregáveis da fase**: ADR-0003; vocabulário congelado; extractor CIQUAL; mappings completos; esquema SQLite fino (documento de esquema + migração); `nutridb-core-0.1.0.sqlite` com proveniência e pesquisa; página mínima de pesquisa; 20 dourados; teste de determinismo.

**Riscos/bloqueios**: rede (CIQUAL 2025 no cache de cache); formato XLS legado (leitura via `duckdb`/`pandas` com engine xls — alternativas: converter XML como fallback); i18n mínimo (A10); seleção dos dourados (A13, auditada).

---

## Fase 2 — Multi-fonte: INSA/TCA no esquema comum (branch `f2/multi-fonte`)

**Objetivo**: segunda fonte (INSA/TCA 7.1) integrada no esquema comum de intermediários (ADR-0005) com CIQUAL; pipeline multi-fonte ponta a ponta (extract→transform→i18n→package); golden INSA; explorer atualizado; fecho da fase.

**Decisões registadas**: ADR-0004 (licença `insa-tca-7.1` custom — atribuição obrigatória, uso comercial ok; evidência e-mail oficial 2026-07-28; formato XLSX, célula nativa = valor verbatim; NaN = não medido, 0 = zero real, sem traces/limites; energia sem método publicado → NULL; `per_100ml` nas bebidas alcoólicas) e ADR-0005 (esquema comum: 4 tabelas por fonte em `build/intermediates/<source_id>/`; canónico único `build/canonical/`; `value.source_nutrient_code` TEXT; conceitos sem fusão até F3; `mv_food_value` por locale; schema/user_version 2; FTS `label_fts_<locale>`; sem dependências novas — XLSX via zipfile+xml.etree) — aprovados 2026-08-16, por commitar.

**Critérios de aceitação da spec (§16 F2)**:
1. Dois extractors produzem o mesmo contrato — ✅ (testes de contrato por fonte)
2. Build orquestrado com as duas fontes — ✅ P10 real (extract 257 816 + 66 048 células → artefacto 229,6 MB, integrity ok)
3. Golden INSA — ✅ `tests/golden/insa_10.csv` (35 células, 10 alimentos) 35/35
4. Sem ramos por fonte no transform — ✅ (factos por fonte em mappings/registry)

| # | Tarefa | DoD | Verificação |
|---|---|---|---|
| F2.0 | **ADR-0004 — licença/formato INSA** ✅ 2026-08-16: licença `insa-tca-7.1` verificada no site oficial (custom não-SPDX, atribuição obrigatória, comercial ok) + e-mail oficial INSA 2026-07-28 como evidência; formato XLSX inspecionado (folha de dados + folha "Componentes-Correspondência"); registry com `license_id: insa-tca-7.1` | ADR aprovado; registry coincide | `nutridb sources audit` |
| F2.1 | **ADR-0005 — esquema comum de intermediários** ✅ 2026-08-16: contrato de 4 tabelas por fonte (`food`, `food_group`, `constituent`, `value` com colunas na ordem fixada) + canónico único + ID `source_nutrient_code` TEXT + conceitos (source, food) sem fusão até F3 + `mv_food_value` 1 linha por (concept, nutrient, locale) com label/locale + schema 2 + FTS por locale | ADR aprovado | leitura dos ADRs |
| F2.2 | **Registry + sync INSA** ✅ 2026-08-16: entrada `[sources.insa]` (URL oficial, SHA-256 fixado, 1 ficheiro `insa_tca.xlsx`); `sources sync` descarrega e verifica | Hash verificado | `uv run nutridb sources sync` |
| F2.3 | **Extractor INSA** ✅ 2026-08-16 (`src/nutridb/sources/insa.py`): XLSX com stdlib (zipfile+xml.etree: rels, sharedStrings, células nativas); validação dos 48 headers contra a folha "Componentes-Correspondência" (fail high); chaves `<nome>_<unidade>` (µ→ug, α/β→a/b, NFKD); alias de ortografia da fonte (`alfa_tocoferol_mg`→`a_tocoferol_mg`); células vazias = não medido (P3); basis `per_100ml` só em "Bebidas alcoólicas" (36 alimentos); energia sem método → NULL (P2); record JSON com valor nativo verbatim; report real: foods 1376 / constituents 48 / values 66048; determinístico | Contrato cumprido; report real coerente | `uv run nutridb extract`; `uv run pytest tests/unit/test_extract_insa.py` (8 testes) |
| F2.4 | **Vocabulário aditivo** ✅ 2026-08-16: +4 tagnames (OLSAC, VITA, CARTBEQ, NIATRP) → 161; freeze F1.1 mantido (expansão aditiva) | `vocab check` 0 erros | `uv run nutridb vocab check` |
| F2.5 | **Mapeamentos INSA** ✅ 2026-08-16: `mappings/nutrients/insa.csv` (48 linhas; FATRN fator 1000 g→mg; `b_caroteno_total_ug`→CARTB e `sodio_mg`→NA sem código INFOODS publicado, documentado; energy_method `-`); `mappings/foodgroups/insa.csv` (22 L1 + overrides L2/L3: Especiarias→condiments, casca rija→nuts_seeds, Amidos→cereals, Crustáceos/Moluscos→seafood, Algas→other, Carne de aves→poultry; dois L1 legumes→legumes) | 48/48 nutrientes + todos os alimentos resolvem | `pytest tests/unit/test_mappings.py` (golden gate) |
| F2.6 | **Transform multi-fonte** ✅ 2026-08-16: sem ramos por fonte (factos em mappings/registry); canónico único `build/canonical/`; report real: foods 4860, concepts 4860, source_records 328724, coverage 122, values 230601 (measured 208012 / trace 2514 / below_loq 20075), not_measured 93263, conversions 1376 (trans INSA ×1000), sources 2; dir de intermediários ausente → TransformError (P9) | Counts coerentes; determinístico | `pytest tests/unit/test_transform.py` |
| F2.7 | **i18n/package multi-fonte** ✅ 2026-08-16: labels nativas por fonte (INSA=pt, CIQUAL=fr/en; pt-PT só vocabulário curado); `mv_food_value` por locale com label/locale; FTS `label_fts_{en,fr,pt,pt_PT}`; schema_version/user_version 2; DDL `value.source_nutrient_code` TEXT | mv 384 897 linhas reais; locales mv {en,fr,pt} | `pytest tests/unit/test_i18n.py tests/unit/test_package.py` |
| F2.8 | **Golden INSA** ✅ 2026-08-16: `tests/golden/insa_10.csv` (35 células, 10 alimentos — incl. vinho `per_100ml`, trans g→mg, energia sem método) com células nativas verbatim + coordenadas linha/coluna; 4 testes golden (forma/evidência, valores no mv com fator do mapping, alimentos existem, proveniência no SQLite) | 35/35 batem o artefacto real | `uv run pytest tests/golden/` |
| F2.9 | **Explorer multi-fonte** ✅ 2026-08-16: `foodValues(conceptId, locale)` com label/locale e cadeia de fallback no mv (fr→en→pt; pt-PT→pt→en); vista de detalhe mostra rótulo no idioma resolvido; footer com as duas fontes; `npm run build` verde | build verde | `npm run build` (explorer) |
| F2.10 | **Fechar a fase** ✅ 2026-08-17: `uv run nutridb build` com as duas fontes (P10, reconstrução completa); golden 96/96 (61 CIQUAL + 35 INSA); suite completa verde; lint/mypy; PLAN/PROGRESS; CI com `f2/**`; commit/push; merge — **concluído 2026-08-17**: 12 commits atómicos, push `f2/multi-fonte`, merge em `f0/fundacoes` (e4fb3a9) | P10 real; CI verde | `uv run nutridb build`; `uv run pytest`; `uv run ruff check .`; `uv run mypy .` |

**Entregáveis da fase**: ADR-0004/0005; extractor INSA; +4 tagnames; mappings INSA; transform/i18n/package multi-fonte; golden INSA; explorer multi-fonte; artefacto `nutridb-core-0.1.0.sqlite` ~229,6 MB com 2 fontes.

**Riscos/bloqueios**: licença custom não-SPDX (P6 resolvido no ADR-0004); INSA sem método de energia (P2 documentado, NULL); `_unmapped/` continua gate.

---

## Registo histórico: fases previstas após F2

- **F2** Multi-fonte: USDA (4 sub-conjuntos), INSA (autorização!), CoFID, Frida, Fineli + 3 à escolha; 1 ADR de licença por fonte. **Ponto de paragem obrigatório: contacto humano para INSA (§17.6).**
- **F3** Identidade: blocking, sinais, adjudicação, dourado de 500 pares (precisão ≥ 0,98 / recall ≥ 0,90).
- **F4** Multilinguismo: facetas, glossários, composição, divergências (8 locales, ≥ 95% native/official/curated).
- **F5** Fusão e derivações. **F6** Qualidade (suite + 200 dourados). **F7** Empacotamento (gate de licenças automático; lite < 25 MB).
- **F8** Explorador (13 vistas). **F9** API e clientes. **F10** 1.0 (reprodutibilidade externa).

## Registo histórico: decisões resolvidas

Resolvidas em 2026-08-15 (ADR-0001 §7): A1–A20 fechadas — remote GitHub, Apache-2.0, pt-PT/EN, CIQUAL 2025 em `core`, XLS+fallback XML, página mínima de pesquisa em F1, cobertura+flags, método de energia, INFOODS + i18n mínimo, dourados/Fixtures, esquema fino, semver 0.1.0, links 1:1, `_unmapped`/READMEs, registry oficial+Zenodo, divergences só F4. Sem decisões em aberto para arrancar F0.
---

## Fase 3 - Identidade (branch `f3/identidade`)

**Objetivo**: resolucao de entidades INSA x CIQUAL: blocking, sinais, adjudicacao, golden de 633 pares rotulados (SPEC §16 F3: precisao >= 0.98, recall >= 0.90); `nutridb link` + consumo de `mappings/links.csv` no transform (tombstones P4, concept_link cross, valores reassignados).

**Criterios de aceitacao da spec (§16 F3)**:
1. Golden >= 500 pares rotulados -> 633 (281 true / 352 false)
2. Precisao >= 0.98 e recall >= 0.90 -> 0.9919 / 0.9037 (food_recall 0.9956) no golden real
3. Decisoes em `mappings/links.csv` consumidas pelo transform (gate P8)
4. `nutridb link` reporta as metricas e falha alto (exit 1) se os gates nao passarem

| # | Tarefa | DoD | Verificacao |
|---|---|---|---|
| F3.0 | Matcher: blocking (termo partilhado + raw df <= 25), sinais (0.55/0.25/0.20), veto de nutrientes, conflitos distintivo/numerico, single-term, 1:1 deterministico, `evaluate()` com precision/recall/food_recall | 111 267 candidatos; AUTO 0.84 / REVIEW 0.50; 123 finais 1:1 | `pytest tests/unit/test_identity.py` |
| F3.1 | Dicionario `mappings/identity/food_terms.csv`: 466+ linhas + 27 queijos (celulas pt so com o token da variedade) | Termos partilhados bilingues | leitura do CSV |
| F3.2 | Golden `tests/golden/identity_pairs.csv`: 633 pares (281 true / 352 false) - julgamento puro (pares + rotulos), revisao manual dos 238 autos a 0.72 (42 FALSE), 181 vencedores 1:1 e amostra de review; 4 missed-TRUE verificados; 2 pares familia-not-identity | >= 500 pares; labels revistos | `uv run nutridb link` |
| F3.3 | `nutridb link`: escreve `mappings/links.csv` (123 finais automatic + 6237 review = 12 720 linhas) e reporta as metricas do golden; exit 1 se precision < 0.98 ou recall < 0.90 | Report real coerente | `uv run nutridb link` |
| F3.4 | Transform consome `mappings/links.csv` (status automatic/adjudicated; review ignorado): tombstone do conceito absorvido (P4), reassign de valores ao survivor, concept_link cross; codigo desconhecido/duplicado = fail high | Real: 123 tombstones, concept_link 4983, integridade ok | `uv run nutridb transform` |
| F3.5 | i18n: conceitos fundidos agregam nomes de todos os registos (deterministico, primeiro nao-vazio); status automatic + adjudicated | Real: labels 8700 | `uv run nutridb i18n build` |
| F3.6 | `mv_food_value` dedup deterministico por (concept, nutrient, locale) com tie-break por fonte | Real: 390 323 linhas, 0 duplicados | SQL no artefacto |
| F3.7 | Testes: evaluate/_status/write_links_csv unitarios (sinteticos), `_apply_identity_links` (merge/tombstone/fail-high), sandbox root sem links.csv em toda a suite | 119+ testes verdes; lint/mypy limpos | `uv run pytest`; `uv run ruff check .`; `uv run mypy .` |
| F3.8 | Fecho: CI `f3/**`, PLAN/PROGRESS, commits atomicos `(f3)`, merge `--no-ff` em `f0/fundacoes`, push, CI verde | P10 real (build completo com links) | `gh run watch` |

**Entregaveis da fase**: `src/nutridb/identity/matching.py`; `mappings/identity/food_terms.csv`; golden 633; `mappings/links.csv` (12 720 linhas); CLI `link`; transform/i18n/package F3; testes; CI `f3/**`.

---

## Fase 4 - Multilinguismo (branch `f4/multilinguismo`)

**Objetivo**: 8 locales compostas (fr, en, pt, pt-PT, pt-BR, es, de, it) com 100% de rotulos em estatuto native/official/curated; zero mt_unreviewed no core (gate P7); pesquisa cruzada funcional; glossarios, divergencias regionais com gate, fluxo de revisao (SPEC §7/§16 F4; ADR-0006).

**Criterios de aceitacao da spec (§16 F4)**:
1. 8 locales com >= 95% de rotulos em estatuto native/official/curated -> 100% (ADR-0006: distribuicao de estatutos; cobertura de nutrientes 161/161 por locale)
2. Zero mt_unreviewed no core -> gate no build falha alto
3. Pesquisa cruzada funcional -> "chicken" encontra o conceito cujo rotulo pt-PT e "frango"; testes no artefacto real

| # | Tarefa | DoD | Verificacao |
|---|---|---|---|
| F4.0 | ✅ 2026-08-18: ADR-0006 (ambito F4: glossarios, divergencias, gates, composicao honesta) | Aprovado | leitura do ADR |
| F4.1 | ✅ 2026-08-18: Glossarios nutrientes: `i18n/glossary/{fr,pt,pt-PT,pt-BR,es,de,it}.csv` (161 tagnames cada, terminologia INFOODS/EuroFIR/FAO, status curated, coluna evidence); os 11 curados pt-PT migrados | 161 x 7 rotulos; 0 tagnames em falta | `uv run nutridb i18n build`; leitura |
| F4.2 | ✅ 2026-08-18: Facetas: `vocab/facets/*.csv` com colunas `name_fr,name_es,name_de,name_it,name_pt_PT,name_pt_BR` (139 facetas); `vocab check` valida (header + celulas nao-vazias) | 139 x 6 celulas; check 0 erros | `uv run nutridb vocab check` |
| F4.3 | ✅ 2026-08-18: `i18n/divergences.csv` (67 linhas: 53 pares pt de nutrientes + 14 alimentos) + gate no build: conceito divergente exige rotulo em cada variante; generico onde ha divergencia -> falha; drift-check vs glossarios; conceito desconhecido falha | 67 pares; gate testado | `pytest tests/unit/test_i18n.py` |
| F4.4 | ✅ 2026-08-18: i18n build F4: composicao por prioridade (reviewed > native > glossario > divergences); gate P7 (mt_unreviewed falha); gate tagnames 161 por locale (pt: 108, sem generico para divergentes); gate >= 95% status; report por locale | Real: 8 locales, 9775 labels, 100% native/official/curated | `uv run nutridb i18n build` |
| F4.5 | ✅ 2026-08-18: Package: FTS por locale das 8 ativas | 8 tabelas label_fts (9775 cada) | SQL no artefacto |
| F4.6 | ✅ 2026-08-18: Pesquisa cruzada: `api.search` resolve rotulo exibido pela cadeia do locale pedido + dedupe por conceito; golden real "zucchini"->"Curgete, polpa e pele, cozida" (pt-PT) | "chicken"->"frango" no artefacto | `pytest tests/integration/test_search.py` |
| F4.7 | ✅ 2026-08-18: Fluxo de revisao: `nutridb i18n review` (lista `i18n/review_queue/<locale>.csv`, aplica aprovados em `i18n/labels/reviewed_<locale>.csv` consumido pelo build); `i18n/untranslatable.csv` com header | Fila vazia; CLI operacional; teste sintetico | `uv run nutridb i18n review`; `pytest` |
| F4.8 | ✅ 2026-08-18: Testes: glossarios (161/161), gates P7/divergencias/95%, FTS 8 locales, pesquisa cruzada, golden i18n (amostra por locale vs artefacto) | 136 testes verdes; lint/mypy limpos | `uv run pytest`; `uv run ruff check .`; `uv run mypy .` |
| F4.9 | Fecho: CI `f4/**`, PLAN/PROGRESS, commits atomicos `(f4)`, merge `--no-ff` em `f0/fundacoes`, push, CI verde | P10 real (build completo com 8 locales) | `gh run watch` |

**Entregaveis da fase**: ADR-0006; glossarios 7 locales (1127 rotulos); facetas 8 locales; divergences.csv + gate; i18n build F4 (gates P7/95%); FTS 8 locales; pesquisa cruzada; CLI `i18n review`; testes + golden i18n.

---

## Fase 5 - Fusao e derivacoes (branch `f5/fusao`)

**Objetivo**: prioridades puramente dados (SPEC §9: por (locale, grupo, nutriente)); valores alternativos que permanecem; divergencias >= 30% sinalizadas; overrides com justificacao obrigatoria; derivacoes com cadeia registada em `derivation` (SPEC §10: retencao, rendimento, densidades, porcoes); schema do artefacto 3 (ADR-0007).

**Criterios de aceitacao da spec (§16 F5)**:
1. Prioridades sao puramente dados -> `mappings/source_priority.csv` + resolucao deterministica; sem regra = falha alta
2. Toda derivacao tem cadeia registada -> `derive` grava `derivation` (formula, inputs, factors) + `derivation_id` no valor; derivacao pedida sem fatores = falha alta; real: 0 derivacoes (fontes medem 100g e 100ml; P2: so calcular sem medicao direta)
3. Divergencias sinalizadas, nunca resolvidas em silencio -> divergence_flag rel >= 0.30 no mv_food_value

| # | Tarefa | DoD | Verificacao |
|---|---|---|---|
| F5.0 | ADR-0007 (ambito F5: prioridades como dados, alternativas, divergencias, overrides, derivacoes com cadeia) | Aprovado | leitura do ADR |
| F5.1 | `mappings/source_priority.csv`: regras por (locale, grupo, nutriente) com wildcards; resolucao por especificidade; fonte desconhecida/locale sem regra = falha alta | 8 regras reais (pt/pt-PT/pt-BR: insa>ciqual; fr/en/es/de/it: ciqual>insa) | `pytest tests/unit/test_merge.py` |
| F5.2 | `nutridb merge`: `mv_food_value.parquet` por (concept, nutrient, locale, basis); preferred por prioridade (tie-break measured>trace>below_loq, source_record_id); alternatives JSON; divergence_flag/divergence_max (rel >= 0.30, measured vs measured, 0/0=0); sem medias | Real: 391 101 linhas, 4 542 flags | `uv run nutridb merge` |
| F5.3 | `mappings/overrides.csv` + gate: sem justificacao ou ref desconhecido = falha alta; override = declarado, registado no mv | Header; 0 overrides reais | `pytest tests/unit/test_merge.py` |
| F5.4 | `nutridb derive`: confeccao (retencao x rendimento), por volume (densidade), validacao de porcoes; `derivation` com formula/inputs/factors; `calculated` + acquisition calculated + derivation_id; sem fatores = falha alta; receitas/base seca adiadas | Maquinaria + testes sinteticos; real: 0 derivacoes (reportado) | `uv run nutridb derive` |
| F5.5 | Tabelas de fatores: `derivations/{retention_factors,yield_factors,densities,portions}.csv` headers + README (dados aguardam fonte publicada verificada, regra 17.6) | 4 ficheiros + README | leitura |
| F5.6 | Package schema 3: mv_food_value com basis/alternatives/divergence_flag/divergence_max/derivation_id; tabelas portion, density, derivation; user_version 3 | SQLite real com schema 3 (integrity ok) | `uv run nutridb package` |
| F5.7 | Testes: prioridades (wildcards/especificidade/falha alta), merge (tie-break, alternatives, divergencias 0/0, overrides gate), derive (formula registada, sem fatores falha), package schema 3, golden reais (preferred por locale, flags) | Suite verde (155); lint/mypy limpos (37 ficheiros) | `uv run pytest`; `uv run ruff check .`; `uv run mypy .` |
| F5.8 | Fecho: CI `f5/**`, PLAN/PROGRESS, commits atomicos `(f5)`, merge `--no-ff` em `f0/fundacoes`, push, CI verde | ✅ 2026-08-19 — P10 real (build completo com merge+derive: 236 380 160 B, integrity ok); merge `4af00b7` | `gh run watch` |

**Entregaveis da fase**: ADR-0007; source_priority.csv; CLI `merge` + `derive`; mv_food_value schema 3 (alternatives/divergencias/basis); overrides.csv com gate; derivations/ com headers; testes + golden F5.

---

## Emenda A8 — Performance de producao e escavabilidade (branch `f5b/perf-busca`)

**Objetivo**: otimizar o build (36,7 s → 18,4 s) e a escavabilidade do artefacto (trigramas, pesquisa de nutrientes, facetas, explorer com IndexedDB). Decisoes em ADR-0008 (2026-08-19).

| # | Tarefa | Estado | Nota |
|---|---|---|---|
| A8.1 | Investigar ULID (perfil pyinstrument) | ✅ | Loop original e o mais rapido na pratica (1,67 s vs 1,83 s por 600k na formula translates byte-identica — o profiler inflava 3x); **sem alteracao ao modulo**; regressao via golden |
| A8.2 | Teste golden ULIDs (P4) | ✅ | `tests/unit/test_identity.py::test_ulid_golden_values` (3 ULIDs reais do artefacto: `ciqual:food:24999`, ananas 13002, courgette 20021) |
| A8.3 | Remover VACUUM do package | ✅ | Build real 36,7 s → 18,7 s (ANALYZE fica; VACUUM era no-op de ~9 s em ficheiro novo) |
| A8.4 | Cache content-addressed por estagio | ✅ | `src/nutridb/cache.py` (fingerprint sha256 dos inputs, hit → copia, fail-high); `build --full` ignora; cached 18,4 s; artefacto byte-identico full vs cached (P5 verificado) |
| A8.5 | Schema 4: FTS trigram por locale | ✅ | `label_fts_<locale>_tri` (tokenize='trigram', content='label'); termos >= 3 chars → trigram (substring), senao prefixo; user_version 4 |
| A8.6 | API: kind, food_group, foods_for_nutrient | ✅ | `search(..., kind, food_group)`; `foods_for_nutrient` ordena por valor (mv, per 100 g); real: "polpa" → Ananas/Curgete; "vitamina c" pt-PT → VITC |
| A8.7 | Explorer: IndexedDB + nutrientes + facetas | ✅ | Artefacto persistido em IDB (chave `<artefacto>@v<schema>`); modo nutrientes (pesquisa + ranking); chips de grupo; espelho das queries da API |
| A8.8 | ADR-0008 | ✅ | Aprovado (contexto, opcoes com evidencia, decisao, consequencias) |
| A8.9 | Testes e fecho | ✅ | 176 testes verdes; ruff/mypy limpos; `npm run build` verde; dev server verificado (pagina/artefacto/wasm 200) |

**Entregaveis da emenda**: ADR-0008; cache.py; CLI `build --full`; schema 4 (trigramas); API alargada; explorer F2/A8; 176 testes.

---

## Fase 6 — Qualidade (branch `f6/qualidade`)

**Objetivo**: suite de qualidade do SPEC §11 (checks com severidades, relatório HTML + métricas), 200 alimentos dourados, propriedades de conjuntos (Hypothesis), job CI com upload do relatório. Decisões em ADR-0009 (2026-08-19).

**Critérios de aceitação da spec (§16 F6)**:
1. Suite executa com o artefacto real — ✅ 0 erros / warnings de revisão (proximados 222, energia 33, AG 44, açúcares 2, sal 937, RAE 2, z-score 1893)
2. 200 alimentos verificados à mão passam — [ ] (golden automatizado pronto; revisão humana pendente)
3. Propriedades: conversões reversíveis, fusão idempotente, ordem de fontes não altera resultado — ✅ (roundtrip, divergência simétrica/limitada, ordem invariante, merge byte-idêntico em re-run)

| # | Tarefa | Estado | Nota |
|---|---|---|---|
| F6.0 | ADR-0009 (severidades por origem da incoerência, energia Atwater UE 1169/2011 com POLYL opcional, piso absoluto 5 kcal, divergência em pares não ordenados) | ✅ | Aprovado 2026-08-19 |
| F6.1 | Suite `src/nutridb/quality/` (20 checks, SPEC §11) | ✅ | `proximates_sum`/`energy_recalc`/`fatty_acids_le_fat`/`sugars_individual_le_total`/`sugars_total_le_carbs`/`amino_acids_vs_protein`/`salt_vs_sodium`/`vita_rae_consistent`/`no_negative_values`/`unit_domain_g`/`unit_domain_vocab`/`zscore_group`/`cross_source_divergence`/`integrity_check`/`fk_orphans`/`label_nutrient_refs`/`derivation_chain`/`no_mt_unreviewed`/`unmapped_empty`; coerência **por (conceito, fonte)** com normalização mg/ug→g (mv mistura fontes por nutriente, ADR-0001) |
| F6.2 | CLI `nutridb qa` + relatório | ✅ | Tabela rich + `build/qa/report.html` + `metrics.json` (schema `qa-1`); exit 1 com erros; stdout UTF-8 (reconfigure guardado por isinstance) |
| F6.3 | Testes unitários da suite (22) | ✅ | Violações sintéticas por check; inclui per-source (não dispara com mistura), mg→g (FATRN 16500 mg, NA 200 mg), POLYL opcional, z-score n≥10, órfãos FK, mt_unreviewed; ruff/mypy limpos |
| F6.4 | Triagem dos dados reais | ✅ | 3702 proximados completos (mediana 99,99; 222 fora de [97,103] — Isolat de soja 107,64 CIQUAL, Farine de seigle T85 110,80 INSA); energia: fibra entra (p95 3,14% vs 18,35% sem fibra), 1485 sem método (P2, não verificados); sal: mediana rácio 1,00 exato (Sel blanc NACL 97,8 g / NA 39 100 mg), 937 fora de ±10% (vinhos); AG 44; açúcares 2; RAE 2; z-score 1893; AA 0 completos (nenhuma fonte mapeia AA — honesto); divergência entre fontes 1200 pares ≥30% |
| F6.5 | Golden 200 alimentos (estratificado ~18/grupo, células ENERC_KCAL/PROCNT/FAT/CHOAVL/WATER, skip de ausentes, tolerância 1e-9) | ✅ script efémero + `tests/golden/ciqual_200.csv` + `test_golden_200.py`; revisão humana do critério 2 pendente | `pytest tests/golden/` |
| F6.6 | Property tests (Hypothesis): shuffle invariante (merge/transform), roundtrip de conversão, propriedades da divergência | ✅ `tests/property/` (roundtrip, divergência simétrica/limitada, ordem de fontes invariante) + merge idempotente (re-run byte-idêntico, `test_merge.py`) | `pytest tests/property/ tests/unit/test_merge.py` |
| F6.7 | CI: trigger `f6/**` + job `qa` (pipeline de fixtures → suite → upload-artifact do relatório) | ✅ `.github/workflows/ci.yml` (jobs checks/explorer/qa/determinism; qa sobe relatório + metadados de release) | `gh run watch` |
| F6.8 | Fecho: PLAN/PROGRESS, commits atómicos `(f6)`, merge `--no-ff` em `f0/fundacoes`, push, CI verde | ✅ 2026-08-20 — merge `--no-ff`; CI verde; pendências humanas (adjudicação, golden à mão) documentadas como pós-F6 | `gh run watch` |
| F6.9 | Adjudicação com ferramenta: `link review` (listagem com contexto + apply determinístico) | ✅ 2026-08-20 — `matching.py` (`LinkError`, `_queue_index` com produto cartesiano por survivor, `apply_link_decisions` com regra de linhas partilhadas), `cli.py` grupo `link` + `review --apply`; 6 237 pares reais listados; fix de colapso de pares partilhados | `uv run nutridb link review --limit 5` |

**Entregáveis da fase**: ADR-0009; `src/nutridb/quality/`; CLI `qa` + relatório HTML/métricas; 22 testes; golden 200; property tests; job CI com artefacto do relatório.

---

## Fase 7 — Release verificável (branch `f6/qualidade`, pós-F6)

**Objetivo**: consumidor externo valida composição legal, origem e autenticidade do artefacto sem abrir código (P2). Decisão em ADR-0015 (2026-08-20).

| # | Tarefa | Estado | Nota |
|---|---|---|---|
| F7.0 | ADR-0015 (SBOM + atestação + assinatura; `cryptography` como dependência) | ✅ | Aprovado 2026-08-20 |
| F7.1 | SBOM CycloneDX 1.6 determinístico (`<artefacto>.sbom.json`; UUID5 do hash; sem timestamp; componente por fonte com licenças SPDX/`UNKNOWN` e hashes dos dumps) | ✅ | `src/nutridb/sbom.py`; byte-idêntico em 2 builds (teste) |
| F7.2 | Atestação `attestation-1` (`<artefacto>.attestation.json`): subject, digests internos, bloco temporal (commit/branch git, uv, host, CI, timestamp), `signature: null` ou Ed25519 | ✅ | `write_attestation`; fail-high com chave inválida; SHA256SUMS cobre só os ficheiros determinísticos |
| F7.3 | `nutridb release verify <artefacto>` — hashes vs manifesto/SBOM/checksums/digests; assinatura com `--public-key` ou `NUTRIDB_PUBLIC_KEY`; assinada sem chave → `unverified` | ✅ | e2e real: `signature: verified` |
| F7.4 | CI: upload de sbom/atestado; determinism gate compara manifesto+SBOM+checksums | ✅ | `.github/workflows/ci.yml`; `scripts/check_determinism.py` |
| F7.5 | Testes | ✅ | 15 novos (sbom determinístico, atestação assinada/verificada, fail-high, tamper, signing unit) |

**Entregáveis**: ADR-0015; sbom.py; signing.py; atestação no release.py; CLI `release verify`; testes; gate de determinismo alargado; `cryptography` no lock.
