# ADR-0003 — Fonte CIQUAL 2025: formato, licença e volume

- **Estado**: Aprovado
- **Data**: 2026-08-15 (proposta F1.0; aprovação humana em revisão de PR)
- **Fase**: F1.0 (`f1/ciqual-ponta-a-ponta`)

---

## 1. Contexto

A Fase 1 precisa da primeira fonte ponta a ponta. A decisão A6 (ADR-0001 §7) fixara
"XLS via engine como primário; XML como fallback" para a CIQUAL, mas o XLS da
CIQUAL **não contém as fontes** — a proveniência ao nível do valor (P1/D4) e o
registo do método de energia (A8/A9) só existem no formato XML. A6 é emendada
neste ADR, como a evidência exige (regra de trabalho SPEC §4: "Verifica sempre a
licença na fonte oficial — não confies em memória").

## 2. Verificação na fonte oficial

| Campo | Valor verificado |
|---|---|
| Publicação | Anses — observatório dos Alimentos (Ciqual). "Table de composition nutritionnelle des aliments Ciqual 2025", publicado em 2025-11-19, DOI `10.57745/RDMHWY` (Recherche Data Gouv, Dataverse). Autores: L. Du Chaffaut, M. Oseredczuk, J. Gauvreau-Béziat |
| Página | `https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi:10.57745/RDMHWY` (consultado e arquivado nesta revisão) |
| Licença | **etalab-2.0** (Licence Ouverte v2.0) — confirmada na página oficial do dataset: "License/Data Use Agreement: etalab 2.0 (spdx.org/licenses/etalab-2.0.html), compatible CC-BY 2.0". O PDF de documentação oficial (p. 4) explicita as condições: reprodução obrigatoriamente com citação `"Anses. 2025. Table de composition nutritionnelle des aliments Ciqual"` (ou com DOI), sem alteração nem desvirtuação do sentido |
| Atribuição | Obrigatória (`attribution_required = true`); citação curta e longa registadas no registry |
| Share-alike | Não |
| Comercial | Permitido |
| Volume | ZIP total 78,3 MB; **8 ficheiros** (5 XML de dados + 1 PDF de documentação + XLS + XLSX) |
| Integridade | Todos os 8 ficheiros descarregados batem com os **MD5 publicados** na página oficial (cross-check `Get-FileHash` local vs. valores do Dataverse) e com o **SHA-256** calculado localmente, que passa a estar fixado no registry |

## 3. Opções consideradas

1. **XLS/XLSX como formato primário (A6 original)** — formato legado, 74 colunas +
   código INFOODS + nota de rodapé, mas **sem `source_code`**: a documentação
   oficial (p. 6, §3.1.1) diz explicitamente que as fontes "ne figurent pas dans
   les données téléchargeables au format Excel. Pour consulter ces sources, il
   faut utiliser le format XML ou consulter les fiches nutritionnelles en ligne".
   Sem fontes por valor, P1/D4 não se cumpre: rejeitado como primário.
2. **Conjunto XML como formato primário** — cada par (alimento, constituinte)
   carrega `teneur`, `min`, `max`, `code_confiance` e `source_code`; unidades
   declaradas no nome do constituinte; códigos INFOODS oficiais na fonte; ficheiro
   `sources.xml` com 1 978 citações bibliográficas. **Escolhido.**
3. **PDF de documentação** — não alimenta o pipeline; descarregado e pinado como
   evidência de licença e semântica (p. 4, 6, 9, 16, 21).

## 4. Decisão

1. **Formato primário da CIQUAL 2025 = conjunto XML** (5 ficheiros): `alim`,
   `alim_grp`, `compo`, `const`, `sources`. A6 fica emendada (ver §7 do ADR-0001).
2. Os 8 ficheiros oficiais (5 XML + PDF doc + XLS + XLSX) ficam **fixados com
   SHA-256 no `sources/registry.toml`** (novo modelo `files` do registry —
   decisão de esquema deste ADR); o XLS/XLSX ficam no cache como evidência
   oficial, fora do pipeline do extractor.
3. **Artefacto de destino: `core`** (etalab-2.0 permissiva, sem share-alike,
   uso comercial permitido). Citação obrigatória gerada automaticamente
   (SPEC §14).

### 4.1 Semântica herdada da fonte (para o extractor e mapeamentos)

- Decimal **vírgula** francesa (`59,7`); valores `0` legítimos existem
  (ex.: constituinte presente mas nulo) — nunca confundir com ausência.
- Células especiais de `teneur` (doc §3.2.2/§3.2.3; nada fora disso foi
  observado no XML 2025): `-` = **valor não conhecido** (nunca zero);
  `traces` = detetado mas não quantificável; `<N` = valor abaixo do limiar
  `N` (permitido pelo schema da fonte, sem ocorrências no XML 2025;
  regra de parse prevista por precaução).
- `min`/`max` = extremos observados nas fontes usadas para a média; **só
  presentes quando numéricos** (31 357 de 257 816 pares); a fonte avisa que
  podem refletir outras fontes que não a citada.
- `code_confiance`: **A** (dados de amostragem Ciqual/Oqali representativos),
  **B** (B ou C consoante avaliação interna ≥ 40), **C** (avaliação < 40),
  **D** (fontes > 10 anos). A classificação é da fonte; preserva-se em bruto.
- Energia em 4 códigos: **327/328** (Reg. UE 1169/2011, kJ/kcal) e
  **332/333** (N × fator de Jones, com fibras, kJ/kcal) — todos INFOODS
  `ENERC` na fonte; o mapeamento distingue-os por código e regista o método.
- Proteínas: **25000** (N × fator de Jones — fator por alimento em
  `alim.facteur_Jones`) e **25003** (N × 6,25).
- `alim`: nome fr/en, nome científico (só aquáticos/frutas/legumes),
  classificação de 3 níveis com `alim_grp`, `facteur_Jones` por alimento.
- `sources`: 1 978 citações numeradas; a citação 1 está vazia (usada em
  pares sem fonte identificada) — registar e não inventar.

### 4.2 Volume verificado (2025-11-03)

| Métrica | Valor |
|---|---|
| Alimentos | 3 484 |
| Constituintes | 74 (todos com `code_INFOODS` na fonte) |
| Pares (alim × const) | 257 816 (= 3 484 × 74, matriz completa) |
| `-` (não medido) | 83 246 |
| `traces` | 2 514 |
| `<N` | 0 (em `teneur`; permitido pelo schema) |
| Pares com `min`/`max` numéricos | 31 357 |
| Confiança A / B / C / D | 76 984 / 20 228 / 21 448 / 55 910 |
| Fontes citadas | 1 978 |

## 5. Consequências

- O extractor F1.2 lê os 5 XML (streaming para `compo`, 69 MB — ~2,3 M linhas);
  o intermediário canónico preserva células cruas, fontes, confiança e min/max.
- `mappings/nutrients/ciqual.csv` mapeia `const_code` → tagname canónico do
  vocabulário (INFOODS da fonte ≠ tagnames canónicos do SPEC §5 em pontos
  conhecidos: `RAE` → `VITA_RAE`, `CLD` → `CL`, hífen INFOODS EuroFIR
  `FIB-`/`VITD-`/`VITE-`/`VITB6-`/`CHOL-` → canónicos sem hífen;
  `ENERC` × 4 → `ENERC_KJ`/`ENERC_KCAL` com método; `PROCNT` × 2 → método
  Jones × 6,25).
- Registry alargado com `files` (name + sha256 + url por ficheiro); fontes de
  ficheiro único continuam suportadas pelos campos legados `sha256`/`filename`.
- A nota registada no ADR-0001 §7 passa a apontar o extractor para XML.

## 6. Critério de aceitação

1. `sources/registry.toml` fixa os 8 SHA-256 e coincide com este ADR.
2. `uv run nutridb sources sync` re-descarrega do zero e valida os 8 (P5).
3. `uv run nutridb sources audit` reporta etalab-2.0 sem restrições de core.
4. Leitura humana deste ADR confirma a semântica §4.1 e o volume §4.2.

---

## 7. Registo de aprovação (2026-08-15)

Aprovação humana (revisão de fase F1.0):

| Item | Decisão |
|---|---|
| Formato primário | JSON **XML** (emenda à A6 do ADR-0001 §7) — proveniência por valor só existe no XML |
| Semântica §4.1 | Confirmada: `-` → `not_measured`, `traces` → `trace`, `<N` → `below_loq` (sem ocorrências em 2025), confiança A–D preservada em bruto, decimal vírgula francesa |
| Volume §4.2 | Confirmado (3 484 × 74; matriz completa; 83 246 ausentes; 2 514 traces; 1 978 fontes) |
| Artefacto | `core` (etalab-2.0 permissiva, sem restrições) |
| Registry | 8 ficheiros fixados por SHA-256; XLS/XLSX fora do pipeline (evidência) |