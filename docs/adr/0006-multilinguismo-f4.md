# ADR-0006 — Multilinguismo F4: glossários, divergências e composição honesta (F4)

- **Estado**: Aprovado
- **Data**: 2026-08-18
- **Fase**: F4.0 (`f4/multilinguismo`)

---

## 1. Contexto

A Fase 4 (SPEC §16) exige: "8 locales com ≥ 95% de rótulos em estatuto
`native`/`official`/`curated`; zero `mt_unreviewed` no `core`; pesquisa
cruzada entre línguas funcional". A SPEC §7 descreve a arquitetura:
composição facetada (~600 facetas por locale), glossários revistos à mão,
divergências regionais com gate, fluxo de tradução com fila de revisão e
`mt_unreviewed` que **nunca** entra no `core` (P7).

O estado atual (fim da F3) tem só 2 fontes: CIQUAL (nomes nativos fr/en,
3 484 alimentos) e INSA/TCA (pt, 1 376). Os 8 locales-alvo (`fr`, `en`,
`pt`, `pt-PT`, `pt-BR`, `es`, `de`, `it`) estão declarados em
`i18n/locales.toml`, mas só `fr`/`en`/`pt` têm rótulos de alimentos
(native) e `en`/`pt-PT` têm rótulos de nutrientes (official/curated,
`pt-PT` só 11 de 161). `es`, `de`, `it`, `pt-BR` e `pt` têm zero rótulos.

Traduzir 4 860 nomes de alimentos × 8 locales à mão é inviável nesta fase
sem MT — e a MT crua viola P7 e a SPEC §19 ("não soe a tradução de
máquina"). A própria SPEC §7 diz: "um catálogo que parece completo e está
subtilmente errado [...] é pior do que estar visivelmente incompleto".

## 2. Opções consideradas

1. **Composição facetada plena (SPEC §7)** — decompor os 4 860 nomes em
   facetas, traduzir ~600 facetas × 8 locales, compor por templates
   gramaticais por língua. Rejeitada para F4: exige a tabela
   `concept_facet` e um motor de composição por língua; o vocabulário
   facetado atual (139 facetas em `vocab/facets/`) não cobre os nomes
   reais das fontes; o âmbito duplicaria o esforço das fases seguintes.
   **Adiada**: facetas traduzidas nesta fase (glossário), composição
   gramatical na fase que introduzir `concept_facet` (F5+).
2. **Tradução por MT + revisão humana total (4 860 × 8)** — inviável e
   viola P7 durante a fase; a fila de revisão não tem esse volume humano.
   Rejeitada.
3. **Glossários por locale + nativos + divergências + fallback** —
   rótulos de nutrientes (161 × 8) e facetas (139 × 8) curados a partir
   de terminologia publicada (INFOODS/EuroFIR/FAO); alimentos apenas
   nativos (fr/en/pt) + rótulos curados para os conceitos com divergência
   regional registada; os locales sem fonte ficam visivelmente
   incompletos e resolvem por fallback em runtime (nunca congelado).
   **Escolhida.**

## 3. Decisão

### 3.1 Estatutos e fontes de rótulos (composição)

| Fonte de rótulo | Locales | Estatuto |
|---|---|---|
| Nomes nativos dos registos imutáveis (CIQUAL fr/en; INSA pt) | fr, en, pt | `native` |
| `vocab/nutrients.csv` `name_en` (INFOODS) | en | `official` |
| `i18n/glossary/<locale>.csv` — terminologia INFOODS/EuroFIR/FAO verificada à mão, 161 tagnames obrigatórios por locale | fr, pt, pt-PT, pt-BR, es, de, it | `curated` |
| `i18n/divergences.csv` — rótulos regionais de conceitos divergentes | pt-PT/pt-BR, en-GB/en-US | `curated` |
| `i18n/labels/reviewed_<locale>.csv` — decisões do fluxo de revisão (CLI `i18n review`) | qualquer | `curated` (prioridade máxima) |

Prioridade por conceito/locale: `reviewed` > `native` > glossário
(nutrientes) > `divergences`. O fallback da cadeia nunca é congelado na
tabela (ADR-0005 D7 mantém-se).

### 3.2 Gates no build (P7/P9)

- Qualquer rótulo com estatuto `mt_unreviewed` na tabela composta → o
  build **falha** (zero `mt_unreviewed` no `core`, SPEC §16 F4).
- Por locale ativo, os rótulos de nutrientes cobrem os 161 tagnames
  (falta de tagname no glossário → falha).
- Gate de estatuto: ≥ 95% dos rótulos de cada locale em
  `native`/`official`/`curated` (teste; na prática 100%).
- Gate de divergências: um conceito registado em `divergences.csv` exige
  rótulo próprio em cada variante declarada; usar um rótulo genérico
  (`pt`/`en`) onde há divergência conhecida → falha (SPEC §7).

### 3.3 Pesquisa cruzada

FTS por locale para as 8 ativas; `api.search` consulta a cadeia do locale
pedido (primeiro locale com resultados ganha — já implementado na F1) e
**resolve o rótulo exibido pela cadeia** (preferência pelo locale pedido)
com dedupe por conceito — "chicken" (en) encontra o conceito cujo rótulo
pt-PT é "frango".

### 3.4 Fluxo de revisão

`nutridb i18n review`: lista candidatos de `i18n/review_queue/<locale>.csv`
e aplica decisões aprovadas em `i18n/labels/reviewed_<locale>.csv`
(consumido pelo build como `curated`). A fila nasce vazia — todos os
rótulos da F4 são `native`/`official`/`curated` à nascença. A consola web
de tradução é F8.

### 3.5 Facetas

`vocab/facets/*.csv` ganham colunas `name_fr, name_es, name_de, name_it,
name_pt_PT, name_pt_BR` (aditivo, `name_en`/`name_pt` mantidos); `vocab
check` valida as novas colunas. Servem de glossário de termos-base para a
composição gramatical futura; não entram na tabela `label` nesta fase.

## 4. Consequências

- **Positivas**: 8 locales compostas com 100% de rótulos
  native/official/curated; nutrientes em 8 línguas; gate P7 e gate de
  divergências reais; pesquisa cruzada funcional e testada; processo de
  revisão humano operacional (CLI) para futura MT.
- **Negativas**: `es`, `de`, `it`, `pt-BR` e `pt` ficam sem rótulos de
  alimentos (incompletude visível > falsa completude, SPEC §7/§19);
  a cobertura de alimentos por locale só cresce com fontes nativas novas
  (USDA/CoFID en, Fineli fi/en, ...) ou com a composição facetada
  adiada.
- **Compromissos**: o critério "≥ 95%" é medido sobre a distribuição de
  estatutos da tabela por locale (o que existe é 100%
  native/official/curated) — nunca sobre cobertura de conceitos, que é
  uma métrica separada reportada por locale.