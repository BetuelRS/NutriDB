# ADR-0001 — Visão geral da arquitetura do NUTRIDB

- **Data**: 2026-08-15
- **Estado**: Aprovado (revisão humana de 2026-08-15; ver §7)
- **Autor**: agente de build
- **Decisões relacionadas**: ADR-0002 (licença do código — Apache-2.0, aprovado), ADR-0003 (licença CIQUAL, Fase 1)

---

## 1. Contexto

O NUTRIDB é **infraestrutura de dados**: uma base de dados de composição alimentar distribuída como artefacto versionado, consumida por outras aplicações, e não uma aplicação de nutrição.

A especificação define três proposições que condicionam todo o desenho:

1. Nenhum valor nutricional é inventado, estimado por IA, ou copiado sem proveniência.
2. A ausência de um valor é um dado de primeira classe, com motivo declarado — nunca um zero silencioso.
3. Uma tradução literal é um bug, não um resultado.

Este ADR fixa a interpretação da arquitetura antes da primeira linha de código. É o documento de referência para todas as decisões subsequentes.

Fatualidade verificada para a Fase 1: a CIQUAL 2020 foi substituída pela **CIQUAL 2025** (3 484 alimentos, 74 constituintes, formatos Excel e XML, publicada em 2025-11-19 no portal de dados de investigação da data.gouv, DOI `10.57745/RDMHWY`, licença **etalab 2.0 / Licence Ouverte**). A fonte oficial para o extractor será confirmada no ADR-0003.

---

## 2. Decisões arquiteturais

### D1 — Pipeline determinístico em etapas, com falha alta

```
sync → extract → vocab check → link → i18n build → merge → derive → qa → package
```

- Cada etapa consome e produz artefactos intermediários (Parquet/duckdb em `build/`), com **cache por hash de conteúdo**.
- O que o pipeline não compreende **faz o build falhar**: `mappings/_unmapped/` é um gate de saída obrigatoriamente vazio, e células não mapeadas vão para fila de revisão — nunca são descartadas.
- **Determinismo (P5)**: ordenação canónica em todas as saídas, sem iteração sobre dicts/hashes de Python, timestamps admitidos apenas no bloco `build_metadata` isolado. A verificação de determinismo (dois builds → byte-idênticos exceto esse bloco) é um teste desde a F1.
- **Reprodutibilidade externa (P10)**: um comando (`uv run nutridb build`) reconstrói o artefacto; `sources/registry.toml` fixa URL, versão e hash de cada fonte.

### D2 — Identidade em três níveis, IDs eternos

- `source_record` — registo tal como existe na fonte, **imutável**, JSON integral preservado, nunca fundido.
- `concept` — entidade canónica com ID próprio estável.
- `link` — associação `concept ↔ source_record` com pontuação, método e estatuto de adjudicação.

- IDs: **ULID com prefixo `nfx_`** (`nfx_01J…`), atribuído uma única vez, nunca derivado de conteúdo mutável.
- Fusões e divisões produzem **tombstones** com sucessor; um ID publicado resolve para sempre (P4).
- Em F1 (uma só fonte) não há fusões: cada concept nasce de um único source_record e o link fica registado com estatuto `automatic`; o mecanismo de adjudicação plena é a F3.

### D3 — Vocabulário canónico congelado (INFOODS)

- `tagnames` INFOODS como identificadores canónicos de ~250 nutrientes (`vocab/nutrients.csv`), imutáveis após congelamento.
- **Uma unidade por nutriente, imutável**; conversões vivem nos mapeamentos (`mappings/nutrients/*.csv` com fator), nunca no extractor.
- Relações de agregação declaradas (`FASAT` = soma de componentes; `NIAEQ`, `VITA_RAE`, `FOLDFE`…), usadas pelo motor de qualidade.
- **Energia em dupla**: `ENERC_KCAL` e `ENERC_KJ` guardados **com o método** (Atwater geral, Atwater específico, declarado pela fonte) — a CIQUAL e o USDA calculam de formas diferentes; sem o método, divergências tornam-se inexplicáveis.
- Congelamento = commit + testes de invariantes; qualquer alteração posterior é mudança de esquema com migração e ADR.

