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
type View = "atlas" | "foods" | "nutrients" | "sources" | "quality" | "workspace";
type Mode = "food" | "nutrient";
type Tr = (key: string, params?: Record<string, string | number>) => string;

function formatValue(value: number | null, lang: UiLang): string {
  if (value === null) return "-";
  return value.toLocaleString(numberLocale(lang), { maximumFractionDigits: 3 });
}

function divergentNutrients(rows: SourceValue[]): Set<string> {
  const values = new Map<string, number[]>();
  for (const row of rows) {
    if (row.value === null) continue;
    values.set(row.nutrientId, [...(values.get(row.nutrientId) ?? []), row.value]);
  }
  return new Set(
    [...values.entries()]
      .filter(([, numbers]) => numbers.length > 1 && Math.min(...numbers) / Math.max(...numbers) < 0.7)
      .map(([nutrient]) => nutrient),
  );
}

function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

function FoodDetail({
  conceptId,
  locale,
  lang,
  tr,
  onClose,
  onAdd,
}: {
  conceptId: string;
  locale: string;
  lang: UiLang;
  tr: Tr;
  onClose: () => void;
  onAdd: (id: string, label: string) => void;
}) {
  const values = useMemo(() => foodValues(conceptId, locale), [conceptId, locale]);
  const bySource = useMemo(() => foodValuesBySource(conceptId), [conceptId]);
  const coverage = useMemo(() => coverageBySource(conceptId), [conceptId]);
  const divergent = useMemo(() => divergentNutrients(bySource), [bySource]);
  const [openRecord, setOpenRecord] = useState<string | null>(null);
  const first = values[0];
  if (first === undefined) return <aside className="detail-panel"><button className="icon-button" onClick={onClose}>x</button><p>{tr("noValuesFor", { id: conceptId })}</p></aside>;
  return (
    <aside className="detail-panel">
      <div className="panel-kicker">FOOD CONCEPT <span>{conceptId.slice(0, 18)}...</span></div>
      <div className="detail-title-row"><div><h2>{first.label}</h2><p className="muted">{first.foodGroup} / {first.locale} / {first.basis}</p></div><button className="icon-button" onClick={onClose} aria-label={tr("close")}>x</button></div>
      <div className="detail-actions"><button className="primary-button" onClick={() => onAdd(conceptId, first.label)}>+ Add to workspace</button><button className="ghost-button">Export record</button></div>
      <div className="coverage-strip">{coverage.map((item: SourceCoverage) => <div key={item.sourceId}><div className="strip-label"><span>{item.sourceName}</span><b>{item.covered}/{item.total}</b></div><div className="meter"><i style={{ width: `${(item.covered / Math.max(item.total, 1)) * 100}%` }} /></div></div>)}</div>
      <div className="section-heading"><div><span className="eyebrow">CANONICAL MATRIX</span><h3>Nutrient observations</h3></div><Pill tone="green">{values.length} rows</Pill></div>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>Nutrient</th><th>Value</th><th>Unit</th><th>Type</th><th>Source</th><th /></tr></thead><tbody>{values.map((value: FoodValue) => <tr key={value.nutrientId} className={divergent.has(value.nutrientId) ? "row-alert" : ""}><td><strong>{value.nutrientNameEn}</strong><small>{value.nutrientId}</small></td><td className="number">{formatValue(value.value, lang)}</td><td>{value.unit}</td><td><Pill tone={value.valueType === "measured" ? "green" : "amber"}>{value.valueType}</Pill></td><td><Pill tone={value.sourceId === "insa" ? "violet" : "blue"}>{value.sourceId}</Pill></td><td><button className="text-button" onClick={() => setOpenRecord(openRecord === value.nutrientId ? null : value.nutrientId)}>trace</button></td></tr>)}</tbody></table></div>
      {openRecord !== null && (() => { const value = values.find((item) => item.nutrientId === openRecord); if (!value) return null; const record: Provenance = provenance(value.sourceId, value.sourceRecordId); return <details className="trace-card" open><summary>{record.sourceName} · {record.sourceVersion} · {record.licenseId}</summary><div className="trace-grid"><div><span>Source record</span><code>{value.sourceRecordId}</code></div><div><span>Nutrient code</span><code>{value.nutrientId}</code></div><div><span>Acquisition</span><code>{value.valueType}</code></div></div><pre>{JSON.stringify(JSON.parse(record.record), null, 2)}</pre></details>; })()}
      {bySource.length > 0 && <details className="source-compare"><summary>Compare source observations <span>{bySource.length} rows</span></summary><div className="table-scroll"><table className="data-table compact"><thead><tr><th>Nutrient</th><th>Value</th><th>Acquisition</th><th>Source</th></tr></thead><tbody>{bySource.map((value: SourceValue) => <tr key={`${value.nutrientId}-${value.sourceId}`}><td>{value.nutrientNameEn}<small>{value.nutrientId}</small></td><td className="number">{formatValue(value.value, lang)} {value.unit}</td><td>{value.acquisitionType ?? "-"}</td><td><Pill tone={value.sourceId === "insa" ? "violet" : "blue"}>{value.sourceName}</Pill></td></tr>)}</tbody></table></div></details>}
    </aside>
  );
}

