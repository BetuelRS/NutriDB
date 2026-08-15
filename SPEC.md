# NUTRIDB — Especificação de Construção

> **Documento de missão para um agente autónomo.**
> Guarda este ficheiro como `SPEC.md` na raiz de um repositório vazio.
> Mensagem de arranque para o Claude Code:
>
> ```
> Lê SPEC.md por inteiro antes de escrever uma linha de código.
> Não implementes nada ainda. Produz primeiro:
>   1. docs/adr/0001-visao-geral.md com a tua interpretação da arquitetura
>   2. PLAN.md com o desdobramento da Fase 0 e Fase 1 em tarefas verificáveis
>   3. Uma lista de todas as ambiguidades e decisões que precisas que eu confirme
> Espera pela minha aprovação antes de avançar para código.
> ```

---

## 0. O que é isto

O NUTRIDB é uma **base de dados de composição de alimentos** — não é uma aplicação de nutrição, não é um contador de calorias, não tem utilizadores. É infraestrutura de dados: o artefacto que outras aplicações consomem.

O objetivo é construir a base de dados de composição alimentar aberta mais rigorosa, mais rastreável e mais bem traduzida que existe, e distribuí-la como ficheiro versionado com um explorador web que permite inspecionar cada valor individual e saber exatamente de onde veio.

**Três frases que definem o projeto:**

1. Nenhum valor nutricional é inventado, estimado por IA, ou copiado sem proveniência.
2. A ausência de um valor é um dado de primeira classe, com motivo declarado — nunca um zero silencioso.
3. Uma tradução literal é um bug, não um resultado.

---

## 1. Princípios invioláveis

Estes princípios têm precedência sobre prazos, elegância de código e cobertura de catálogo. Se um princípio colidir com uma tarefa, o princípio ganha e escreves um ADR a explicar.

| # | Princípio | Consequência prática |
|---|---|---|
| P1 | **Proveniência ao nível do valor** | Cada célula da matriz nutricional guarda de que fonte, que registo, que código de nutriente e que tipo de aquisição veio. Não basta saber a fonte do alimento. |
| P2 | **Nunca fabricar** | Não existe imputação implícita. Valores derivados por cálculo são possíveis, mas marcados como `calculated` e com a fórmula e os inputs registados. |
| P3 | **Ausência tipada** | Distingue `not_measured`, `not_detected`, `below_loq`, `trace`, `not_applicable`, `assumed_zero`. Achatar tudo para `0` ou `NULL` é destruição de informação. |
| P4 | **IDs eternos** | Um identificador publicado nunca é reutilizado nem alterado. Fusões e divisões produzem lápides (`tombstones`) com sucessor. |
| P5 | **Builds determinísticos** | Duas execuções sobre as mesmas fontes produzem ficheiros byte-idênticos (exceto bloco de metadados temporal isolado). |
| P6 | **Licenças auditadas antes de código** | Nenhuma fonte entra no pipeline sem um ADR de análise de licença aprovado. O build separa artefactos por compatibilidade de licença. |
| P7 | **Tradução com estatuto** | Cada rótulo linguístico carrega o seu estatuto de confiança. Tradução automática não revista nunca entra no artefacto principal nem é apresentada sem marcação. |
| P8 | **Configuração como dados** | Prioridades, mapeamentos, correções e decisões de fusão vivem em ficheiros CSV/TOML revisíveis em diff, não em condicionais Python. |
| P9 | **Falhar alto** | O que o pipeline não compreende faz o build falhar e vai para uma fila de revisão. Nunca é descartado em silêncio. |
| P10 | **Reprodutibilidade externa** | Um terceiro com o repositório e ligação à internet reconstrói o artefacto idêntico com um comando. |

---

## 2. Entregáveis

Ao fim do projeto existem:

**Artefactos de dados**
- `nutridb-core-X.Y.Z.sqlite` — apenas fontes com licença permissiva, redistribuível sem restrições
- `nutridb-extended-X.Y.Z.sqlite` — inclui fontes com share-alike ou não-comercial, licenciado em conformidade
- `nutridb-lite-X.Y.Z.sqlite` — subconjunto otimizado para embutir em apps móveis (< 25 MB, macros + micros essenciais + pesquisa)
- Conjunto Parquet particionado, para análise
- Dumps JSONL por tabela
- Export RDF/Turtle e JSON-LD alinhado com a ontologia FoodOn
- `SHA256SUMS`, SBOM e atestação de proveniência do build

**Software**
- Pipeline ETL reprodutível com CLI
- `nutridb` — pacote Python tipado com cliente de leitura, publicado no PyPI
- `@nutridb/client` — pacote npm com tipos TypeScript
- API REST com OpenAPI 3.1
- **NUTRIDB Explorer** — aplicação web estática que expõe a base de dados inteira

