"""F3 entity resolution: blocking, signals, adjudication (SPEC §6).

The matcher is deterministic (P5) and reads only pinned inputs: the shared
intermediates (`build/intermediates/<source>/`) and the mapping CSVs (P8).
It proposes links between INSA (pt) foods and CIQUAL (fr/en) foods and
writes them to ``mappings/links.csv`` — the git-tracked adjudication record
(SPEC §6.3: "Se a decisão não está no git, não aconteceu").

Pipeline per SPEC §6:

1. **Blocking** — shared dictionary term (bilingual food_terms.csv) or a
   shared distinctive raw token; name-similarity blocking was dropped
   during F3 tuning (it removed true positives such as "Sardinha" vs
   "Sardine, crue").
2. **Signals** — term overlap (0.55), name similarity (0.25), canonical
   food-group agreement (0.20); the nutrient vector is a veto only
   (SPEC §6.2), never a decision-maker.
3. **Adjudication** — score >= AUTO: status ``automatic``; >= REVIEW:
   status ``review`` (human queue); otherwise no link. 1:1 resolution
   (greedy, deterministic) prevents two records claiming one concept.
4. **Evaluation** — precision/recall against the hand-labelled golden set
   (`tests/golden/identity_pairs.csv`), reported by ``nutridb link``.

Term ratio ``t``: |shared| / min(|a|,|b|) when the shorter name covers most
of the longer one (len ratio >= 0.6), else |shared| / max(|a|,|b|) — the
guard prevents single shared terms in one-token names from auto-linking
(e.g. "Massa para pizza" vs "Pizza").
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

import polars as pl

from nutridb.identity import canonical_id
from nutridb.mappings import load_foodgroup_mapping, load_nutrient_mapping, resolve_food_group

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = [
    "AUTO_THRESHOLD",
    "REVIEW_THRESHOLD",
    "LinkError",
    "LinkProposal",
    "apply_link_decisions",
    "block_candidates",
    "evaluate",
    "load_terms",
    "match_foods",
    "normalize",
    "score_pair",
    "write_links_csv",
]

# Source ids participating in F3 matching (sorted, deterministic).
MATCH_SOURCES = ("ciqual", "insa")

AUTO_THRESHOLD = 0.84
REVIEW_THRESHOLD = 0.50


class LinkError(ValueError):
    """Invalid adjudication input or state (fail high, P9)."""


# Nutrient veto (SPEC §6.2): core vector, veto if >= 2 of these diverge.
CORE_NUTRIENTS = ("ENERC_KCAL", "PROCNT", "FAT", "CHOAVL", "WATER", "FIBTG")
VETO_DIVERGENT = 2
VETO_DIFF_RATIO = 0.65

_SIM_BLOCK = 0.75
_RAW_DF_MAX = 25
_SIM_SIGNAL = 0.25
_TERM_WEIGHT = 0.55
_GROUP_WEIGHT = 0.20

# Descriptor terms never decide alone: raw/cooked states, packaging, cuts of
# meat, milk fat levels. If BOTH sides carry an unshared *distinctive* term
# (not in this set), the pair is demoted out of automatic adjudication.
GENERIC_TERMS = frozenset(
    {
        "raw",
        "boiled",
        "cooked",
        "grilled",
        "fried",
        "roasted",
        "roast",
        "stewed",
        "breaded",
        "fresh",
        "dried",
        "dry",
        "dehydrated",
        "frozen",
        "canned",
        "drained",
        "whole",
        "skin",
        "with_skin",
        "without_skin",
        "lean",
        "fat",
        "semi_skimmed",
        "skimmed",
        "liquid",
        "solid",
        "natural",
        "plain",
        "salted",
        "unsalted",
        "with_salt",
        "sweetened",
        "flavoured",
        "fortified",
        "powder",
        "instant",
        "concentrated",
        "pulp",
        "pieces",
        "grated",
        "squeezed",
        "stuffed",
        "filled",
        "green",
        "white",
        "black",
        "red",
        "sweet",
        "light",
        "reduced",
        "homemade",
        "crystallized",
        "pasteurized",
        "uht",
        "seco",
    }
)

COLOR_TERMS = frozenset({"green", "white", "black", "red", "yellow"})


class TermIndex:
    """Dictionary index: token/phrase -> term per language + explained tokens."""

    __slots__ = ("explained", "langs")

    def __init__(self, langs: dict[str, dict[str, str]], explained: dict[str, set[str]]) -> None:
        self.langs = langs
        self.explained = explained


class LinkProposal:
    """One proposed cross-source link, pre-adjudication."""

    __slots__ = (
        "ciqual_code",
        "cq_name",
        "distinctive_conflict",
        "group",
        "insa_code",
        "numeric_conflict",
        "pt_name",
        "score",
        "sim",
        "single_term_pair",
        "terms",
        "vetoed",
    )

    def __init__(
        self,
        insa_code: str,
        ciqual_code: str,
        pt_name: str,
        cq_name: str,
        terms: float,
        sim: float,
        group: bool,
        score: float,
        vetoed: bool,
        distinctive_conflict: bool,
        numeric_conflict: bool,
        single_term_pair: bool,
    ) -> None:
        self.insa_code = insa_code
        self.ciqual_code = ciqual_code
        self.pt_name = pt_name
        self.cq_name = cq_name
        self.terms = terms
        self.sim = sim
        self.group = group
        self.score = score
        self.vetoed = vetoed
        self.distinctive_conflict = distinctive_conflict
        self.numeric_conflict = numeric_conflict
        self.single_term_pair = single_term_pair


def normalize(text: str) -> str:
    """NFKD casefold, strip diacritics, non-alphanumeric -> space, collapse."""
    folded = unicodedata.normalize("NFKD", text).casefold()
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    words = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return " ".join(words.split())


def _split(text: str) -> list[str]:
    """Normalized tokens: hyphens and spaces both split words."""
    return normalize(text).split()


def load_terms(root: Path) -> TermIndex:
    """Bilingual dictionary ``term <- (pt|fr|en) token|phrase`` (P8).

    A token may map to several terms (e.g. 'gordo' = whole in milk and fat
    in meat); keys are normalized single tokens. Multi-word synonym cells
    (e.g. 'alho-francês', 'chouriço de sangue', 'arc-en-ciel') are phrase
    keys and only match as a unit, so 'alho' never inherits the leek row.
    """
    path = root / "mappings" / "identity" / "food_terms.csv"
    if not path.is_file():
        raise FileNotFoundError(f"dictionary missing: {path}")
    langs = ("pt", "fr", "en")
    index: dict[str, dict[str, str]] = {lang: {} for lang in langs}
    explained: dict[str, set[str]] = {lang: set() for lang in langs}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            term = row["term"].strip()
            if not term or term.startswith("#"):
                continue
            for lang in langs:
                for cell in (row.get(lang, "") or "").split("|"):
                    keys = _split(cell)
                    if not keys:
                        continue
                    explained[lang].update(keys)
                    if len(keys) == 1 and len(keys[0]) >= 2:
                        index[lang][keys[0]] = term
                    elif len(keys) > 1:
                        index[lang][" ".join(keys)] = term
    return TermIndex(index, explained)


def _term_keys(name: str, lang: str, terms: TermIndex) -> frozenset[str]:
    """Term keys of a name: longest match wins at each position.

    Phrases (multi-token keys) take precedence over single tokens so
    'alho-francês' yields leek, not garlic+raw.
    """
    tokens = _split(name)
    index = terms.langs.get(lang, {})
    phrases = sorted((k for k in index if " " in k), key=lambda k: -k.count(" "))
    keys: set[str] = set()
    i = 0
    while i < len(tokens):
        matched = False
        for phrase in phrases:
            k = phrase.count(" ") + 1
            if i + k <= len(tokens) and " ".join(tokens[i : i + k]) == phrase:
                keys.add(index[phrase])
                i += k
                matched = True
                break
        if matched:
            continue
        term = index.get(tokens[i])
        if term is not None:
            keys.add(term)
        i += 1
    return frozenset(keys)


def _name_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def block_candidates(
    insa_foods: pl.DataFrame,
    ciqual_foods: pl.DataFrame,
    terms: TermIndex,
) -> list[tuple[str, str, frozenset[str], frozenset[str], float, float]]:
    """Blocking (SPEC §6.1): candidate (insa_code, ciqual_code) pairs.

    Returns (insa_code, ciqual_code, pt_keys, cq_keys, sim_pt_fr,
    sim_pt_en) per candidate. A pair is a candidate when it shares a
    dictionary term, when the names are similar (>= 0.75), or when it
    shares a distinctive raw token (document frequency <= 25).
    """
    insa_rows: list[tuple[str, frozenset[str], list[str], str]] = []
    raw_df: dict[str, int] = {}
    for row in insa_foods.rows(named=True):
        name = json.loads(row["names"])["pt"]
        keys = _term_keys(name, "pt", terms)
        toks = _split(name)
        insa_rows.append((row["food_code"], keys, toks, name))
        for tok in toks:
            raw_df[tok] = raw_df.get(tok, 0) + 1

    ciqual_rows: dict[str, tuple[frozenset[str], frozenset[str], str, str]] = {}
    for row in ciqual_foods.rows(named=True):
        names = json.loads(row["names"])
        fr_name = names.get("fr", "")
        en_name = names.get("en", "")
        ciqual_rows[row["food_code"]] = (
            _term_keys(fr_name, "fr", terms),
            _term_keys(en_name, "en", terms),
            fr_name,
            en_name,
        )
        for tok in _split(fr_name) + _split(en_name):
            raw_df[tok] = raw_df.get(tok, 0) + 1

    by_term: dict[str, list[str]] = {}
    by_raw: dict[str, list[str]] = {}
    for code, (fr_keys, en_keys, _, _) in ciqual_rows.items():
        for key in (fr_keys | en_keys) - GENERIC_TERMS:
            by_term.setdefault(key, []).append(code)
    # raw tokens per ciqual food
    for code, (_, _, fr_name, en_name) in ciqual_rows.items():
        for tok in set(_split(fr_name) + _split(en_name)):
            if raw_df.get(tok, 0) <= _RAW_DF_MAX:
                by_raw.setdefault(tok, []).append(code)

    candidates: list[tuple[str, str, frozenset[str], frozenset[str], float, float]] = []
    for insa_code, pt_keys, pt_toks, pt_name in insa_rows:
        seen: set[str] = set()
        for key in pt_keys:
            for cq_code in by_term.get(key, ()):
                if cq_code in seen:
                    continue
                seen.add(cq_code)
                fr_keys, en_keys, fr_name, en_name = ciqual_rows[cq_code]
                candidates.append(
                    (
                        insa_code,
                        cq_code,
                        pt_keys,
                        frozenset(fr_keys | en_keys),
                        _name_sim(pt_name, fr_name),
                        _name_sim(pt_name, en_name),
                    )
                )
        for tok in set(pt_toks):
            for cq_code in by_raw.get(tok, ()):
                if cq_code in seen:
                    continue
                seen.add(cq_code)
                fr_keys, en_keys, fr_name, en_name = ciqual_rows[cq_code]
                candidates.append(
                    (
                        insa_code,
                        cq_code,
                        pt_keys,
                        frozenset(fr_keys | en_keys),
                        _name_sim(pt_name, fr_name),
                        _name_sim(pt_name, en_name),
                    )
                )
    return candidates


def score_pair(
    pt_keys: frozenset[str],
    cq_keys: frozenset[str],
    sim: float,
    group: bool,
) -> float:
    """Weighted signal combination (SPEC §6.2).

    Term ratio is Jaccard (shared / union): a one-token name sharing only
    a generic descriptor cannot dominate ("Porco, pé cru" vs "Porc, carré
    cru": 2/4 = 0.5), while full agreements reach 1.0.
    """
    union = pt_keys | cq_keys
    t = len(pt_keys & cq_keys) / len(union) if union else 0.0
    return _TERM_WEIGHT * t + _SIM_SIGNAL * min(sim, 1.0) + _GROUP_WEIGHT * float(group)


_STOP_TOKENS = frozenset(
    (
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "ou",
        "em",
        "para",
        "no",
        "na",
        "ao",
        "aos",
        "as",
        "um",
        "uma",
        "sem",
        "com",
        "o",
        "a",
        "os",
        "du",
        "des",
        "et",
        "en",
        "au",
        "aux",
        "la",
        "le",
        "les",
        "un",
        "une",
        "l",
        "sans",
        "avec",
        "y",
        "d",
        "n",
        "the",
        "of",
        "and",
        "a",
        "an",
        "in",
        "on",
        "for",
        "with",
        "without",
        "to",
        "is",
        "tipo",
        "type",
        "moyen",
        "media",
        "medio",
        "average",
        "pur",
        "puro",
        "pure",
        "pura",
        "simples",
        "standard",
        "tablete",
        "tablette",
        "aliment",
        "emballe",
        "preemballe",
        "embalado",
        "preembalado",
        "rafinee",
        "refinado",
    )
)


def _raw_distinctive(name: str, lang: str, terms: TermIndex) -> set[str]:
    """Raw name tokens not explained by the dictionary nor stop words."""
    explained = terms.explained.get(lang, set())
    tokens = set(normalize(name).split())
    return {t for t in tokens - explained - _STOP_TOKENS if not re.search(r"\d", t)}


def _distinctive_conflict(
    pt_name: str,
    cq_fr_name: str,
    cq_en_name: str,
    pt_keys: frozenset[str],
    cq_keys: frozenset[str],
    terms: TermIndex,
) -> bool:
    """Both sides carry an unshared distinctive signal -> demote.

    Distinctive = dictionary term not present on the other side, or raw
    token (word outside the dictionary and stop words) absent on the other
    side. Symmetric only: "tipo 85" vs "T85" has raw tokens on one side
    only and stays automatic.
    """
    pt_side: set[str] = set((pt_keys - cq_keys) - GENERIC_TERMS)
    pt_side |= _raw_distinctive(pt_name, "pt", terms)
    cq_side: set[str] = set((cq_keys - pt_keys) - (GENERIC_TERMS - COLOR_TERMS))
    cq_side |= _raw_distinctive(cq_fr_name, "fr", terms)
    cq_side |= _raw_distinctive(cq_en_name, "en", terms)
    return bool(pt_side) and bool(cq_side)


def _numeric_conflict(pt_name: str, cq_name: str) -> bool:
    """Both names carry numbers and the numeric sets differ -> demote.

    Catches extraction-type mismatches ("farinha tipo 70" vs "T170") that
    term sets cannot see.
    """
    own = set(re.findall(r"\d+(?:[.,]\d+)?", normalize(pt_name)))
    other = set(re.findall(r"\d+(?:[.,]\d+)?", normalize(cq_name)))
    return bool(own and other and own != other)


def _measured_vectors() -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Measured core-nutrient vectors per food, in canonical units (P1).

    Reads the intermediate value tables and the nutrient mappings; only
    ``measured`` cells (value_kind == 'number') with the per-100g basis.
    """
    from nutridb.paths import paths

    base = paths()
    out: list[dict[str, dict[str, float]]] = []
    for source in MATCH_SOURCES:
        mapping = load_nutrient_mapping(base["root"], source)
        tagname = {row["nutrient_code"]: row["tagname"] for row in mapping}
        factor = {row["nutrient_code"]: float(row["factor"]) for row in mapping}
        values = pl.read_parquet(base["build"] / "intermediates" / source / "value.parquet")
        vec: dict[str, dict[str, float]] = {}
        for r in values.rows(named=True):
            if r["value_kind"] != "number" or r["basis"] != "per_100g_edible":
                continue
            code = r["nutrient_code"]
            if code not in tagname or tagname[code] not in CORE_NUTRIENTS:
                continue
            if r["value"] is None:
                continue
            vec.setdefault(r["food_code"], {})[tagname[code]] = float(r["value"]) * factor[code]
        out.append(vec)
    return out[0], out[1]


def _veto(insa_vec: dict[str, float], ciqual_vec: dict[str, float]) -> bool:
    """Nutrient veto: >= 2 divergent core nutrients (SPEC §6.2)."""
    shared = sorted(set(insa_vec) & set(ciqual_vec))
    if len(shared) < 3:
        return False
    divergent = sum(
        1
        for n in shared
        if abs(insa_vec[n] - ciqual_vec[n]) / max(abs(insa_vec[n]), abs(ciqual_vec[n]))
        > VETO_DIFF_RATIO
    )
    return divergent >= VETO_DIVERGENT


def _resolve_group(foods: pl.DataFrame, source: str, root: Path) -> dict[str, str]:
    mapping = load_foodgroup_mapping(root, source)
    groups: dict[str, str] = {}
    for row in foods.rows(named=True):
        group = resolve_food_group(mapping, json.loads(row["group_path"]))
        groups[row["food_code"]] = group if group is not None else "other"
    return groups


def match_foods(intermediates_dir: Path, root: Path) -> list[LinkProposal]:
    """Run blocking + signals + veto over INSA x CIQUAL; unsorted proposals."""
    insa_foods = pl.read_parquet(intermediates_dir / "insa" / "food.parquet")
    ciqual_foods = pl.read_parquet(intermediates_dir / "ciqual" / "food.parquet")
    insa_names = {r["food_code"]: json.loads(r["names"])["pt"] for r in insa_foods.rows(named=True)}
    ciqual_names_all = {
        r["food_code"]: json.loads(r["names"]) for r in ciqual_foods.rows(named=True)
    }
    ciqual_names = {
        code: names.get("fr", "") or names.get("en", "") for code, names in ciqual_names_all.items()
    }
    insa_values, ciqual_values = _measured_vectors()
    insa_groups = _resolve_group(insa_foods, "insa", root)
    ciqual_groups = _resolve_group(ciqual_foods, "ciqual", root)

    terms = load_terms(root)
    candidates = block_candidates(insa_foods, ciqual_foods, terms)

    proposals: list[LinkProposal] = []
    for insa_code, ciqual_code, pt_keys, cq_keys, sim_fr, sim_en in candidates:
        sim = max(sim_fr, sim_en)
        group = insa_groups[insa_code] == ciqual_groups[ciqual_code]
        score = score_pair(pt_keys, cq_keys, sim, group)
        vetoed = _veto(insa_values.get(insa_code, {}), ciqual_values.get(ciqual_code, {}))
        insa_name = insa_names[insa_code]
        ciqual_name = ciqual_names[ciqual_code]
        shared = pt_keys & cq_keys
        proposals.append(
            LinkProposal(
                insa_code,
                ciqual_code,
                insa_name,
                ciqual_name,
                len(shared),
                sim,
                group,
                score,
                vetoed,
                _distinctive_conflict(
                    insa_name,
                    ciqual_names_all[ciqual_code].get("fr", ""),
                    ciqual_names_all[ciqual_code].get("en", ""),
                    pt_keys,
                    cq_keys,
                    terms,
                ),
                _numeric_conflict(insa_name, ciqual_name),
                len(pt_keys) == 1 and len(cq_keys) == 1 and bool(shared),
            )
        )
    return proposals


def _status(proposal: LinkProposal) -> str | None:
    if proposal.vetoed or proposal.score < REVIEW_THRESHOLD:
        return None
    if proposal.distinctive_conflict or proposal.numeric_conflict:
        return "review"
    if proposal.single_term_pair:
        if proposal.sim >= 0.80:
            return "automatic"
        if (
            proposal.sim >= 0.65
            and not proposal.distinctive_conflict
            and not proposal.numeric_conflict
        ):
            return "automatic"
        return "review"
    return "automatic" if proposal.score >= AUTO_THRESHOLD else "review"


def resolve_one_to_one(proposals: Iterable[LinkProposal]) -> list[LinkProposal]:
    """Greedy deterministic 1:1 resolution (SPEC §6.3).

    Sort by score desc, then similarity desc (prefer the most similar name
    on score ties, e.g. generic "Farinha de centeio" -> T85 rather than
    T170), then (insa_code, ciqual_code) asc; each food claims at most one
    counterpart. Non-winning proposals drop out.
    """
    ordered = sorted(
        proposals,
        key=lambda p: (-p.score, -p.sim, p.insa_code, p.ciqual_code),
    )
    claimed_insa: set[str] = set()
    claimed_ciqual: set[str] = set()
    winners: list[LinkProposal] = []
    for proposal in ordered:
        if (
            proposal.insa_code in claimed_insa
            or proposal.ciqual_code in claimed_ciqual
            or _status(proposal) is None
        ):
            continue
        claimed_insa.add(proposal.insa_code)
        claimed_ciqual.add(proposal.ciqual_code)
        winners.append(proposal)
    return winners


def _survivor(insa_code: str, ciqual_code: str) -> str:
    """Deterministic survivor id: min canonical concept id (ADR-0006)."""
    ids = (
        canonical_id("concept", "insa", "food", insa_code),
        canonical_id("concept", "ciqual", "food", ciqual_code),
    )
    return min(ids)


def write_links_csv(
    proposals: Iterable[LinkProposal], path: Path, preserve: Path | None = None
) -> int:
    """Write adjudicated links to ``mappings/links.csv`` (P8 gate).

    Each automatic 1:1 winner and each review pair writes two rows — one
    per source record, both pointing at the deterministic survivor concept
    (ADR-0006). Rows with status ``automatic`` are merged by the
    transform; ``review`` rows wait for human adjudication; ``None``
    proposals are not written. Rows with status ``adjudicated`` already in
    ``preserve`` (the existing file) are carried over untouched: human
    decisions survive re-runs of the matcher.
    """
    auto = [p for p in proposals if _status(p) == "automatic"]
    rows: list[tuple[str, str, str, str]] = []
    for proposal in resolve_one_to_one(auto):
        survivor = _survivor(proposal.insa_code, proposal.ciqual_code)
        rows.append((survivor, "insa", proposal.insa_code, "automatic"))
        rows.append((survivor, "ciqual", proposal.ciqual_code, "automatic"))
    for proposal in proposals:
        if _status(proposal) != "review":
            continue
        survivor = _survivor(proposal.insa_code, proposal.ciqual_code)
        rows.append((survivor, "insa", proposal.insa_code, "review"))
        rows.append((survivor, "ciqual", proposal.ciqual_code, "review"))
    if preserve is not None and preserve.is_file():
        kept: dict[tuple[str, str, str], str] = {}
        with preserve.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row["status"] or "").strip() != "adjudicated":
                    continue
                key = (row["concept_id"].strip(), row["source"].strip(), row["source_code"].strip())
                kept[key] = "adjudicated"
        rows.extend((*key, status) for key, status in kept.items())
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        writer = csv.writer(fh)
        writer.writerow(("concept_id", "source", "source_code", "status"))
        writer.writerows(rows)
    return len(rows)


