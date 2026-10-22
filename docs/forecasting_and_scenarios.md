# Forecasting and scenario modelling

Implemented in `src/scenario_model.py`. The engine runs at job family × site level (48 cells), FY2027–FY2029. The Excel model (`outputs/excel/KHS_workforce_scenario_model.xlsx`) is a family-level replica; every one of its formulas is recalculated and checked against Python (432 cells, maximum difference 5.8 × 10⁻⁸).

## 1. Model structure

For each cell and year *t*:

```
Demand_t        = Demand_{t-1} × (1 + g_family + scenario add-on)        Demand_FY2026 = Finance establishment
Separations_t   = HC_start × attrition × scenario multiplier
EN→RN_t         = HC_start(EN) × conversion rate         (outflow from EN, inflow to RN at the same site)
Graduates_t     = graduate RNs per year × site share × scenario multiplier
HC_pre          = HC_start − Separations − EN→RN out + EN→RN in + Graduates + Net transfers
Required hires  = max(0, (Demand_t − HC_pre × FTE/head) ÷ FTE/head)
Hires_t         = min(Required hires, Capacity × scenario multiplier)
HC_end          = HC_pre + Hires                         ← Ending = Starting + Hires + Other inflows − Separations − Other outflows
Supply_t (FTE)  = HC_end × FTE/head
Gap_t (FTE)     = Demand_t − Supply_t                    (+ = shortage)
Agency FTE      = max(Gap, 0) × measured agency cover;  Unfilled FTE = shortage − agency FTE
Cost            = avg FTE × salary × (1+w)^t × on-cost  +  agency FTE × salary × (1+w)^t × premium  +  hires × cost per hire
```

**Built-in validation** (`outputs/tables/model_validation_checks.csv`), all passing for every scenario:
- the stock-flow identity closes exactly (maximum error 0.0 heads);
- hires ≤ capacity and hires ≤ required;
- no negative headcount;
- EN→RN flows net to zero;
- modelled FY2027 Baseline demand is within **−0.8%** of Finance's separately set FY2027 budget.

## 2. Assumptions and evidence

| Assumption | Baseline value | Evidence | Provenance |
|---|---|---|---|
| Demand growth by family | RN 2.37%, Midwife 2.43%, EN 1.98%, Medical 2.92%, Allied 3.03%, Care 1.84%, Admin 0.94%, Support 0.50% p.a. | JSA Employment Projections 2025–35 10-year CAGR × WA/AUS adjustment (1.0003) | **REAL** |
| Growth scenario add-on | +2.0pp clinical, +0.5pp non-clinical | Service expansion. Bounded above by ABS HCSA filled-jobs 5-year CAGR of 5.6% | ILLUSTRATIVE |
| Attrition | Cell rates FY2025–26, credibility-weighted to the family rate (K = 60 person-years); organisation 14.5% | KHS history | SYNTHETIC (measured) |
| Constraint attrition multiplier | ×1.224 | KHS FY2023 turnover (tight market) ÷ FY2026 turnover | SYNTHETIC (measured) |
| Recruitment capacity | 478 hires a year (best year per cell, FY2023–26) | KHS history | SYNTHETIC (measured) |
| Constraint capacity multiplier | ×0.731 for OSL shortage occupations | JSA OSL 2026 fill rates: 57% (shortage) ÷ 78% (no shortage) | **REAL** |
| Graduate RNs | 16 a year (Constraint ×0.75) | KHS average placements | SYNTHETIC / ILLUSTRATIVE |
| EN→RN conversion | 5.5% of ENs a year | KHS role changes | SYNTHETIC (measured) |
| Wage growth | 3.71% p.a. (Constraint +1pp) | ABS WPI HCSA, average year-on-year over the last 8 quarters | **REAL** (+ illustrative) |
| On-costs | ×1.25 | 12% super guarantee is legislated; payroll tax, workers' comp and leave assumed | ILLUSTRATIVE |
| Agency premium / cover | ×1.65 / measured cover 0.10–0.63 by family | Premium assumed; cover = KHS FY2026 agency FTE ÷ vacant FTE | ILLUSTRATIVE / SYNTHETIC |
| Productivity | 0% | No activity data; tested via FTE-per-head ±5% | ILLUSTRATIVE |

