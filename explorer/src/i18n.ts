export type UiLang = "pt" | "en";

const STRINGS = {
  loading: {
    pt: "a carregar o artefacto SQLite (≈241 MB) via WASM…",
    en: "loading the SQLite artifact (≈241 MB) via WASM…",
  },
  readyHeader: {
    pt: "SQLite {version} (WASM) · artefacto de {builtAt} · pesquisa FTS5 acentos-insensível, trigramas e facetas",
    en: "SQLite {version} (WASM) · artifact from {builtAt} · FTS5 accent-insensitive search, trigrams and facets",
  },
  foods: { pt: "alimentos", en: "foods" },
  nutrients: { pt: "nutrientes", en: "nutrients" },
  coverage: { pt: "cobertura", en: "coverage" },
  search: { pt: "pesquisar", en: "search" },
  searchTerm: { pt: "termo de pesquisa", en: "search term" },
  language: { pt: "idioma", en: "language" },
  resultsCount: { pt: "número de resultados", en: "number of results" },
  placeholderFood: {
    pt: "ex.: pomme, lait, água, noix…",
    en: "e.g. pomme, lait, água, noix…",
  },
  placeholderNutrient: {
    pt: "ex.: vitamina c, fibra…",
    en: "e.g. vitamin c, fibre…",
  },
  group: { pt: "grupo:", en: "group:" },
  allGroups: { pt: "todos", en: "all" },
  noResults: { pt: "sem resultados para “{query}”", en: "no results for “{query}”" },
  close: { pt: "fechar", en: "close" },
  noValuesFor: { pt: "sem valores para {id}", en: "no values for {id}" },
  detailSub: {
    pt: "grupo {group} · {n} nutrientes · rótulo em {locale}",
    en: "group {group} · {n} nutrients · label in {locale}",
  },
  nutrient: { pt: "nutriente", en: "nutrient" },
  value: { pt: "valor", en: "value" },
  unit: { pt: "un", en: "unit" },
  type: { pt: "tipo", en: "type" },
  conf: { pt: "conf.", en: "conf." },
  acq: { pt: "aquis.", en: "acq." },
  source: { pt: "fonte", en: "source" },
  provenance: { pt: "proveniência", en: "provenance" },
  divergent: { pt: "divergente", en: "divergent" },
  nutrientsCovered: {
    pt: "{covered}/{total} nutrientes",
    en: "{covered}/{total} nutrients",
  },
  valuesBySource: {
    pt: "valores por fonte ({n}) — comparação entre fontes",
    en: "values by source ({n}) — cross-source comparison",
  },
  foodsByContent: {
    pt: "{id} — alimentos por teor",
    en: "{id} — foods by content",
  },
  byContent: { pt: "alimentos por teor", en: "foods by content" },
  foodsLabel: { pt: "número de alimentos", en: "number of foods" },
  rankSub: {
    pt: "{n} alimentos · por 100 g · {group}",
    en: "{n} foods · per 100 g · {group}",
  },
  allGroupsLower: { pt: "todos os grupos", en: "all groups" },
  food: { pt: "alimento", en: "food" },
  datasetSummary: {
    pt: "dataset: {foods} alimentos · {cells} células medidas",
    en: "dataset: {foods} foods · {cells} measured cells",
  },
  foodsCount: { pt: "{n} alimentos", en: "{n} foods" },
  footer: {
    pt: "Dados: CIQUAL 2025 (etalab-2.0) · INSA/TCA 7.1 (insa-tca-7.1) · artefacto em IndexedDB (sem HTTP-range) · motor F1/F2 (emendas A7/A8)",
    en: "Data: CIQUAL 2025 (etalab-2.0) · INSA/TCA 7.1 (insa-tca-7.1) · artifact in IndexedDB (no HTTP-range) · engine F1/F2 (amendments A7/A8)",
  },
} as const satisfies Record<string, { pt: string; en: string }>;

export function t(
  lang: UiLang,
  key: string,
  params?: Record<string, string | number>,
): string {
  const entry = (STRINGS as Record<string, { pt: string; en: string } | undefined>)[key];
  let text = entry?.[lang] ?? key;
  if (params !== undefined) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

export function numberLocale(lang: UiLang): string {
  return lang === "pt" ? "pt-PT" : "en-US";
}