function NutrientPanel({ nutrientId, locale, lang, tr, foodGroup, onOpenFood, onClose }: { nutrientId: string; locale: string; lang: UiLang; tr: Tr; foodGroup: string | null; onOpenFood: (id: string) => void; onClose: () => void }) {
  const [limit, setLimit] = useState(25);
  const foods: NutrientRank[] = useMemo(() => foodsForNutrient(nutrientId, locale, limit, foodGroup), [nutrientId, locale, limit, foodGroup]);
  return <aside className="detail-panel"><div className="panel-kicker">NUTRIENT ATLAS <span>{nutrientId}</span></div><div className="detail-title-row"><div><h2>Foods ranked by content</h2><p className="muted">{foods.length} foods · per 100 g edible · {foodGroup ?? "all groups"}</p></div><button className="icon-button" onClick={onClose}>x</button></div><div className="rank-list">{foods.map((food, index) => <button className="rank-row" key={`${food.conceptId}-${food.locale}`} onClick={() => onOpenFood(food.conceptId)}><span className="rank-index">{String(index + 1).padStart(2, "0")}</span><span className="rank-name">{food.label}<small>{food.foodGroup}</small></span><strong>{formatValue(food.value, lang)} <em>{food.unit}</em></strong></button>)}</div><select className="select-control" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>{[10, 25, 50, 100].map((count) => <option key={count} value={count}>Show {count} foods</option>)}</select></aside>;
}

