const LIGATURES: Record<string, string> = {
  "œ": "oe",
  "Œ": "OE",
  "æ": "ae",
  "Æ": "AE",
  "ß": "ss",
};

export function normalizeLabel(text: string): string {
  let out = "";
  for (const char of text) out += LIGATURES[char] ?? char;
  return out
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function escapeFtsTerm(term: string): string {
  return term.replace(/["*]/g, "");
}

export function buildMatch(query: string): string | null {
  const terms = normalizeLabel(query).split(/\s+/).filter(Boolean);
  if (terms.length === 0) return null;
  return terms.map((term) => `"${escapeFtsTerm(term)}"*`).join(" AND ");
}