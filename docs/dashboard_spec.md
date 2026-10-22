# Power BI dashboard specification

> **Status: design specification only.** No `.pbix` file has been built. This document, the wireframe (`outputs/charts/12_dashboard_wireframe.png`) and the star-schema tables in `data/processed/workforce.db` (built by `sql/05_star_schema.sql`) are what a developer needs to build it. The DAX below has not been tested in Power BI.

## Data model (star schema)

```
                  dim_date (date_key, financial_year, year, month)
                       │
 dim_job_family ── fact_workforce_snapshot (date_key, employee_id, job_family_key, location_key, employment_type, fte, headcount, annual_salary_cost)
 (job_family_key,  fact_movement           (event_id, date_key, employee_id, event_type, job_family_key, location_key, reason, source)
  anzsco,          fact_requisition        (requisition_id, open_date_key, filled_date_key, status, job_family_key, location_key, applicants, source)
  family_group)    fact_establishment      (financial_year, job_family_key, location_key, budgeted_fte)
                   fact_forecast           (scenario, financial_year, job_family_key, location_key, demand_fte, supply_fte, gap_fte, hires,
                       │                    required_hires, capacity, separations, agency_fte, employee_cost, agency_cost, total_cost)
 dim_location ─────┘   fact_external_indicator (anzsco or region, period_date, indicator, value, source)   ← REAL data
 (location_key, gccsa, remoteness)
 dim_scenario (scenario, description)      dim_provenance (REAL / SYNTHETIC / MODEL)
```

- Relationships are one-to-many from each dimension to the facts, with single-direction filters.
- `fact_requisition` has two date roles: open is active, filled is inactive and used via `USERELATIONSHIP`.
- `fact_external_indicator` joins to `dim_job_family` on `anzsco` (many-to-many is avoided by giving the family dimension one ANZSCO key per family).
- Every visual's subtitle shows its provenance from `dim_provenance`.

**Refresh.** Rerun `run_all.sh` (or the equivalent ETL), then refresh: monthly for HRIS/ATS/payroll, quarterly for ABS/JSA.

## Pages, visuals, filters, drill-downs

| Page | Visuals | Filters / slicers | Drill-down / drill-through |
|---|---|---|---|
| 1 Executive overview | 7 KPI cards (Headcount, FTE, Vacancy rate, Turnover 12m, Median time-to-fill, Agency FTE, FY2029 shortage FTE), each with vs last year and target; demand vs supply line (actual + forecast); risk heatmap matrix | Scenario, FY, job family, location / GCCSA, employment type | Heatmap cell → *Cell detail* page |
| 2 Supply vs demand | Clustered line (demand FTE, supply FTE) FY2023–29; gap waterfall by family; external panel: WA IVI index and OSL rating per family [REAL] | Scenario, family, site | Family → site |
| 3 Vacancies & recruitment | Vacant FTE by site (bar); open requisitions by age band (0–30, 31–60, 61–90, 90+); time-to-fill median/P90 by family and site (dot plot); fill rate trend; unrequisitioned vacant FTE | FY, family, site, requisition reason | Requisition list (table) |
| 4 Composition & movement | Headcount by employment type (100% bar); age-band histogram vs Census 2021 WA HCSA [REAL]; monthly hires/separations (column); turnover by family vs ABS Job Mobility benchmark line [REAL]; separation reasons | FY, family, site, gender | Family → site → employment type |
| 5 Forecast & scenarios | Shortage FTE by scenario (line); required hires vs capacity (line + reference); 3-year cost and agency cost by scenario (bar); intervention comparison table | Scenario (multi-select), family, site | Year → family → site |
| 6 Risk heatmap | Matrix family × site, conditional formatting on risk score with component tooltip; scatter of internal risk vs external risk | Risk band, component weights (what-if) | Cell detail |
| 7 Assumptions & sensitivity | What-if parameters: attrition multiplier, demand add-on (pp), capacity multiplier, wage growth; tornado (from `model_sensitivity_tornado`); assumption register table with provenance | – | – |

## KPI definitions

