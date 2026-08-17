# ADR-0004 — Fonte INSA/TCA (Portugal): regime de utilização e formato

- **Estado**: Aprovado (decisão humana 2026-08-16)
- **Data**: 2026-08-16 (proposta F2.0; aprovação humana via e-mail oficial e decisão de licença)
- **Fase**: F2.0 (`f2/multi-fonte`)

---

## 1. Contexto

A Fase 2 traz o INSA (Tabela da Composição de Alimentos — TCA) como fonte
portuguesa. A regra de trabalho §17.6 exige **contacto humano prévio** para o
INSA; esse contacto aconteceu (pedido 2026-07-21, resposta oficial
**2026-07-28** de Maria da Graça Dias, PhD — Coordenadora da Unidade de
Observação e Vigilância, Departamento de Alimentação e Nutrição, INSA). Este
ADR regista a evidência, o regime de utilização e a decisão de licença (P6:
ADR de licença por fonte, antes do extractor).

## 2. Verificação na fonte oficial

| Campo | Valor verificado |
|---|---|
| Publicação | INSA, I.P. — "Tabela da Composição de Alimentos", **v 7.1 (2026)**: 1 376 alimentos (crus, cozinhados e processados), 50 componentes/nutrientes, valores por 100 g de parte edível, categorias FoodEx2; anunciada em 2026-05-13 no PortFIR ("Atualização da Tabela da Composição de Alimentos") |
| Página | `https://portfir.insa.min-saude.pt/pt/` (consultada 2026-08-16) |
| Download | `https://portfir.insa.min-saude.pt/wp-content/uploads/2025/11/insa_tca.xlsx` — ficheiro Excel único "Descarregar a Base de Dados da Composição de Alimentos" |
| Contacto | `tabela.alimentos@insa.min-saude.pt` — resposta oficial em anexo (§7) |
| Regime | **Livre utilização** "dentro da sua missão como Instituto Público", **sujeita a referenciação** sempre que os dados sejam utilizados por terceiros. **Não é uma licença SPDX** (não é CC-BY nem etalab) — regime próprio com atribuição obrigatória |
| Atribuição | Obrigatória (`attribution_required = true`); citação sugerida pela fonte registada no registry (§7) |
| Share-alike | Não indicado (regime próprio; sem cláusula) |
| Comercial | Permitido — decisão humana 2026-08-16 (opção "permissiva com atribuição"): o e-mail diz "livre utilização" e só impõe referenciação; a referência à missão explica a gratuidade, não restringe terceiros |
| Volume | 1 376 alimentos × 50 componentes (estimativa 68 800 células; verificado na extração) |
| Formato | XLSX único (folhas a inspecionar na F2.1; sem proveniência por valor publicada — documentar na extração) |

## 3. Opções consideradas

1. **Permissiva com atribuição (core)** — "livre utilização... sujeita a
   referenciação"; sem cláusulas restritivas explícitas; a missão do INSA
   (instituto público de saúde) justifica a gratuidade, não limita reutilizadores.
   **Escolhida** (decisão humana).
2. **Restrita (perfil próprio, fora de core)** — leitura conservadora de
   "dentro da sua missão como Instituto Público"; rejeitada por contradizer o
   "livre utilização" expresso e por não haver nenhuma cláusula de restrição
   comercial no texto oficial.
3. **Adiar até confirmação adicional** — desnecessário: a resposta é explícita
   e assinada pela equipa responsável; reabrir o contacto só se a F7 (gate de
   licenças) levantar dúvidas de compatibilidade de artefacto.

## 4. Decisão

1. **Fonte INSA/TCA v 7.1 (2026) incluída no pipeline**, licença `insa-tca-7.1`
   (custom, sem SPDX): `attribution_required = true`, `share_alike = false`,
   `commercial_use = true`, artefactos `core`.
2. Citação registada no registry (sugestão oficial, com `[data de consulta]`).
3. Formato primário: **XLSX oficial único** (`insa_tca.xlsx`), fixado por
   SHA-256 no registry (modelo `files`); o ficheiro fica no cache, nunca no git.
4. O extractor da F2.1 lê o XLSX para os intermediários do esquema comum
   (mesmo contrato da CIQUAL: `source_record` com célula crua + referência);
   ausências/limites semânticos da fonte documentados na extração.
5. Sem proveniência por valor publicada na TCA — registar a limitação na
   camada canónica (fonte única por linha; sem `source_code`).

### 4.1 Volume verificado (na extração)

| Métrica | Valor |
|---|---|
| Alimentos | 1 376 (anunciado; confirmar na extração) |
| Componentes | 50 (anunciado; confirmar na extração) |
| Pares | ~68 800 (confirmar na extração) |
| Unidade declarada | por 100 g de parte edível |

## 5. Consequências

- O gate de licenças da F7 deve reconhecer `insa-tca-7.1` como permissiva com
  atribuição (não-SPDX) e emitir a citação no artefacto (SPEC §14).
- A ausência de proveniência por valor na TCA significa `confidence`/
  `acquisition` por convenção da fonte (documentar; nunca inventar, P2).
- Vocabulário: os 50 componentes da TCA devem caber nos 157 tagnames
  congelados ou em expansão **aditiva** (não quebra o freeze — nota F1.1).
- O extractor INSA é o primeiro de múltiplos na F2; o transform passa a ler
  **N fontes** para o mesmo esquema canónico (SPEC §16 F2: "esquema comum sem
  casos especiais espalhados pelo código").

## 6. Critério de aceitação

1. `sources/registry.toml` tem a fonte `insa` com `license_id = "insa-tca-7.1"`,
   SHA-256 fixado e citação oficial.
2. `uv run nutridb sources sync` + `sources audit` validam o ficheiro e
   reportam a licença sem restrições de core.
3. Leitura humana deste ADR confirma a evidência §7 (e-mail oficial).

---

## 7. Registo de aprovação (2026-08-16)

Evidência — resposta oficial por e-mail (INSA, 2026-07-28, Maria da Graça
Dias, PhD; pedido de 2026-07-21 de Betuel), texto integral:

> "A Tabela da Composição de Alimentos editada pelo Instituto Nacional de
> saúde Doutor Ricardo Jorge, IP é disponibilizada em
> https://portfir.insa.min-saude.pt/pt/, e é de livre utilização, dentro da
> sua missão como Instituto Público. No entanto, a sua utilização está sujeita
> a referenciação, sempre que os dados nela contido forem utilizados por
> terceiros.
>
> Sugestão de referência:
> Instituto Nacional de Saúde Doutor Ricardo Jorge, I. P.- INSA. Tabela da
> Composição de Alimentos, v 7.1 [base de dados online]. Lisboa. 2026, [data
> de consulta]. Disponível em: https://portfir.insa.min-saude.pt/pt/"

| Item | Decisão |
|---|---|
| Regime | Livre utilização com **referenciação obrigatória**; sem cláusulas restritivas explícitas |
| Licença | `insa-tca-7.1` (custom, não-SPDX); `commercial_use = true` — decisão humana (opção "permissiva com atribuição") |
| Artefacto | `core` |
| Versão | v 7.1 (2026) — 1 376 alimentos, 50 componentes (anunciado no PortFIR) |
| Citação | Oficial (acima), com `[data de consulta]` por preencher no artefacto |