### D4 — Proveniência ao nível do valor

A tabela `value` (núcleo intelectual do desenho) guarda por célula: `concept_id`, `nutrient_id`, valor, unidade, `value_type`, `acquisition_type`, `source_id`, `source_record_id`, `source_nutrient_code`, `n_samples`, `standard_deviation`, `min_value`, `max_value`, `analytical_method`, `confidence_score`, `derivation_id`, `basis`.

Responde à pergunta definidora do projeto: *"porque é que este alimento diz 0,4 mg de ferro?"* — com fonte, registo, método, n e desvio-padrão, não com um encolher de ombros.

### D5 — Ausência tipada (nunca zero silencioso)

- `value_type ∈ {measured, calculated, trace, not_detected, below_loq, not_measured, not_applicable, assumed_zero}`.
- **Materialização por cobertura, não por cross-product**: ausência declarada ao nível `(fonte, nutriente)` (a fonte não mede X de todo → `not_measured` declarado uma vez por cobertura) **mais** células com marcação explícita individual (a CIQUAL usa `-` para ausente, `traces` para vestígios e `<10` para limite/valor máximo — cada um mapeado para o tipo canónico respetivo, `trace` / `below_loq` com o limiar preservado). O produto cartesiano completo (74 × 3 484 ≈ 258 mil linhas irreais) é rejeitado como destruição inversa de informação.
- Zero, quando existir, é um valor real analisado (`measured`), ou `assumed_zero` com justificação.

### D6 — Configuração como dados

- `sources/registry.toml`: fonte de verdade de licenças (URL, licença, versão, obrigações de atribuição, share-alike, restrição comercial, artefacto de destino). É o que alimenta os gates de empacotamento.
- `mappings/*.csv`: mapeamentos de nutrientes, grupos, prioridades por `(locale, grupo, nutriente)`, `overrides.csv` (com justificação obrigatória — o build rejeita override sem ela), `links.csv`, `tombstones.csv`.
- Zero condicionais de fonte no código Python: o comportamento por fonte é dado, não código.
- Nenhuma fusão existe sem registo em `links.csv`; "se a decisão não está no git, não aconteceu".

### D7 — Multilinguismo facetado (o separador do projeto)

- Um nome de alimento é uma estrutura: `termo_base + parte + estado + método_confeção + meio + tratamento + qualificadores`.
- Traduz-se à mão ~600 facetas por locale (não 50 000 nomes); os termos base vêm de Wikidata/AGROVOC; a composição final usa **templates gramaticais por língua**.
- Cada rótulo carrega estatuto (`native|official|curated|mt_reviewed|mt_unreviewed|borrowed`). `mt_unreviewed` nunca entra em `core` nem é exibido sem marcação.
- Fallback chain por locale (`pt-PT → pt → en`), `divergences.csv` com falha de build se um rótulo genérico for usado onde há divergência conhecida; `untranslatable.csv` com glosa + aproximado marcado como não-equivalente.
- Em F1 o âmbito é mínimo: nomes nativos (`fr`, estatuto `native`) + rótulos do vocabulário (`en` base, `pt-PT` mínimo). A composição plena é a F4.

### D8 — Fusão sem média

- Um concept recolhe valores de todas as fontes ligadas; o preferido é escolhido por prioridade; os restantes **ficam consultáveis** como alternativos.
- **Nunca se calcula média entre fontes.**
- Divergência > 30% → sinalizador visível, não resolução silenciosa.

### D9 — Derivações registadas

- Só se deriva quando não há medição direta; qualquer valor `calculated` tem `derivation_id` com fórmula, inputs e fatores.
- Pools: retenção (confeção), rendimento, densidades, porções, base seca, receitas (EuroFIR).
- Não aplicável em F1 — o mecanismo (tabela `derivation` + registo) fica no esquema.

