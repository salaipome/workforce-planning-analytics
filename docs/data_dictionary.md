# Data dictionary and lineage

**Provenance codes:** `REAL` = public data as published; `SYNTHETIC` = generated for the fictional organisation; `DERIVED` = computed by this pipeline from the inputs shown. Every synthetic table carries `record_source = SYNTHETIC`.

## Lineage

```
REAL   data/raw/abs/*.csv (ABS Data API) ──► clean_public_data.py ──► data/processed/public_observations.csv (+ extracts)
REAL   data/raw/{jsa,abs,other}/*.xlsx   ──► parse_external_files.py ──► data/processed/ivi_*, osl_*, eq08_*, reos_*, ...
REAL   labour_account + census G54       ──► generate_synthetic_data.py (tightness index, age calibration)
SYNTH  data/synthetic/*.csv (with injected defects) ──► clean_internal_data.py ──► data/processed/*_clean.csv
                                                                              └─► outputs/tables/recon_* , cleaning_scorecard.json
DERIVED processed tables ──► analyse_workforce.py ──► outputs/tables/int_* (synthetic), ext_* (real), risk_* (mixed)
DERIVED real series      ──► forecast_backtest.py ──► outputs/tables/backtest_*
DERIVED int_* + ext_*    ──► scenario_model.py   ──► outputs/tables/model_*  ──► build_excel_model.py ──► outputs/excel/*.xlsx
SYNTH  raw extracts      ──► run_sql.py (sql/01-05) ──► data/processed/workforce.db, outputs/tables/sql_*
```

`data/synthetic/_truth/` holds the generator's clean ground truth and the log of injected defects. **It is never an input to the cleaning rules.** It is read in exactly three places:

1. To score the cleaning step (`cleaning_scorecard.json`).
2. To validate the rebuilt opening headcount (1,819 rebuilt = 1,819 true).
3. In `analyse_workforce.py`, for two history fields a real HRIS holds but the active-employee snapshot extract does not carry:
   - terminated employees' start and end dates, used for 12-month retention;
   - monthly filled FTE, used for the agency cover ratio.

In a real deployment, (3) would come from an HRIS "all employees" extract and monthly position snapshots.

## Synthetic source extracts (`data/synthetic/`)

### `hris_employee_snapshot.csv` – HRIS employee master as at 30 Jun 2026 (2,057 raw rows)
| Field | Type | Description | Known defects (injected) |
|---|---|---|---|
| employee_id | text | HRIS employee number (a new number on rehire) | exact duplicate rows (25); stale prior IDs for rehired people (12) |
| person_id | text | Persistent person key across rehires | – |
| job_family | text | Job family (free-text in the source system) | 199 variant labels (e.g. "RN", "AIN", "Doctor") |
| location | text | Work site | 145 variants (case, "Nth", "Campus" suffix, spaces) |
| cost_centre | text | Finance cost centre (system-controlled) | – |
| employment_type | text | Permanent Full-time / Permanent Part-time / Fixed-term / Casual | 19 missing |
| fte | number | Contracted FTE (1.0 = 76 h per fortnight) | 39 missing; 10 decimal-shift errors (×10) |
| classification_level | int | Award level 1–4 | – |
| annual_salary_fte | number | Annual base salary at 1.0 FTE (AUD) | – |
| date_of_birth | date | ISO date | 6 placeholder `1900-01-01` |
| gender | text | Female / Male / Non-binary/Not stated | – |
| hire_date | date | Start date | 298 in `dd/mm/yyyy` |
| status | text | Active | 30 separated staff still "Active" (termination date populated) |
| termination_date, separation_reason | date, text | Populated only for the late-processed leavers | – |

### `hris_movements.csv` – workforce events, Jul 2022 – Jun 2026
`event_id`, `employee_id`, `person_id`, `event_type` (HIRE / SEPARATION / TRANSFER / ROLE_CHANGE), `event_date`, `job_family`, `location` (destination), `from_job_family`, `from_location` (origin, for TRANSFER/ROLE_CHANGE), `reason` (separations: Resignation, Retirement, End of contract, Dismissal, Other), `source` (hires: External, Graduate program), `requisition_id`. **Defect:** 20 duplicated events.

### `payroll_fortnight.csv` – pay period ending 28 Jun 2026
`employee_id`, `cost_centre`, `fte`, `annual_salary_fte`, `ordinary_hours`, `overtime_hours`, `gross_pay`, `pay_period_end`. **Defects / real-world differences:** 29 active staff not paid (leave without pay), 20 final pays for leavers, 18 contractors paid through payroll with no HRIS record (`C9xxx`).

### `finance_establishment.csv`
`cost_centre`, `fy` (FY2023–FY2027), `budgeted_fte`: the approved FTE establishment, used as **demand**.

