import { buildMatch } from "./fts";
import { query } from "./db";

export interface SearchResult {
  refKind: string;
  ref: string;
  locale: string;
  status: string;
  text: string;
  score: number;
}

export interface FoodValue {
  conceptId: string;
  label: string;
  locale: string;
  foodGroup: string;
  nutrientId: string;
  value: number | null;
  unit: string;
  valueType: string;
  confidenceCode: string | null;
  sourceId: string;
  sourceRecordId: string;
  belowLoqThreshold: number | null;
  basis: string;
  nutrientNameEn: string;
}

export interface Provenance {
  sourceName: string;
  sourceVersion: string;
  licenseId: string;
  licenseUrl: string;
  sourceUrl: string;
  attribution: string | null;
  record: string;
}

const LOCALE_CHAINS: Record<string, string[]> = {
  fr: [],
  en: [],
  "pt-PT": ["pt", "en"],
  "pt-BR": ["pt-PT", "pt", "en"],
};

export const ACTIVE_LOCALES = Object.keys(LOCALE_CHAINS);

// mv_food_value holds one row per (concept, nutrient, locale); labels are
// native per source (INSA=pt, CIQUAL=fr/en). Display falls back through the
// locales that exist in the mv: exact match first, then a stable order.
const VALUE_LOCALE_FALLBACK: Record<string, string[]> = {
  fr: ["en", "pt"],
  en: ["fr", "pt"],
  pt: ["en", "fr"],
  "pt-PT": ["pt", "en", "fr"],
};

export function search(queryText: string, locale: string, limit: number): SearchResult[] {
  const match = buildMatch(queryText);
  if (match === null) return [];
  const chain = [locale, ...(LOCALE_CHAINS[locale] ?? [])];
  const collected: SearchResult[] = [];
  for (const candidate of chain) {
    const table = `label_fts_${candidate.replaceAll("-", "_")}`;
    const exists =
      query(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        [table],
      ).length > 0;
    if (!exists) continue;
    const rows = query(
      `SELECT l.ref_kind, l.ref, l.locale, l.status, l.text, f.rank
       FROM ${table} f JOIN label l ON l.rowid = f.rowid
       WHERE ${table} MATCH ? ORDER BY f.rank LIMIT ?`,
      [match, limit],
    );
    for (const row of rows) {
      collected.push({
        refKind: row.values[0]?.toString() ?? "",
        ref: row.values[1]?.toString() ?? "",
        locale: row.values[2]?.toString() ?? "",
        status: row.values[3]?.toString() ?? "",
        text: row.values[4]?.toString() ?? "",
        score: typeof row.values[5] === "number" ? row.values[5] : 0,
      });
    }
    if (collected.length > 0) break;
  }
  return collected.slice(0, limit);
}

export function foodValues(conceptId: string, locale: string): FoodValue[] {
  const chain = [locale, ...(VALUE_LOCALE_FALLBACK[locale] ?? [])];
  const collected: FoodValue[] = [];
  for (const candidate of chain) {
    const rows = query(
      `SELECT v.concept_id, v.label, v.locale, v.food_group, v.nutrient_id,
              v.value, v.unit, v.value_type, v.confidence_code, v.source_id,
              v.source_record_id, v.below_loq_threshold, v.basis, n.name_en
       FROM mv_food_value v JOIN nutrient n ON n.tagname = v.nutrient_id
       WHERE v.concept_id = ? AND v.locale = ? ORDER BY v.nutrient_id`,
      [conceptId, candidate],
    );
    for (const row of rows) {
      collected.push({
        conceptId: row.values[0]?.toString() ?? "",
        label: row.values[1]?.toString() ?? "",
        locale: row.values[2]?.toString() ?? "",
        foodGroup: row.values[3]?.toString() ?? "",
        nutrientId: row.values[4]?.toString() ?? "",
        value: typeof row.values[5] === "number" ? row.values[5] : null,
        unit: row.values[6]?.toString() ?? "",
        valueType: row.values[7]?.toString() ?? "",
        confidenceCode: row.values[8]?.toString() ?? null,
        sourceId: row.values[9]?.toString() ?? "",
        sourceRecordId: row.values[10]?.toString() ?? "",
        belowLoqThreshold: typeof row.values[11] === "number" ? row.values[11] : null,
        basis: row.values[12]?.toString() ?? "",
        nutrientNameEn: row.values[13]?.toString() ?? "",
      });
    }
    if (collected.length > 0) break;
  }
  return collected;
}

export function provenance(sourceId: string, sourceRecordId: string): Provenance {
  const rows = query(
    `SELECT s.name, s.version, s.license_id, s.license_url, s.url, s.attribution,
            r.record
     FROM source s JOIN source_record r ON r.source_id = s.source_id
     WHERE s.source_id = ? AND r.source_record_id = ?`,
    [sourceId, sourceRecordId],
  );
  const row = rows[0];
  if (row === undefined) throw new Error("provenance not found");
  return {
    sourceName: row.values[0]?.toString() ?? "",
    sourceVersion: row.values[1]?.toString() ?? "",
    licenseId: row.values[2]?.toString() ?? "",
    licenseUrl: row.values[3]?.toString() ?? "",
    sourceUrl: row.values[4]?.toString() ?? "",
    attribution: row.values[5]?.toString() ?? null,
    record: row.values[6]?.toString() ?? "",
  };
}

export function buildMetadata(): Record<string, string> {
  const rows = query("SELECT key, value FROM build_metadata");
  const out: Record<string, string> = {};
  for (const row of rows) {
    out[row.values[0]?.toString() ?? ""] = row.values[1]?.toString() ?? "";
  }
  return out;
}