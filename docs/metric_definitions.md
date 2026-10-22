# Metric definitions and measured results

**Provenance:** Values marked **[S]** are computed from the **synthetic** KHS data. They are case-study results, not real-world facts. Values marked **[R]** are computed from **real** public data.

## Workforce size and mix

| Metric | Definition / formula | Denominator & date | Result | Interpretation |
|---|---|---|---|---|
| Headcount | Count of unique active employees (after de-duplication and person-level rules) | Snapshot 30 Jun 2026 | **1,990** [S] | People. Used for turnover, hiring and culture metrics |
| FTE | Σ contracted FTE (1.0 = 76 ordinary hours per fortnight) | Snapshot 30 Jun 2026 | **1,627.5** [S] | Work capacity. Used for demand, vacancy and cost |
| FTE per head | FTE ÷ headcount | 30 Jun 2026 | 0.818 [S] (Care Workers 0.72, Medical 0.90) | The bridge between heads to hire and FTE to fill. Benchmark: WA public-sector RNs are **0.71** [R] (WA PSC 2025-26, 14,755 FTE / 20,795 headcount) |
| Employment-type mix | Share of headcount by Permanent FT / PT / Fixed-term / Casual | 30 Jun 2026 | PT 719, Fixed-term 211, Casual 129, Unknown 19 of 1,990 [S] | High part-time share raises the hires needed per FTE |
| Location mix | Headcount and FTE by site / GCCSA | 30 Jun 2026 | Greater Perth 1,193 (60%); Rest of WA 797 (40%) [S] | |
| Age 55+ share | Headcount aged ≥ 55 ÷ headcount (6 nulls excluded) | 30 Jun 2026 | **21.5%** [S]. WA HCSA Census 2021: 22.9%; Rest of WA 27.7% [R] | Retirement exposure over the horizon |

## Movement

| Metric | Definition / formula | Denominator & date | Result | Interpretation |
|---|---|---|---|---|
| Hires | Count of HIRE events (external + graduate) | Financial year | FY2026: 323 [S] | |
| Separations | Count of SEPARATION events (all reasons) | Financial year | FY2026: 285 [S] | |
| Turnover rate | Separations ÷ average headcount, where average = (opening + closing) ÷ 2 and opening is rebuilt from movements | FY2023–FY2026 | 17.7% → 16.8% → 14.9% → **14.5%** [S] | Benchmark (not a target): ABS Job Mobility HCSA outflow **10.8%** (5.3% left employment + 5.4% changed jobs, Feb 2026) [R] |
| Voluntary share | Resignations ÷ separations | FY2026 | 77.2% [S] | Most turnover is controllable |
| Early attrition | Hires who separated within 365 days of start ÷ hires in the cohort | Hires 1 Jul 2023 – 30 Jun 2025 | **24.2%** [S]; Care Workers 38.8% | Onboarding and first-year experience |
| 12-month retention | Employees present on 1 Jul 2025 still employed on 30 Jun 2026 ÷ employees present on 1 Jul 2025 | FY2026 | 88.1% [S] | Not 1 − turnover: excludes people hired during the year |
| Internal mobility | TRANSFER events between sites; ROLE_CHANGE events (EN→RN) | FY2026 | 34 transfers; 8 EN→RN; EN→RN rate 5.5% p.a. (FY2023–26) [S] | Internal supply |

## Vacancies and recruitment

| Metric | Definition / formula | Denominator & date | Result | Interpretation |
|---|---|---|---|---|
| Vacant FTE | Budgeted FTE (Finance establishment) − filled FTE (HRIS), by cost centre | FY2026 establishment vs 30 Jun 2026 | **74.3 FTE** [S] | Requires the establishment. Not available from public data |
| Vacancy rate | Vacant FTE ÷ budgeted FTE | as above | **4.4%** overall; Broome 14.0%, Kalgoorlie 9.8%, Geraldton 9.2%, Perth South 1.0% [S] | |
| Open requisitions | Requisitions with status Open at snapshot | 30 Jun 2026 | 28 (1 open > 90 days) [S] | Compare with vacant FTE to find unrequisitioned vacancies |
| Time-to-fill | Filled date − requisition open date (days), for filled requisitions; median and P90 | Fills in FY2026 | Median **39 days** (P90 by family: Medical 213, Allied 135) [S]; trend 48 → 43 → 42 → 39 | Benchmark: OSL 2026 vacancy duration 10.6 weeks for shortage occupations vs 7.8 weeks otherwise [R] |
| Fill rate | Filled ÷ (filled + cancelled) requisitions closed in the year | FY2026 | 91.3% overall; Broome 73.7% [S] | Benchmark: JSA OSL fill rate 57% (shortage) vs 78% (non-shortage), 2025-26 [R]. *Different definition*: JSA measures vacancies filled within the survey window |
| Demonstrated recruitment capacity | Highest annual external hires per family × site, FY2023–26 | FY2023–26 | 478 hires a year [S] | Throughput proven to be achievable. Used as the model's hiring ceiling |

