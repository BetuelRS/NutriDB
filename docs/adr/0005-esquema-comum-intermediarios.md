# ADR-0005 — Esquema comum de intermediários e canónico único (F2)

- **Estado**: Aprovado
- **Data**: 2026-08-16
- **Fase**: F2.0 (`f2/multi-fonte`)

---

## 1. Contexto

A Fase 2 carrega N fontes (INSA/TCA primeiro; USDA, CoFID, Frida, Fineli + 3
à frente — SPEC §16). O pipeline da F1 é de fonte única:

- o extractor da CIQUAL escreve intermediários com formas próprias
  (`foods`/`food_groups`/`constituents`/`sources`/`values` com `alim_code`
  inteiro, `const_code` inteiro, campos fr/en);
- o transform tem `_SOURCE_ID = "ciqual"` hard-coded, chaves int, nomes
  fr/en assumidos e `basis` fixo;
- o canónico vive em `build/canonical/ciqual/` e o i18n lê campos fr/en do
  JSON bruto dos registos.

O critério de aceitação da F2 exige: "todas as fontes carregam num **esquema
comum sem casos especiais espalhados pelo código**". Sem esta decisão, cada
fonte nova duplicaria ramos `if source == ...` no transform, i18n e package.

## 2. Opções consideradas

1. **Contrato de intermediários comum** — cada extractor escreve 4 tabelas
   de esquema fixo (`food`, `food_group`, `constituent`, `value`) em
   `build/intermediates/<source_id>/`; o transform itera fontes com zero
   branches por fonte; os mapeamentos (CSV) são os únicos dados por fonte.
   **Escolhida.**
2. **Adaptadores por fonte no transform** — formas de intermediários livres
   e um "adapter" por fonte no código do transform. Rejeitada: os casos
   especiais ficam no código (viola o critério de aceitação) e cada fonte
   nova muda o transform.
3. **Canónico por fonte + merge posterior** — manter `build/canonical/<fonte>/`
   e concatenar na F3. Rejeitada: o canónico é único por definição (SPEC §8);
   os conceitos de fontes distintas são entidades distintas até à adjudicação
   da F3, o que não exige separar diretórios, e os consumidores (i18n,
   package, explorer) ganham uma única leitura desde já.

## 3. Decisão

### 3.1 Contrato de intermediários (todos os extractores escrevem)

`build/intermediates/<source_id>/` com 4 tabelas Parquet:

| Tabela | Colunas | Semântica |
|---|---|---|
| `food` | `food_code` (Utf8), `name` (Utf8), `names` (Utf8 JSON `{locale: texto}`), `group_path` (Utf8 JSON `{"1": código, "2": código, "3": código}` — só níveis presentes), `record` (Utf8 JSON bruto) | um alimento |
| `food_group` | `level` (Utf8 "1"\|"2"\|"3"), `code` (Utf8), `name` (Utf8) | um nível da hierarquia da fonte |
| `constituent` | `nutrient_code` (Utf8, chave normalizada da fonte), `name` (Utf8), `unit` (Utf8, unidade da fonte) | um nutriente/componente |
| `value` | `food_code`, `nutrient_code`, `value` (Float64), `value_kind` (Utf8 `number\|missing\|trace\|below_loq`), `threshold` (Float64, só below_loq), `min_value`, `max_value` (Float64), `confidence_code` (Utf8), `basis` (Utf8 `per_100g_edible\|per_100ml`), `record` (Utf8 JSON célula crua) | uma célula |

- Códigos de alimento e nutriente são **strings nativas da fonte** (a CIQUAL
  mantém os seus numéricos como texto; a TCA usa chaves normalizadas);
- `basis` é por célula porque a TCA exprime bebidas alcoólicas por 100 ml e o
  resto por 100 g (a CIQUAL é sempre `per_100g_edible`);
- `record` preserva a célula crua (P1): na CIQUAL a linha COMPO verbatim; na
  TCA o número exato + unidade + coluna (o XLSX armazena números nativamente —
  a "célula crua" é o float da fonte, documentado no ADR-0004).

### 3.2 Transform multi-fonte

- `transform(build/intermediates, build/canonical, root)` itera
  `build/intermediates/*/` (ordenado); cada diretório exige entrada no
  registry e as 4 tabelas (fail high, P9);
- mapeamentos por fonte: `mappings/nutrients/<source_id>.csv` (chave
  `nutrient_code` **texto**) e `mappings/foodgroups/<source_id>.csv`
  (níveis **"1"\|"2"\|"3"**); os CSV da CIQUAL são migrados mecanicamente
  (revisível em diff, P8);
- canónico único em `build/canonical/`: `value.source_nutrient_code` passa a
  **TEXT**; `source`, `coverage`, `source_record` com `source_id` por linha;
  conceitos por fonte (sem fusão até F3) com `canonical_id("concept",
  <source_id>, "food", <food_code>)`.

### 3.3 Rótulos (i18n + package + explorer)

- O i18n lê `record["names"]` dos registos de alimento (qualquer locale —
  a TCA só tem `pt`, a CIQUAL `fr`+`en`); sem mapeamento de campos no código;
- `mv_food_value` passa a **uma linha por (concept, nutrient, locale)** com
  `label` e `locale` (fallback continua a ser só em runtime — nunca congelado,
  decisão D7); **schema_version 2** e `PRAGMA user_version = 2`;
- FTS por locale presente na tabela `label` (fr/en/pt na F2).

### 3.4 Sem novas dependências

O extractor TCA lê o XLSX com `zipfile` + `xml.etree` (stdlib) — o ficheiro
é um ZIP XML simples; a stack do projeto não muda (sem ADR de dependência).

## 4. Consequências

- Extractores e testes F1 migram para o contrato (renomeações mecânicas);
- `source_nutrient_code` TEXT no canónico e no artefacto (integridade dos
  códigos nativos preservada — a TCA não tem códigos inteiros);
- INSA: energia sem método publicado → `analytical_method` NULL documentado
  (ADR-0004 §5; P2 — nunca inventar um método);
- vocabulário: expansão aditiva `VITA`, `CARTBEQ`, `OLSAC`, `NIATRP`
  (permitida pelo freeze F1.1);
- explorer mostra o rótulo do locale ativo (a TCA aparece em pt com fallback
  en nas cadeias já existentes).

## 5. Critério de aceitação (F2)

1. `uv run nutridb build` carrega CIQUAL **e** INSA num único canónico;
2. nenhum `if source == ...` no transform/i18n/package (grep verifica);
3. golden CIQUAL (61/61) e novo golden INSA passam sobre o mesmo artefacto;
4. `schema_version = 2` e `user_version = 2` no artefacto.