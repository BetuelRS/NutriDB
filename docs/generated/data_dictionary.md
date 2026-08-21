# NutriDB data dictionary

Generated from the packaged SQLite schema by
`nutridb docs dictionary`. Do not edit by hand.

## `acquisition_type`

Rows: 5

| # | column | type | notnull |
|---|---|---|---|
| 1 | `id` | TEXT |  |
| 2 | `name_en` | TEXT | yes |
| 3 | `description` | TEXT | yes |

## `analytical_method`

Rows: 22

| # | column | type | notnull |
|---|---|---|---|
| 1 | `id` | TEXT |  |
| 2 | `name_en` | TEXT | yes |
| 3 | `description` | TEXT | yes |

## `concept`

Rows: 4,860

| # | column | type | notnull |
|---|---|---|---|
| 1 | `concept_id` | TEXT |  |
| 2 | `kind` | TEXT | yes |
| 3 | `food_group` | TEXT | yes |

## `concept_classification`

Rows: 0

| # | column | type | notnull |
|---|---|---|---|
| 1 | `concept_id` | TEXT | yes |
| 2 | `scheme` | TEXT | yes |
| 3 | `code` | TEXT | yes |
| 4 | `status` | TEXT | yes |

## `concept_facet`

Rows: 0

| # | column | type | notnull |
|---|---|---|---|
| 1 | `concept_id` | TEXT | yes |
| 2 | `facet` | TEXT | yes |
| 3 | `value` | TEXT | yes |
| 4 | `status` | TEXT | yes |

## `concept_link`

Rows: 5,096

| # | column | type | notnull |
|---|---|---|---|
| 1 | `concept_id` | TEXT | yes |
| 2 | `source_record_id` | TEXT | yes |
| 3 | `status` | TEXT | yes |

## `coverage`

Rows: 122

| # | column | type | notnull |
|---|---|---|---|
| 1 | `source_id` | TEXT | yes |
| 2 | `nutrient_id` | TEXT | yes |

## `density`

Rows: 0

| # | column | type | notnull |
|---|---|---|---|
| 1 | `food_group` | TEXT | yes |
| 2 | `density_g_per_ml` | REAL | yes |
| 3 | `evidence` | TEXT | yes |

## `derivation`

Rows: 0

| # | column | type | notnull |
|---|---|---|---|
| 1 | `derivation_id` | TEXT |  |
| 2 | `formula` | TEXT |  |
| 3 | `inputs` | TEXT |  |
| 4 | `factors` | TEXT |  |

## `food_group`

Rows: 18

| # | column | type | notnull |
|---|---|---|---|
| 1 | `id` | TEXT |  |
| 2 | `name_en` | TEXT | yes |
| 3 | `name_pt` | TEXT | yes |

## `label`

Rows: 9,948

| # | column | type | notnull |
|---|---|---|---|
| 1 | `ref_kind` | TEXT | yes |
| 2 | `ref` | TEXT | yes |
| 3 | `locale` | TEXT | yes |
| 4 | `status` | TEXT | yes |
| 5 | `text` | TEXT | yes |
| 6 | `text_normalized` | TEXT | yes |

## `mv_food_value`

Rows: 396,627

| # | column | type | notnull |
|---|---|---|---|
| 1 | `concept_id` | TEXT | yes |
| 2 | `locale` | TEXT | yes |
| 3 | `label` | TEXT | yes |
| 4 | `food_group` | TEXT | yes |
| 5 | `nutrient_id` | TEXT | yes |
| 6 | `value` | REAL |  |
| 7 | `unit` | TEXT |  |
| 8 | `value_type` | TEXT | yes |
| 9 | `confidence_code` | TEXT |  |
| 10 | `acquisition_type` | TEXT |  |
| 11 | `source_id` | TEXT |  |
| 12 | `source_record_id` | TEXT |  |
| 13 | `below_loq_threshold` | REAL |  |
| 14 | `basis` | TEXT | yes |
| 15 | `alternatives` | TEXT |  |
| 16 | `divergence_flag` | INTEGER | yes |
| 17 | `divergence_max` | REAL |  |
| 18 | `derivation_id` | TEXT |  |
| 19 | `override_justification` | TEXT |  |