def _queue_index(
    links_csv: Path,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str, str], set[tuple[str, str]]]]:
    """Index of pending review rows: pair -> survivor and row -> pairs.

    Each review pair writes two rows sharing the survivor concept
    (ADR-0006). A survivor may host several pairs (one food proposed
    against several counterparts), in which case a row is shared by all
    the pairs of its side at that survivor; the index keeps the full
    cross product so no pair is lost.
    """
    by_survivor: dict[str, dict[str, set[str]]] = {}
    with links_csv.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row["status"] or "").strip() != "review":
                continue
            concept_id = row["concept_id"].strip()
            by_survivor.setdefault(concept_id, {}).setdefault(row["source"].strip(), set()).add(
                row["source_code"].strip()
            )
    pairs: dict[tuple[str, str], str] = {}
    row_pairs: dict[tuple[str, str, str], set[tuple[str, str]]] = {}
    for survivor in sorted(by_survivor):
        insa_codes = sorted(by_survivor[survivor].get("insa", ()))
        ciqual_codes = sorted(by_survivor[survivor].get("ciqual", ()))
        for insa in insa_codes:
            for ciqual in ciqual_codes:
                pair = (insa, ciqual)
                pairs[pair] = survivor
                row_pairs.setdefault((survivor, "insa", insa), set()).add(pair)
                row_pairs.setdefault((survivor, "ciqual", ciqual), set()).add(pair)
    return pairs, row_pairs


