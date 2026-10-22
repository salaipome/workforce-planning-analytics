# Resume entry and interview answers

## Resume project entry

**Workforce Planning Analytics: From Workforce Data to Executive Decisions** | Portfolio project | Python, SQL, Excel, Power BI design | Oct 2026

- Sourced and verified 21 public data files (ABS Data API, JSA, WA Public Sector Commission), 17 datasets of which feed the analysis, in a reproducible pipeline with SHA-256 manifests and 7 reconciliation rules. Handled real quirks: a 2008–09 survey suspension, unpublished WA seasonally adjusted part-time employment, and age codes that triple-count if summed.
- Built a synthetic HRIS, payroll, finance and applicant-tracking dataset for a fictional 2,000-employee WA health provider, with 11 types of injected defects. The cleaning pipeline restored the true headcount (1,990) and FTE (1,627.5 vs 1,627.6). The raw extract would have overstated FTE by 6.2%.
- Backtested five forecast methods on real ABS series (rolling origin, 12-quarter horizon). The best method's error was 3.5% for national health employment, against 12.9% for a no-change forecast. Used the results to justify occupation-projection-based demand assumptions.
- Developed a 3-year stock-and-flow scenario model (48 job-family × site cells) in Python and in an Excel workbook with live formulas, verified to match on all 432 compared cells. Added sensitivity, a 2,000-draw Monte Carlo and intervention testing.
- Translated results into 7 executive findings and a Power BI specification (star schema, DAX, wireframe). Showed that recruitment capacity and attrition, not agency pricing, drive the modelled shortage (13–95 FTE range).

*Shorter version (3 bullets):*
- Integrated 17 public ABS / JSA / WA datasets and a synthetic multi-system HR dataset into a reproducible Python/SQL pipeline with validation rules and exception logs.
- Built and backtested a 3-year stock-and-flow workforce scenario model (Python + Excel, cross-verified) with sensitivity and Monte Carlo analysis.
- Produced an executive summary and a Power BI design that link shortages, recruitment capacity and labour cost to specific actions.

## STAR response: "Tell me about a time you used data to support workforce planning decisions."

**Situation.** I wanted to show how a workforce planning analyst would answer an executive question for a WA health provider: how to manage shortages, vacancies, recruitment capacity and labour cost over three years. No real employer data was available to me, so I combined genuine public labour-market data with a clearly labelled synthetic internal dataset for a fictional 2,000-employee organisation.

**Task.** Build an evidence base that an executive could trust. That meant:
- reconcile HR, payroll and finance numbers;
- measure current vacancy, turnover and recruitment performance;
- forecast supply and demand under different scenarios;
- say which actions matter most, and how certain the answer is.

**Action.**
1. Verified and downloaded 17 public datasets from the ABS API, JSA and the WA Public Sector Commission. I validated them with reconciliation rules; for example, summing every age row in ABS population data triple-counts, so I filtered to single years and reconciled to the total.
2. Cleaned the synthetic HR extracts with documented rules:
   - duplicates, stale rehire records and separated staff still flagged as active;
   - FTE decimal errors, repaired using payroll hours;
   - inconsistent site and job-family labels.

   I reconciled HRIS to payroll, explaining every unmatched record, and rebuilt the 4-year stock-and-flow history so it closed exactly.
3. Backtested five forecast methods on real ABS series. Occupation-by-state data was too noisy to trend (about 10% error at 3 years), so I anchored demand on JSA occupation projections.
4. Built a 3-year stock-and-flow model with Baseline, Growth and Constraint scenarios. Where I could, I tied assumptions to evidence; for example, the Constraint capacity cut uses JSA's 57% vs 78% fill rates. I labelled the rest illustrative. I replicated the model in Excel and verified every formula against Python.
5. Ran sensitivity, Monte Carlo and intervention tests, then wrote seven findings with actions and triggers.

**Result.**
- The pipeline produced one reconciled view. The raw extract would have shown the organisation as over-establishment, when it was actually 74 FTE (4.4%) vacant.
- The model showed:
  - a 28 FTE shortage in the Baseline, against 182 FTE under Constraint;
  - recruitment capacity and attrition as the dominant drivers;
  - medical, allied, care-worker and regional roles as the priorities.
- Because the internal data is synthetic, I don't claim business impact. What the project demonstrates is the method, the controls and the communication. I can explain every number and its source, and I've documented what real data I'd need to rerun it.

## Likely follow-up questions (with honest answers)

- **"How do you know the model is accurate?"** I don't claim it is. I quantify error instead:
  - 3.5–10% MAPE at 3 years on real series, depending on granularity;
  - Monte Carlo P10–P90 of 18–111 FTE for the FY2029 shortage.

  The synthetic backtest only checks the mechanics.
- **"Headcount or FTE?"** FTE for demand, vacancy and cost; headcount for hiring, turnover and people metrics. The bridge is FTE per head: 0.82 here, against 0.71 for WA public-sector RNs.
- **"Why not use HCSA growth for demand?"** HCSA includes fast-growing social assistance (5.6% p.a.). Hospital occupations are projected to grow about 2–3% p.a. Using HCSA growth would roughly double the demand assumption.
- **"What would you do first with real data?"** Monthly HRIS snapshots including leavers, position-level establishment, and the ATS requisition lifecycle (see `limitations_and_next_steps.md`).