## 3. Choosing a forecast method: backtest on real series

Rolling origin: one origin every 4 quarters, at least 7 years of history at the first origin, horizons of 4, 8 and 12 quarters. Results are in `outputs/tables/backtest_summary.csv`; the 12-quarter-ahead results are shown below.

| Series (REAL) | Best method | MAPE | Bias | Naive MAPE | Origins |
|---|---|---|---|---|---|
| AUS Health Care & Social Assistance filled jobs (ABS Labour Account) | 5-year CAGR | **3.5%** | −1.9% (under-forecasts) | 12.9% | 22 |
| WA employed persons (ABS LF) | Holt damped | 4.7% (3.0% excluding COVID-affected windows) | −3.2% | 5.6% | 12 |
| WA Registered Nurses, 4-quarter mean (ABS EQ08) | Linear trend, 20 quarters | **10.1%** | −1.5% | 12.0% | 29 |

**What this means.** Trend-based methods beat naive forecasts on the aggregate health series. Every method tends to *under*-forecast health employment growth, so demand assumptions should lean up rather than down.

State × occupation employment is too noisy (a 10% error at 3 years) to forecast directly. That is why demand growth comes from JSA's occupation projections, which draw on a much larger national base, rather than from a trend fitted to WA RN employment. The 5-year HCSA trend (5.6% p.a.) is far above the hospital-occupation projections, because HCSA includes fast-growing social assistance and NDIS services. It is used only as an upper bound for the Growth scenario.

**Model backtest (synthetic, labelled as such).** Starting from the rebuilt 30 Jun 2024 stock, with FY2023–24 rates and the actual establishment:
- Organisation level: the model predicted FY2025 and FY2026 headcount within **0.01% and 0.4%**, against 2.3% and 4.2% for a no-change forecast.
- Job-family level: mean absolute error was 2.5% (FY2025) and 2.9% (FY2026), against 2.0% and 3.2% for no-change. In FY2025 the model was *not* better than naive at family level.
- The synthetic history was generated by a similar process, so this validates the mechanics, not real-world accuracy (`model_backtest_synthetic*.csv`).

## 4. Scenario results (MODEL output on synthetic internal data)

| Scenario | Year | Demand FTE | Supply FTE | Shortage FTE | Required hires | Hires | Capacity | Utilisation | Agency cost |
|---|---|---|---|---|---|---|---|---|---|
| A Baseline | FY2027 | 1,735 | 1,690 | 45.6 | 408 | 351 | 478 | 85% | $4.85M |
| | FY2028 | 1,770 | 1,740 | 30.1 | 385 | 349 | 478 | 81% | $4.02M |
| | FY2029 | 1,805 | 1,777 | **27.9** | 376 | 344 | 478 | 79% | $4.34M |
| B Growth | FY2027 | 1,764 | 1,705 | 58.8 | 442 | 369 | 478 | 92% | $6.28M |
| | FY2028 | 1,828 | 1,776 | 52.3 | 441 | 377 | 478 | 92% | $6.58M |
| | FY2029 | 1,895 | 1,837 | **57.9** | 449 | 379 | 478 | 94% | $8.02M |
| C Constraint | FY2027 | 1,735 | 1,619 | 117.1 | 476 | 327 | 394 | 121% | $11.58M |
| | FY2028 | 1,770 | 1,620 | 150.1 | 526 | 335 | 394 | 134% | $16.05M |
| | FY2029 | 1,805 | 1,623 | **182.4** | 566 | 336 | 394 | 144% | $20.83M |

Utilisation can be below 100% at organisation level while shortages remain, because spare capacity in one cell cannot fill another (e.g. Medical Practitioners at 149% in FY2027 Baseline while RNs are at 47%).

**3-year totals:**