| KPI | Calculation | Visual | Target (proposed) |
|---|---|---|---|
| Headcount | DISTINCTCOUNT(employee_id) at snapshot | Card | – |
| FTE | SUM(fte) at snapshot | Card | – |
| Vacancy rate | (Σ budgeted FTE − Σ filled FTE) ÷ Σ budgeted FTE | Card + bar by site | < 3% |
| Turnover (rolling 12 months) | Separations in last 12 months ÷ average monthly headcount | Card + line | < 13% |
| Early attrition | Separations within 365 days of hire ÷ hires in cohort | Card | < 18% |
| Median time-to-fill | MEDIAN(filled_date − open_date) for fills in period | Card + dot plot | < 35 days |
| Fill rate | Filled ÷ (filled + cancelled) | Line | > 90% |
| Agency FTE | Agency hours ÷ (76 × 26) | Card | ≤ FY2026 |
| Shortage FTE (forecast) | Σ max(0, demand − supply) at family × site level | Card + line | < 30 FTE |
| Hiring requirement vs capacity | Σ required hires ÷ Σ capacity | Gauge | < 90% |

## Sample DAX measures

```DAX
Headcount = DISTINCTCOUNT ( fact_workforce_snapshot[employee_id] )

FTE = SUM ( fact_workforce_snapshot[fte] )

Budgeted FTE = SUM ( fact_establishment[budgeted_fte] )

Vacant FTE = [Budgeted FTE] - [FTE]

Vacancy Rate = DIVIDE ( [Vacant FTE], [Budgeted FTE] )

Separations =
CALCULATE ( COUNTROWS ( fact_movement ), fact_movement[event_type] = "SEPARATION" )

Hires =
CALCULATE ( COUNTROWS ( fact_movement ), fact_movement[event_type] = "HIRE" )

-- Opening headcount rebuilt from the closing stock and the period's flows (same identity as the Python/SQL pipeline)
Opening Headcount =
[Headcount] - [Hires] + [Separations]

Average Headcount = DIVIDE ( [Opening Headcount] + [Headcount], 2 )

Turnover Rate = DIVIDE ( [Separations], [Average Headcount] )

Turnover Rate 12M =
VAR _end = MAX ( dim_date[date_key] )
RETURN
    CALCULATE ( [Turnover Rate],
        DATESINPERIOD ( dim_date[date_key], _end, -12, MONTH ) )

Median Time to Fill =
CALCULATE (
    MEDIANX ( FILTER ( fact_requisition, fact_requisition[status] = "Filled" ),
              DATEDIFF ( fact_requisition[open_date_key], fact_requisition[filled_date_key], DAY ) ),
    USERELATIONSHIP ( fact_requisition[filled_date_key], dim_date[date_key] ) )

Fill Rate =
DIVIDE (
    CALCULATE ( COUNTROWS ( fact_requisition ), fact_requisition[status] = "Filled" ),
    CALCULATE ( COUNTROWS ( fact_requisition ), fact_requisition[status] IN { "Filled", "Cancelled" } ) )

-- Forecast measures: the scenario comes from a disconnected slicer table
Selected Scenario = SELECTEDVALUE ( dim_scenario[scenario], "A Baseline" )

Shortage FTE =
SUMX (
    FILTER ( fact_forecast, fact_forecast[scenario] = [Selected Scenario] ),
    MAX ( 0, fact_forecast[gap_fte] ) )

Hiring Requirement vs Capacity =
VAR _s = [Selected Scenario]
RETURN DIVIDE (
    CALCULATE ( SUM ( fact_forecast[required_hires] ), fact_forecast[scenario] = _s ),
    CALCULATE ( SUM ( fact_forecast[capacity] ), fact_forecast[scenario] = _s ) )

-- What-if: approximate sensitivity using a parameter table 'Attrition Multiplier'[Value]
-- (exact re-simulation stays in Python/Excel; this shows the first-order effect on separations)
Separations What-if =
SUMX ( FILTER ( fact_forecast, fact_forecast[scenario] = [Selected Scenario] ),
       fact_forecast[separations] * SELECTEDVALUE ( 'Attrition Multiplier'[Value], 1 ) )

Risk Score (weighted) =
    0.25 * [Vacancy Score] + 0.15 * [Turnover Score] + 0.15 * [TTF Score]
  + 0.10 * [Age55 Score] + 0.20 * [OSL Score] + 0.15 * [Ads Intensity Score]
```

**Design notes.**
- Use one colour per series, consistent across pages: scenario A blue, B orange, C aqua.
- Use a single-hue sequential scale on the heatmap, and never red/green alone. Every KPI shows its value and a text label.
- Synthetic visuals carry a "Synthetic case-study data" watermark, so screenshots cannot be mistaken for real results.
- Row-level security: site directors see their site; executives see all. Employee-level tables are hidden from viewers. Only aggregates are shown (minimum cell size 5).
