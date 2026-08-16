declare module "@sqlite.org/sqlite-wasm" {
  export interface SQLite3Capi {
    [key: string]: any;
  }
  export interface SQLite3Wasm {
    [key: string]: any;
  }
  export interface SQLite3Module {
    capi: SQLite3Capi;
    wasm: SQLite3Wasm;
    exports: Record<string, unknown>;
    oo1: unknown;
  }
  const init: (opts?: Record<string, unknown>) => Promise<SQLite3Module>;
  export default init;
}