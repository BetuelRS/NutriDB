# NUTRIDB

[![status: pre-alpha](https://img.shields.io/badge/status-pre--alpha-b45309)](PROGRESS.md)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776ab)](pyproject.toml)
[![Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-2ea44f)](LICENSE)

> Uma base de dados de composição alimentar aberta, versionada e auditável.

O NutriDB reúne alimentos de várias fontes, preserva a proveniência de cada
valor nutricional e disponibiliza um Explorer web para pesquisa, comparação e
inspeção humana. O dataset é o produto principal. O Explorer é a forma mais
simples de o compreender; APIs e bibliotecas serão camadas de integração
posteriores.

## Em uma frase

**Dados nutricionais reutilizáveis para aplicações, com a origem de cada número
visível.**

O objetivo é servir aplicações de nutrition tracking, investigação, análise de
alimentos, receitas e outros produtos sem transformar o NutriDB numa aplicação
de saúde ou num diário alimentar.

## O produto

### Dataset

- alimentos e nutrientes num modelo canónico comum;
- valores medidos, ausências e limites preservados sem imputação silenciosa;
- fonte, registo original, código do nutriente, unidade, método e estado de aquisição por valor;
- valores alternativos e divergências entre fontes mantidos para consulta;
- artefactos versionados em SQLite e Parquet.

### Explorer

Uma aplicação web orientada a dados para:

- pesquisar alimentos e nutrientes;
- consultar a ficha nutricional completa de um alimento;
- abrir a proveniência de qualquer valor;
- comparar fontes e identificar divergências;
- perceber porque falta um valor;
- explorar alimentos por grupo e nutriente;
- futuramente, montar uma composição neutra de alimentos e quantidades e ver os totais calculados com os inputs visíveis.

O Explorer não fará aconselhamento clínico nem esconderá incerteza atrás de um
valor único.

### Integrações futuras

Depois de o dataset cumprir os gates de produção:

- API REST;
- biblioteca Python e cliente TypeScript;
- exports JSONL, RDF/JSON-LD e formatos para análise;
- perfis de dados com regras de licença diferentes.

## Estado atual

O projeto está em **pre-alpha**, com uma implementação real do pipeline para a
base europeia inicial:

| Área | Estado atual |
| --- | --- |
| CIQUAL 2025 | Integrada, extraída e mapeada |
| INSA/TCA 7.1 | Integrada, extraída e mapeada |
| Modelo canónico | Parquet com source records e valores tipados |
| Artefacto de leitura | SQLite schema 4 com FTS5 e pesquisa trigram |
| Explorer | Build React/TypeScript funcional; cobertura de produto ainda inicial |
| Qualidade | Suite QA e relatório HTML; hardening de produção em curso |
| Golden/property/CI de release | Ainda em execução na Fase 6 |

O artefacto local atual contém 4 860 conceitos, 230 601 valores canónicos e
391 101 linhas materializadas. Estes números descrevem o build de
desenvolvimento, não uma promessa de release estável.

## Arquitetura

```text
fontes oficiais + registry + mappings + vocab
                    |
                 extract
                    |
       contrato intermédio comum por fonte
                    |
                transform
                    |
             dataset canónico
          /         |          \
       derive     merge        i18n
          \         |          /
             QA + package
                    |
          SQLite + Parquet + Explorer
                    |
             aplicações consumidoras
```

O fluxo preserva a separação entre o registo original, o conceito canónico e o
valor nutricional. A configuração vive em CSV/TOML; o tooling não edita o
registry de fontes.

## Princípios de dados

1. **Proveniência:** nenhum número sem fonte, registo e código de nutriente.
2. **Não fabricação:** cálculos exigem fórmula, inputs e fatores registados.
3. **Ausência tipada:** `not_measured`, `trace`, `below_loq` e outros estados não são zeros silenciosos.
4. **IDs estáveis:** fusões preservam IDs antigos através de tombstones.
5. **Determinismo:** as mesmas entradas devem produzir o mesmo artefacto, exceto metadados temporais isolados.
6. **Licenças:** cada fonte tem análise própria e atribuição verificável.
7. **Tradução com estatuto:** rótulos não revistos não entram no artefacto principal.

## Começar localmente

Requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/) e Node.js 20+
para o Explorer.

```sh
uv sync
uv run nutridb --help
uv run nutridb sources audit
uv run nutridb sources sync
uv run nutridb build --full
uv run nutridb qa
uv run nutridb explorer dev
```

Os dumps oficiais ficam em `sources/cache/` e não entram no Git. O build
precisa de acesso à rede apenas quando esses ficheiros ainda não existem ou
quando se pretende verificar novamente a fonte.

## Verificações de desenvolvimento

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest
npm --prefix explorer run build
```

Fixtures sintéticas estão em `tests/fixtures/`. Valores reais usados como
golden ficam em `tests/golden/` com referência à fonte primária.

## Fontes iniciais

| Fonte | Conteúdo | Licença/regime | Destino |
| --- | --- | --- | --- |
| CIQUAL 2025 | 3 484 alimentos, 74 constituintes | etalab-2.0 | `core` |
| INSA/TCA 7.1 | 1 376 alimentos, componentes portugueses | regime próprio com atribuição | `core` |

Uma nova fonte só entra depois de licença verificada, ADR aprovado, hash fixado,
extractor, mapping, golden e checks de qualidade. A lista completa e as
obrigações de atribuição estão em [`sources/registry.toml`](sources/registry.toml).

## Roadmap

- **P0 - Contrato do produto:** dataset como núcleo, Explorer como interface e workspace neutro sem aconselhamento.
- **P1 - Confiabilidade:** fechar proveniência, ausência, IDs, licenças, determinismo e build externo.
- **P2 - Release de dados:** golden 200, propriedades, QA no CI, manifesto e checksums.
- **P3 - Explorer v1:** `pt-PT` primeiro, `en` depois, pesquisa, ficha, proveniência, comparação e cobertura.
- **P4 - Expansão:** mais fontes europeias, USDA, porções, estados e valores de referência com evidência.
- **P5 - Integração:** API, clientes e exports adicionais.

O plano verificável está em [`PLAN.md`](PLAN.md) e o estado confirmado em
[`PROGRESS.md`](PROGRESS.md). As decisões caras de reverter estão em
[`docs/adr/`](docs/adr/).

## O que não é

- não é um diário alimentar;
- não é um contador de calorias;
- não cria contas ou planos clínicos;
- não substitui profissionais de saúde;
- não inventa valores para preencher lacunas;
- não redistribui produtos de marca sem licença adequada.

Aplicações consumidoras podem usar o dataset para construir essas experiências
por sua conta, respeitando a proveniência e a licença dos dados.

## Contribuir

Leia [`CONTRIBUTING.md`](CONTRIBUTING.md) antes de alterar mappings, vocabulario,
fontes ou valores. Para vulnerabilidades, consulte [`SECURITY.md`](SECURITY.md).

## Licenças

- Código: [Apache-2.0](LICENSE).
- Dados: licenciados por artefacto, segundo a composição das fontes em
  [`sources/registry.toml`](sources/registry.toml).
- Atribuições: [`NOTICE`](NOTICE) e os metadados de cada fonte.
