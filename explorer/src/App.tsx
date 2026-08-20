import { useCallback, useEffect, useMemo, useState } from "react";
import {
  availableLocales,
  buildMetadata,
  coverageBySource,
  coverageGlobal,
  foodGroups,
  foodValues,
  foodValuesBySource,
  foodsForNutrient,
  provenance,
  search,
  type CoverageGroupRow,
  type CoverageRow,
  type FoodGroup,
  type FoodValue,
  type NutrientRank,
  type Provenance,
  type SearchResult,
  type SourceCoverage,
  type SourceValue,
} from "./search";
import { loadArtifact, sqliteVersion } from "./db";
import { numberLocale, t, type UiLang } from "./i18n";
import "./App.css";

type Status =
  | { kind: "loading" }
  | { kind: "ready"; version: string; builtAt: string }
  | { kind: "error"; message: string };

type Mode = "food" | "nutrient" | "coverage";

type Tr = (key: string, params?: Record<string, string | number>) => string;

function formatValue(value: number | null, lang: UiLang): string {
  if (value === null) return "";
  if (Number.isInteger(value)) return value.toFixed(0);
  return value.toLocaleString(numberLocale(lang), { maximumFractionDigits: 3 });
}

function divergentNutrients(rows: SourceValue[]): Set<string> {
  const perNutrient = new Map<string, number[]>();
  for (const row of rows) {
    if (row.value === null) continue;
    const list = perNutrient.get(row.nutrientId) ?? [];
    list.push(row.value);
    perNutrient.set(row.nutrientId, list);
  }
  const out = new Set<string>();
  for (const [nutrientId, values] of perNutrient) {
    if (values.length < 2) continue;
    const max = Math.max(...values);
    const min = Math.min(...values);
    if (max > 0 && min / max < 0.7) out.add(nutrientId);
  }
  return out;
}

