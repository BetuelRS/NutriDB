# ADR-0007 — Fusão por prioridades e derivações (F5)

- **Estado**: Aprovado
- **Data**: 2026-08-18
- **Fase**: F5.0 (`f5/fusao`)

---

## 1. Contexto

A Fase 5 (SPEC §16) exige: "Prioridades, valores alternativos, retenção,
rendimento, porções, densidades" e aceita quando "prioridades são
puramente dados; toda derivação tem cadeia registada". A SPEC §9 define a
fusão: prioridade por **(locale, grupo alimentar, nutriente)** — não uma
ordem global —, valores não preferidos que **permanecem como alternativas
consultáveis**, proibição de médias entre fontes ("média de duas medições
incompatíveis é uma terceira medição errada com aparência de consenso") e
divergências acima de um limiar (30%) sinalizadas em vez de resolvidas em
silêncio. A SPEC §10: só se calcula um alimento derivado quando não existe
medição direta, e o resultado é sempre `calculated` com a cadeia registada
em `derivation` (fórmula, inputs, fatores).

O estado atual (fim da F4): o artefacto `mv_food_value` dedup por
(concept, nutrient, locale) com tie-break alfabético por `source_id`
(F3.6 — "ciqual" < "insa" → a CIQUAL vence sempre), sem alternativas e sem
sinalização de divergências; 2 fontes (CIQUAL 2025, INSA 7.1), 123
conceitos fundidos na F3; sondagens reais: 4 090 pares (concept, nutrient,
basis) medidos por ambas as fontes, **1 597 com divergência ≥ 30%** (36
nutrientes, 122 conceitos). O valor preferido atual está errado para
alimentos portugueses (a CIQUAL vence por acaso alfabético onde a SPEC
quer o INSA a vencer).

## 2. Opções consideradas

- **A. Prioridade global por fonte** — uma ordem única (ex.: INSA > CIQUAL).
  Simples, mas viola a SPEC §9: "o INSA vence para alimentos portugueses;
  o USDA Foundation vence para minerais" — a nuance é por (locale, grupo,
  nutriente), não global.
- **B. Prioridade por (locale, grupo alimentar, nutriente) como dados**
  (`mappings/source_priority.csv`) com resolução determinística
  (match exato > wildcards). É a SPEC §9 e P8 (configuração como dados).
  Escolhida.
- **C. Média entre fontes** — rejeitada pela SPEC §9 (§2) e P2 (nunca
  fabricar): média de duas medições incompatíveis é uma terceira medição
  errada com aparência de consenso.
- **D. Derivações reais com os dados atuais** — sondagem: a CIQUAL e o INSA
  já medem valores por 100 g e por 100 ml (INSA: 1 461 linhas per_100ml em
  84 bebidas), incluindo energia (INSA mede `energia_kcal`; método não
  registado na fonte, mas o valor é medido). Não existe nenhuma célula
  pedida sem medição direta → **zero derivações reais** (SPEC §10: "só se
  calcula quando não existe medição direta"). A maquinaria (confeção com
  retenção/rendimento, por volume com densidades, porções, base seca)
  é implementada e testada com fixtures sintéticas; as tabelas de fatores
  ficam com headers + README porque não há fonte verificada à mão para
  retenção/rendimento/densidades/porções reais (regra §17.6: não fabricar;
  dados curados exigem a fonte publicada à frente, registada com evidence).

## 3. Decisão

1. **`mappings/source_priority.csv`** — colunas
   `locale, food_group, nutrient, source_order`. Resolução por
   especificidade (mais específico vence): `(l,g,n)` > `(l,g,*)` >
   `(l,*,n)` > `(l,*,*)`; `source_order` = fontes ordenadas `>`.
   Sem regra para um locale ativo → falha alta (P9). Regras reais F5:
   `pt`, `pt-PT`, `pt-BR` → `insa>ciqual` (alimentos portugueses, SPEC §9);
   `fr`, `en`, `es`, `de`, `it` → `ciqual>insa` (cobertura geral).
2. **`nutridb merge`** — nova etapa canónica que escreve
   `build/canonical/mv_food_value.parquet` (substitui o dedup da F3.6 no
   package): uma linha por **(concept, nutrient, locale, basis)** com
   `preferred` escolhido por prioridade (tie-break: `measured` > `trace` >
   `below_loq`; depois `source_record_id` asc), **alternatives** (JSON com
   os valores não preferidos), **divergence_flag** (rel ≥ 30% entre o
   preferido medido e qualquer alternativa medida; rel =
   |a−b|/max(|a|,|b|), 0/0 = 0), **divergence_max**. A `basis` entra na
   chave (mesclar per_100g com per_100ml fabricaria uma mistura, P2).
   Nenhuma média entre fontes. Valores `calculated` só são preferidos
   quando não há medido na célula.
3. **`mappings/overrides.csv`** — `concept_id, nutrient_id, basis, value,
   unit, justification`; o build rejeita override sem justificação
   preenchida (SPEC §9) ou com conceito/nutriente/basis desconhecidos
   (P9). Override = decisão humana declarada (acquisition `declared`),
   registada na linha do mv.
4. **`nutridb derive`** — implementa **confeção** (valor cozido =
   valor cru × retenção × rendimento, fatores em
   `derivations/retention_factors.csv` + `yield_factors.csv`), **por
   volume** (valor_100ml = valor_100g × densidade,
   `derivations/densities.csv`) e valida **porções**
   (`derivations/portions.csv`, medidas caseiras curadas). Toda derivação
   regista `derivation` (derivation_id ULID, formula, inputs, factors) e o
   valor entra com `value_type=calculated`, `acquisition_type=calculated`,
   `derivation_id`. Derivação pedida sem fatores → falha alta. Receitas
   EuroFIR e base seca materializada: adiadas (F5+; base seca é recálculo
   de consulta, F9).
5. **Ordem do build**: extract → transform → **derive** → **merge** →
   i18n → package (o merge vê os valores derivados). Artefacto: schema
   **2 → 3** (mv_food_value + alternatives/divergence_flag/divergence_max/
   derivation_id; tabelas `portion`, `density`, `derivation`).

## 4. Consequências

- O valor preferido do artefacto muda onde a F3.6 escolhia por acaso
  alfabético: para o locale `pt` (e variantes), o INSA passa a vencer nos
  123 conceitos fundidos; `mv_food_value` ganha a dimensão `basis` e 3
  colunas novas; 1 597 divergências ≥ 30% ficam sinalizadas (explorador
  pode exibi-las, F8). Golden e contagens de testes atualizados.
- As alternativas permanecem consultáveis (SPEC §9) — nada é apagado.
- Derivações reais = 0 com as fontes atuais, por design e por honestidade
  (P2); a maquinaria e os gates estão testados sinteticamente; as tabelas
  de fatores aguardam fontes publicadas verificadas (regra §17.6).
- O CLI `merge`/`derive` são re-executáveis e idempotentes; `nutridb build`
  (P10) encadeia tudo na ordem fixada.