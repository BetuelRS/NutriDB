# ADR-0009 — Qualidade F6: severidades, energia e limiar de divergência

- **Estado**: Aprovado
- **Data**: 2026-08-19
- **Fase**: F6 (`f6/qualidade`)

---

## 1. Contexto

A F6 implementa a suite de qualidade do SPEC §11. Ao triar os dados reais
(CIQUAL + INSA, mv com 9 775 conceitos), duas questões de desenho
exigiram decisão com evidência:

1. **A que severidade atribuir cada check?** O pipeline reproduz a fonte
   *verbatim* (provado pelos dourados F1/F5: byte-idêntico às células
   oficiais). Muitas incoerências vêm da própria fonte: a CIQUAL publica
   "Isolat de soja" com proximados a 107,64 g/100 g; a INSA publica
   "Farine de seigle T85" a 110,80 g/100 g; vinhos têm sal (NaCl) que
   diverge de Na×2,5 em >10%. Corrigir isso no artefacto violaria P1
   (proveniência verbatim); ignorá-lo esconderia dados que os consumidores
   do artefacto precisam de ver.
2. **Que modelo de energia usar no `energy_recalc`?** O mv mistura fontes
   por nutriente por design (ADR-0001): um conceito pode ter WATER da
   CIQUAL e CHOAVL da INSA — recálculos globais seriam inválidos. E o
   fator da fibra (2 kcal/g vs 0) muda materialmente o resultado.

## 2. Evidência da triagem (dados reais, 2026-08-19)

- **Proximados por fonte**: 3 702 (conceito, fonte) completos; mediana
  99,99 g/100 g; 222 fora de [97, 103]. Agrupado por conceito sem fonte, a
  soma chega a 157,01 ("Jus d'orange": CHOAVL 64,9 da INSA contra os
  restantes da CIQUAL) — a mistura por nutriente (ADR-0001) invalida a
  coerência agregada.
- **Energia**: com fibra ×2 (Atwater UE 1169/2011), n=2 962, p95 do desvio
  3,14%; sem fibra, p95 18,35% — a fibra **entra** no modelo. Vinhos com
  energia declarada ~80 kcal e 10 g de álcool recalcularam a ~70 kcal
  (±5% de piso absoluto 5 kcal); ácidos orgânicos (vinagre) permanecem
  fora — a fonte não publica OACID e o vocabulário não o tem.
- **POLYL**: a CIQUAL mapeia 34000; sem fator, doces com polióis recalculam
  ~2,4 kcal/g acima do declarado. Com o fator, os 80 infratores caem para
  24 (antes do piso absoluto).
- **Sal vs sódio**: 4 259 (conceito, fonte) com ambos; mediana do rácio
  NaCl/(Na×2,5) = 1,00 (exato, ex. "Sel blanc": NACL 97,8 g, NA 39 100 mg);
  937 fora de ±10% — quase todos vinhos CIQUAL.
- **AG**: 44 violações de ΣAG > gordura×1,02 (FATRN em mg normalizado);
  açúcares: 2 individuais > total; aminoácidos: 0 completos (nenhuma fonte
  mapeia AA — o check reporta honestamente 0).

## 3. Opções consideradas

### Severidades

- **A. Tudo `error`** — o build falha com 3 000+ achados legítimos da
  própria fonte; P1 proíbe "corrigi-los" no artefacto. Inviável.
- **B. Tudo `warning`/info** — o gate estrutural (órfãos, unidades,
  traduções, `_unmapped`) perderia a força de bloquear o release.
- **C. Triage por origem da incoerência** — incoerência **da fonte**
  (proximados, energia, AG, açúcares, sal, RAE, z-score intra-grupo,
  divergência entre fontes) → `warning` (fila de revisão, com
  (conceito, nutriente, fonte) como evidência); violação **do nosso
  contrato** (unidades fora do domínio, valores negativos, órfãos FK,
  `mt_unreviewed`, `_unmapped/` não vazio, cadeia de derivação) → `error`.
  **Escolhida.** A severidade documenta a quem pertence a correção: a
  fonte (revisão) ou o pipeline (bloqueio).

