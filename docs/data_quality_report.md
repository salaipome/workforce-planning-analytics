# Data quality report

All figures come from `outputs/logs/quality_metrics_*.csv`, `outputs/logs/exceptions_*.csv` and `outputs/tables/` after running `./run_all.sh`. Nothing below is typed in by hand without a source file.

## 1. Real public data (ABS / JSA / WA PSC)

### Profiling results

| Dataset | Raw rows | Missing values | Duplicate keys | Flagged (kept) | Period |
|---|---|---|---|---|---|
| ABS Labour Force (WA, AUS) | 2,871 | 0 | 0 | 0 | 2005-01 – 2026-09 |
| ABS Job Vacancies | 7,878 | **510** (status `q`: survey suspended 2008-Q3 – 2009-Q3) | 0 | 178 high-RSE (`y`/`z`) | 2005-Q1 – 2026-Q3 |
| ABS Labour Account (division, SA) | 2,944 | 286 (public/private split before 2010-Q3; 2008-09 JV gap) | 0 | 0 | 1994-Q3 – 2026-Q2 |
| ABS Labour Account (subdivisions, original) | 4,608 | 60 | 0 | 0 | 1994-Q3 – 2026-Q2 |
| ABS Estimated Resident Population (WA) | 7,080 | 0 | 0 | 0 | 2011-Q3 – 2026-Q1 |
| ABS WPI / AWE | 2,580 / 609 | 0 | 0 | 0 | to 2026-Q2 / 2026-S1 |
| Census 2021 G54 / G56 / G60 | 1,890 / 630 / 900 | 0 | 0 | 0 | 2021 |
| JSA IVI 4-digit (WA + AUST, long) | 177,346 | 3,458 suppressed (`.`) | – | – | 2006-03 – 2026-09 |
| ABS EQ08 | 801,208 scanned | – | – | – | 1986-08 – 2026-02 |
| JSA REOS | – | – | – | 6 small-sample values (`nn%*`) converted and flagged | 2020-09 – 2026-09 |

### Validation and reconciliation rules (real data)

| Rule | Result | Interpretation |
|---|---|---|
| R1 Labour Force: full-time + part-time = employed (±0.5k) | 261/261 pass (Australia) | WA SA part-time is **not published** in the LF dataflow, so it is derived as employed − full-time and flagged `obs_status = derived` |
| R2 Unemployment rate recomputed from levels (±0.1pp) | 522/522 pass | |
| R3 Job vacancies: sum of states = Australia (±1%) | 82/82 pass | |
| R4 Job vacancies: sum of industries = all industries (±1%) | 68/68 pass | |
| R5 ERP: sum of single-year ages = published total | 59/59 pass **after** removing the overlapping `8599` "85 and over" code | Summing every AGE row would give 3.0× the population (single years + 5-year groups + total) |
| R6 Census: Greater Perth + Rest of WA within −1.5%…+0.1% of WA | 21/21 pass | WA total includes migratory/offshore people and those with no usual address; cells are perturbed |
| R7 Census G56: sum of occupations = industry total (±10) | 20/21 pass | 1 exception (Public Administration, −15), consistent with perturbation; kept and logged |
| JSA projections: 4-digit sum / major-group sum | 0.977 | "Not further defined" (NFD) employment sits outside unit groups; projections used as growth rates, not levels |

## 2. Synthetic internal data (fictional KHS)

### Before and after (HRIS snapshot)

| Metric | Raw extract | After pipeline |
|---|---|---|
| Rows | 2,057 | **1,990** (one per active employee) |
| Exact duplicate rows | 25 | 0 |
| Distinct location values | 26 | 6 |
| Distinct job family values | 23 | 8 |
| FTE missing or outside (0, 1.0] | 49 | 0 |
| hire_date in `dd/mm/yyyy` | 298 | 0 (all ISO) |
| Separated staff still "Active" | 30 | 0 |
| Stale prior records for the same person | 12 | 0 |
| Total FTE | 1,728.5 (naive sum of the raw extract) | **1,627.5** (truth 1,627.6) |
| Headcount | 2,057 rows marked Active | **1,990** (truth 1,990) |

**What this means for an executive:** reporting straight from the raw extract would have **overstated headcount by 3.4% and FTE by 6.2%**. Worse, the raw FTE (1,728.5) is *above* the 1,701.8 FTE establishment, so KHS would have looked over-staffed when it actually has 74.3 vacant FTE.

### Rules and measured detection