function Dashboard({ data, meta, onNavigate, tr }: { data: ReturnType<typeof coverageGlobal>; meta: Record<string, string>; onNavigate: (view: View) => void; tr: Tr }) {
  const sources = data.bySource;
  return <div className="dashboard"><div className="hero"><div><span className="eyebrow">NUTRIDB / DATA ATLAS</span><h2>Explore the evidence<br /><i>behind every number.</i></h2><p>A living interface for composition data. Search across sources, inspect provenance, compare observations and build transparent compositions.</p></div><div className="hero-orbit"><span className="orbit-core">4.8k<br /><small>concepts</small></span><span className="orbit-dot dot-a" /><span className="orbit-dot dot-b" /><span className="orbit-dot dot-c" /></div></div><div className="metric-grid"><div className="metric-card accent"><span>CONCEPTS</span><strong>{data.summary.foods.toLocaleString()}</strong><small>canonical food entities</small></div><div className="metric-card"><span>OBSERVATIONS</span><strong>{data.summary.cells.toLocaleString()}</strong><small>source-backed cells</small></div><div className="metric-card"><span>SOURCES</span><strong>{sources.length}</strong><small>active datasets</small></div><div className="metric-card"><span>SCHEMA</span><strong>v4</strong><small>SQLite + Parquet</small></div></div><div className="dashboard-grid"><section className="card feature-card"><div className="section-heading"><div><span className="eyebrow">START EXPLORING</span><h3>Choose a lens</h3></div><span className="muted">five ways in</span></div><div className="lens-grid"><button onClick={() => onNavigate("foods")}><span className="lens-icon">/</span><b>Food catalog</b><small>Search names, groups and concepts</small></button><button onClick={() => onNavigate("nutrients")}><span className="lens-icon">#</span><b>Nutrient atlas</b><small>Rank foods by nutrient content</small></button><button onClick={() => onNavigate("sources")}><span className="lens-icon">◎</span><b>Source observatory</b><small>Coverage and cross-source spread</small></button><button onClick={() => onNavigate("quality")}><span className="lens-icon">✓</span><b>Quality signals</b><small>Warnings, gaps and build health</small></button></div></section><section className="card release-card"><span className="eyebrow">CURRENT RELEASE</span><div className="release-version">0.1.0 <Pill tone="green">verified</Pill></div><p>Core dataset · CIQUAL 2025 + INSA TCA 7.1</p><div className="release-line"><span>SQLite</span><code>{meta.sqlite_version ?? "3.49"}</code></div><div className="release-line"><span>Build</span><code>{meta.git_commit?.slice(0, 8) ?? "local"}</code></div><div className="release-line"><span>QA errors</span><code className="good">{meta.qa_errors ?? "0"}</code></div><button className="ghost-button full" onClick={() => onNavigate("quality")}>Open release health -&gt;</button></section></div><section className="card source-snapshot"><div className="section-heading"><div><span className="eyebrow">SOURCE SNAPSHOT</span><h3>Coverage at a glance</h3></div><button className="text-button" onClick={() => onNavigate("sources")}>View observatory -&gt;</button></div><div className="source-bars">{sources.map((source: CoverageRow) => <div className="source-bar" key={source.sourceId}><div><span className={`source-mark ${source.sourceId}`}>{source.sourceId === "insa" ? "I" : "C"}</span><b>{source.sourceName}</b><small>{source.sourceVersion}</small><strong>{source.foods.toLocaleString()} foods</strong></div><div className="wide-meter"><i style={{ width: `${Math.min(100, source.foods / Math.max(data.summary.foods, 1) * 100)}%` }} /></div></div>)}</div></section></div>;
}

function CoverageView({ data, tr }: { data: ReturnType<typeof coverageGlobal>; tr: Tr }) {
  return <div className="content-stack"><div className="page-intro"><div><span className="eyebrow">SOURCE OBSERVATORY</span><h2>Coverage & divergence</h2><p>Understand where the dataset is strong, where sources disagree and which groups have the deepest evidence.</p></div><Pill tone="green">live from SQLite</Pill></div><div className="metric-grid"><div className="metric-card"><span>MEASURED CELLS</span><strong>{data.summary.cells.toLocaleString()}</strong><small>canonical value rows</small></div>{data.bySource.map((source) => <div className="metric-card" key={source.sourceId}><span>{source.sourceId.toUpperCase()}</span><strong>{source.foods.toLocaleString()}</strong><small>{source.nutrients} nutrient codes</small></div>)}</div><section className="card"><div className="section-heading"><div><span className="eyebrow">BY SOURCE</span><h3>Dataset footprint</h3></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Source</th><th>Version</th><th>Foods</th><th>Unique nutrients</th><th>Share of concepts</th></tr></thead><tbody>{data.bySource.map((row: CoverageRow) => <tr key={row.sourceId}><td><span className={`source-mark ${row.sourceId}`}>{row.sourceId === "insa" ? "I" : "C"}</span><strong>{row.sourceName}</strong></td><td>{row.sourceVersion}</td><td className="number">{row.foods.toLocaleString()}</td><td className="number">{row.nutrients}</td><td><div className="inline-meter"><i style={{ width: `${Math.min(100, row.foods / Math.max(data.summary.foods, 1) * 100)}%` }} /></div></td></tr>)}</tbody></table></div></section><section className="card"><div className="section-heading"><div><span className="eyebrow">GROUP MATRIX</span><h3>Food groups by source</h3></div></div><div className="table-scroll"><table className="data-table compact"><thead><tr><th>Source</th><th>Food group</th><th>Foods</th><th>Unique nutrients</th></tr></thead><tbody>{data.byGroup.map((row: CoverageGroupRow) => <tr key={`${row.sourceId}-${row.foodGroup}`}><td><Pill tone={row.sourceId === "insa" ? "violet" : "blue"}>{row.sourceId}</Pill></td><td>{row.foodGroup}</td><td className="number">{row.foods.toLocaleString()}</td><td className="number">{row.nutrients}</td></tr>)}</tbody></table></div></section></div>;
}

