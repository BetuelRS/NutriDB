# ADR-0017 - USDA Nutrient Retention Factors Release 6

- **Estado**: Proposta; integração bloqueada até pin de artefacto e revisão de licença
- **Data**: 2026-08-21
- **Fase**: F5/Futuro

---

## 1. Contexto

O NutriDB tem o estágio de derivações preparado para retenção e rendimento,
mas as tabelas estão vazias. Uma derivação de retenção sem fonte, fórmula,
inputs e fator versionado violaria P1 e P2.

A fonte candidata é a publicação oficial USDA Agricultural Research Service,
*USDA Table of Nutrient Retention Factors Release 6 (2007)*:

- PDF oficial: `https://www.ars.usda.gov/ARSUserFiles/80400530/pdf/retn06.pdf`;
- DOI indicado pela distribuição: `10.15482/USDA.ADC/1409034`;
- conteúdo: fatores por nutriente, alimento e método de preparação.

O PDF oficial está acessível, mas a página de catálogo anteriormente consultada
em data.gov já não responde no URL usado na pesquisa. Não existe ainda no
registry do NutriDB um artefacto descarregado com hash fixado.

## 2. Decisão provisória

1. Não integrar fatores no build atual.
2. Não preencher `derivations/retention_factors.csv` com valores retirados de
   memória, de mirrors ou de uma transcrição não verificada.
3. Antes da integração, descarregar o artefacto oficial, calcular SHA-256,
   guardar URL, data de acesso, licença e evidência no registry/ADR, e criar
   golden fixtures marcadas como dados reais da fonte.
4. Cada aplicação deverá guardar `derivation_id`, fórmula, inputs, unidade,
   método culinário e fator usado.
5. Se a licença não estiver explicitamente confirmada na fonte oficial,
   parar e pedir contacto humano, conforme §17.6.

## 3. Integração futura

- mapear chaves USDA para o vocabulário NutriDB em CSV revisável;
- validar fator numérico, unidade e chave contra os alimentos/nutrientes
  conhecidos;
- rejeitar fatores sem evidência ou com múltiplas linhas para a mesma chave;
- testar uma derivação sintética separada de valores reais;
- reconstruir e verificar a cadeia completa no artefacto.

## 4. Consequências

- O NutriDB não publica valores calculados de retenção enquanto a proveniência
  não estiver fechada.
- O estágio `derive` continua corretamente vazio para retenção, em vez de
  fabricar resultados.
- A decisão pode ser revertida sem migração de dados, porque nenhum fator foi
  integrado.