**Documentação**
- Dicionário de dados gerado automaticamente a partir do esquema
- Registo de decisões arquiteturais (ADRs)
- Relatório de qualidade por build, em HTML
- Página de atribuições gerada a partir do registo de licenças
- Guia de contribuição para tradutores e revisores

---

## 3. Estrutura do repositório

```
nutridb/
├── SPEC.md                     # este documento
├── CLAUDE.md                   # instruções operacionais do agente
├── PLAN.md                     # plano vivo, atualizado a cada sessão
├── PROGRESS.md                 # estado, decisões pendentes, bloqueios
│
├── sources/
│   ├── registry.toml           # catálogo de fontes: URL, licença, hash, versão
│   └── cache/                  # dumps descarregados (gitignored)
│
├── vocab/                      # ← vocabulário canónico. Núcleo intelectual.
│   ├── nutrients.csv           # ~250 nutrientes canónicos, tagnames INFOODS
│   ├── nutrient_groups.csv
│   ├── units.csv
│   ├── value_types.csv
│   ├── acquisition_types.csv
│   ├── analytical_methods.csv
│   ├── food_groups.csv         # taxonomia própria, mapeada a FoodEx2
│   └── facets/                 # vocabulário facetado para nomes compostos
│       ├── base_terms.csv
│       ├── parts.csv
│       ├── states.csv
│       ├── cooking_methods.csv
│       ├── media.csv
│       ├── treatments.csv
│       └── qualifiers.csv
│
├── mappings/                   # ← o trabalho real. Tudo revisível em diff.
│   ├── nutrients/
│   │   ├── ciqual.csv          # (código fonte) → (nutriente canónico, fator)
│   │   ├── usda_fdc.csv
│   │   ├── insa.csv
│   │   └── ...
│   ├── foodgroups/
│   ├── source_priority.csv     # prioridade por (locale, grupo, nutriente)
│   ├── overrides.csv           # correções manuais, cada uma com justificação
│   ├── links.csv               # concept_id ↔ (fonte, id_fonte), adjudicado
│   ├── tombstones.csv
│   └── _unmapped/              # gerado pelo build; esvaziar é obrigatório
│
├── i18n/
│   ├── locales.toml            # cadeias de fallback, variantes regionais
│   ├── glossary/               # terminologia por locale, revista à mão
│   │   ├── pt-PT.csv
│   │   ├── pt-BR.csv
│   │   ├── en.csv
│   │   └── ...
│   ├── labels/                 # rótulos por conceito e locale, com estatuto
│   ├── divergences.csv         # pt-PT vs pt-BR, en-GB vs en-US
│   ├── untranslatable.csv      # conceitos sem equivalente + glosa
│   └── review_queue/
│
├── reference/                  # valores de referência dietéticos
│   ├── efsa_drv.csv
│   ├── iom_dri.csv
│   ├── nnr.csv
│   └── who_fao.csv
│
├── derivations/
│   ├── retention_factors.csv   # perdas de nutrientes por método de cozedura
│   ├── yield_factors.csv       # variação de peso na confeção
│   ├── densities.csv           # g/ml para conversão por volume
│   └── portions.csv            # medidas caseiras curadas
│
├── src/nutridb/
│   ├── sources/                # um extractor por fonte, interface comum
│   ├── vocab/
│   ├── identity/               # resolução de entidades
│   ├── i18n/
│   ├── merge/
│   ├── derive/
│   ├── quality/
│   ├── package/                # escritores sqlite/parquet/jsonl/rdf
│   ├── api/
│   └── cli.py
│
├── explorer/                   # aplicação web
├── tests/
│   ├── unit/
│   ├── property/               # Hypothesis
│   ├── golden/                 # 200 alimentos verificados à mão
│   └── integration/
├── docs/
│   ├── adr/
│   └── site/                   # MkDocs Material
└── build/                      # artefactos (gitignored)
```

---

## 4. Fontes de dados

**Antes de escrever o extractor de qualquer fonte, produz um ADR** com: URL oficial, licença exata e sua versão, se exige atribuição, se é share-alike, se restringe uso comercial, formato e volume, cobertura de nutrientes, e conclusão sobre em que artefacto pode entrar (`core`, `extended`, ou nenhum). Verifica sempre a licença na fonte oficial — não confies em memória, nem na minha, nem na tua.

### Camada 1 — Tabelas nacionais de composição