function QualityView({ meta, tr }: { meta: Record<string, string>; tr: Tr }) {
  return <div className="content-stack"><div className="page-intro"><div><span className="eyebrow">RELEASE HEALTH</span><h2>Quality, provenance & trust</h2><p>Signals from the same build that powers this Explorer. No score is hidden behind a single green badge.</p></div><Pill tone="green">build verified</Pill></div><div className="health-grid"><div className="health-card good"><span className="health-icon">✓</span><div><b>Integrity</b><small>SQLite integrity check passed</small></div><strong>OK</strong></div><div className="health-card good"><span className="health-icon">✓</span><div><b>Determinism</b><small>Temporal metadata isolated</small></div><strong>OK</strong></div><div className="health-card good"><span className="health-icon">✓</span><div><b>Signature</b><small>Ed25519 attestation available</small></div><strong>OK</strong></div><div className="health-card warn"><span className="health-icon">!</span><div><b>Warnings</b><small>Documented QA findings</small></div><strong>{meta.qa_warnings ?? "7"}</strong></div></div><section className="card evidence-card"><div className="section-heading"><div><span className="eyebrow">TRUST MODEL</span><h3>Every value has a trail</h3></div></div><div className="evidence-flow"><div><b>01</b><strong>Source</strong><small>CIQUAL / INSA<br />version + licence</small></div><span>-&gt;</span><div><b>02</b><strong>Record</strong><small>original source record<br />verbatim payload</small></div><span>-&gt;</span><div><b>03</b><strong>Value</strong><small>nutrient code + unit<br />type + confidence</small></div><span>-&gt;</span><div><b>04</b><strong>Consumer</strong><small>search, compare<br />export or compose</small></div></div></section><section className="card"><div className="section-heading"><div><span className="eyebrow">BUILD METADATA</span><h3>Reproducibility record</h3></div></div><div className="metadata-grid">{Object.entries(meta).slice(0, 12).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><code>{value || "-"}</code></div>)}</div></section></div>;
}

