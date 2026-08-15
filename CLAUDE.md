# CLAUDE.md — instruções operacionais do agente

Condensado das regras de trabalho (SPEC §17) e das decisões aprovadas (docs/adr/0001 §7).

## Regras invioláveis (SPEC §1)

- **P1** Proveniência ao nível do valor — nenhum número sem fonte, registo, código de nutriente e tipo de aquisição.
- **P2** Nunca fabricar — sem imputação implícita; `calculated` exige fórmula e inputs registados.
- **P3** Ausência tipada — `not_measured | not_detected | below_loq | trace | not_applicable | assumed_zero`; nunca aplanar para `0`/`NULL`.
- **P4** IDs eternos — ULID `nfx_...` atribuído uma vez; fusões produzem lápides com sucessor.
- **P5** Builds determinísticos — byte-idênticos exceto bloco temporal `build_metadata`.
- **P6** Licenças auditadas antes de código — ADR de licença por fonte antes do extractor; verificar sempre na fonte oficial.
- **P7** Tradução com estatuto — `mt_unreviewed` nunca entra em `core` nem é exibido sem marcação.
- **P8** Configuração como dados — prioridades, mapeamentos, correções e fusões em CSV/TOML revisíveis em diff; o tooling nunca edita `sources/registry.toml`.
- **P9** Falhar alto — o que não se compreende faz o build falhar e vai para fila de revisão.
- **P10** Reproduzibilidade externa — um comando (`uv run nutridb build`) reconstrói o artefacto.

## Regras de trabalho (SPEC §17)

1. `PLAN.md` e `PROGRESS.md` atualizados no fim de cada sessão.
2. ADR para decisões caras de reverter (contexto, opções, decisão, consequências).
3. Testes primeiro em tudo o que envolve correção numérica.
4. Commits atómicos, convencionais (`feat:`/`fix:`/`test:`/`docs:`/`chore:`/`refactor:`), uma fase por branch (`f0/...`, `f1/...`).
5. Paralelizar só o paralelizável — nunca decisões de esquema.
6. **Parar e perguntar**: licença ambígua; fusão que afete >500 registos; alterar o vocabulário depois de congelado; fonte que exija contacto humano (INSA).
7. Nunca inventar um valor nutricional — nem para testes (fixtures marcadas `synthetic`, isoladas).
8. Sem dumps no git — `registry.toml` fixa URL e hash; `nutridb sources sync` descarrega.
9. Dúvidas de composição alimentar → documentação EuroFIR, INFOODS, FAO.
10. Preferir adiar funcionalidade a comprometer princípios.

## Decisões aprovadas (ADR-0001 §7)

- Código sob **Apache-2.0** (ADR-0002); dados licenciam-se por artefacto.
- Primeira fonte: **CIQUAL 2025** (3 484 alimentos, 74 constituintes, etalab-2.0 → `core`); XLS via engine com fallback XML; hash fixado no ADR-0003 (F1.0) após download + revisão.
- `vocab/nutrients.csv` ~250 tagnames INFOODS, congelado na F1 (mudar = migração + ADR).
- Ausência materializada por cobertura (fonte, nutriente) + flags explícitas; energia com método registado.
- Pesquisa F1: motor FTS5 + página mínima (sql.js/WASM, sem HTTP-range — F8).
- Docs em pt-PT; identificadores/mensagens de código em EN.
- `_unmapped/` esvaziado é gate; `mappings/links.csv` 1:1 automático em F1; semver `0.1.0`.

## Comandos

```sh
uv run nutridb --help          # CLI
uv run ruff format . && uv run ruff check .   # lint
uv run mypy .                  # tipos (strict)
uv run pytest                  # testes
uv run nutridb sources sync    # descarrega + verifica hashes (rede)
uv run nutridb sources audit   # relatório de licenças
```

Fixtures sintéticas → `tests/fixtures/` (marcar `synthetic` no nome/conteúdo). Golden → `tests/golden/` (valores reais da fonte, com referência).