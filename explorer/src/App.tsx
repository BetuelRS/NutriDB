import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ACTIVE_LOCALES,
  buildMetadata,
  foodValues,
  provenance,
  search,
  type FoodValue,
  type Provenance,
  type SearchResult,
} from "./search";
import { loadArtifact, sqliteVersion } from "./db";
import "./App.css";

type Status =
  | { kind: "loading" }
  | { kind: "ready"; version: string; builtAt: string }
  | { kind: "error"; message: string };

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

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const [queryText, setQueryText] = useState("");
  const [locale, setLocale] = useState("fr");
  const [limit, setLimit] = useState(25);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadArtifact()
      .then(() => {
        if (cancelled) return;
        const version = sqliteVersion() ?? "?";
        const meta = buildMetadata();
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
      setSelected(null);
      try {
        setResults(search(text, locale, limit));
      } catch (err) {
        setError(String(err));
        setResults([]);
      }
      setSearched(true);
    },
    [locale, limit],
  );

  if (status.kind === "loading") {
    return (
      <main className="app">
        <h1>NUTRIDB Explorer</h1>
        <p className="muted">a carregar o artefacto SQLite (≈219 MB) via WASM…</p>
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
          NUTRIDB Explorer <span className="tag">F2</span>
        </h1>
        <p className="muted">
          SQLite {status.version} (WASM) · artefacto de {status.builtAt} · pesquisa FTS5
          acentos-insensível
        </p>
      </header>

      <form
        className="search"
        onSubmit={(event) => {
          event.preventDefault();
          runSearch(queryText);
        }}
      >
        <input
          aria-label="termo de pesquisa"
          type="search"
          placeholder="ex.: pomme, lait, água, noix…"
          value={queryText}
          onChange={(event) => setQueryText(event.target.value)}
        />
        <select
          aria-label="idioma"
          value={locale}
          onChange={(event) => setLocale(event.target.value)}
        >
          {ACTIVE_LOCALES.map((l) => (
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
                  className={`result ${selected === r.ref ? "selected" : ""}`}
                  onClick={() => setSelected(selected === r.ref ? null : r.ref)}
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
        {selected !== null && (
          <FoodDetail
            conceptId={selected}
            locale={locale}
            onClose={() => setSelected(null)}
          />
        )}
      </div>

      <footer className="muted">
        Dados: CIQUAL 2025 (etalab-2.0) · INSA/TCA 7.1 (insa-tca-7.1) · motor de pesquisa F1
        (emenda A7) · sem HTTP-range
      </footer>
    </main>
  );
}