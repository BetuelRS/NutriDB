# Contribuir para o NutriDB

Obrigado pelo interesse. O NutriDB é principalmente um projeto de dados: uma
alteração aparentemente pequena num mapping pode mudar milhares de valores.
Todas as contribuições devem privilegiar rastreabilidade e revisão.

## Antes de começar

- Leia [`SPEC.md`](SPEC.md), [`CLAUDE.md`](CLAUDE.md) e os ADRs relevantes.
- Verifique o estado atual em [`PROGRESS.md`](PROGRESS.md).
- Para uma fonte nova, não escreva código antes de existir um ADR de licença aprovado.
- Para alterações de esquema, vocabulário ou identidade, abra primeiro uma proposta de decisão.

## Ambiente

```sh
uv sync
uv run nutridb --help
```

O Explorer requer Node.js 20+:

```sh
npm --prefix explorer ci
npm --prefix explorer run build
```

## Alterações de dados

- Nunca faça commit de dumps em `sources/cache/` ou artefactos em `build/`.
- Mappings, prioridades, overrides e decisões de identidade devem ser CSV/TOML revisáveis.
- Cada valor golden deve apontar para a fonte primária e preservar a forma original.
- Não transforme uma ausência em `0` ou `NULL` sem uma decisão explícita e evidência.
- Fixtures de teste devem ser sintéticas, isoladas e identificadas como tal.
- Não corrija silenciosamente um valor publicado pela fonte; registe a divergência.

## Verificações locais

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest
npm --prefix explorer run build
```

Alterações que envolvam fontes ou o artefacto devem também executar:

```sh
uv run nutridb vocab check
uv run nutridb sources audit
uv run nutridb build --full
uv run nutridb qa
```

## Pull requests

- Explique o problema, a decisão e o impacto nos dados.
- Inclua testes antes de alterar lógica numérica.
- Inclua referências oficiais para licenças, unidades e fatores.
- Separe alterações de código, dados e documentação quando possível.
- Não esconda warnings de qualidade; explique-os ou crie uma tarefa de revisão.
- Atualize `PLAN.md` e `PROGRESS.md` no fecho da sessão.

Use commits convencionais: `feat:`, `fix:`, `test:`, `docs:`, `chore:` ou
`refactor:`.
