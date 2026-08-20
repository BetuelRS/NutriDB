# ADR-0016 - Ausência tipada com evidência disponível (P3)

- **Estado**: Aprovado tecnicamente; sem novos códigos de ausência
- **Data**: 2026-08-21
- **Fase**: F6/P3

---

## 1. Contexto

P3 exige que a ausência seja tipada e que nunca seja achatada para `0` ou
`NULL`. A decisão depende do que as fontes publicam, não do que seria útil
inferir no consumidor.

Na CIQUAL 2025, a inspeção do XML oficial encontrou quatro classes de célula:

- número;
- `-`, documentado como teor desconhecido;
- `<N`, documentado como valor máximo, materializado como `below_loq`;
- `traces`, materializado como `trace`.

A CIQUAL não publica um código de motivo por célula para distinguir, por
exemplo, não medido de não aplicável.

Na INSA/TCA 7.1, a folha de dados contém células vazias, sem tokens de razão e
sem uma coluna que as classifique. A fonte preenche ausências em alguns casos
por método de receita EuroFIR, mas não publica uma taxonomia de ausência por
célula.

O vocabulário EuroFIR de tipos de valor é uma referência externa, não evidência
de que uma das duas fontes tenha atribuído esses tipos às suas células.

## 2. Opções

1. **Inferir `not_detected`, `not_applicable` ou `assumed_zero` a partir de
   células vazias ou do contexto alimentar** - rejeitada: fabricaria uma razão
   que a fonte não publicou, violando P2.
2. **Converter todas as ausências em zero ou `NULL`** - rejeitada: perde a
   distinção material exigida por P3.
3. **Manter cobertura e flags publicados, sem inventar razões adicionais** -
   escolhida.

## 3. Decisão

1. A ausência implícita é representada por `coverage` mais ausência de linha
   em `value`, conforme ADR-0001 D5.
2. `trace` e `below_loq` são materializados quando publicados pela CIQUAL.
3. Células vazias da INSA permanecem `not_measured` no modelo de cobertura,
   sem serem convertidas em zero.
4. `not_detected`, `not_applicable`, `assumed_zero` e outros motivos só podem
   entrar quando a fonte ou uma configuração revista fornecer evidência
   explícita por célula.
5. O extractor continua a falhar alto para tokens desconhecidos; nenhum novo
   token será tratado como ausência por conveniência.

## 4. Consequências

- O produto permanece conservador e auditável, sem falsa precisão semântica.
- Consumidores devem consultar cobertura e tipo de valor em conjunto.
- Uma futura fonte com códigos próprios exigirá mapping, golden e revisão antes
  de alterar o vocabulário.
- O bloqueio de P3 por razões adicionais fica encerrado como limitação de
  evidência, não como funcionalidade omitida silenciosamente.

## 5. Evidência

- CIQUAL 2025: XML oficial `compo_2025_11_03.xml`, 257 816 registos COMPO
  verificados; classes `-`, `<N` e `traces` contabilizadas no extractor.
- INSA/TCA 7.1: workbook oficial, 10 018 células vazias observadas e nenhuma
  coluna de motivo publicada.
- Implementação: `src/nutridb/sources/ciqual.py`, `src/nutridb/transform.py`
  e `tests/unit/test_extract_ciqual.py`.