### `ats_requisitions.csv`
`requisition_id`, `job_family`, `location`, `open_date`, `reason` (Replacement, New position, Re-advertised, Replacement (internal move)), `applicants`, `status` (Filled / Cancelled / Open), `filled_date`, `filled_by` (employee_id), `source` (External / Internal transfer / Graduate program), `cancel_date`. **Defects:** 2% duplicates, 10 swapped open/filled dates, 15 filled with no filled date.

### `agency_usage.csv`
`month`, `job_family`, `location`, `agency_hours`, `agency_cost` (AUD).

### `cost_centre_map.csv`, `market_tightness_index.csv`, `synthetic_metadata.json`
Reference mapping; the monthly tightness index derived from **real** ABS Labour Account data; all generator parameters and the random seed (20260630).

## Cleaned / processed tables (`data/processed/`)

### `employee_snapshot_clean.csv` (1,990 rows: one per active employee)
Adds `anzsco` (mapped unit group), `gccsa`, `remoteness`, `age`, `tenure_years`, and `fte_imputed` ("payroll hours", "job family median" or blank).

### `public_observations.csv` (REAL, about 31k rows, long format)
One row per published observation: `dataset`, `<dimension>_code` / `<dimension>` label pairs (measure, sex, age, adjustment, region, industry, sector, index, occupation), `period` (as published), `period_start` (date), `fy`, `value`, `unit`, `unit_mult`, `value_scaled` (= value × 10^unit_mult), `obs_status` (ABS flags, plus `derived` for WA part-time).

### Other processed tables
| File | Grain | Notes |
|---|---|---|
| `lf_state_monthly.csv` | region × month | wide: employed FT/PT/total, LF, participation, unemployment rate |
| `jv_quarterly.csv` | region × sector × industry × adjustment × quarter | job vacancies ('000) |
| `labour_account_health.csv` | industry × adjustment × quarter | filled jobs, vacancies, hours, labour cost |
| `wpi.csv`, `awe.csv` | series × period | |
| `erp_wa_age_bands.csv` | quarter | WA population 0–14 / 15–64 / 65–74 / 75+ (single years only, reconciled to total) |
| `census2021_g54_wa.csv` etc. | region × industry × age | |
| `ivi_4digit_wa_aus.csv` | anzsco × state (WA, AUST) × month | `ads` (3-month average), `suppressed` flag |
| `osl_2026_unit_group.csv` | anzsco | `rating_2026`, `shortage_driver` |
| `employment_projections_occupation.csv` | anzsco | 2025/2030/2035 employment, `cagr_10y` |
| `eq08_wa_health_occupations.csv` | anzsco × quarter | WA employed ('000), persons |
| `reos_recruitment_difficulty.csv`, `job_mobility_industry.csv`, `wa_psc_anzsco.csv`, `osl_key_findings.csv` | | |
| `workforce.db` | SQLite | staging, standardised, reconciliation, metric and star-schema tables built by `sql/` |

## Model output (`outputs/tables/model_cells_all_scenarios.csv`)
Grain: scenario × year (FY2027–29) × job family × location. Columns follow the stock-and-flow equation: `hc_start`, `separations`, `conv_out`/`conv_in` (EN→RN), `net_transfer`, `grads`, `required_hires`, `capacity`, `hires`, `hc_end`, `supply_fte`, `demand_fte`, `gap_fte` (+ = shortage), `agency_fte`, `unfilled_fte`, `employee_cost`, `agency_cost`, `recruitment_cost`, `total_cost` (nominal AUD).

## Reference mappings (`src/common.py`)
| Job family | ANZSCO | Title |
|---|---|---|
| Registered Nurse | 2544 | Registered Nurses |
| Midwife | 2541 | Midwives |
| Enrolled Nurse | 4114 | Enrolled and Mothercraft Nurses |
| Medical Practitioner | 253 (2531–2539) | Medical Practitioners |
| Allied Health | 252 (2521–2527) | Health Therapy Professionals |
| Care Worker | 4233 (+4231 for IVI) | Nursing Support and Personal Care Workers |
| Administration | 5 | Clerical and Administrative Workers |
| Support Services | 8 | Labourers |

| Site | GCCSA | SA4 | Remoteness (indicative) |
|---|---|---|---|
| Perth North | Greater Perth | Perth – North West | Major city |
| Perth South | Greater Perth | Perth – South East | Major city |
| Bunbury | Rest of WA | Bunbury | Inner regional |
| Geraldton | Rest of WA | WA – Outback (South) | Outer regional |
| Kalgoorlie | Rest of WA | WA – Outback (South) | Remote |
| Broome | Rest of WA | WA – Outback (North) | Very remote |