### D10 — Empacotamento por perfil, com gate de licenças

- Três perfis SQLite: `core` (só permissivas), `extended` (share-alike/não-comercial), `lite` (< 25 MB).
- O empacotador **recusa** incluir fonte incompatível com a licença declarada do artefacto — gate automatizado com teste (F7), não boa intenção.
- Saídas: Parquet particionado, JSONL por tabela, RDF/Turtle + JSON-LD alinhados a FoodOn, `SHA256SUMS`, SBOM, atestação de proveniência, atribuições automáticas (`NOTICE`, tabela no SQLite, página web, README).
- CIQUAL (etalab 2.0, permissiva) → `core`.

### D11 — Interfaces

- **Explorer**: web estática (GitHub Pages), SQLite em WASM com pedidos HTTP por intervalo de bytes, fallback para a API REST. React + TS + Vite, TanStack Router/Table, Tailwind, virtualização nas listas longas, acessibilidade AA, teclado integral, URLs partilháveis.
- **API**: FastAPI, OpenAPI 3.1, `/v1`, paginação por cursor, cache agressivo (dados imutáveis por versão). Dump JSON estático por concept para consumo sem servidor.
- 13 vistas obrigatórias (pesquisa, ficha, proveniência, comparação fontes, comparador, nutrientes, cobertura, consolas de tradução e resolução, diffs entre versões, dicionário de dados, atribuições, playground SQL).
- F1: apenas o motor de pesquisa SQLite subjacente (FTS5 + normalização sem acentos); a UI é a F8.

### D12 — Stack

- Python 3.12+ gerido com `uv`; `ruff`; `mypy --strict`; `pydantic v2` (todos os modelos); `duckdb` (transformações); `polars` (processamento em memória); `typer` + `rich` + `structlog`; `pytest` + `hypothesis`.
- Grafo de dependências de build explícito com cache por hash de conteúdo.
- GitHub Actions: lint, testes, build da BD em tag, release com artefactos e checksums, deploy do explorador, publicação PyPI/npm.
- Esquema SQLite: **normalizado como verdade, desnormalizado como conveniência** (vistas materializadas geradas no build, nunca editadas); `page_size` afinado para HTTP por intervalos, índices cobertos, FTS5 externo por locale, `VACUUM`/`ANALYZE` no fim, ficheiro imutável sem WAL. (O desenho fino das tabelas é da minha responsabilidade — a spec delega explicitamente.)

---

## 3. Opções consideradas e rejeitadas

| Opção rejeitada | Motivo |
|---|---|
| Imputação de valores em falta | Viola P2; ausência é declarada, `assumed_zero` só com justificação |
| Média entre fontes | "Uma terceira medição errada com aparência de consenso" |
| Aplanar ausência para `0`/`NULL` | Destruição de informação (P3) |
| IDs derivados do nome/coordenadas | Nomes mudam; IDs devem resolver para sempre |
| Condicionais de fonte no código | Não revisíveis em diff; viola P8 |
| Tradução automática sem estatuto no artefacto | P7; `mt_unreviewed` banido do `core` |
| Open Food Facts no artefacto | ODbL share-alike obrigaria a base derivada a herdar a licença |
| Recolha automática de sites que a proíbem | Proibido pela spec, sem discussão |

---

## 4. Consequências

**Positivas**

- Cada número da base responde a *de onde veio, como foi obtido, com que confiança* — o objetivo nº 1 do projeto (§19).
- Ficheiros de configuração em CSV/TOML tornam o trabalho intelectual (mapeamentos, prioridades, glossários) revisível em diff por qualquer pessoa.
- Determinismo + registry com hashes dá reprodutibilidade externa com um comando.
- Faseamento por camadas (1 fonte → n fontes → identidade → multilinguismo) mantém cada fase verificável.