| Fonte | País | Notas |
|---|---|---|
| **CIQUAL** (ANSES) | França | Maior tabela europeia, base do catálogo. Boa cobertura de micros. |
| **USDA FoodData Central** | EUA | Quatro sub-conjuntos distintos, tratar como fontes separadas: **SR Legacy**, **Foundation Foods** (com dados de amostragem e laboratório), **FNDDS** (pesos de porções domésticas), **Branded** (fora do core). |
| **INSA — TCA** | Portugal | Prioridade máxima para pt-PT. Requer pedido de autorização e referenciação. |
| **CoFID** (McCance & Widdowson) | Reino Unido | Medições sérias, longa série histórica. |
| **BEDCA** | Espanha | Dieta ibérica, complementa a CIQUAL. |
| **Frida** (DTU) | Dinamarca | Excelente em ácidos gordos. |
| **Fineli** (THL) | Finlândia | Boa estrutura, componentes bem documentados. |
| **Livsmedelsdatabasen** | Suécia | |
| **Matvaretabellen** | Noruega | |
| **Canadian Nutrient File** | Canadá | |
| **AUSNUT / NUTTAB** (FSANZ) | Austrália | |
| **FOODfiles** | Nova Zelândia | |
| **TBCA** (USP) | Brasil | Essencial para pt-BR. Verificar cláusula não-comercial. |
| **TACO** (UNICAMP) | Brasil | Mais antiga, mas cobre alimentos ausentes da TBCA. |
| **STFCJ** (MEXT) | Japão | Cobre alimentos ausentes de todas as tabelas ocidentais. |
| **IFCT** | Índia | |
| **FAO/INFOODS** regionais | Vários | Tabelas de África Ocidental, ASEAN, LATINFOODS. |

### Camada 2 — Componentes especializados

- **USDA Table of Nutrient Retention Factors** — retenção por método de confeção
- **USDA Table of Cooking Yields** — variação de peso
- **Phenol-Explorer** — polifenóis
- Bases de flavonoides e isoflavonas do USDA
- Tabelas de índice glicémico: **verificar licença com cuidado**, a maioria é proprietária

### Camada 3 — Terminologia e classificação

- **FoodEx2** (EFSA) — classificação hierárquica com facetas
- **LanguaL** — tesauro facetado; várias tabelas nacionais já trazem códigos LanguaL, o que o torna a melhor ponte entre fontes
- **AGROVOC** (FAO) — tesauro multilingue com terminologia agrícola real em dezenas de línguas
- **Wikidata** — Q-IDs com rótulos e sinónimos multilingues revistos por humanos
- **FoodOn** — ontologia formal, para o export semântico

### Camada 4 — Valores de referência

EFSA DRV, IOM DRI, Nordic Nutrition Recommendations, WHO/FAO. Guardados por (nutriente, sexo, faixa etária, estado fisiológico, autoridade). Nunca um único número global.

### Fora do build

**Open Food Facts** — a licença ODbL é share-alike e pode obrigar a base derivada a herdar a licença. Não entra em `core` nem em `extended`. Se quiseres dados de produtos de marca, é consumo por API em tempo real do lado do cliente, com armazenamento local — nunca redistribuído no artefacto.

Qualquer site cujos termos proíbam recolha automática também está fora, sem exceção e sem discussão.

---

## 5. Vocabulário canónico de nutrientes

Esta é a decisão que condiciona tudo o resto. Congela-a cedo e trata alterações como mudanças de esquema com migração.

**Usa os `tagnames` INFOODS como identificadores canónicos.** É a norma internacional, resolve ambiguidades que os nomes comuns não resolvem, e torna o mapeamento entre fontes verificável em vez de intuitivo.

Alvo: **~250 componentes**, agrupados assim:

- **Energia** — `ENERC_KCAL`, `ENERC_KJ`. Guarda ambos, e guarda **como foram obtidos**: fatores de Atwater gerais, fatores específicos, ou declarados pela fonte. A CIQUAL e o USDA calculam energia de maneira diferente; se não registares o método, tens divergências silenciosas entre fontes que ninguém consegue explicar depois.
- **Proximados** — `WATER`, `PROCNT`, `NT`, `FAT`, `FATCE`, `CHOAVL`, `CHOAVLDF`, `CHOCDF`, `FIBTG`, `FIBC`, `ASH`, `ALC`
- **Hidratos discriminados** — `SUGAR`, `FRUS`, `GLUS`, `SUCS`, `LACS`, `MALS`, `GALS`, `STARCH`, `POLYL`, fibra solúvel e insolúvel
- **Lípidos** — `FASAT`, `FAMS`, `FAPU`, `FATRN`, `CHOLE`, mais ácidos gordos individuais em notação `FnnDnnNn` (`F18D2CN6`, `F18D3N3`, `F20D5N3`, `F22D6N3`, e o resto do perfil)
- **Minerais** — `CA`, `FE`, `MG`, `P`, `K`, `NA`, `ZN`, `CU`, `MN`, `SE`, `ID`, `CL`, `F`, `CR`, `MO`, `NACL`
- **Vitaminas lipossolúveis** — `VITA_RAE`, `RETOL`, `CARTB`, `CARTA`, `CRYPXB`, `LUTN`, `ZEA`, `LYCPN`, `VITD`, `CHOCAL`, `ERGCAL`, `VITE`, `TOCPHA`, `TOCPHB`, `TOCPHG`, `TOCPHD`, `TOCTRA`, `VITK`, `VITK1`, `VITK2`
- **Vitaminas hidrossolúveis** — `THIA`, `RIBF`, `NIA`, `NIAEQ`, `VITB6A`, `PANTAC`, `BIOT`, `FOL`, `FOLDFE`, `FOLFD`, `FOLAC`, `VITB12`, `VITC`, `CHOLN`
- **Aminoácidos** — os 20, mais triptofano tratado à parte pela sua relação com a niacina
- **Outros** — `CAFFN`, `THEBRN`, esteróis vegetais, betaína

