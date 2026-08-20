# ADR-0011 - Aquisição controlada e ausência tipada (P1/P3)

- **Estado**: Aprovado
- **Data**: 2026-08-19
- **Fase**: hardening P1

---

## 1. Contexto

O esquema canónico já tem a coluna `acquisition_type`, mas o transform grava
`NULL` em todas as células provenientes de CIQUAL e INSA. Isso contradiz P1:
um valor publicado deve indicar como entrou no NutriDB. O vocabulário existente
usa códigos EuroFIR (`A`, `B`, `C`, ...), enquanto a SPEC descreve os estados
por nomes semânticos (`analysed`, `calculated`, `borrowed`, `imputed`,
`declared`). O código também escrevia `calculated` e `declared` diretamente,
sem correspondência controlada.

As fontes iniciais não publicam, para todas as células, o tipo de aquisição
subjacente. Inferir que cada célula foi analisada seria fabricar proveniência.

## 2. Opções

1. **Manter `NULL` quando a fonte não classifica** - rejeitada por violar P1
   e por obrigar cada consumidor a interpretar uma ausência de semântica.
2. **Inferir `analysed` a partir da existência de um valor** - rejeitada por
   confundir valor publicado com método de aquisição subjacente.
3. **Usar `declared` na fronteira do NutriDB** - escolhida. Significa que a
   fonte publicou a célula, sem afirmar que o laboratório ou método subjacente
   está classificado. A proveniência bruta, confiança, código e método ficam
   preservados separadamente.
4. **Usar `calculated` apenas para derivações próprias** - escolhida. Exige
   `derivation_id`, fórmula, inputs e fatores.

## 3. Decisão

1. `vocab/acquisition_types.csv` passa a usar IDs semânticos controlados:
   `analysed`, `calculated`, `borrowed`, `imputed` e `declared`.
2. Células CIQUAL e INSA que existem no intermediário, incluindo `trace` e
   `below_loq`, recebem `acquisition_type = declared`. Isto descreve o ato de
   publicação da fonte, não uma medição inferida.
3. Valores derivados recebem `acquisition_type = calculated` e um
   `derivation_id` válido.
4. Overrides humanos recebem `acquisition_type = declared` e mantêm a
   justificação obrigatória.
5. Células `missing` continuam sem linha em `value`, conforme ADR-0001 D5:
   a ausência é recuperada por `coverage` + ausência da célula. A distinção
   entre `not_measured`, `not_applicable` e outros motivos só pode ser emitida
   quando a fonte ou uma configuração revisada fornecer essa evidência.
6. O package deve validar que qualquer `acquisition_type` não nulo existe no
   vocabulário e que nenhum valor publicado chega ao artefacto com `NULL`.

## 4. Consequências

- P1 deixa de depender de `NULL` para valores publicados.
- A semântica é conservadora: `declared` não inventa um método laboratorial.
- A mudança de códigos do vocabulário é uma migração controlada, registada
  neste ADR; consumidores devem usar os IDs semânticos.
- A cobertura de ausência permanece compacta, sem fabricar um produto
  cartesiano por alimento/nutriente.
- Uma futura fonte que publique aquisição analítica pode usar `analysed`,
  com a evidência correspondente.