function FoodDetail({
  conceptId,
  locale,
  lang,
  tr,
  onClose,
}: {
  conceptId: string;
  locale: string;
  lang: UiLang;
  tr: Tr;
  onClose: () => void;
}) {
  const values: FoodValue[] = useMemo(() => foodValues(conceptId, locale), [conceptId, locale]);
  const bySource: SourceValue[] = useMemo(() => foodValuesBySource(conceptId), [conceptId]);
  const coverage: SourceCoverage[] = useMemo(() => coverageBySource(conceptId), [conceptId]);
  const divergent = useMemo(() => divergentNutrients(bySource), [bySource]);
  const [openRecord, setOpenRecord] = useState<string | null>(null);
  const first = values[0];
  if (first === undefined) {
    return (
      <aside className="detail">
        <button onClick={onClose}>{tr("close")}</button>
        <p>{tr("noValuesFor", { id: conceptId })}</p>
      </aside>
    );
  }
  return (
    <aside className="detail">
      <div className="detail-head">
        <h2>{first.label}</h2>
        <button onClick={onClose}>{tr("close")}</button>
      </div>
      <p className="detail-sub">
        {tr("detailSub", {
          group: first.foodGroup,
          n: values.length,
          locale: first.locale,
        })}
      </p>
      <table className="values">
        <thead>
          <tr>
            <th>{tr("nutrient")}</th>
            <th>{tr("value")}</th>
            <th>{tr("unit")}</th>
            <th>{tr("type")}</th>
            <th>{tr("conf")}</th>
          </tr>
        </thead>
        <tbody>
          {values.map((v) => (
            <tr key={v.nutrientId}>
              <td>
                <span className="mono">{v.nutrientId}</span> {v.nutrientNameEn}
              </td>
              <td className="num">{formatValue(v.value, lang)}</td>
              <td>{v.unit}</td>
              <td>{v.valueType}</td>
              <td>{v.confidenceCode ?? "—"}</td>
              <td>
                <button
                  className="link"
                  onClick={() => setOpenRecord(openRecord === v.nutrientId ? null : v.nutrientId)}
                >
                  {tr("provenance")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {openRecord !== null &&
        (() => {
          const v = values.find((item) => item.nutrientId === openRecord);
          if (v === undefined) return null;
          const p: Provenance = provenance(v.sourceId, v.sourceRecordId);
          return (
            <details className="provenance" open>
              <summary>
                {p.sourceName} {p.sourceVersion} · {p.licenseId} · {v.basis}
              </summary>
              <pre>{JSON.stringify(JSON.parse(p.record), null, 2)}</pre>
            </details>
          );
        })()}
      {coverage.length > 0 && (
        <div className="chips">
          {coverage.map((c) => (
            <span key={c.sourceId} className="chip">
              {c.sourceName} {c.sourceVersion}:{" "}
              {tr("nutrientsCovered", { covered: c.covered, total: c.total })}
            </span>
          ))}
        </div>
      )}
      {bySource.length > 0 && (
        <details className="provenance">
          <summary>{tr("valuesBySource", { n: bySource.length })}</summary>
          <table className="values">
            <thead>
              <tr>
                <th>{tr("nutrient")}</th>
                <th>{tr("value")}</th>
                <th>{tr("unit")}</th>
                <th>{tr("type")}</th>
                <th>{tr("acq")}</th>
                <th>{tr("conf")}</th>
                <th>{tr("source")}</th>
              </tr>
            </thead>
            <tbody>
              {bySource.map((v) => (
                <tr key={`${v.nutrientId}-${v.sourceId}`}>
                  <td>
                    <span className="mono">{v.nutrientId}</span> {v.nutrientNameEn}
                    {divergent.has(v.nutrientId) && (
                      <span className="chip chip-score">{tr("divergent")}</span>
                    )}
                  </td>
                  <td className="num">{formatValue(v.value, lang)}</td>
                  <td>{v.unit}</td>
                  <td>{v.valueType}</td>
                  <td>{v.acquisitionType ?? "—"}</td>
                  <td>{v.confidenceCode ?? "—"}</td>
                  <td>
                    {v.sourceName} {v.sourceVersion} · {v.licenseId}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </aside>
  );
}

function NutrientDetail({
  nutrientId,
  locale,
  lang,
  tr,
  foodGroup,
  onOpenFood,
  onClose,
}: {
  nutrientId: string;
  locale: string;
  lang: UiLang;
  tr: Tr;
  foodGroup: string | null;
  onOpenFood: (conceptId: string) => void;
  onClose: () => void;
}) {
  const [limit, setLimit] = useState(25);
  const foods: NutrientRank[] = useMemo(
    () => foodsForNutrient(nutrientId, locale, limit, foodGroup),
    [nutrientId, locale, limit, foodGroup],
  );
  return (
    <aside className="detail">
      <div className="detail-head">
        <h2>
          <span className="mono">{nutrientId}</span> — {tr("byContent")}
        </h2>
        <button onClick={onClose}>{tr("close")}</button>
      </div>
      <p className="detail-sub">
        {tr("rankSub", {
          n: foods.length,
          group: foodGroup ?? tr("allGroupsLower"),
        })}
      </p>
      <table className="values">
        <thead>
          <tr>
            <th>{tr("food")}</th>
            <th>{tr("value")}</th>
            <th>{tr("unit")}</th>
            <th>{tr("group")}</th>
          </tr>
        </thead>
        <tbody>
          {foods.map((f) => (
            <tr key={`${f.conceptId}-${f.locale}`}>
              <td>
                <button className="link" onClick={() => onOpenFood(f.conceptId)}>
                  {f.label}
                </button>
              </td>
              <td className="num">{formatValue(f.value, lang)}</td>
              <td>{f.unit}</td>
              <td>{f.foodGroup}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="search">
        <select
          aria-label={tr("foodsLabel")}
          value={limit}
          onChange={(event) => setLimit(Number(event.target.value))}
        >
          {[10, 25, 50, 100].map((n) => (
            <option key={n} value={n}>
              {tr("foodsCount", { n })}
            </option>
          ))}
        </select>
      </div>
    </aside>
  );
}

function CoverageView({ lang, tr }: { lang: UiLang; tr: Tr }) {
  const data = useMemo(() => coverageGlobal(), []);
  return (
    <section className="coverage">
      <p className="muted">
        {tr("datasetSummary", {
          foods: data.summary.foods.toLocaleString(numberLocale(lang)),
          cells: data.summary.cells.toLocaleString(numberLocale(lang)),
        })}
      </p>
      <table className="values">
        <thead>
          <tr>
            <th>{tr("source")}</th>
            <th>{tr("foods")}</th>
            <th>{tr("nutrients")}</th>
          </tr>
        </thead>
        <tbody>
          {data.bySource.map((row: CoverageRow) => (
            <tr key={row.sourceId}>
              <td>
                {row.sourceName} {row.sourceVersion} · {row.sourceId}
              </td>
              <td className="num">{row.foods}</td>
              <td className="num">{row.nutrients}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="values">
        <thead>
          <tr>
            <th>{tr("group")}</th>
            <th>{tr("source")}</th>
            <th>{tr("foods")}</th>
            <th>{tr("nutrients")}</th>
          </tr>
        </thead>
        <tbody>
          {data.byGroup.map((row: CoverageGroupRow) => (
            <tr key={`${row.sourceId}-${row.foodGroup}`}>
              <td>{row.foodGroup}</td>
              <td>{row.sourceId}</td>
              <td className="num">{row.foods}</td>
              <td className="num">{row.nutrients}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const [uiLang, setUiLang] = useState<UiLang>("pt");
  const [queryText, setQueryText] = useState("");
  const [locales, setLocales] = useState<string[]>([]);
  const [locale, setLocale] = useState("pt-PT");
  const [limit, setLimit] = useState(25);
  const [mode, setMode] = useState<Mode>("food");
  const [foodGroup, setFoodGroup] = useState<string | null>(null);
  const [groups, setGroups] = useState<FoodGroup[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [selectedNutrient, setSelectedNutrient] = useState<string | null>(null);
  const [selectedFood, setSelectedFood] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tr = useCallback(
    (key: string, params?: Record<string, string | number>) => t(uiLang, key, params),
    [uiLang],
  );

  useEffect(() => {
    let cancelled = false;
    loadArtifact()
      .then(() => {
        if (cancelled) return;
        const version = sqliteVersion() ?? "?";
        const meta = buildMetadata();
        const found = availableLocales();
        setLocales(found);
        setLocale((current) => (found.includes(current) ? current : found[0] ?? "pt-PT"));
        setGroups(foodGroups());
        setStatus({
          kind: "ready",
          version,
          builtAt: meta.built_at ?? "?",
        });
      })
      .catch((err: unknown) => {
        if (!cancelled) setStatus({ kind: "error", message: String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const runSearch = useCallback(
    (text: string) => {
      setError(null);
      setSelectedFood(null);
      setSelectedNutrient(null);
      try {
        setResults(search(text, locale, limit, mode === "coverage" ? "food" : mode, foodGroup));
      } catch (err) {
        setError(String(err));
        setResults([]);
      }
      setSearched(true);
    },
    [locale, limit, mode, foodGroup],
  );

  const changeMode = useCallback(
    (next: Mode) => {
      setMode(next);
      setSelectedFood(null);
      setSelectedNutrient(null);
    },
    [],
  );

  const changeGroup = useCallback(
    (group: string | null) => {
      setFoodGroup(group);
      setSelectedFood(null);
      setSelectedNutrient(null);
    },
    [],
  );

  if (status.kind === "loading") {
    return (
      <main className="app">
        <h1>NUTRIDB Explorer</h1>
        <p className="muted">{tr("loading")}</p>
      </main>
    );
  }
  if (status.kind === "error") {
    return (
      <main className="app">
        <h1>NUTRIDB Explorer</h1>
        <p className="error">{status.message}</p>
      </main>
    );
  }

  return (
    <main className="app">
      <header>
        <h1>
          NUTRIDB Explorer <span className="tag">F2 · A8</span>
        </h1>
        <select
          className="lang"
          aria-label={tr("language")}
          value={uiLang}
          onChange={(event) => setUiLang(event.target.value as UiLang)}
        >
          <option value="pt">pt</option>
          <option value="en">en</option>
        </select>
        <p className="muted">
          {tr("readyHeader", { version: status.version, builtAt: status.builtAt })}
        </p>
      </header>

      <form
        className="search"
        onSubmit={(event) => {
          event.preventDefault();
          runSearch(queryText);
        }}
      >
        <button
          type="button"
          className={mode === "food" ? "result selected" : "result"}
          onClick={() => changeMode("food")}
        >
          {tr("foods")}
        </button>
        <button
          type="button"
          className={mode === "nutrient" ? "result selected" : "result"}
          onClick={() => changeMode("nutrient")}
        >
          {tr("nutrients")}
        </button>
        <button
          type="button"
          className={mode === "coverage" ? "result selected" : "result"}
          onClick={() => changeMode("coverage")}
        >
          {tr("coverage")}
        </button>
        {mode !== "coverage" && (
          <>
            <input
              aria-label={tr("searchTerm")}
              type="search"
              placeholder={
                mode === "food" ? tr("placeholderFood") : tr("placeholderNutrient")
              }
              value={queryText}
              onChange={(event) => setQueryText(event.target.value)}
            />
            <select
              aria-label={tr("language")}
              value={locale}
              onChange={(event) => setLocale(event.target.value)}
            >
              {locales.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
            <select
              aria-label={tr("resultsCount")}
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            >
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <button type="submit">{tr("search")}</button>
          </>
        )}
      </form>

      {mode === "coverage" ? (
        <CoverageView lang={uiLang} tr={tr} />
      ) : (
        <>
          {groups.length > 0 && (
        <div className="search">
          <span className="muted">{tr("group")}</span>
          <button
            type="button"
            className={`chip ${foodGroup === null ? "chip-score" : ""}`}
            onClick={() => changeGroup(null)}
          >
            {tr("allGroups")}
          </button>
          {groups.map((g) => (
            <button
              key={g.id}
              type="button"
              className={`chip ${foodGroup === g.id ? "chip-score" : ""}`}
              onClick={() => changeGroup(foodGroup === g.id ? null : g.id)}
              title={g.nameEn}
            >
              {g.namePt || g.nameEn}
            </button>
          ))}
        </div>
      )}

      {error !== null && <p className="error">{error}</p>}

      <div className="columns">
        <section className="results">
          {searched && results.length === 0 && (
            <p className="muted">{tr("noResults", { query: queryText })}</p>
          )}
          <ul>
            {results.map((r) => (
              <li key={`${r.refKind}-${r.ref}-${r.locale}`}>
                <button
                  className={`result ${
                    (mode === "nutrient" ? selectedNutrient : selectedFood) === r.ref
                      ? "selected"
                      : ""
                  }`}
                  onClick={() => {
                    if (mode === "nutrient") {
                      setSelectedFood(null);
                      setSelectedNutrient(selectedNutrient === r.ref ? null : r.ref);
                    } else {
                      setSelectedNutrient(null);
                      setSelectedFood(selectedFood === r.ref ? null : r.ref);
                    }
                  }}
                >
                  <span className="result-text">{r.text}</span>
                  <span className="chips">
                    <span className="chip">{r.refKind}</span>
                    <span className="chip">{r.locale}</span>
                    <span className="chip">{r.status}</span>
                    <span className="chip chip-score">{r.score.toFixed(3)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        {selectedFood !== null ? (
          <FoodDetail
            conceptId={selectedFood}
            locale={locale}
            lang={uiLang}
            tr={tr}
            onClose={() => setSelectedFood(null)}
          />
        ) : selectedNutrient !== null ? (
          <NutrientDetail
            nutrientId={selectedNutrient}
            locale={locale}
            lang={uiLang}
            tr={tr}
            foodGroup={foodGroup}
            onOpenFood={(conceptId) => {
              setSelectedNutrient(null);
              setSelectedFood(conceptId);
            }}
            onClose={() => setSelectedNutrient(null)}
          />
        ) : null}
      </div>
        </>
      )}

      <footer className="muted">{tr("footer")}</footer>
    </main>
  );
}