Regras:
- Uma unidade canónica por nutriente, imutável. Fatores de conversão vivem no mapeamento, nunca no extractor.
- Equivalentes (`VITA_RAE`, `NIAEQ`, `FOLDFE`) guardam-se **calculados e declarados em separado**, com a fórmula usada.
- Cada nutriente declara relações de agregação (`FASAT` é soma de quais componentes) para o motor de qualidade poder validar.

---

## 6. Identidade e resolução de entidades

O problema: "Chicken, broilers or fryers, breast, meat only, cooked, roasted" (USDA), "Poulet, blanc, cuit au four" (CIQUAL) e "Frango, peito, sem pele, assado" (INSA) são o mesmo conceito? Provavelmente. Mas provavelmente não é suficiente.

**Modelo de três níveis:**

1. **`source_record`** — um registo tal como existe na fonte, imutável, nunca fundido
2. **`concept`** — a entidade canónica, com ID próprio e estável
3. **`link`** — a associação entre os dois, com pontuação, método e estatuto de adjudicação

**Pipeline de ligação:**

1. **Blocking** — reduz o espaço de comparação por grupo alimentar, código FoodEx2 e assinatura de nome
2. **Sinais de candidatura**, combinados e nunca usados isoladamente:
   - Códigos **LanguaL** partilhados (o sinal mais forte disponível)
   - Correspondência **FoodEx2** ao nível do termo base
   - Alinhamento **Wikidata** / **AGROVOC**
   - Similaridade de embeddings multilingues sobre o nome
   - Distância no **vetor nutricional** — como confirmação ou como veto, nunca como decisor
   - Concordância de facetas (estado, parte, método de confeção)
3. **Adjudicação** — acima de um limiar alto, proposta automática; na zona cinzenta, fila humana. **Nenhuma fusão acontece sem ficar registada em `mappings/links.csv`.** Se a decisão não está no git, não aconteceu.
4. **Avaliação** — conjunto dourado de 500 pares rotulados à mão, com precisão e recall reportados por build. Uma regressão de recall bloqueia o release.

**Geração de IDs:** ULID prefixado (`nfx_01J...`) atribuído uma única vez e registado. Nunca derivado de conteúdo mutável. Fusão de dois conceitos gera lápide do ID absorvido com apontador para o sucessor, e o ID antigo continua a resolver para sempre.

---

## 7. Multilinguismo — a parte difícil

Este capítulo é o que separa este projeto de todos os outros. Lê-o duas vezes.

### O problema

Traduzir "cottage cheese" para "requeijão" é errado — são produtos diferentes. Traduzir "broa" para "cornbread" é errado — a broa portuguesa não é o cornbread americano. Traduzir "courgette" para "abobrinha" está certo em pt-BR e errado em pt-PT, onde é "curgete". Uma tradução literal produz um catálogo que parece completo e está subtilmente errado em milhares de sítios, que é pior do que estar visivelmente incompleto.

### Arquitetura: composição facetada

Um nome de alimento não é uma frase. É uma estrutura:

```
termo_base + parte + estado + método_confeção + meio + tratamento + qualificadores
```

- `Frango` + `peito` + `sem pele` + `assado`
- `Atum` + `—` + `enlatado` + `—` + `em óleo` + `escorrido`
- `Leite` + `—` + `—` + `—` + `—` + `—` + `meio-gordo, UHT`

**Consequência:** traduzes à mão umas **600 facetas** por locale — não 50 000 nomes. Os termos base (~8 000) obtêm-se em grande parte de Wikidata e AGROVOC, que já têm terminologia humana revista, e o resto passa por revisão. A composição final é feita por **templates gramaticais por língua**, porque a ordem e a concordância mudam: o português precisa de género e de preposições que o inglês não usa.

Guarda sempre a **forma composta** e a **forma nativa original** da fonte. Nunca deites fora o nome original.

### Estatuto de cada rótulo

Toda a entrada de `i18n/labels/` carrega um estatuto:

| Estatuto | Significado |
|---|---|
| `native` | Veio de uma tabela nacional escrita nessa língua. Autoridade máxima. |
| `official` | Tradução oficial publicada por autoridade competente. |
| `curated` | Composta por facetas revistas, ou traduzida e verificada por humano. |
| `mt_reviewed` | Tradução automática que passou revisão humana. |
| `mt_unreviewed` | Tradução automática crua. **Nunca entra no `core`. Nunca é mostrada sem marcação visível.** |
| `borrowed` | Sem equivalente na língua de destino: mantém-se o nome original com glosa. |