### Energia

- **D. Global por conceito** — inválido (mv mistura fontes; provado acima).
- **E. Por (conceito, fonte)** com método registado — só entra no
  artefacto se a célula ENERC tiver `analytical_method` (P1); a fórmula é
  fixa (Atwater UE 1169/2011) e registada. POLYL é opcional (só a CIQUAL
  o mapeia). **Escolhida.** 1 485 (conceito, fonte) sem método não são
  verificados (P2: sem imputação) e o número é reportado no detalhe.
- **F. Piso relativo puro** — perto de zero (0,92 kcal de uma água
  mineral) o desvio relativo é inútil; piso absoluto de 5 kcal.
  **Escolhida** em conjunto com E.

### Divergência entre fontes

- **G. Pares orientados** — cada par aparece 2× (a vs b e b vs a);
  ruído no relatório.
- **H. Pares não ordenados** (source_id < source_id_b), divergência
  relativa ao menor valor, limiar ≥30%, severidade `info` (é um convite
  à revisão, não uma falha). **Escolhida.**

## 4. Decisão

1. **Severidades por origem**: checks de coerência da fonte
   (`proximates_sum`, `energy_recalc`, `fatty_acids_le_fat`,
   `sugars_individual_le_total`, `sugars_total_le_carbs`,
   `amino_acids_vs_protein`, `salt_vs_sodium`, `vita_rae_consistent`,
   `zscore_group`, `cross_source_divergence`) → `warning` (info quando 0
   achados); checks do contrato do pipeline (`no_negative_values`,
   `unit_domain_g`, `unit_domain_vocab`, `integrity_check`, `fk_orphans`,
   `label_nutrient_refs`, `derivation_chain`, `no_mt_unreviewed`,
   `unmapped_empty`) → `error`. Erros → exit 1 da CLI e gate no CI.
2. **Todos os checks de coerência por (concept_id, source_id)**,
   normalizando unidades a g (`mg`/`ug` → g). A evidência de cada achado
   é (conceito, nutriente, fonte, valor) — nada de agregações que o mv
   não suporte.
3. **Energia**: fórmula Atwater UE 1169/2011 (PROCNT 4, FAT 9, CHOAVL 4,
   FIBTG 2, ALC 7, POLYL 2,4), tolerância ±5% com piso absoluto 5 kcal;
   só para células ENERC com método registado `"Reg. UE 1169/2011
   (Atwater)"`; POLYL opcional; sem método → contado no detalhe e não
   verificado (P2).
4. **`cross_source_divergence`**: pares não ordenados, divergência
   relativa ao menor valor, limiar 30%, `info`.
5. **Reporte**: `build/qa/report.html` + `metrics.json` (schema `qa-1`)
   com todas as severidades e exemplos; a CLI `nutridb qa` imprime a
   tabela e falha alto (P9) com qualquer `error`.

## 5. Consequências

- **Resultado real**: 0 erros; warnings: proximados 222, energia 33
  (1 485 sem método), AG 44, açúcares individuais 2, sal 937, RAE 2,
  z-score 1 893; info: divergência 1 200 pares (≥30%), o resto 0.
- **O gate de release** é os `error` (0 hoje) + `_unmapped/` vazio —
  os `warning` entram no relatório e na fila de revisão, não bloqueiam.
- **Falsos positivos conhecidos**: energia em alimentos com ácidos
  orgânicos sem OACID na fonte; sal em vinhos (fonte pública valores que
  não casam com Na×2,5) — documentados como quirks da fonte no relatório.
- **Não feito** (adiado): propriedades de conjuntos (Hypothesis) e dourado
  de 200 alimentos — em curso na F6; revisão humana da fila de warnings
  (F6/F7).

## 6. Referências

- SPEC §11 (checks e tolerâncias), §16 (fila de revisão).
- ADR-0001 (mv, mistura de fontes por nutriente), ADR-0005 (esquema comum).
- Reg. (UE) 1169/2011, Anexo XIV (fatores de conversão de energia).