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

export interface Match {
  match: string;
  trigram: boolean;
}

// Emenda A8: terms of >= 3 characters run on the per-locale trigram index
// (substring matching); shorter terms fall back to the prefix index.
export function buildMatch(query: string): Match | null {
  const terms = normalizeLabel(query).split(/\s+/).filter(Boolean);
  if (terms.length === 0) return null;
  const trigram = terms.every((term) => term.length >= 3);
  const suffix = trigram ? "" : "*";
  return {
    match: terms.map((term) => `"${escapeFtsTerm(term)}"${suffix}`).join(" AND "),
    trigram,
  };
}