### Intraduzíveis

Ficheiro próprio, `i18n/untranslatable.csv`. Quando um conceito não tem equivalente, a saída é o nome nativo mais uma glosa curta, e opcionalmente uma ligação a um conceito aproximado **explicitamente marcada como não-equivalente**:

```
broa de milho  →  en: "broa (Portuguese dense maize bread)"
                  aproximado: cornbread [NÃO EQUIVALENTE]
```

Isto é preferível a uma tradução limpa e falsa. A honestidade do catálogo é a funcionalidade.

### Variantes regionais

Locale é língua **mais** região. Cadeia de fallback declarada em `i18n/locales.toml`: `pt-PT → pt → en`. Um ficheiro `divergences.csv` regista pares onde pt-PT e pt-BR divergem — ananás/abacaxi, brócolos/brócolis, curgete/abobrinha, chávena/xícara — e o build **falha** se um rótulo `pt` genérico for usado onde existe divergência conhecida.

Locales alvo mínimos: `pt-PT`, `pt-BR`, `en-GB`, `en-US`, `es-ES`, `fr-FR`, `de-DE`, `it-IT`. Arquitetura preparada para mais sem alterações de esquema.

### Fluxo de tradução

1. Candidato gerado por composição de facetas ou por MT
2. **Verificação de restrições** — cumpre o glossário? viola algum mapeamento proibido? (`cottage cheese ≠ requeijão` está codificado como proibição)
3. **Retro-tradução** e comparação com o original
4. **Adjudicação por LLM** com critérios explícitos, produzindo uma pontuação e uma justificação
5. **Fila de revisão humana**, ordenada por `frequência de uso × grau de desacordo` — revê-se primeiro o que mais aparece e mais duvidoso está
6. Decisão escrita em CSV, versionada, com autor e data

Cada passo fica guardado. Uma tradução aprovada tem histórico auditável.

### Pesquisa multilingue

- Coluna normalizada sem acentos e em minúsculas, por locale (`açúcar` → `acucar`)
- FTS5 com tokenizador adequado a cada língua
- Sinónimos e nomes coloquiais numa tabela própria, pesquisáveis mas não exibidos como nome principal
- Tolerância a erros de escrita por distância de edição, com limiar por comprimento
- Pesquisa cruzada: escrever "chicken" encontra alimentos cujo rótulo pt-PT é "frango"

---

## 8. Esquema de armazenamento

Princípio: **normalizado como verdade, desnormalizado como conveniência.** As tabelas canónicas são estritamente normalizadas; vistas materializadas e uma tabela larga pré-calculada existem para leitura rápida, geradas no build, nunca editadas.

Tabelas centrais (nomes indicativos, o desenho fino é teu):

```
source                    fonte, versão, licença, hash, data de recolha
source_record             registo cru, JSON preservado integralmente
concept                   entidade canónica, id estável
concept_link              concept ↔ source_record, com estatuto de adjudicação
concept_classification    FoodEx2, LanguaL, Wikidata, AGROVOC, FoodOn
concept_facet             decomposição facetada
label                     concept × locale × estatuto × texto × texto_normalizado
nutrient                  vocabulário canónico
nutrient_relation         relações de agregação para validação
value                     ⟵ a tabela que importa
portion                   medidas caseiras, gramas, fonte
density
derivation                registo de valores calculados: fórmula, inputs, fatores
reference_value           DRV/DRI por autoridade, sexo, idade, estado
tombstone
build_metadata
```

A tabela `value` guarda, por cada célula:

```
concept_id, nutrient_id,
value, unit,
value_type          (measured | calculated | trace | not_detected |
                     below_loq | not_measured | not_applicable | assumed_zero)
acquisition_type    (analysed | calculated | borrowed | imputed | declared)
source_id, source_record_id, source_nutrient_code,
n_samples, standard_deviation, min_value, max_value,
analytical_method,
confidence_score,
derivation_id       (não nulo se calculado)
basis               (per_100g_edible | per_100ml | dry_matter)
```

Isto é a diferença entre uma base de dados e uma folha de cálculo com pretensões. Torna possível responder à pergunta *"porque é que este alimento diz 0,4 mg de ferro?"* com *"análise laboratorial do USDA Foundation Foods, 12 amostras, desvio-padrão 0,08, método AOAC"* — em vez de um encolher de ombros.

**Otimização SQLite:** `page_size` afinado para pedidos HTTP por intervalo, índices cobertos para os padrões de consulta do explorador, FTS5 externo por locale, `VACUUM` e `ANALYZE` no fim do build, ficheiro imutável sem WAL.

---

## 9. Fusão e prioridades

