# Workforce Planning Analytics: From Workforce Data to Executive Decisions

A reproducible portfolio project for workforce planning analytics. It covers the full chain: verified public labour-market data and multi-source internal HR data → cleaning, reconciliation and validation → workforce metrics → backtested forecasts and a 3-year stock-and-flow scenario model → executive recommendations and a Power BI design.

**Setting:** *Kestrel Health Services* (KHS), a **fictional** 2,000-employee health provider with six sites across Western Australia.

**Case study page:** https://salaipome.github.io/portfolio/case-studies/workforce-planning-analytics.html

| Provenance | What | Where |
|---|---|---|
| **REAL** public data | ABS (Labour Force, Job Vacancies, Labour Account, WPI, AWE, population, Census 2021, EQ08, Job Mobility), Jobs and Skills Australia (IVI, Occupation Shortage List 2026, Employment Projections, REOS), WA Public Sector Commission | `data/raw/` (downloaded), `data/processed/` |
| **SYNTHETIC** internal data | HRIS snapshot and movements, payroll, finance establishment, applicant tracking, agency use for the fictional KHS, with deliberately injected data-quality defects | `data/synthetic/` (`record_source = SYNTHETIC`) |
| **MODEL** output | Scenarios, sensitivity, Monte Carlo, interventions | `outputs/tables/model_*`, `outputs/excel/` |

Synthetic and real records are never mixed in one table without a provenance column. Every chart footer states its provenance.

## Headline results

Internal figures are synthetic; [R] = real public data.

- **Data quality:** the raw HRIS extract had 2,057 "active" rows and 1,728.5 FTE. After cleaning there are **1,990 employees and 1,627.5 FTE** (true value 1,627.6). Raw data would show KHS over establishment when it is **74.3 FTE (4.4%) vacant**.
- **Labour market [R]:**
  - WA vacancies per unemployed person: 0.56 (2015–19 average: 0.24).
  - WA RN online ads: +93% vs 2019.
  - Medical ads: +189% vs 2019.
  - RNs, midwives, doctors and key allied health occupations are in national shortage (JSA OSL 2026).
- **Forecast error [R]:** the best of five methods has a 12-quarter-ahead MAPE of 3.5% (national health employment) and 10.1% (WA Registered Nurses).
- **Scenarios (FY2029 shortage):**
  - Baseline: **28 FTE**.
  - Growth: **58 FTE**.
  - Constraint: **182 FTE**, with 3-year agency spend at $48.5M against $13.2M in the Baseline.
  - Monte Carlo P10–P90: 18–111 FTE.
- **Drivers:** recruitment capacity and attrition dominate. Agency pricing changes cost but not supply.

## Quick start

```bash
cd workforce-planning-analytics
```

```bash
python3 -m pip install -r requirements.txt
```

```bash
./run_all.sh
```

`./run_all.sh` downloads about 80 MB of public data and takes about 3 minutes. Use `./run_all.sh --offline` to reuse files already in `data/raw/`.

Tested with Python 3.9.6 on macOS. The synthetic data is seeded (20260630), so a run reproduces the results exactly. Public data can be revised by publishers; `data/raw/manifest.csv` records the SHA-256 of each file used.

## Repository structure

