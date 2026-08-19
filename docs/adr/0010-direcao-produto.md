# ADR-0010 - Direção de produto e fronteiras do NutriDB

- **Estado**: Aprovado
- **Data**: 2026-08-19
- **Fase**: direção de produto

---

## 1. Contexto

O NutriDB começou como um pipeline de composição alimentar e cresceu para
incluir um artefacto SQLite, um Explorer e várias camadas de qualidade. A
intenção de produto agora está definida: o dataset é o núcleo reutilizável;
o Explorer torna esse dataset fácil de descobrir e auditar; outras aplicações
podem construir trackers, receitas ou experiências de planeamento sobre ele.

A `SPEC.md` atual exclui planos alimentares como antiobjetivo. A direção
confirmada permite apenas uma composição neutra no Explorer, sem aconselhamento
ou recomendação clínica. Essa diferença deve ser formalizada na SPEC antes da
implementação dessa vista.

## 2. Decisão

### 2.1 Produto principal

O NutriDB será uma plataforma aberta e versionada de dados de composição
alimentar. O produto principal é o dataset, não uma aplicação de nutrição.

O dataset deve suportar:

- alimentos de múltiplas fontes;
- nutrientes, unidades, estados e bases de quantificação;
- valores medidos, ausências tipadas e valores derivados auditáveis;
- proveniência ao nível do valor;
- alternativas e divergências entre fontes;
- distribuição em SQLite e Parquet na primeira etapa.

### 2.2 Explorer

O Explorer será a interface pública de inspeção humana, com prioridade para
`pt-PT`, depois `en` e, posteriormente, outras variantes. A primeira versão
de produto deve privilegiar pesquisa, ficha alimentar, proveniência,
comparação de fontes e explicação de ausências.

Uma vista futura poderá oferecer um **workspace neutro**: seleção de alimentos,
quantidades e cálculo de totais com fórmula e inputs visíveis. Essa vista não
recomenda dietas, não faz diagnóstico e não cria metas clínicas.

### 2.3 Integrações

API REST, bibliotecas Python/TypeScript, exports semânticos e perfis adicionais
são camadas posteriores. Não bloqueiam a primeira release do dataset + Explorer.

### 2.4 Fontes

CIQUAL 2025 e INSA/TCA 7.1 são a base europeia inicial. A expansão para fontes
nacionais, USDA e produtos de marca é incremental: cada fonte exige ADR de
licença, hash fixado, extractor, mapping, golden e QA. Produtos de marca não
entram automaticamente no `core`.

### 2.5 Fronteiras

Ficam fora do NutriDB core:

- diário alimentar e tracking de utilizadores;
- contas e autenticação de consumidores;
- aconselhamento nutricional ou clínico;
- geração automática de dietas como decisão de saúde;
- imputação ou estimativa de valores ausentes.

## 3. Consequências

- O trabalho imediato concentra-se na confiabilidade do dataset, não em
  multiplicar interfaces ou fontes sem gates.
- A camada de produto pode crescer sem contaminar o modelo canónico com
  regras de recomendação.
- O Explorer precisa de ser intuitivo, mas deve continuar a expor números,
  limites, fontes e incertezas.
- A SPEC §18 precisa de uma emenda documental antes de implementar o
  workspace neutro.
- O roadmap passa a ser: hardening do dataset, release verificável, Explorer
  v1, expansão de fontes e só depois API/clientes/exports.

## 4. Critério de sucesso

O NutriDB está no caminho certo quando um terceiro consegue reconstruir o
artefacto, um consumidor consegue integrá-lo sem o Explorer e uma pessoa
consegue rastrear qualquer valor até à fonte sem ler o código do pipeline.