def review_pairs(links_csv: Path) -> list[tuple[str, str]]:
    """Pending adjudication pairs from ``mappings/links.csv`` (status review)."""
    pairs, _ = _queue_index(links_csv)
    return sorted(pairs)


def apply_link_decisions(
    links_csv: Path,
    decisions: list[tuple[str, str, str, str]],
) -> dict[str, int]:
    """Apply human decisions to the adjudication record (P8, SPEC §6.3).

    ``decisions`` rows: ``(insa_code, ciqual_code, decision, justification)``
    with decision ``accepted`` | ``rejected``. Every pair must exist in the
    current review queue or the call fails high (P9): the queue is the
    authority and silent edits are never invented. Accepted pairs become
    status ``adjudicated`` (merged by the transform), rejected pairs are
    removed. A row shared by several pairs (one food proposed against
    several counterparts at the same survivor) is only removed once every
    pair using it has been decided. All other rows are preserved verbatim.
    """
    queue, row_pairs = _queue_index(links_csv)
    seen: set[tuple[str, str]] = set()
    accepted: set[tuple[str, str]] = set()
    rejected: set[tuple[str, str]] = set()
    for insa_code, ciqual_code, decision, justification in decisions:
        pair = (insa_code, ciqual_code)
        if pair in seen:
            raise LinkError(f"duplicate decision for pair {pair!r}")
        seen.add(pair)
        if decision not in ("accepted", "rejected"):
            raise LinkError(
                f"pair {pair!r}: unknown decision {decision!r} (expected accepted|rejected)"
            )
        if pair not in queue:
            raise LinkError(f"pair {pair!r} is not in the review queue")
        if decision == "accepted":
            if not justification.strip():
                raise LinkError(f"pair {pair!r}: accepted requires a justification (SPEC §6.3)")
            accepted.add(pair)
        else:
            rejected.add(pair)
    decided = accepted | rejected

    rows: list[tuple[str, str, str, str]] = []
    with links_csv.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            status = (row["status"] or "").strip()
            concept_id = row["concept_id"].strip()
            source = row["source"].strip()
            source_code = row["source_code"].strip()
            if status != "review":
                rows.append((concept_id, source, source_code, status))
                continue
            my_pairs = row_pairs.get((concept_id, source, source_code), set())
            if my_pairs and my_pairs <= decided:
                continue
            rows.append((concept_id, source, source_code, status))
    for insa_code, ciqual_code in accepted:
        survivor = queue[(insa_code, ciqual_code)]
        rows.append((survivor, "insa", insa_code, "adjudicated"))
        rows.append((survivor, "ciqual", ciqual_code, "adjudicated"))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    with links_csv.open("w", encoding="utf-8", newline="\n") as fh:
        writer = csv.writer(fh)
        writer.writerow(("concept_id", "source", "source_code", "status"))
        writer.writerows(rows)
    return {
        "accepted": len(accepted),
        "rejected": len(decisions) - len(accepted),
        "remaining_review": sum(1 for r in rows if r[3] == "review"),
    }


