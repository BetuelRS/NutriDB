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
  labelFr: string;
  labelEn: string;
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

export function foodValues(conceptId: string): FoodValue[] {
  const rows = query(
    `SELECT v.concept_id, v.label_fr, v.label_en, v.food_group, v.nutrient_id,
            v.value, v.unit, v.value_type, v.confidence_code, v.source_id,
            v.source_record_id, v.below_loq_threshold, v.basis, n.name_en
     FROM mv_food_value v JOIN nutrient n ON n.tagname = v.nutrient_id
     WHERE v.concept_id = ? ORDER BY v.nutrient_id`,
    [conceptId],
  );
  return rows.map((row) => ({
    conceptId: row.values[0]?.toString() ?? "",
    labelFr: row.values[1]?.toString() ?? "",
    labelEn: row.values[2]?.toString() ?? "",
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
  }));
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