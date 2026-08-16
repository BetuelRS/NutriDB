import sqlite3InitModule from "@sqlite.org/sqlite-wasm";
import type { SQLite3Module } from "@sqlite.org/sqlite-wasm";

type SQLite3 = SQLite3Module;

const ARTIFACT = "nutridb-core-0.1.0.sqlite";

let module: SQLite3 | null = null;
let dbHandle: number | null = null;

function capi(): SQLite3["capi"] {
  if (module === null) throw new Error("SQLite WASM not initialised");
  return module.capi;
}

function ensureHandle(): number {
  if (dbHandle !== null) return dbHandle;
  const m = capi();
  const pp = m.wasm.allocPtr();
  const rc = m.capi.sqlite3_open_v2(
    ":memory:",
    pp,
    m.capi.SQLITE_OPEN_READWRITE | m.capi.SQLITE_OPEN_CREATE,
    0,
  );
  if (rc !== 0) throw new Error(`sqlite3_open_v2 rc=${rc}`);
  const handle: number = m.wasm.peekPtr(pp);
  dbHandle = handle;
  return handle;
}

export async function loadArtifact(): Promise<void> {
  module ??= await sqlite3InitModule({ locateFile: () => "sqlite3.wasm" });
  const m = module;
  const response = await fetch(`/artifacts/${ARTIFACT}`);
  if (!response.ok) {
    throw new Error(
      `artefacto ${ARTIFACT} indisponivel (HTTP ${response.status}) - corre 'uv run nutridb build'`,
    );
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  const handle = ensureHandle();
  const p = m.wasm.allocFromTypedArray(bytes);
  const rc = m.capi.sqlite3_deserialize(
    handle,
    "main",
    p,
    bytes.length,
    bytes.length,
    m.capi.SQLITE_DESERIALIZE_FREEONCLOSE | m.capi.SQLITE_DESERIALIZE_RESIZEABLE,
  );
  if (rc !== 0) throw new Error(`sqlite3_deserialize rc=${rc}`);
}

export interface QueryRow {
  values: Array<string | number | null>;
}

export function query(sql: string, params: Array<string | number> = []): QueryRow[] {
  const m = capi();
  const handle = ensureHandle();
  const ppStmt = m.wasm.allocPtr();
  const prc = m.capi.sqlite3_prepare_v2(handle, sql, -1, ppStmt, 0);
  const stmt = m.wasm.peekPtr(ppStmt);
  if (prc !== 0 || stmt === 0) {
    throw new Error(`sqlite3_prepare_v2 rc=${prc}: ${m.capi.sqlite3_errmsg(handle)}`);
  }
  try {
    params.forEach((value, index) => {
      const i = index + 1;
      if (typeof value === "number") {
        m.capi.sqlite3_bind_double(stmt, i, value);
      } else {
        m.capi.sqlite3_bind_text(stmt, i, new TextEncoder().encode(value).buffer, -1, 0);
      }
    });
    const rows: QueryRow[] = [];
    let step: number;
    while ((step = m.capi.sqlite3_step(stmt)) === m.capi.SQLITE_ROW) {
      const count = m.capi.sqlite3_column_count(stmt);
      const values: Array<string | number | null> = [];
      for (let c = 0; c < count; c++) {
        const type = m.capi.sqlite3_column_type(stmt, c);
        if (type === m.capi.SQLITE_NULL) values.push(null);
        else if (type === m.capi.SQLITE_INTEGER || type === m.capi.SQLITE_FLOAT) {
          values.push(m.capi.sqlite3_column_double(stmt, c));
        } else {
          values.push(m.capi.sqlite3_column_text(stmt, c));
        }
      }
      rows.push({ values });
    }
    if (step !== m.capi.SQLITE_DONE) {
      throw new Error(`sqlite3_step rc=${step}: ${m.capi.sqlite3_errmsg(handle)}`);
    }
    return rows;
  } finally {
    m.capi.sqlite3_finalize(stmt);
  }
}

export function sqliteVersion(): string | null {
  if (module === null || dbHandle === null) return null;
  return query("SELECT sqlite_version()")[0]?.values[0]?.toString() ?? null;
}