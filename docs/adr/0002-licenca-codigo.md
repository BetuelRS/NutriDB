# ADR-0002 — Licença do código do NUTRIDB

- **Data**: 2026-08-15
- **Estado**: Aprovado (revisão humana de 2026-08-15)
- **Decisões relacionadas**: ADR-0001 (§7, A2)

---

## 1. Contexto

A spec (§14) exige escolher entre **AGPL-3.0** e **Apache-2.0** para o código do projeto, e deixa claro que **os dados não seguem o código**: cada artefacto de dados é licenciado pela composição das licenças das fontes que contém. O código a licenciar inclui: pipeline ETL (`src/nutridb`), API, clientes Python/npm, e o explorador web.

## 2. Opções

1. **Apache-2.0** — permissiva, sem obrigação de copyleft para consumidores; patente-safe; compatível com a maioria dos ecossistemas (PyPI, npm, GitHub Actions).
2. **AGPL-3.0** — copyleft forte; qualquer serviço que exponha o software modificado via rede fica obrigado a disponibilizar o código.

## 3. Decisão

**Apache-2.0** para todo o código do repositório.

## 4. Consequências

- Consumidores podem usar o pipeline e os clientes em produtos fechados sem obrigações de divulgação — adequado ao papel do NUTRIDB como infraestrutura de dados consumida por terceiros.
- A separação código/dados mantém-se: os artefactos SQLite/Parquet/JSONL/RDF são licenciados pela composição das fontes de cada perfil (`core`/`extended`), nunca pela licença do código.
- A atribuição e os avisos de licença de fontes (`NOTICE`, tabela no SQLite, página de atribuições) são independentes desta decisão e regem-se pelo `sources/registry.toml`.
- Proibido contribuir código de terceiros AGPL/mais restritivo para dentro do repositório sem revisão.

## 5. Impacto nas fases

- F0: ficheiros de licença (`LICENSE`, `NOTICE`), header no README.
- F7: SBOM e atestação referenciam Apache-2.0 para componentes de software e as licenças de dados por artefacto.