`mappings/source_priority.csv` define a ordem de preferência por **(locale, grupo alimentar, nutriente)** — não uma ordem global. O INSA vence para alimentos portugueses; o USDA Foundation vence para minerais onde tem amostragem laboratorial; a CIQUAL vence em cobertura geral. Estas nuances são dados, não código.

Regras de fusão:

- Um conceito recolhe valores de todas as fontes ligadas. O valor **preferido** é escolhido por prioridade; os restantes **permanecem na base de dados** como valores alternativos consultáveis.
- Nunca se calcula média entre fontes. Média de duas medições incompatíveis é uma terceira medição errada com aparência de consenso.
- Divergências acima de um limiar (por exemplo 30% entre fontes para o mesmo nutriente) geram um sinalizador visível no explorador em vez de serem resolvidas em silêncio.
- `overrides.csv` permite forçar um valor, e **exige** coluna de justificação preenchida. O build rejeita override sem justificação.

---

## 10. Derivações

Só se calcula um alimento derivado quando não existe medição direta, e o resultado é sempre marcado como tal, com a cadeia de cálculo registada em `derivation`.

- **Confeção** — aplicar fatores de retenção de nutrientes e fatores de rendimento para obter "cozido a partir de cru"
- **Receitas** — seguir o procedimento de cálculo de receitas do EuroFIR, com perdas por ingrediente
- **Por volume** — usar a tabela de densidades para produzir valores por 100 ml em líquidos
- **Porções** — pesos de medidas caseiras, com os dados do FNDDS mais uma tabela curada para alimentos portugueses, que nenhuma fonte internacional cobre bem
- **Base seca** — permitir recálculo em matéria seca, indispensável para comparar fontes com teores de água diferentes

---

## 11. Motor de qualidade

Suite de validação executada em cada build, com relatório HTML. Cada verificação tem severidade: `error` bloqueia o release, `warning` entra no relatório, `info` alimenta métricas.

**Coerência interna**
- Soma dos proximados (água + proteína + gordura + hidratos + fibra + cinzas + álcool) entre 97 e 103 g/100 g
- Energia recalculada a partir dos macronutrientes dentro de ±5% do valor declarado
- Σ ácidos gordos ≤ gordura total × 1,02
- Σ açúcares individuais ≤ açúcares totais × 1,02 ≤ hidratos disponíveis × 1,02
- Σ aminoácidos entre 85% e 115% da proteína total
- Sal ≈ sódio × 2,5
- Vitamina A RAE consistente com retinol e carotenoides
- Nenhum valor negativo; nenhuma unidade fora do domínio do nutriente

**Coerência externa**
- Z-score por (nutriente, grupo alimentar); |z| > 4 vai para revisão
- Comparação entre fontes para o mesmo conceito, divergências reportadas
- Comparação contra a versão anterior: alterações bruscas sinalizadas

**Integridade estrutural**
- Sem órfãos, sem violações de chave estrangeira
- Todos os IDs do release anterior resolvem ou têm lápide com sucessor
- `mappings/_unmapped/` vazio
- Todo o rótulo `mt_unreviewed` ausente do artefacto `core`
- Determinismo: dois builds consecutivos com hash idêntico

**Testes dourados**
- 200 alimentos verificados à mão contra a fonte primária impressa ou oficial. Qualquer desvio é erro. Este conjunto é a consciência do projeto.

**Propriedades (Hypothesis)**
- Conversões de unidade são reversíveis
- Fusão é idempotente
- Ordem de processamento das fontes não altera o resultado

---

## 12. NUTRIDB Explorer

Aplicação web **estática**, alojável em GitHub Pages sem servidor. A base de dados completa é consultável no cliente através de SQLite compilado para WASM com pedidos HTTP por intervalo de bytes — descarregam-se dezenas ou centenas de kilobytes por consulta, não a base inteira. Fallback para a API REST quando disponível.

### Vistas obrigatórias

1. **Pesquisa** — instantânea, insensível a acentos, multilingue, tolerante a erros; facetas por grupo, fonte, locale, intervalos de nutrientes; atalho de teclado, navegação sem rato
2. **Ficha do alimento** — matriz nutricional **completa**, agrupada e colapsável; alternador de base (por 100 g / por porção / por 100 kcal / matéria seca); percentagem de DRV configurável por perfil demográfico; cada valor com chip de proveniência clicável
3. **Painel de proveniência** — abre a partir de qualquer valor e mostra fonte, registo de origem, código de nutriente na fonte, tipo de aquisição, n, desvio-padrão, método analítico, e a cadeia de derivação se aplicável
4. **Comparação entre fontes** — o mesmo conceito lado a lado em todas as fontes ligadas, com divergências realçadas por magnitude
5. **Comparador de alimentos** — até 6 alimentos em paralelo, com diferenças destacadas
6. **Explorador de nutrientes** — ordenar todos os alimentos por qualquer nutriente, com filtros; "quais os 50 alimentos com mais selénio por 100 kcal"
7. **Cobertura** — mapa de calor nutriente × fonte, e a página que responde a *porque falta este valor*, distinguindo os tipos de ausência
8. **Consola de tradução** — fila de revisão, original e candidato lado a lado, aprovar/rejeitar/editar; a saída é um patch CSV descarregável, pronto para pull request
9. **Consola de resolução de entidades** — clusters candidatos, evidência por sinal, fundir/separar; saída igualmente como patch
10. **Diferenças entre versões** — o que mudou entre dois builds, ao nível do valor
11. **Dicionário de dados** — gerado do esquema, com todos os nutrientes, códigos e listas controladas
12. **Atribuições** — gerada do registo de licenças, cumprindo os requisitos de cada fonte
13. **Playground SQL** — consulta livre em modo leitura, com exemplos guardados. É a demonstração mais forte de que a base de dados é real.