| Scenario | Agency cost | Total labour cost | Unfilled FTE-years |
|---|---|---|---|
| Baseline | $13.2M | $810.4M | 61 |
| Growth | $20.9M | $831.6M | 97 |
| Constraint | $48.5M | $818.1M | **252** |

Constraint total cost is *lower* than Growth because roles go unfilled. Lower cost here means less service delivered, not efficiency.

**Where the shortage sits** (FY2029, shortage FTE):

| Job family | Baseline | Growth | Constraint |
|---|---|---|---|
| Care Worker | 1.7 | 14.3 | **76.9** |
| Medical Practitioner | **11.4** | 18.6 | 31.4 |
| Allied Health | 1.6 | 6.2 | 26.0 |
| Registered Nurse | 0.0 | 0.0 | 20.6 |
| Enrolled Nurse | 6.7 | 9.6 | 9.8 |
| Administration | 5.4 | 6.8 | 11.4 |

By site under Constraint: Perth North 61.7, Perth South 41.4, Bunbury 30.4, Broome 20.4, Geraldton 17.9, Kalgoorlie 10.6.

## 5. Sensitivity (Baseline, one assumption at a time)

| Assumption (low / high) | FY2029 shortage FTE (low / high) | 3-year cost (low / high) |
|---|---|---|
| Recruitment capacity ×0.8 / ×1.2 | 95 / 13 | $804.8M / $812.9M |
| Attrition ×0.8 / ×1.2 | 14 / 75 | $811.4M / $808.4M |
| FTE per head ×0.95 / ×1.05 | 56 / 16 | $800.8M / $819.3M |
| Demand growth −1pp / +1pp | 19 / 42 | $798.7M / $822.2M |
| EN→RN conversion ×0 / ×2 | 23 / 33 | $810.7M / $810.3M |
| Wage growth −1pp / +1pp | 28 / 28 | $794.7M / $826.2M |
| Agency premium 1.3 / 2.0 | 28 / 28 | $807.6M / $813.2M |

**Recruitment capacity and attrition dominate the shortage.** Wage growth dominates cost but not shortage. If part-time preferences grow (lower FTE per head), the hires needed rise sharply.

**Monte Carlo** (2,000 draws; attrition ×tri(0.85, 1, 1.25), demand ±N(0, 0.75pp), capacity ×tri(0.7, 1, 1.15), conversion ×U(0.5, 1.5)): FY2029 shortage P10 **18**, P50 **47**, P90 **111** FTE; 3-year agency cost P10 $10.2M, P50 $17.5M, P90 $30.3M.

The median is above the deterministic Baseline (28) because the plausible ranges are skewed toward higher attrition and lower capacity. **The risk is asymmetric.**

## 6. Interventions tested against the Constraint scenario

| Option (illustrative effect and cost) | FY2029 shortage | Shortage FTE-years avoided (3 yrs) | Programme cost (3 yrs) | Programme cost per FTE-year avoided | Net 3-yr labour cost change* |
|---|---|---|---|---|---|
| None (Constraint) | 182.4 | – | – | – | – |
| M1 Retention programme: clinical attrition −15% | 133.6 | 105.1 | $5.85M | $55.7k | +$7.9M |
| M2 Regional recruitment uplift: +30% capacity in Rest of WA | 138.9 | 97.0 | $0.78M | **$8.0k** | +$3.9M |
| M3 Grow-your-own: EN→RN ×2, +12 graduates | 174.6 | 13.3 | $1.44M | $108.3k | +$1.0M |
| M4 Agency panel: premium 1.65 → 1.45 | 182.4 | 0 | $0.18M | n/a | **−$5.7M** |
| All four combined | 104.8 | 173.6 | $8.25M | $47.5k | +$9.0M |

\*Net change includes the salaries of the extra staff retained or hired. Filling roles costs money; the benefit is the care delivered (unfilled FTE falls from 101 to 59 in FY2029 with all four options).

**M2 being cheapest is a result of the assumed effect and cost, both of which are illustrative.** The finding to take to executives is the *structure*: capacity- and attrition-side levers move the shortage; agency procurement moves only cost. Each option needs a business case using KHS's own pilot evidence before funding.
