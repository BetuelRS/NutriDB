# PROGRESS.md — estado, decisões pendentes, bloqueios

> Atualizado no fim de cada sessão (regra §17.1). Fonte da verdade operacional: `PLAN.md`; arquitetura: `docs/adr/`.

## Estado atual (2026-08-15)

**Fase 0 — Fundações: concluída** (branch `f0/fundacoes`).

| Tarefa | Estado | Nota |
|---|---|---|
| F0.1 repositório (SPEC.md, git, remote, ignore/attributes, README/LICENSE/NOTICE) | ✅ | remote `origin` → `github.com/BetuelRS/NutriDB.git` (push pendente de credenciais) |
| F0.2 scaffold de diretórios | ✅ | espelha SPEC §3; dirs de dados com README |
| F0.3 projeto uv (py 3.12, deps, ruff, mypy strict) | ✅ | `uv.lock` gerado |
| F0.4 CLI esqueleto (16 comandos + `--version`) | ✅ | stubs falham alto com mensagem e exit 2 |
| F0.5 registry.toml + modelo pydantic + validação | ✅ | `[sources.ciqual]` com condições de ODbL/sha256/artefactos |
| F0.6 `sources audit` | ✅ | relatório rich + contagem por perfil |
| F0.7 `sources sync` / `fetch` | ✅ | gate de hash fixado: unpinned → falha alta; `fetch` imprime hash para pin manual (P8) |
| F0.8 CI (GitHub Actions) | ✅ | runs on push/PR; requer remote para executar |
| F0.9 ADR-0001/0002 + PROGRESS.md | ✅ | ADR-0003 agenda na F1.0 |

**Gate de aceitação F0 (SPEC §16)**: `nutridb --help` exit 0 ✅ · CI verde (verificado localmente: ruff/mypy/pytest) ✅ · ADR aprovado ✅.

## Decisões em aberto

- Nenhuma para F1 (A1–A20 resolvidas em 2026-08-15; ADR-0001 §7).

## Bloqueios / pendências

- **CI no GitHub**: o push de `f0/fundacoes` foi feito (2026-08-15); confirmar o run `checks` no Actions.
- **F1.0 / ADR-0003**: resolver URL exata do ficheiro CIQUAL 2025 (Excel) no entrepot recherche.data.gouv, fixar `sha256` e `filename` no registry (download + revisão antes de fixar — P6/P8).

## Histórico de sessões

- **2026-08-15**: arranque. SPEC lida, ADR-0001/0002, PLAN, ambiguidades resolvidas por aprovação humana; Fase 0 implementada e verificada (19 testes, lint e mypy verdes).