### Direção de design

Densa, orientada a dados, para quem quer ler números. Referência mental: um bom terminal financeiro ou um site de referência científica — **não** uma app de fitness. Numerais tabulares e monoespaçados para alinhamento em coluna. Hierarquia por tipografia e espaçamento, não por caixas coloridas e sombras. Tema claro e escuro, ambos deliberados. Nada de cartões arredondados pastel, nada de gradientes decorativos, nada de dashboard genérico.

Antes de escrever a UI, consulta a skill `frontend-design` disponível no ambiente.

**Stack:** React + TypeScript + Vite, TanStack Router e TanStack Table, Tailwind. Sem bibliotecas de componentes pesadas. Virtualização obrigatória em qualquer lista longa. Acessibilidade AA, navegável inteiramente por teclado, URLs partilháveis para qualquer estado de vista.

---

## 13. API

FastAPI com OpenAPI 3.1, cliente TypeScript gerado. Versionada em `/v1`. Endpoints para pesquisa, conceito, valores, proveniência, comparação, nutrientes, referências, e um endpoint de consulta estruturada. Paginação por cursor. Caching agressivo — os dados são imutáveis por versão, o que torna isto trivial.

Adicionalmente, um **dump estático de JSON** por conceito, para quem quer consumir sem servidor nenhum.

---

## 14. Licenciamento e conformidade

- `sources/registry.toml` é a fonte de verdade: cada fonte declara licença, versão, exigência de atribuição, share-alike, restrição comercial, e artefacto de destino
- O empacotador **recusa** incluir num artefacto qualquer fonte incompatível com a licença declarada desse artefacto. Isto é um teste automatizado, não uma boa intenção.
- Atribuições geradas automaticamente para: `NOTICE`, tabela dentro do SQLite, página do explorador, README
- Código sob AGPL-3.0 ou Apache-2.0 (decide num ADR); dados sob a licença resultante da composição de fontes de cada artefacto
- O INSA exige autorização e referenciação — documenta o pedido, a resposta e a forma de citação exigida

---

## 15. Stack técnica

**Obrigatório**
- Python 3.12+, gerido com `uv`
- `ruff` (lint + format), `mypy --strict`, sem exceções não justificadas
- `pydantic` v2 para todos os modelos de dados
- `duckdb` para as transformações — SQL sobre CSV e Parquet, rápido e legível
- `polars` onde for necessário processamento em memória
- `typer` para a CLI, `rich` para saída, `structlog` para logs estruturados
- `pytest` + `hypothesis`
- Grafo de dependências de build explícito, com cache por hash de conteúdo em cada etapa
- GitHub Actions: lint, testes, build da BD em tag, publicação de release com artefactos e checksums, deploy do explorador, publicação no PyPI e npm
- MkDocs Material para documentação

**CLI**

```
nutridb sources sync            descarrega e verifica hashes
nutridb sources audit           relatório de licenças
nutridb extract [--source X]
nutridb vocab check             valida vocabulário e mapeamentos
nutridb link                    resolução de entidades
nutridb i18n build              composição de rótulos
nutridb i18n review             exporta fila de revisão
nutridb merge
nutridb derive
nutridb qa                      suite de qualidade, relatório HTML
nutridb package [--profile core|extended|lite]
nutridb build                   tudo o acima, ordenado
nutridb diff v1 v2
nutridb serve                   API local
nutridb explorer dev
```

---

## 16. Fases e critérios de aceitação

Uma fase por branch. Não avanças sem os critérios cumpridos e testes verdes.

**F0 — Fundações**
Repositório, CI, lint, tipos, CLI esqueleto, registo de fontes, ADR 0001.
*Aceite quando:* `nutridb --help` funciona, CI verde, ADR de arquitetura aprovado.

**F1 — Vocabulário e primeira fonte, ponta a ponta**
`vocab/nutrients.csv` completo e congelado. CIQUAL extraída, mapeada, empacotada. SQLite com pesquisa a funcionar.
*Aceite quando:* consultas ao SQLite devolvem alimentos com nutrientes corretos e proveniência; `_unmapped` vazio; 20 alimentos verificados à mão.