## Labour cost and productivity

| Metric | Definition / formula | Result | Notes |
|---|---|---|---|
| Employee cost (annualised) | Σ salary per FTE × FTE × on-cost factor 1.25 | $232.2M [S] | On-cost factor illustrative (12% superannuation guarantee is legislated; other on-costs assumed) |
| Agency spend | Σ agency invoices | $3.6M (FY2023) → **$6.6M (FY2026)**; 39.8 agency FTE [S] | Medical practitioners are $2.67M of FY2026 agency cost |
| Wage growth | ABS WPI, HCSA, total hourly rates excl. bonuses, year-on-year | 3.8% (2026-Q2); 8-quarter average 3.71% [R] | Model wage assumption |
| Labour cost per hour (HCSA) | ABS Labour Account | $66.87 per hour worked (2026-Q2, SA) [R] | Context |
| Productivity | Not measured: no activity or output data in scope | n/a | Tested indirectly through FTE-per-head sensitivity |

## External labour-market indicators [R]

| Indicator | Definition | Latest value | Source |
|---|---|---|---|
| WA unemployment rate | Unemployed ÷ labour force (SA) | 4.22% (Sep 2026) vs Australia 4.72% | ABS LF |
| WA V/U ratio | Job vacancies (4-quarter mean of original) ÷ unemployed persons (SA, quarterly mean) | **0.56** vs 2015–19 average 0.24; peak 1.22 (2022-Q2) | ABS JV + LF |
| HCSA vacant-job share | Job vacancies ÷ (filled jobs + vacancies) | 2.19% (2026-Q2) vs 1.54% (2019 average) | ABS Labour Account |
| Online ads (WA) by occupation | JSA IVI 3-month average, Sep 2026; change vs 2019 average | RN 583.7 (+93%); Medical 421.7 (+189%); Allied 500.3 (+168%); Care 324.7 (+66%) | JSA IVI |
| Ads per 100 employed (WA) | 12-month mean IVI ÷ (4-quarter mean EQ08 employed × 1,000) × 100 | Allied 2.80, Medical 2.50, EN 2.11, RN 1.36, Care 0.78 | JSA IVI + ABS EQ08 |
| Shortage rating | JSA OSL 2026, national | S: RN, Midwife, Medical (6 unit groups), Allied (6 of 7); R: Enrolled Nurse; Care: 4231 S, 4233 NS | JSA OSL |
| Projected growth | JSA 10-year CAGR, May 2025–May 2035, national | Allied 3.03%, Medical 2.92%, Midwife 2.43%, RN 2.37%, EN 1.98%, Care 1.84%, Admin 0.94%, Support 0.50% | JSA Employment Projections |
| Recruitment difficulty | Share of recruiting employers reporting difficulty | WA 46%, HCSA 44%, all 45% (Sep 2026 quarter) | JSA REOS |
| WA population 75+ growth | 5-year CAGR of ERP aged 75+ | 5.4% p.a. (total WA 2.5%) | ABS ERP |

## Risk score (job family × site)

`risk = 0.25·vacancy + 0.15·turnover + 0.15·time-to-fill + 0.10·age55+ [S]  + 0.20·OSL shortage + 0.15·ads per 100 employed [R]`

Each component is min–max scaled to 0–100 across the 48 cells. OSL adds +0.5 for Rest-of-WA cells when the occupation has a regional (R) rating. Time-to-fill cells with fewer than 3 fills take the median of other cells. Bands: Low < 35, Medium 35–55, High > 55. **The weights are illustrative** and should be agreed with stakeholders.
