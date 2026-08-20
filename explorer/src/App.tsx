import { useCallback, useEffect, useMemo, useState } from "react";
import {
  availableLocales,
  buildMetadata,
  foodGroups,
  foodsForNutrient,
  foodValues,
  provenance,
  search,
  type FoodGroup,
  type FoodValue,
  type NutrientRank,
  type Provenance,
  type SearchResult,
} from "./search";
import { loadArtifact, sqliteVersion } from "./db";
import "./App.css";

type Status =
  | { kind: "loading" }
  | { kind: "ready"; version: string; builtAt: string }
  | { kind: "error"; message: string };

type Mode = "food" | "nutrient";

function formatValue(value: number | null): string {
  if (value === null) return "";
  if (Number.isInteger(value)) return value.toFixed(0);
  return value.toLocaleString("pt-PT", { maximumFractionDigits: 3 });
}

function FoodDetail({
  conceptId,
  locale,
  onClose,
}: {
  conceptId: string;
  locale: string;
  onClose: () => void;
}) {
  const values: FoodValue[] = useMemo(() => foodValues(conceptId, locale), [conceptId, locale]);
  const [openRecord, setOpenRecord] = useState<string | null>(null);
  const first = values[0];
  if (first === undefined) {
    return (
      <aside className="detail">
        <button onClick={onClose}>fechar</button>
        <p>sem valores para {conceptId}</p>
      </aside>
    );
  }
  return (
    <aside className="detail">
      <div className="detail-head">
        <h2>{first.label}</h2>
        <button onClick={onClose}>fechar</button>
      </div>
      <p className="detail-sub">
        grupo {first.foodGroup} · {values.length} nutrientes · rótulo em {first.locale}
      </p>
      <table className="values">
        <thead>
          <tr>
            <th>nutriente</th>
            <th>valor</th>
            <th>un</th>
            <th>tipo</th>
            <th>conf.</th>
          </tr>
        </thead>
        <tbody>
          {values.map((v) => (
            <tr key={v.nutrientId}>
              <td>
                <span className="mono">{v.nutrientId}</span> {v.nutrientNameEn}
              </td>
              <td className="num">{formatValue(v.value)}</td>
              <td>{v.unit}</td>
              <td>{v.valueType}</td>
              <td>{v.confidenceCode ?? "—"}</td>
              <td>
                <button
                  className="link"
                  onClick={() => setOpenRecord(openRecord === v.nutrientId ? null : v.nutrientId)}
                >
                  proveniência
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
    </aside>
  );
}

function NutrientDetail({
  nutrientId,
  locale,
  foodGroup,
  onOpenFood,
  onClose,
}: {
  nutrientId: string;
  locale: string;
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
          <span className="mono">{nutrientId}</span> — alimentos por teor
        </h2>
        <button onClick={onClose}>fechar</button>
      </div>
      <p className="detail-sub">
        {foods.length} alimentos · por 100 g · {foodGroup ?? "todos os grupos"}
      </p>
      <table className="values">
        <thead>
          <tr>
            <th>alimento</th>
            <th>valor</th>
            <th>un</th>
            <th>grupo</th>
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
              <td className="num">{formatValue(f.value)}</td>
              <td>{f.unit}</td>
              <td>{f.foodGroup}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="search">
        <select
          aria-label="número de alimentos"
          value={limit}
          onChange={(event) => setLimit(Number(event.target.value))}
        >
          {[10, 25, 50, 100].map((n) => (
            <option key={n} value={n}>
              {n} alimentos
            </option>
          ))}
        </select>
      </div>
    </aside>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });
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
        setResults(search(text, locale, limit, mode, foodGroup));
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
        <p className="muted">a carregar o artefacto SQLite (≈241 MB) via WASM…</p>
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
        <p className="muted">
          SQLite {status.version} (WASM) · artefacto de {status.builtAt} · pesquisa FTS5
          acentos-insensível, trigramas e facetas
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
          alimentos
        </button>
        <button
          type="button"
          className={mode === "nutrient" ? "result selected" : "result"}
          onClick={() => changeMode("nutrient")}
        >
          nutrientes
        </button>
        <input
          aria-label="termo de pesquisa"
          type="search"
          placeholder={mode === "food" ? "ex.: pomme, lait, água, noix…" : "ex.: vitamina c, fibra…"}
          value={queryText}
          onChange={(event) => setQueryText(event.target.value)}
        />
        <select
          aria-label="idioma"
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
          aria-label="número de resultados"
          value={limit}
          onChange={(event) => setLimit(Number(event.target.value))}
        >
          {[10, 25, 50, 100].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <button type="submit">pesquisar</button>
      </form>

      {groups.length > 0 && (
        <div className="search">
          <span className="muted">grupo:</span>
          <button
            type="button"
            className={`chip ${foodGroup === null ? "chip-score" : ""}`}
            onClick={() => changeGroup(null)}
          >
            todos
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
            <p className="muted">sem resultados para “{queryText}”</p>
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
            onClose={() => setSelectedFood(null)}
          />
        ) : selectedNutrient !== null ? (
          <NutrientDetail
            nutrientId={selectedNutrient}
            locale={locale}
            foodGroup={foodGroup}
            onOpenFood={(conceptId) => {
              setSelectedNutrient(null);
              setSelectedFood(conceptId);
            }}
            onClose={() => setSelectedNutrient(null)}
          />
        ) : null}
      </div>

      <footer className="muted">
        Dados: CIQUAL 2025 (etalab-2.0) · INSA/TCA 7.1 (insa-tca-7.1) · artefacto em IndexedDB
        (sem HTTP-range) · motor F1/F2 (emendas A7/A8)
      </footer>
    </main>
  );
}