The cleaned snapshot was scored against the generator's hidden truth (`outputs/tables/cleaning_scorecard.json`, `cleaning_detection_scores.csv`):

| Rule | Treatment | Injected | Flagged | Recall | Precision |
|---|---|---|---|---|---|
| R-H1 exact duplicate | remove | 25 | 25 | 100% | 100% |
| R-H2 location variants | trim, case-fold, expand abbreviations, map to master list | 145 | 145 | 100% | 100% |
| R-H3 job family variants | synonym table reviewed with HR | 199 | 199 | 100% | 100% |
| R-H5 implausible date of birth | set null; excluded from age analysis | 6 | 6 | 100% | 100% |
| R-H6 terminated but Active | status → Terminated | 30 | 30 | 100% | 100% |
| R-H7 same person, two active records | keep latest hire | 12 | 12 | 100% | 100% |
| R-H8a FTE > 1.0 (decimal shift) | divide by 10, confirmed against payroll hours | 10 | 10 | 100% | 100% |
| R-H8b missing FTE | impute from payroll ordinary hours ÷ 76; else job-family median | 39 | 39 | 100% | 100% |
| R-H9 missing employment type | set "Unknown" (FTE 1.0 is ambiguous) for HR to confirm | 19 | 19 | 100% | 100% |
| R-A1 requisition dates swapped | swap back | 10 | 10 | 100% | 100% |
| R-A2 Filled with no filled date | recover from HRIS HIRE event linked by requisition or employee | 15 | 15 | 100% | 100% |

Field accuracy after cleaning: job family 100%, location 100%, hire date 100%, FTE 99.95% (one imputed FTE differs from truth by more than 0.05).

> **Read the 100% with care.** The same author wrote the defect generator and the rules, so perfect recall is expected. It proves the pipeline works as designed and that detection *can be measured*. It is **not** evidence of performance on real HRIS data, which will contain defect types not anticipated here. In production, the scorecard would be replaced by sample audits against source documents.

### Cross-source reconciliation

**HRIS vs payroll** (fortnight ending 28 Jun 2026; `recon_hris_vs_payroll.csv`):

| Category | Count | Explanation |
|---|---|---|
| Matched | 1,961 | |
| Payroll only: final pay after separation | 20 | Leave payouts; confirmed by SEPARATION event |
| Payroll only: contractor via payroll | 18 | `C`-prefixed IDs, no HRIS record. Contingent workforce to report separately |
| Payroll only: unexplained | **0** | |
| HRIS only: not paid this fortnight | 29 | Likely leave without pay; listed for payroll to confirm |

For matched staff, contracted FTE and paid ordinary hours ÷ 76 differ by more than 0.1 FTE for 1 employee (mean absolute difference 0.019).

**Establishment vs filled FTE (FY2026):** 1,701.8 budgeted FTE, 1,627.5 filled FTE, **74.3 vacant FTE (4.4%)**. Nine cost centres are over establishment, mainly Registered Nurses at Perth South (−14.1 FTE), where graduates are placed above budget. Open requisitions cover only about 22.8 FTE of the vacancies; another **80.3 FTE of vacant establishment, summed over under-filled cost centres, has no live requisition** (`recon_establishment_vs_filled.csv`). That matters because vacancies without a requisition will not be filled.

**Movements vs snapshot:** 0 staff hired since 1 Jul 2022 lack a HIRE event, and 0 staff with a SEPARATION event remain active. Rebuilding the opening stock backwards from the 30 Jun 2026 snapshot gives **1,819** at 1 Jul 2022, the same as the true figure. This confirms that the stock-and-flow identity closes on the history before it is used for forecasting.

**SQL vs Python:** headcount, FTE, vacancy rate and turnover for FY2023–FY2026 match exactly (`sql_vs_python_check.csv`).

**Excel vs Python:** 432 model cells compared across 3 scenarios; all match (maximum absolute difference 5.8 × 10⁻⁸) (`excel_vs_python_check.csv`).

## 3. Quality metrics to monitor in production

| Metric | Threshold | Owner |
|---|---|---|
| Unmapped job family / location values | 0 | HRIS administrator |
| Payroll-only unexplained records | 0 | Payroll |
| HRIS FTE vs paid FTE mismatch > 0.1 | < 1% of matched staff | Payroll + HR |
| Separations processed > 14 days after last day | < 5% | HR operations |
| Filled requisitions missing a filled date | 0 | Talent acquisition |
| Rebuilt opening stock vs prior-period snapshot | exact | Workforce analytics |
