# ADR-0018 — Integração dos fatores de retenção USDA R6

- **Estado**: Aprovado (emenda ao ADR-0017)
- **Data**: 2026-08-21
- **Fase**: F5 / derivações

---

## 1. Contexto

O ADR-0017 bloqueou a integração até existir artefacto oficial descarregado,
hash fixado e licença confirmada na fonte. As três condições ficaram agora
satisfeitas:

- **Fonte primária**: `retn06.txt` (ASCII, campos delimitados por `^`, texto
  entre `~`), publicado pelo USDA ARS.
  URL: `https://www.ars.usda.gov/ARSUserFiles/80400525/Data/retn/retn06.txt`
  SHA-256:
  `5B71867F6649E801DB3BF88C6CD1887B0673E853D4BA94AA0AF2B3C091E983F9`
- **Licença**: CC0 1.0 — confirmada nos metadados oficiais do dataset em
  data.gov (`license: https://creativecommons.org/publicdomain/zero/1.0/`)
  e no Ag Data Commons (DOI `10.15482/USDA.ADC/1409034`).
- **Artefactos de referência** (mesmo DOI, também em cache):
  `retn06.pdf`
  (`53EA1B82008226D8F4D24998D10A19995268BF64CD63DA87543D0B94E6C8AF8F`),
  `NutrientRetention.csv` de 2017
  (`B863E891989020EDF3A429AF8060523E5DEE275699AE08893A5F91FF9A84B1E5`) e
  dicionário de dados.

O CSV de 2017 sofreu corrupção clássica de Excel (datas `09/1975`
convertidas para `Sep-75`, destruindo o fator em 24 linhas); por isso o
`.txt` oficial é a fonte primária e o CSV fica apenas como referência.

## 2. Decisão

1. O ficheiro `derivations/retention_factors.csv` passa a ser **gerado** por
   `scripts/build_retention_factors.py` a partir do `.txt` fixado — nunca
   editado à mão (P8/P10).
2. Mapeamento de nutrientes: `Nutr_No` → tagname INFOODS do vocabulário
   congelado. Excluídos por não existir tagname correspondente:
   `318` (Vitamina A IU) e `338` (Luteína+Zeaxantina combinadas). Incluído
   `392→VITA_RAE` com nota de que o USDA publica RE.
3. Classificação de método culinário por palavras-chave no `RetnDesc`,
   primeira correspondência ganha; preparações de calor não especificado
   (`COOKED/CKD/HEATED`) ficam no método explícito `cooked`; linhas sem
   correspondência (ex.: `DRIED`, `FROZEN`, `MASHED`) ficam fora da tabela
   de fatores mas permanecem na referência integral.
4. Fatores vazios na fonte (ex.: minerais em bebidas destiladas, 24 linhas)
   são ausência declarada — não se inventa fator.
5. Redução para o contrato `(nutrient, cooking_method)` do estágio derive
   (ADR-0007): **mediana** das linhas USDA que caem em cada par, com
   evidência a registar contagem, mínimo e máximo. A fidelidade integral
   das 7 018 linhas fica em `derivations/usda_r6_reference.csv`.
6. A validação do derive contra nutrientes passa a usar o vocabulário
   congelado (não os nutrientes atualmente medidos): fatores servem fontes
   futuras.
7. Testes institucionais (`tests/unit/test_retention_factors.py`) garantem
   contrato de header, unicidade, intervalo (0, 1], vocabulário, DOI na
   evidência, fidelidade da referência e hash pinado no cabeçalho.

## 3. Consequências

- O NutriDB tem pela primeira vez uma tabela de fatores real e auditável;
  derivações `calculated` passam a ser possíveis assim que exista um valor
  cru sem medição direta (hoje: 0, porque CIQUAL+INSA já medem 100 g).
- A granularidade grupo×método do USDA foi agregada para nutriente×método;
  quando houver necessidade clínica/estatística de maior resolução, o
  contrato do derive pode ser estendido sem migrar dados (a referência
  integral já está no repositório).
- Consumidores devem citar o DOI USDA e esta decisão ao usar fatores.