```
workforce-planning-analytics/
├── README.md                     this file
├── run_all.sh                    end-to-end pipeline (steps 1-10)
├── requirements.txt
├── src/
│   ├── common.py                 paths, job-family↔ANZSCO and site↔GCCSA mappings, FY labels, QualityLog
│   ├── fetch_public_data.py      1  ABS Data API queries + JSA/ABS/WA files → data/raw (+ manifest, SHA-256)
│   ├── clean_public_data.py      2  ABS SDMX → tidy long table; profiling; rules R1–R7
│   ├── parse_external_files.py   2b JSA IVI/OSL/projections/REOS, ABS EQ08 & Job Mobility, WA PSC → tidy
│   ├── generate_synthetic_data.py 3 fictional KHS source systems + injected defects + hidden truth
│   ├── clean_internal_data.py    4  cleaning rules R-H1…R-H9, R-A1…R-A2; HRIS↔payroll↔finance reconciliation
│   ├── score_detection.py        4b recall/precision of each rule vs injected defects
│   ├── analyse_workforce.py      5  headcount/FTE, turnover, retention, vacancy, time-to-fill, cost; external indicators; risk score
│   ├── forecast_backtest.py      6  rolling-origin backtest of 5 methods on real series
│   ├── scenario_model.py         7  stock-and-flow model, 3 scenarios, interventions, tornado, Monte Carlo, model backtest
│   ├── build_excel_model.py      8  Excel model with live formulas; recalculated and verified vs Python
│   ├── run_sql.py                9  runs sql/*.sql on SQLite; cross-checks vs Python
│   └── make_charts.py            10 portfolio charts + dashboard wireframe
├── sql/                          01 standardise · 02 quality checks · 03 reconciliation · 04 metrics · 05 star schema
├── data/
│   ├── raw/                      downloads (git-ignored; manifest.csv and other_sources.csv kept)
│   ├── processed/                tidy, validated tables (+ workforce.db)
│   └── synthetic/                fictional KHS extracts; _truth/ used only for scoring and validation
├── outputs/
│   ├── charts/                   12 PNG charts
│   ├── excel/                    KHS_workforce_scenario_model.xlsx
│   ├── tables/                   every computed metric (int_* synthetic, ext_* real, model_*, backtest_*, recon_*, sql_*)
│   └── logs/                     quality_metrics_*.csv, exceptions_*.csv, run_all.log
└── docs/
    ├── case_study_report.md      the full narrative (start here)
    ├── executive_summary.md      findings and recommendations for executives
    ├── business_case.md          organisation, question, stakeholders, constraints, success measures
    ├── source_register.md        verified datasets with direct links, licences, limitations, reconciliation
    ├── data_dictionary.md        fields, provenance, lineage
    ├── data_quality_report.md    before/after metrics, rules, reconciliations
    ├── metric_definitions.md     formulas, denominators, results
    ├── forecasting_and_scenarios.md  model equations, assumptions, backtests, scenarios, sensitivity
    ├── dashboard_spec.md         Power BI pages, KPIs, star schema, DAX (design only)
    ├── limitations_and_next_steps.md  limitations and the real internal data needed
    └── resume_and_star.md        resume entry and STAR interview answer
```

## Verification built into the pipeline

| Check | Result |
|---|---|
| ABS/Census reconciliation rules R1–R7 | All pass or explained (`outputs/logs/quality_metrics_public.csv`) |
| Cleaned snapshot vs hidden truth | Headcount exact; family, location and hire date 100%; FTE 99.95% |
| Stock-flow history: rebuilt opening stock 1 Jul 2022 | 1,819 rebuilt = 1,819 true |
| SQL vs Python (headcount, FTE, vacancy, turnover FY2023–26) | Exact match |
| Excel formulas vs Python engine (432 cells, 3 scenarios) | All match (maximum difference 5.8 × 10⁻⁸) |
| Model identities (stock-flow, capacity, conversions) | Pass, every scenario |

## Honest limits

- Internal data is synthetic. Rule recall is 100% because I wrote both the defects and the rules.
- Shortage ratings are national only.
- Demand is proxied by the budgeted establishment.
- Intervention effects and costs are illustrative.
- No Power BI file has been built; the dashboard is a specification.

See [docs/limitations_and_next_steps.md](docs/limitations_and_next_steps.md).

## Data licences

ABS and JSA data are © Commonwealth of Australia, licensed under CC BY 4.0. WA Public Sector Commission data is used under WA Government copyright terms (non-commercial reuse with attribution). APSC data on data.gov.au is CC BY 3.0 AU. Details: [docs/source_register.md](docs/source_register.md). The code in this repository can be released under MIT if you add a LICENSE file.