## `nutrient`

Rows: 161

| # | column | type | notnull |
|---|---|---|---|
| 1 | `tagname` | TEXT |  |
| 2 | `grp` | TEXT | yes |
| 3 | `name_en` | TEXT | yes |
| 4 | `unit` | TEXT | yes |

## `nutrient_relation`

Rows: 54

| # | column | type | notnull |
|---|---|---|---|
| 1 | `parent` | TEXT | yes |
| 2 | `child` | TEXT | yes |

## `portion`

Rows: 0

| # | column | type | notnull |
|---|---|---|---|
| 1 | `concept_id` | TEXT | yes |
| 2 | `measure` | TEXT | yes |
| 3 | `grams` | REAL | yes |
| 4 | `evidence` | TEXT | yes |

## `reference_value`

Rows: 0

| # | column | type | notnull |
|---|---|---|---|
| 1 | `nutrient_id` | TEXT | yes |
| 2 | `authority` | TEXT | yes |
| 3 | `age_min` | INTEGER |  |
| 4 | `age_max` | INTEGER |  |
| 5 | `sex` | TEXT |  |
| 6 | `state` | TEXT |  |
| 7 | `value` | REAL | yes |
| 8 | `unit` | TEXT | yes |

## `source`

Rows: 2

| # | column | type | notnull |
|---|---|---|---|
| 1 | `source_id` | TEXT | yes |
| 2 | `name` | TEXT | yes |
| 3 | `version` | TEXT | yes |
| 4 | `license_id` | TEXT | yes |
| 5 | `license_url` | TEXT | yes |
| 6 | `url` | TEXT | yes |
| 7 | `attribution` | TEXT |  |

## `source_record`

Rows: 328,724

| # | column | type | notnull |
|---|---|---|---|
| 1 | `source_record_id` | TEXT |  |
| 2 | `source_id` | TEXT | yes |
| 3 | `kind` | TEXT | yes |
| 4 | `ref` | TEXT | yes |
| 5 | `record` | TEXT | yes |

## `tombstone`

Rows: 236

| # | column | type | notnull |
|---|---|---|---|
| 1 | `tombstone_id` | TEXT |  |
| 2 | `successor_id` | TEXT | yes |
| 3 | `reason` | TEXT | yes |

## `unit`

Rows: 6

| # | column | type | notnull |
|---|---|---|---|
| 1 | `id` | TEXT |  |
| 2 | `name_en` | TEXT | yes |

## `value`

Rows: 230,601

| # | column | type | notnull |
|---|---|---|---|
| 1 | `concept_id` | TEXT | yes |
| 2 | `nutrient_id` | TEXT | yes |
| 3 | `value` | REAL |  |
| 4 | `unit` | TEXT | yes |
| 5 | `value_type` | TEXT | yes |
| 6 | `acquisition_type` | TEXT |  |
| 7 | `source_id` | TEXT | yes |
| 8 | `source_record_id` | TEXT | yes |
| 9 | `source_nutrient_code` | TEXT |  |
| 10 | `n_samples` | REAL |  |
| 11 | `standard_deviation` | REAL |  |
| 12 | `min_value` | REAL |  |
| 13 | `max_value` | REAL |  |
| 14 | `analytical_method` | TEXT |  |
| 15 | `confidence_code` | TEXT |  |
| 16 | `derivation_id` | TEXT |  |
| 17 | `basis` | TEXT | yes |
| 18 | `below_loq_threshold` | REAL |  |

## `value_type`

Rows: 9

| # | column | type | notnull |
|---|---|---|---|
| 1 | `id` | TEXT |  |
| 2 | `name_en` | TEXT | yes |
| 3 | `is_absence` | INTEGER | yes |
| 4 | `description` | TEXT | yes |