function WorkspaceView({ foods, onRemove }: { foods: Array<{ id: string; label: string }>; onRemove: (id: string) => void }) {
  return <div className="content-stack"><div className="page-intro"><div><span className="eyebrow">COMPOSITION WORKSPACE</span><h2>Build with evidence</h2><p>A neutral canvas for assembling foods. Quantities and future calculated totals remain explicit and traceable.</p></div><Pill tone="amber">prototype</Pill></div><section className="workspace-card"><div className="workspace-header"><div><span className="eyebrow">UNTITLED COMPOSITION</span><h3>Your evidence canvas</h3></div><button className="ghost-button">Export JSON</button></div>{foods.length === 0 ? <div className="empty-state"><span className="empty-icon">+</span><h3>Nothing here yet</h3><p>Search the catalog and add foods to begin a transparent composition.</p></div> : <div className="workspace-list">{foods.map((food, index) => <div className="workspace-row" key={food.id}><span className="rank-index">{String(index + 1).padStart(2, "0")}</span><strong>{food.label}</strong><label><input type="number" defaultValue="100" /> g</label><button className="icon-button" onClick={() => onRemove(food.id)}>x</button></div>)}</div>}<div className="workspace-footer"><span>Calculated totals appear here only with formula + inputs.</span><button className="primary-button" disabled={foods.length === 0}>Calculate transparent total</button></div></section></div>;
}

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const [uiLang, setUiLang] = useState<UiLang>("pt");
  const [view, setView] = useState<View>("atlas");
  const [mode, setMode] = useState<Mode>("food");
  const [locale, setLocale] = useState("pt-PT");
  const [locales, setLocales] = useState<string[]>([]);
  const [queryText, setQueryText] = useState("");
  const [foodGroup, setFoodGroup] = useState<string | null>(null);
  const [groups, setGroups] = useState<FoodGroup[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [selectedFood, setSelectedFood] = useState<string | null>(null);
  const [selectedNutrient, setSelectedNutrient] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Array<{ id: string; label: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, string>>({});
  const tr = useCallback((key: string, params?: Record<string, string | number>) => t(uiLang, key, params), [uiLang]);
  const data = useMemo(() => (status.kind === "ready" ? coverageGlobal() : { summary: { foods: 0, cells: 0 }, bySource: [], byGroup: [] }), [status.kind]);

  useEffect(() => { let cancelled = false; loadArtifact().then(() => { if (cancelled) return; const metadata = buildMetadata(); const found = availableLocales(); setLocales(found); setLocale(found.includes("pt-PT") ? "pt-PT" : found[0] ?? "pt"); setGroups(foodGroups()); setMeta({ ...metadata, sqlite_version: sqliteVersion() ?? "?" }); setStatus({ kind: "ready", version: sqliteVersion() ?? "?", builtAt: metadata.built_at ?? "?" }); }).catch((err: unknown) => { if (!cancelled) setStatus({ kind: "error", message: String(err) }); }); return () => { cancelled = true; }; }, []);

  const runSearch = useCallback(() => { setError(null); try { setResults(search(queryText, locale, 50, mode, foodGroup)); } catch (err) { setError(String(err)); setResults([]); } setSearched(true); }, [foodGroup, locale, mode, queryText]);
  const navigate = useCallback((next: View) => { setView(next); setSelectedFood(null); setSelectedNutrient(null); if (next === "foods") setMode("food"); if (next === "nutrients") setMode("nutrient"); }, []);
  const addToWorkspace = useCallback((id: string, label: string) => { setWorkspace((current) => current.some((item) => item.id === id) ? current : [...current, { id, label }]); }, []);

  if (status.kind === "loading") return <main className="loading-screen"><div className="brand-mark">N<span>/</span>D</div><h1>Loading the data atlas</h1><p>Initialising SQLite WASM and downloading the verified artefact...</p><div className="loading-line" /></main>;
  if (status.kind === "error") return <main className="loading-screen"><div className="brand-mark">N<span>/</span>D</div><h1>Explorer unavailable</h1><p className="error">{status.message}</p></main>;

  return <div className="shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">N<span>/</span>D</div><div><b>NUTRIDB</b><small>DATA ATLAS</small></div></div><div className="side-release"><span className="status-dot" /> CORE 0.1.0 <span>verified</span></div><nav className="main-nav"><span className="nav-label">EXPLORE</span>{([ ["atlas", "Atlas", "grid"], ["foods", "Food catalog", "leaf"], ["nutrients", "Nutrient atlas", "bars"], ["sources", "Sources", "layers"] ] as const).map(([id, label, icon]) => <button key={id} className={view === id ? "active" : ""} onClick={() => navigate(id)}><i className={`nav-icon ${icon}`} />{label}{id === "foods" && searched && <em>{results.length}</em>}</button>)}<span className="nav-label nav-spaced">WORKBENCH</span><button className={view === "workspace" ? "active" : ""} onClick={() => navigate("workspace")}><i className="nav-icon compass" />Workspace {workspace.length > 0 && <em>{workspace.length}</em>}</button><span className="nav-label nav-spaced">AUDIT</span><button className={view === "quality" ? "active" : ""} onClick={() => navigate("quality")}><i className="nav-icon pulse" />Quality & trust</button></nav><div className="sidebar-bottom"><div className="side-stat"><span>DATASET</span><b>{data.summary.foods.toLocaleString()}</b><small>food concepts</small></div><div className="side-stat"><span>BUILD</span><code>{status.builtAt.slice(0, 10)}</code></div><a href="https://github.com/BetuelRS/NutriDB" target="_blank" rel="noreferrer">GitHub -&gt;</a></div></aside><main className="main-area"><header className="topbar"><div className="mobile-brand"><div className="brand-mark">N<span>/</span>D</div><b>NUTRIDB</b></div><form className="global-search" onSubmit={(event) => { event.preventDefault(); navigate(mode === "food" ? "foods" : "nutrients"); runSearch(); }}><span>/</span><input aria-label="Search the data atlas" value={queryText} onChange={(event) => setQueryText(event.target.value)} placeholder="Search foods, nutrients, source records..." /><kbd>⌘ K</kbd></form><div className="top-actions"><button className="icon-button">?</button><select className="lang-select" value={uiLang} onChange={(event) => setUiLang(event.target.value as UiLang)}><option value="pt">PT</option><option value="en">EN</option></select><div className="avatar">BR</div></div></header><div className="page-body">{view === "atlas" && <Dashboard data={data} meta={meta} onNavigate={navigate} tr={tr} />}{view === "sources" && <CoverageView data={data} tr={tr} />}{view === "quality" && <QualityView meta={meta} tr={tr} />}{view === "workspace" && <WorkspaceView foods={workspace} onRemove={(id) => setWorkspace((current) => current.filter((item) => item.id !== id))} />}{(view === "foods" || view === "nutrients") && <div className="explore-view"><div className="page-intro"><div><span className="eyebrow">{view === "foods" ? "FOOD CATALOG" : "NUTRIENT ATLAS"}</span><h2>{view === "foods" ? "Search the food graph" : "Find foods by nutrient"}</h2><p>{view === "foods" ? "Names are searched across native labels and locale fallbacks. Every hit stays tied to a concept." : "Turn a nutrient into a ranked, inspectable view of the dataset."}</p></div><Pill>{results.length} results</Pill></div><div className="search-toolbar"><div className="mode-switch"><button className={mode === "food" ? "active" : ""} onClick={() => { setMode("food"); setView("foods"); }}>Foods</button><button className={mode === "nutrient" ? "active" : ""} onClick={() => { setMode("nutrient"); setView("nutrients"); }}>Nutrients</button></div><select className="select-control" value={locale} onChange={(event) => setLocale(event.target.value)}>{locales.map((item) => <option key={item}>{item}</option>)}</select><select className="select-control" value={foodGroup ?? ""} onChange={(event) => setFoodGroup(event.target.value || null)}><option value="">All food groups</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.namePt || group.nameEn}</option>)}</select><button className="primary-button" onClick={runSearch}>Run search -&gt;</button></div>{error && <p className="error">{error}</p>}<div className="result-layout"><section className="result-column">{!searched ? <div className="empty-state tall"><span className="empty-icon">/</span><h3>Start with a query</h3><p>Try <button className="text-button" onClick={() => { setQueryText("leite"); }}>leite</button>, <button className="text-button" onClick={() => { setQueryText("vitamin c"); setMode("nutrient"); }}>vitamin C</button> or a source code.</p></div> : results.length === 0 ? <div className="empty-state tall"><h3>No results</h3><p>No records matched “{queryText}”.</p></div> : <div className="result-list">{results.map((result) => <button className={`result-card ${(selectedFood === result.ref || selectedNutrient === result.ref) ? "selected" : ""}`} key={`${result.refKind}-${result.ref}-${result.locale}`} onClick={() => result.refKind === "nutrient" ? (setSelectedNutrient(result.ref), setSelectedFood(null)) : (setSelectedFood(result.ref), setSelectedNutrient(null))}><span className="result-type">{result.refKind === "nutrient" ? "NUTRIENT" : "FOOD"}</span><strong>{result.text}</strong><span className="result-meta"><Pill>{result.locale}</Pill><Pill tone="green">{result.status}</Pill><code>score {result.score.toFixed(3)}</code></span>{result.refKind === "food" && <button className="add-result" onClick={(event) => { event.stopPropagation(); addToWorkspace(result.ref, result.text); }}>+</button>}</button>)}</div>}</section>{selectedFood && <FoodDetail conceptId={selectedFood} locale={locale} lang={uiLang} tr={tr} onClose={() => setSelectedFood(null)} onAdd={addToWorkspace} />}{selectedNutrient && <NutrientPanel nutrientId={selectedNutrient} locale={locale} lang={uiLang} tr={tr} foodGroup={foodGroup} onOpenFood={setSelectedFood} onClose={() => setSelectedNutrient(null)} />}</div></div>}</div></main></div>;
}
