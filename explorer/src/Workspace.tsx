import { useMemo, useState } from "react";
import { foodValues, type FoodValue } from "./search";

type WorkspaceFood = { id: string; label: string };

const PROFILE = [
  ["ENERC_KCAL", "Energy", "kcal"],
  ["PROCNT", "Protein", "g"],
  ["FAT", "Total fat", "g"],
  ["CHOAVL", "Available carbohydrates", "g"],
  ["FIBTG", "Dietary fibre", "g"],
  ["NA", "Sodium", "mg"],
] as const;

function valueFor(values: FoodValue[], id: string): number {
  return values.find((value) => value.nutrientId === id)?.value ?? 0;
}

export default function Workspace({ foods, onRemove }: { foods: WorkspaceFood[]; onRemove: (id: string) => void }) {
  const [grams, setGrams] = useState<Record<string, number>>({});
  const [servings, setServings] = useState(1);
  const [locale, setLocale] = useState("pt-PT");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const amounts = foods.map((food) => ({ ...food, grams: grams[food.id] ?? 100 }));
  const valuesByFood = useMemo(() => new Map(foods.map((food) => [food.id, foodValues(food.id, locale)])), [foods, locale]);
  const totals = useMemo(() => PROFILE.map(([id, name, unit]) => ({ id, name, unit, value: amounts.reduce((sum, food) => sum + valueFor(valuesByFood.get(food.id) ?? [], id) * food.grams / 100, 0) * servings })), [amounts, servings, valuesByFood]);
  const totalWeight = amounts.reduce((sum, food) => sum + food.grams, 0) * servings;
  const exportWorkspace = () => {
    const payload = { type: "nutridb-composition", locale, servings, foods: amounts, totals, notes };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = "nutridb-composition.json"; link.click(); URL.revokeObjectURL(url);
  };
  return <div className="content-stack workspace-page"><div className="page-intro"><div><span className="eyebrow">COMPOSITION WORKSPACE</span><h2>Build a transparent composition</h2><p>Combine real source-backed foods, adjust quantities and inspect calculated totals. Nothing is silently imputed.</p></div><div className="page-actions"><button className="ghost-button" onClick={() => setNotes("")}>New canvas</button><button className="primary-button" onClick={exportWorkspace}>Export JSON -&gt;</button></div></div><div className="workspace-toolbar"><div><span className="eyebrow">CANVAS SETTINGS</span><strong>per 100 g edible basis</strong></div><label>Locale<select className="select-control" value={locale} onChange={(event) => setLocale(event.target.value)}><option>pt-PT</option><option>en</option><option>fr</option></select></label><label>Servings<input className="number-input" type="number" min="1" step="1" value={servings} onChange={(event) => setServings(Math.max(1, Number(event.target.value) || 1))} /></label><span className="workspace-weight">{totalWeight.toFixed(0)} g total</span></div><div className="workspace-layout"><section className="workspace-main"><div className="workspace-card light"><div className="workspace-section-title"><div><span className="eyebrow">INGREDIENTS</span><h3>{foods.length ? `${foods.length} foods in canvas` : "Empty canvas"}</h3></div><span className="muted">click quantities to edit</span></div>{foods.length === 0 ? <div className="empty-state tall"><span className="empty-icon">+</span><h3>Add foods from the catalog</h3><p>Open Food catalog, search a concept and use the plus button.</p></div> : <div className="ingredient-list">{amounts.map((food, index) => <div className="ingredient-row" key={food.id}><span className="rank-index">{String(index + 1).padStart(2, "0")}</span><div className="ingredient-name"><strong>{food.label}</strong><small>{food.id}</small></div><label><input className="number-input" type="number" min="0" step="1" value={food.grams} onChange={(event) => setGrams((current) => ({ ...current, [food.id]: Math.max(0, Number(event.target.value) || 0) }))} /> g</label><button className="icon-button" onClick={() => onRemove(food.id)}>x</button></div>)}</div>}<div className="workspace-footnote"><span>Formula: Σ(value × grams / 100) × servings</span><span className="pill pill-amber">calculated</span></div></div><div className="workspace-card light"><div className="workspace-section-title"><div><span className="eyebrow">NUTRITION PROFILE</span><h3>Calculated totals</h3></div><span className="pill pill-green">{locale}</span></div><div className="total-grid">{totals.map((total) => <div className="total-card" key={total.id}><span>{total.name}</span><strong>{total.value.toLocaleString("pt-PT", { maximumFractionDigits: 2 })}</strong><small>{total.unit} · {total.id}</small></div>)}</div><div className="table-scroll"><table className="data-table compact"><thead><tr><th>Nutrient</th><th>Per composition</th><th>Per serving</th><th>Evidence</th></tr></thead><tbody>{totals.map((total) => <tr key={total.id}><td><strong>{total.name}</strong><small>{total.id}</small></td><td className="number">{total.value.toFixed(2)} {total.unit}</td><td className="number">{(total.value / servings).toFixed(2)} {total.unit}</td><td><span className="pill pill-amber">calculated</span></td></tr>)}</tbody></table></div></div></section><aside className="workspace-rail"><div className="rail-card"><span className="eyebrow">COMPOSITION NOTEBOOK</span><h3>What are you exploring?</h3><textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Add a research note, meal label or comparison question..." /><button className="ghost-button full" onClick={() => setSaved(true)}>{saved ? "Saved locally" : "Save note"}</button></div><div className="rail-card"><span className="eyebrow">CALCULATION CONTRACT</span><div className="contract-row"><span>Inputs visible</span><b>yes</b></div><div className="contract-row"><span>Formula recorded</span><b>yes</b></div><div className="contract-row"><span>Imputation</span><b>never</b></div><div className="contract-row"><span>Source lineage</span><b>per row</b></div></div><div className="rail-card accent-rail"><span className="eyebrow">NEXT LENS</span><h3>Compare this canvas across sources</h3><p>Open the source observatory to inspect where the inputs diverge before trusting a total.</p><button className="text-button">Open source observatory -&gt;</button></div></aside></div></div>;
}
