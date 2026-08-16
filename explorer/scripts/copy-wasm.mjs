import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const wasm = join(
  here,
  "..",
  "node_modules",
  "@sqlite.org",
  "sqlite-wasm",
  "sqlite-wasm",
  "jswasm",
  "sqlite3.wasm",
);
const outDir = join(here, "..", "public");
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "sqlite3.wasm"), readFileSync(wasm));
console.log("copied sqlite3.wasm -> public/sqlite3.wasm");