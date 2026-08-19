# ADR-0008 — Performance de produção e escavabilidade (emenda A8, f5b)

- **Estado**: Aprovado
- **Data**: 2026-08-19
- **Fase**: emenda A8 (`f5b/perf-busca`)

---

## 1. Contexto

A F5 fechou com o pipeline real a 36,7 s (build quente, Windows) e um
artefacto de 236 MB. Dois problemas operacionais foram identificados no
fecho da F5:

1. **Performance**: o `VACUUM` no fim do package custava ~9 s por build —
   e era um *no-op* (o ficheiro acaba de ser criado; o VACUUM apenas o
   reescreve). Cada execução de `nutridb build` re-executava extract
   (7 s) e transform (5 s) mesmo com entradas inalteradas. O perfil
   pyinstrument do build completo (44,4 s) apontava `_to_crockford`
   (identidade ULID) como o maior custo individual, mas a medição real
   (600k chamadas, sem profiler) mostrou que o loop original custa
   ~2,3 µs/chamada — o profiler inflava 3× o custo.
2. **Escavabilidade**: a pesquisa FTS5 é só prefixo (`"term"*`) — uma
   busca por "polpa" não encontra "Curgete, polpa e pele, cozida"; não há
   pesquisa por nutriente ("vitamina c" → alimentos ricos em VITC) nem
   facetas por grupo alimentar. O explorer re-descarrega os 219 MB do
   artefacto em cada reload (sem HTTP-range, F8 — mas nada obriga a
   re-descarga por rede quando o browser já tem os bytes em IndexedDB).

## 2. Opções consideradas

### Performance

- **A. Manter o VACUUM** — correto mas inútil aqui (ficheiro novo) e caro
  (~9 s). Rejeitado; o `ANALYZE` (estatísticas de plano) fica.
- **B. Reescrita do ULID com translates (C-speed)** — fórmula
  byte-idêntica verificada em 100k seeds (0 mismatches): base-32 dígitos
  do digest via `b32hexencode` + per-byte bit-reversal + reverse + tabela
  Crockford. Benchmark real: **mais lento** que o loop (1,83 s vs 1,67 s
  por 600k chamadas). Rejeitado; fica o loop original (sem alteração
  líquida ao módulo) e um **teste golden** (P4) como regressão contra
  futuras otimizações.
- **C. Cache de estágios content-addressed** — `build/cache/<estágio>/`
  com fingerprint SHA-256 dos inputs (registry, cache de fontes, código
  dos sources, intermediários, mappings, vocab, versão); hit → reutiliza
  os bytes anteriores (P5/P10); `--full` para ignorar. Escolhida.
- **D. Extract paralelo (threads/processos)** — descartado com evidência:
  parsing XML é CPU-bound (GIL), e o spawn de processos no Windows
  (~1,5 s) não compensa a divisão (~6 s → 1 s). O cache (C) elimina o
  custo repetido de qualquer forma.

### Escavabilidade

- **E. Manter só o FTS prefixo** — não resolve "polpa" (substring).
- **F. FTS5 trigram por locale (schema 4)** — substring acentos-insensível
  sobre `text_normalized`, externo `content='label'` como o índice atual.
  Escolhida. Limitação documentada: termos < 3 caracteres não têm
  trigramas → fallback para o índice prefixo (a API decide por query).
- **G. `LIKE '%x%'`** — sem índice, varredura completa; só aceitável para
  nutrientes (1 288 rótulos), não para 9 775 alimentos. Usada apenas
  indiretamente (facetas/grupos vêm de `concept`, sem LIKE).
- **H. Explorer com IndexedDB** — o artefacto é imutável (P5) e a chave
  inclui o schema_version: uma mudança de schema invalida a cache do
  browser. Mantém o "sem HTTP-range" (F8) intacto: é só persistência
  local, não range requests.

## 3. Decisão

1. **Remover o `VACUUM`** do package (fica `ANALYZE`); o ficheiro é criado
   de raiz em cada build — o VACUUM era um no-op de ~9 s.
2. **`src/nutridb/cache.py`**: fingerprint SHA-256 determinístico dos
   inputs por estágio; `build/cache/extract/<fp>` e
   `build/cache/transform/<fp>`; hit → copia para o live dir (limpo antes);
   falha alta (P9) se um input referenciado faltar.
3. **`nutridb build --full`** ignora a cache; `build` usa-a (extract e
   transform são os únicos estágios com cache — derive/i18n/merge/package
   são baratos e sempre correm).
4. **ULID**: sem alteração ao algoritmo (o loop é o mais rápido na
   prática); `tests/unit/test_identity.py::test_ulid_golden_values` fixa
   3 ULIDs reais (P4).
5. **Schema 4**: `label_fts_<locale>_tri` (trigram) por locale ativo;
   `user_version`/`build_metadata.schema_version` = 4; `search()` escolhe
   trigram quando todos os termos têm >= 3 caracteres, senão prefixo;
   `search(..., kind="food"|"nutrient", food_group=...)` filtra por tipo e
   faceta; `foods_for_nutrient()` ordena por valor os alimentos de um
   nutriente (mv_food_value, per 100 g).
6. **Explorer**: artefacto persistido em IndexedDB (chave
   `<artefacto>@v<schema>`); modo "nutrientes" (pesquisa + ranking);
   chips de grupo alimentar como faceta; espelho das queries da API.

## 4. Consequências

- **Build**: 36,7 s → 18,4 s (quente, sem cache) → 18,4 s com cache
  (extract+transform reutilizados; ~16 s poupados por build em entradas
  inalteradas). Artefacto byte-idêntico entre `build` e `build --full`
  exceto `build_metadata` (P5, verificado com comparação de todas as
  tabelas).
- **Artefacto**: 240 730 112 B (trigramas ≈ +2,5 MB); schema 4;
  `integrity_check ok`; 176 testes verdes; golden 96/96 preservados.
- **Semântica de pesquisa**: termos >= 3 chars passam a casar em qualquer
  posição do rótulo ("polpa" → "Curgete, polpa e pele, cozida"); termos
  curtos mantêm a semântica de prefixo. Documentado no docstring da API e
  espelhado no explorer.
- **Determinismo**: fingerprints sobre conteúdos ordenados; a cache nunca
  altera o artefacto (verificado: full vs cached byte-idênticos exceto o
  bloco temporal).
- **IndexedDB**: primeiro load descarrega e guarda; reloads abrem dos
  bytes locais; mudar o schema_version (ou o nome do artefacto) invalida
  a chave e força re-descarga — sem risco de artefacto velho.
- **Não feito** (adiado por âmbito): extract paralelo (descartado acima),
  HTTP-range (F8), mais vistas do explorer (F8), cache de derive/i18n/
  merge/package.