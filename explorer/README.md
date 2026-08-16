# explorer/ — NUTRIDB Explorer (SPEC §12)

Aplicação web **estática** (React + TypeScript + Vite).

- **F1.8b**: página mínima de pesquisa — carrega o artefacto SQLite
  (`build/artifacts/nutridb-core-0.1.0.sqlite`) por **fetch integral** e
  pesquisa via **FTS5** acentos-insensível em WASM. Sem HTTP-range (a
  otimização de pedidos por intervalos é a F8).
- F8: as 13 vistas completas (SQLite WASM + pedidos HTTP por intervalo de bytes).

## Nota de decisão (F1.8b, 2026-08-16)

O mecanismo é o **WASM oficial do SQLite** (`@sqlite.org/sqlite-wasm`,
versão pinada `3.49.1-build3`), não o pacote `sql.js`: o build pré-compilado
do `sql.js` **não inclui FTS5** (verificado empiricamente — `no such module:
fts5` ao abrir o artefacto), e o FTS5 é o motor de pesquisa da F1 (emenda
A7). O resto da arquitetura é idêntica ao planeado: WASM, `:memory:`,
`sqlite3_deserialize` do ficheiro integral, sem servidor intermédio.

## Executar

```sh
uv run nutridb explorer dev     # dev server (vite) — serve /artifacts do build/
uv run nutridb explorer build   # tsc + vite build -> explorer/dist/
```

Requisitos: Node >= 20 e `npm install` em `explorer/` (o lockfile
`package-lock.json` está commitado). O dev server expõe `/artifacts/*` a
partir de `build/artifacts/` (middleware vite, `NUTRIDB_ROOT` respeitado);
o build de produção é estático e espera o artefacto servido por um servidor
qualquer (F8).

## Pesquisa

Semântica espelhada de `src/nutridb/api/__init__.py`: normalização
acentos-insensível (ligaduras + NFKD + minúsculas), termos `"term"*` AND,
cadeia de fallback de `i18n/locales.toml` resolvida em runtime. As cadeias
estão duplicadas em `src/search.ts` (P8: dados como dados — manter em
sincronia com o TOML).

## Ficheiros

- `vite.config.ts` — base `./` (estático), middleware `/artifacts`, wasm em `public/`.
- `scripts/copy-wasm.mjs` — copia `sqlite3.wasm` de `node_modules` para
  `public/` (pré-dev/pré-build; o binário não vai para o git).
- `src/db.ts` — init WASM + `sqlite3_deserialize` + helpers de query (capi).
- `src/fts.ts` — normalização e construção do MATCH FTS5 (espelho do Python).
- `src/search.ts` — pesquisa, `mv_food_value` e proveniência (`source_record`).