**Negativas / custos**

- Gate de `_unmapped` vazio e falha-alta tornam o build severo: exige completar mapeamentos antes de ver luz verde.
- O trabalho humano (adjudicação de entidades, traduções, dourados) é parte do caminho crítico; a arquitetura só reduz o seu volume, não o elimina.
- Dependência de fontes externas: formatos (CIQUAL em XLS/XML), disponibilidade de rede e instabilidade de URLs exigem cache com hashes e mirror documentado (cross-check Zenodo para CIQUAL 2020).

**Riscos**

- Licenças ambíguas (TBCA, índices glicémicos) → parar e perguntar (regra §17.6); ADR de licença antes de qualquer extractor (P6).
- Alteração do vocabulário canónico depois de congelado → tratada como migração de esquema com ADR.
- Divergências silenciosas de energia/tipos de ausência entre fontes → mitigadas em D3/D5 desde a F1.

---

## 5. Decisões adiadas (ver lista de ambiguidades em aberto)

O estado destas decisões é acompanhado em `PLAN.md`/`PROGRESS.md`:

- A1: nome do ficheiro da spec e inicialização do repositório (git/remote)
- A2: licença do código — Apache-2.0 vs AGPL-3.0 (ADR-0002)
- A4: versão da CIQUAL a usar (2020 vs 2025)
- A5: âmbito de "pesquisa a funcionar" na F1 (SQLite/FTS5, não UI)
- A8: materialização da ausência por cobertura
- A9: registo do método de energia
- A10: âmbito de i18n na F1
- A13: seleção do conjunto dourado de 20 alimentos
- A15: versionamento de artefactos (proposta: `0.1.0`)
- A18: fonte principal da CIQUAL no registry (entrepot/data.gouv vs Zenodo)

---

## 6. Critério de aceitação deste ADR

Revisão humana que confirme: (1) a interpretação das três proposições (§1), (2) as decisões D1–D12 como desenho de referência, (3) o tratamento das ambiguidades A1–A21 conforme planeado. Após aprovação, o estado passa a **Aprovado** e a Fase 0 arranca.

---

## 7. Registo de aprovação (2026-08-15)

Revisão humana concluída via questionário. Decisões registadas:

| Ref | Decisão | Resolução |
|---|---|---|
| A1 | Repositório | `SPEC.md` (renomear), git init, remote `https://github.com/BetuelRS/NutriDB.git`; workflows CI prontos desde F0 |
| A2 | Licença do código | **Apache-2.0** (ADR-0002) |
| A3 | Língua | Docs em pt-PT; identificadores e mensagens de código em EN |
| A4/A5 | CIQUAL | **Versão 2025**, entra em `core` (etalab 2.0 permissiva); confirmar na fonte no ADR-0003 |
| A6 | Extractor | XLS via engine (pandas/duckdb) como primário; XML como fallback |
| A7 | Pesquisa em F1 | **Emenda ao DELTA-0001**: além do motor FTS5, a F1 inclui uma **página mínima de pesquisa** (bootstrap do `explorer/` com Vite+React+TS, carregamento do SQLite via sql.js/WASM, sem HTTP-range — otimização dessa parte é F8) |
| A8/A9 | Ausência e energia | Materialização por cobertura + flags explícitas; energia com método registado |
| A10/A11 | Vocabulário e i18n | INFOODS como autoridade primária; i18n da F1 mínimo (nomes fr nativos + rótulos en/pt-PT do vocabulário) |
| A13/A14 | Dourados e fixtures | Seleção dos 20 pelo agente, auditada pelo revisor; fixtures sintéticas marcadas e isoladas |
| A12, A15–A19 | Recomendações assumidas | Esquema fino do agente; semver `0.1.0`; IDs `nfx_`; `links.csv` 1:1 automático na F1; `_unmapped` gerado e dirs vazios com README; registry na fonte oficial com fallback documentado; `divergences.csv` só na F4 |