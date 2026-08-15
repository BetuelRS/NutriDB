# NUTRIDB

Base de dados de composição alimentar aberta, rastreável e traduzida — distribuída como artefacto versionado com um explorador web.

> Especificação completa e vinculativa: [`SPEC.md`](SPEC.md). Planos e estado: [`PLAN.md`](PLAN.md), [`PROGRESS.md`](PROGRESS.md). Decisões: [`docs/adr/`](docs/adr/).

## Princípios

1. Nenhum valor nutricional é inventado, estimado por IA, ou copiado sem proveniência.
2. A ausência de um valor é um dado de primeira classe, com motivo declarado — nunca um zero silencioso.
3. Uma tradução literal é um bug, não um resultado.

## Como começar

```sh
uv sync
uv run nutridb --help
```

## Licenças

- Código: Apache-2.0 (ver [`LICENSE`](LICENSE)).
- Dados: licenciados por artefacto, conforme a composição das fontes declaradas em `sources/registry.toml` (ver `NOTICE`).