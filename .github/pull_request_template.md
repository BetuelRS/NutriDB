## Resumo

<!-- O que muda e porquê? -->

## Tipo de alteração

- [ ] código
- [ ] dados/mappings/vocabulário
- [ ] documentação
- [ ] CI ou tooling

## Proveniência e impacto

- Fonte/ADR/referência oficial:
- Tabelas ou artefactos afetados:
- Impacto esperado nos valores, ausências ou IDs:

## Verificação

- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy .`
- [ ] `uv run pytest`
- [ ] `npm --prefix explorer run build` (quando aplicável)
- [ ] QA/golden executados (quando aplicável)

## Checklist de integridade

- [ ] Nenhum valor foi inventado ou imputado silenciosamente.
- [ ] Ausências continuam tipadas.
- [ ] Configuração permanece em dados revisíveis.
- [ ] Não foram adicionados dumps ou segredos.
- [ ] `PLAN.md`/`PROGRESS.md` foram atualizados se a tarefa fechou uma etapa.
