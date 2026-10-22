# Limitations and next steps

## Limitations

### Data provenance
- **The organisation and all of its internal data are synthetic.** Every internal metric (turnover, time-to-fill, vacancy, agency cost) is the output of a simulation whose parameters I chose (`data/synthetic/synthetic_metadata.json`). Findings about KHS illustrate the *method*. They are not evidence about any real employer.
- The synthetic data is calibrated to real data in only two places:
  - ages follow the 2021 Census age profile of WA health workers;
  - monthly time-to-fill and quit intensity follow the ABS health vacant-job share.

  Other parameters (base turnover by family, salaries, cost per hire, agency premium) are illustrative.

### Cleaning and model validation
- Cleaning-rule recall of 100% is expected because the same author designed both the defects and the rules. Real HRIS data will contain unanticipated issues.
- The model backtest on synthetic history validates mechanics only, because the data-generating process resembles the model.

### Real-data coverage gaps
- **No state-level shortage ratings.** JSA's Occupation Shortage List is national. Regional shortage relies on "R" ratings and internal data.
- **No employer-level public benchmarks** for turnover, time-to-fill or vacancy rate in WA health.
  - ABS Job Mobility is industry-wide and national; WA × industry is not crossed.
  - JSA fill rates use a different definition.
- **ABS EQ08** state × occupation estimates are volatile (backtest error about 10% at 3 years) and coded to ANZSCO 2013.
- **The Census is from 2021.** Age profiles may have shifted.
- **IVI counts new online ads**, not vacancies. Changes in advertising behaviour (e.g. channel shifts) affect it independently of demand.
- **National Health Workforce Dataset** data could not be verified as a downloadable file and was not used.

### Model design
- **Annual time step.** Within-year timing (hiring lags, seasonal leave, graduate intake in February) is averaged out.
- **Demand = establishment.** Budgeted FTE stands in for clinical need, and establishment growth uses occupation-level national projections. Activity-based demand (bed days, ED presentations, aged-care places, nurse-to-patient ratios) is not modelled.
- **Productivity** is held flat. There is no activity data to measure it.
- **Capacity.** Demonstrated recruitment capacity assumes the past best year is repeatable. Capacity is not linked to recruiter numbers.
- **Interventions.** Effects and costs are illustrative, and their rankings change with those inputs.

## Next steps: obtaining real internal workforce data

| Priority | Data | Source system / owner | Use | Privacy / governance |
|---|---|---|---|---|
| 1 | Monthly employee snapshots incl. terminated staff (ID, person key, position, cost centre, FTE, employment type, start/end dates, DOB year, award level) | HRIS (e.g. SAP SuccessFactors, Workday) – HR Systems | Stock-and-flow history, turnover, retention, tenure | De-identify at extract; age bands not DOB; minimum cell size 5 |
| 2 | Position management / establishment by cost centre and month | Finance (budget system) | Demand, vacancy rate | |
| 3 | Requisition lifecycle (open, approval, advertised, offer, start, cancel; source, applicants) | ATS – Talent Acquisition | Time-to-fill, fill rate, capacity, funnel conversion | |
| 4 | Payroll hours by pay type (ordinary, overtime, leave, agency recharge) | Payroll | Paid FTE, overtime as a shortage signal, leave liability | |
| 5 | Agency / locum invoices by cost centre and role | Accounts payable / vendor management | Contingent workforce cost and FTE | |
| 6 | Activity and acuity (occupied bed days, ED presentations, theatre hours, care minutes) | Patient administration system | Activity-based demand and productivity | Aggregate only |
| 7 | Exit survey reasons; engagement survey by unit | HR | Drivers of turnover, retention-programme targeting | Aggregate only |
| 8 | Graduate and EN→RN programme cohorts and completion | Nursing education | Internal pipeline assumptions | |

**Governance before go-live:**
- A privacy impact assessment.
- A data-sharing agreement between HR, Finance and Payroll.
- An agreed metric dictionary (this repo's `metric_definitions.md` as the draft).
- Stakeholder agreement on risk-score weights.
- Reconciliation sign-off each month.

## Technical next steps
1. Replace `generate_synthetic_data.py` with extract loaders for the real systems; the cleaning and model code is source-agnostic.
2. Move to a monthly time step with hiring lags drawn from the time-to-fill distribution.
3. Add activity-based demand drivers and test them against the establishment.
4. Link recruitment capacity to recruiter FTE and requisition load.
5. Re-run the forecast-method backtest on 3+ years of real KHS history.
6. Build the Power BI report from `dashboard_spec.md` and schedule refreshes.