def evaluate(
    proposals: list[LinkProposal],
    golden_path: Path,
) -> dict[str, float | int]:
    """Precision / recall on the hand-labelled golden set (SPEC §6.4).

    Golden rows: ``insa_code,ciqual_code,label`` with label true|false.
    Precision is measured on the automatic 1:1 final links only (SPEC
    F3: >= 0.98). ``recall`` is the matcher coverage: automatic finals plus
    golden-true pairs sitting in the review queue (found but unconfirmed);
    ``recall_confirmed`` counts only automatic finals — what a consumer can
    trust before human adjudication of the review queue. Golden-true pairs
    with no candidate at all are the unreachable misses of the matcher.
    """
    golden_true: set[tuple[str, str]] = set()
    golden_false: set[tuple[str, str]] = set()
    with golden_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pair = (row["insa_code"], row["ciqual_code"])
            if row["label"].strip().lower() == "true":
                golden_true.add(pair)
            else:
                golden_false.add(pair)

    auto_proposals = [p for p in proposals if _status(p) == "automatic"]
    finals = {(p.insa_code, p.ciqual_code) for p in resolve_one_to_one(auto_proposals)}
    review_golden_true = {
        (p.insa_code, p.ciqual_code) for p in proposals if _status(p) == "review"
    } & golden_true
    true_positives = len(finals & golden_true)
    false_positives = len(finals & golden_false)
    false_negatives = len(golden_true - finals - review_golden_true)
    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives)
        else 0.0
    )
    matcher_recall = (
        (true_positives + len(review_golden_true)) / len(golden_true) if golden_true else 0.0
    )
    confirmed_recall = true_positives / len(golden_true) if golden_true else 0.0
    golden_foods = {pair[0] for pair in golden_true}
    covered_foods = {pair[0] for pair in (finals | review_golden_true) & golden_true}
    food_recall = len(covered_foods) / len(golden_foods) if golden_foods else 0.0
    return {
        "golden_true": len(golden_true),
        "golden_false": len(golden_false),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "auto_finals": len(finals),
        "review_golden_true": len(review_golden_true),
        "golden_foods": len(golden_foods),
        "covered_foods": len(covered_foods),
        "precision": precision,
        "recall": matcher_recall,
        "recall_confirmed": confirmed_recall,
        "food_recall": food_recall,
    }