**F2 — Multi-fonte**
Extractores para USDA (4 sub-conjuntos), INSA, CoFID, Frida, Fineli, e mais três à escolha justificada. Um ADR de licença por fonte.
*Aceite quando:* todas as fontes carregam num esquema comum sem casos especiais espalhados pelo código.

**F3 — Identidade**
Blocking, sinais, adjudicação, conjunto dourado de 500 pares.
*Aceite quando:* precisão ≥ 0,98 e recall ≥ 0,90 no conjunto dourado; todas as fusões registadas em `links.csv`.

**F4 — Multilinguismo**
Facetas, glossários, composição, fluxo de revisão, divergências regionais.
*Aceite quando:* 8 locales com ≥ 95% de rótulos em estatuto `native`/`official`/`curated`; zero `mt_unreviewed` no `core`; pesquisa cruzada entre línguas funcional.

**F5 — Fusão e derivações**
Prioridades, valores alternativos, retenção, rendimento, porções, densidades.
*Aceite quando:* prioridades são puramente dados; toda derivação tem cadeia registada.

**F6 — Qualidade**
Suite completa, relatório HTML, 200 testes dourados, testes de propriedade.
*Aceite quando:* zero erros de severidade `error`; relatório publicado no CI; determinismo verificado.

**F7 — Empacotamento**
Três perfis SQLite, Parquet, JSONL, RDF, checksums, atestação.
*Aceite quando:* o gate de licenças bloqueia efetivamente uma fonte incompatível num teste; `lite` abaixo de 25 MB.

**F8 — Explorador**
As 13 vistas. Estático. Base de dados completa navegável.
*Aceite quando:* qualquer alimento é alcançável em ≤ 3 interações; qualquer valor revela a sua proveniência num clique; Lighthouse ≥ 95 em performance e acessibilidade.

**F9 — API e clientes**
FastAPI, OpenAPI, pacote Python, pacote npm.
*Aceite quando:* clientes gerados e testados contra a API real.

**F10 — 1.0**
Documentação, guia de contribuição, política de versionamento, release.
*Aceite quando:* um terceiro reconstrói o artefacto idêntico seguindo apenas a documentação.

---

## 17. Regras de trabalho para o agente

1. Mantém `PLAN.md` e `PROGRESS.md` atualizados no fim de cada sessão. Nunca dependas do contexto sobreviver.
2. Escreve um ADR para qualquer decisão que seja cara de reverter. Numerados, com contexto, opções, decisão e consequências.
3. Testes primeiro nas partes que envolvem correção numérica. Não negociável.
4. Commits atómicos, mensagens convencionais, uma fase por branch.
5. Paraleliza com subagentes o que for paralelizável — extractores independentes, glossários por locale, vistas do explorador. Não paralelizes decisões de esquema.
6. **Para e pergunta** quando: uma licença for ambígua; uma decisão de resolução de entidades afetar mais de 500 registos; o vocabulário canónico precisar de mudar depois de congelado; ou uma fonte exigir contacto humano.
7. Nunca inventes um valor nutricional para preencher uma lacuna. Nem uma vez. Nem para testes — usa fixtures explicitamente marcados como sintéticos e isolados dos dados reais.
8. Não faças commit de dumps grandes. `sources/registry.toml` guarda URL e hash; `nutridb sources sync` descarrega.
9. Quando não souberes qual é a prática correta em composição de alimentos, procura a documentação do EuroFIR, do INFOODS ou do FAO em vez de improvisares. Este domínio tem normas; segue-as.
10. Prefere adiar funcionalidade a comprometer os princípios da secção 1.

---

## 18. Anti-objetivos

Coisas que este projeto **não** faz, e que não deves acrescentar por iniciativa própria:

- Registo de refeições, contagem de calorias, contas de utilizador, planos alimentares
- Aconselhamento nutricional de qualquer espécie
- Valores nutricionais estimados por modelos de linguagem
- Dados de produtos de marca no artefacto principal
- Recolha automática de sites que a proíbem
- Otimizar para número de alimentos. Um catálogo de 40 000 alimentos rastreáveis vale mais do que 2 milhões de linhas de origem duvidosa.
- Suportar todas as línguas do mundo mal, em vez de oito bem

---

## 19. Como se avalia o sucesso

Não é o número de alimentos. É isto:

- Escolhe um alimento ao acaso e um nutriente ao acaso. Consegues, em menos de dez segundos e sem ler código, dizer de onde veio aquele número, como foi obtido, e com que grau de confiança?
- Um falante nativo de cada um dos oito locales lê 100 nomes ao acaso e não encontra nenhum que soe a tradução de máquina?
- Apagas `build/`, corres um comando, e obténs o mesmo ficheiro byte a byte?
- Alguém que nunca falou contigo acrescenta uma fonte nova em meio dia, seguindo apenas a documentação?

Se as quatro respostas forem sim, o projeto está feito.
