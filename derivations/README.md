# derivations/ — fatores para valores calculados

F5 (ADR-0007): `retention_factors.csv`, `yield_factors.csv`,
`densities.csv`, `portions.csv` — headers prontos; dados aguardam fonte
publicada verificada (regra §17.6: nunca fabricar; ex.: USDA Nutrient
Retention Factors Release 6, Bucher et al. 2015, FNDDS).

`nutridb derive` falha alto se uma derivação pedida não tiver fatores
registados. Qualquer valor `calculated` tem cadeia registada em
`derivation` (fórmula + inputs + fatores). Receitas EuroFIR e base seca
materializada: adiadas (F5+). Com CIQUAL+INSA, todas as células pedidas
já são medidas (100 g e 100 ml) → 0 derivações reais (P2: só calcular
quando não existe medição direta).