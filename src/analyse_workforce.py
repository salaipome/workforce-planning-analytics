"""Step 5 - Workforce analysis: internal (SYNTHETIC) metrics and external (REAL) labour market indicators.

Outputs in outputs/tables/:
  int_*  computed from the synthetic KHS data     -> case-study results, not real-world findings
  ext_*  computed from real public data           -> genuine measured results
  risk_* combine both, with the provenance of each component recorded
"""
import numpy as np
import pandas as pd

from common import PROCESSED, SYNTH, TABLES, SNAPSHOT_DATE, HISTORY_START, JOB_FAMILIES, LOCATIONS, fy_label, save_json

emp = pd.read_csv(PROCESSED / "employee_snapshot_clean.csv", parse_dates=["hire_date", "date_of_birth"],
                  dtype={"anzsco": str, "employee_id": str})
mv = pd.read_csv(PROCESSED / "movements_clean.csv", parse_dates=["event_date"], dtype={"employee_id": str})
req = pd.read_csv(PROCESSED / "requisitions_clean.csv", parse_dates=["open_date", "filled_date", "cancel_date"])
agency = pd.read_csv(SYNTH / "agency_usage.csv", parse_dates=["month"])
est = pd.read_csv(SYNTH / "finance_establishment.csv").merge(pd.read_csv(SYNTH / "cost_centre_map.csv"), on="cost_centre")
recon = pd.read_csv(TABLES / "recon_establishment_vs_filled.csv")
FAMS, LOCS = list(JOB_FAMILIES), list(LOCATIONS)
mv["fy"] = fy_label(mv.event_date)
FYS = ["FY2023", "FY2024", "FY2025", "FY2026"]
summary = {}

# ============================================================ 1. workforce profile (30 Jun 2026)
prof = emp.groupby(["job_family", "location"]).agg(headcount=("employee_id", "size"), fte=("fte", "sum")).reset_index()
prof["fte_per_head"] = (prof.fte / prof.headcount).round(3)
prof.to_csv(TABLES / "int_profile_family_location.csv", index=False)
fam = emp.groupby("job_family").agg(headcount=("employee_id", "size"), fte=("fte", "sum"),
                                    median_age=("age", "median"), pct_55_plus=("age", lambda a: (a >= 55).mean()),
                                    median_tenure=("tenure_years", "median"),
                                    pct_part_time_or_casual=("employment_type", lambda t: t.isin(["Permanent Part-time", "Casual"]).mean()),
                                    pct_female=("gender", lambda g: (g == "Female").mean()))
fam["fte_per_head"] = fam.fte / fam.headcount
fam.round(3).to_csv(TABLES / "int_profile_family.csv")
mix = pd.crosstab(emp.job_family, emp.employment_type, margins=True)
mix.to_csv(TABLES / "int_mix_employment_type.csv")
loc_mix = emp.groupby(["location", "gccsa", "remoteness"]).agg(headcount=("employee_id", "size"), fte=("fte", "sum")).reset_index()
loc_mix.to_csv(TABLES / "int_mix_location.csv", index=False)
emp["age_band"] = pd.cut(emp.age, [0, 24, 34, 44, 54, 64, 120], labels=["15-24", "25-34", "35-44", "45-54", "55-64", "65+"])
emp.groupby(["job_family", "age_band"], observed=False).size().unstack().to_csv(TABLES / "int_age_profile.csv")
summary["headcount"] = int(len(emp))
summary["fte"] = round(float(emp.fte.sum()), 1)
summary["fte_per_head"] = round(float(emp.fte.sum() / len(emp)), 3)
summary["pct_55_plus"] = round(float((emp.age >= 55).mean()), 4)

# ============================================================ 2. stock-and-flow history (rebuilt from the movements)
# HC(start of FY) = HC(end) - hires + separations - transfers_in + transfers_out - role_changes_in + role_changes_out
flows = []
end_hc = emp.groupby(["job_family", "location"]).size()
cur = end_hc.copy()
for fy in reversed(FYS):
    e = mv[mv.fy == fy]
    g = lambda m: e[m].groupby(["job_family", "location"]).size()
    hires = g(e.event_type == "HIRE")
    seps = g(e.event_type == "SEPARATION")
    t_in = g(e.event_type == "TRANSFER")
    t_out = e[e.event_type == "TRANSFER"].groupby(["from_job_family", "from_location"]).size()
    t_out.index.names = ["job_family", "location"]
    r_in = g(e.event_type == "ROLE_CHANGE")
    r_out = e[e.event_type == "ROLE_CHANGE"].groupby(["from_job_family", "from_location"]).size()
    r_out.index.names = ["job_family", "location"]
    idx = pd.MultiIndex.from_product([FAMS, LOCS], names=["job_family", "location"])
    f = pd.DataFrame(index=idx)
    f["closing"] = cur.reindex(idx).fillna(0)
    for n, s in [("hires", hires), ("separations", seps), ("transfers_in", t_in), ("transfers_out", t_out),
                 ("role_change_in", r_in), ("role_change_out", r_out)]:
        f[n] = s.reindex(idx).fillna(0)
    f["opening"] = f.closing - f.hires + f.separations - f.transfers_in + f.transfers_out - f.role_change_in + f.role_change_out
    f["fy"] = fy
    flows.append(f.reset_index())
    cur = f.opening
flows = pd.concat(flows).sort_values(["fy", "job_family", "location"])
flows.to_csv(TABLES / "int_stock_flow_history.csv", index=False)
# reconciliation of the rebuilt opening stock against the generator truth (1 Jul 2022)
truth_all = pd.read_csv(SYNTH / "_truth" / "all_employees_truth.csv", parse_dates=["hire_date", "termination_date"])
open_true = ((truth_all.hire_date < HISTORY_START) &
             (truth_all.termination_date.isna() | (truth_all.termination_date >= HISTORY_START))).sum()
summary["opening_hc_rebuilt_FY2023"] = int(flows[flows.fy == "FY2023"].opening.sum())
summary["opening_hc_truth_FY2023"] = int(open_true)

# turnover = separations / average headcount ((opening + closing) / 2)
def rates(df, by):
    a = df.groupby(by)[["opening", "closing", "hires", "separations", "transfers_in", "transfers_out",
                        "role_change_in", "role_change_out"]].sum()
    a["avg_hc"] = (a.opening + a.closing) / 2
    a["turnover_rate"] = a.separations / a.avg_hc
    a["hire_rate"] = a.hires / a.avg_hc
    a["net_change"] = a.closing - a.opening
    return a.round(4)


org_fy = rates(flows, ["fy"])
fam_fy = rates(flows, ["fy", "job_family"])
loc_fy = rates(flows, ["fy", "location"])
org_fy.to_csv(TABLES / "int_turnover_org_fy.csv")
fam_fy.to_csv(TABLES / "int_turnover_family_fy.csv")
loc_fy.to_csv(TABLES / "int_turnover_location_fy.csv")
cell_rates = rates(flows[flows.fy.isin(["FY2025", "FY2026"])], ["job_family", "location"])
cell_rates.to_csv(TABLES / "int_turnover_cell_fy25_26.csv")

seps = mv[mv.event_type == "SEPARATION"]
reason = pd.crosstab(seps.fy, seps.reason, normalize="index").round(3)
reason.to_csv(TABLES / "int_separation_reasons.csv")
vol = seps.reason.eq("Resignation")
summary["turnover_FY2026"] = float(org_fy.loc["FY2026", "turnover_rate"])
summary["voluntary_share_FY2026"] = round(float(vol[seps.fy == "FY2026"].mean()), 3)

# early attrition: hires in FY2024-FY2025 who separated within 12 months of starting
hires = mv[mv.event_type == "HIRE"][["employee_id", "event_date", "job_family", "location"]].rename(columns={"event_date": "hire"})
hs = hires[(hires.hire >= "2023-07-01") & (hires.hire < "2025-07-01")].merge(
    seps[["employee_id", "event_date"]].rename(columns={"event_date": "sep"}), on="employee_id", how="left")
hs["left_12m"] = (hs.sep - hs.hire).dt.days.le(365)
early = hs.groupby("job_family").left_12m.mean().round(3)
early.to_csv(TABLES / "int_early_attrition_family.csv")
summary["early_attrition_12m"] = round(float(hs.left_12m.mean()), 3)

# 12-month retention: people employed on 1 Jul 2025 still employed on 30 Jun 2026
start = truth_all  # NB: uses only fields an HRIS holds (hire/termination dates); truth used for the full history
present = start[(start.hire_date < "2025-07-01") & (start.termination_date.isna() | (start.termination_date >= "2025-07-01"))]
retained = present.termination_date.isna() | (present.termination_date > SNAPSHOT_DATE)
summary["retention_12m_FY2026"] = round(float(retained.mean()), 4)

# ============================================================ 3. vacancies and recruitment
recon["vacancy_rate"] = recon.vacant_fte / recon.budgeted_fte
vac_fam = recon.groupby("job_family")[["budgeted_fte", "filled_fte", "vacant_fte", "open_requisitions"]].sum()
vac_fam["vacancy_rate"] = vac_fam.vacant_fte / vac_fam.budgeted_fte
vac_loc = recon.groupby("location")[["budgeted_fte", "filled_fte", "vacant_fte", "open_requisitions"]].sum()
vac_loc["vacancy_rate"] = vac_loc.vacant_fte / vac_loc.budgeted_fte
vac_fam.round(4).to_csv(TABLES / "int_vacancy_family.csv")
vac_loc.round(4).to_csv(TABLES / "int_vacancy_location.csv")
summary["vacancy_rate"] = round(float(recon.vacant_fte.sum() / recon.budgeted_fte.sum()), 4)
summary["vacant_fte"] = round(float(recon.vacant_fte.sum()), 1)

req["fy_open"] = fy_label(req.open_date)
filled = req[(req.status == "Filled") & req.time_to_fill_days.notna()].copy()
filled["fy_fill"] = fy_label(filled.filled_date)
ttf = filled[filled.fy_fill == "FY2026"].groupby(["job_family", "location"]).time_to_fill_days \
    .agg(["count", "median", lambda s: s.quantile(.9)]).rename(columns={"<lambda_0>": "p90"})
ttf.round(1).to_csv(TABLES / "int_time_to_fill_cell_fy26.csv")
ttf_f = filled[filled.fy_fill == "FY2026"].groupby("job_family").time_to_fill_days.agg(["count", "median", lambda s: s.quantile(.9)])
ttf_f.columns = ["fills", "median_days", "p90_days"]
ttf_f.round(1).to_csv(TABLES / "int_time_to_fill_family_fy26.csv")
ttf_l = filled[filled.fy_fill == "FY2026"].groupby("location").time_to_fill_days.agg(["count", "median", lambda s: s.quantile(.9)])
ttf_l.columns = ["fills", "median_days", "p90_days"]
ttf_l.round(1).to_csv(TABLES / "int_time_to_fill_location_fy26.csv")
ttf_trend = filled.groupby("fy_fill").time_to_fill_days.median()
ttf_trend.to_csv(TABLES / "int_time_to_fill_trend.csv")
closed = req[req.status.isin(["Filled", "Cancelled"])].copy()
closed["fy_close"] = fy_label(closed.filled_date.fillna(closed.cancel_date))
closed = closed[closed.fy_close >= "FY2023"]          # requisitions closed before the history window are out of scope
fill_rate = closed.groupby(["fy_close", "location"]).status.apply(lambda s: (s == "Filled").mean()).unstack().round(3)
fill_rate.to_csv(TABLES / "int_fill_rate_location_fy.csv")
op = req[req.status == "Open"].copy()
op["age_days"] = (SNAPSHOT_DATE - op.open_date).dt.days
summary["open_requisitions"] = int(len(op))
summary["open_req_over_90_days"] = int((op.age_days > 90).sum())
summary["median_ttf_FY2026"] = float(filled[filled.fy_fill == "FY2026"].time_to_fill_days.median())
summary["fill_rate_FY2026"] = round(float((closed[closed.fy_close == "FY2026"].status == "Filled").mean()), 3)
src = filled[filled.fy_fill == "FY2026"].source.value_counts(normalize=True).round(3)
src.to_csv(TABLES / "int_hire_source_fy26.csv")
# recruitment throughput: external + graduate hires per FY (used as recruitment capacity evidence)
thr = mv[mv.event_type == "HIRE"].groupby(["fy", "job_family", "location"]).size().unstack("fy").fillna(0)
thr.to_csv(TABLES / "int_hires_cell_fy.csv")

# ============================================================ 4. agency / contingent workforce and cost
agency["fy"] = fy_label(agency.month)
ag = agency.groupby(["fy", "job_family"])[["agency_hours", "agency_cost"]].sum()
ag["agency_fte"] = ag.agency_hours / (76 * 26)
ag.round(1).to_csv(TABLES / "int_agency_family_fy.csv")
ag_fy = agency.groupby("fy")[["agency_hours", "agency_cost"]].sum()
ag_fy["agency_fte"] = ag_fy.agency_hours / (76 * 26)
ag_fy.round(1).to_csv(TABLES / "int_agency_fy.csv")
ONCOST = 1.25     # illustrative: super guarantee 12% (from 1 Jul 2025) + payroll tax + workers comp + leave loading
emp["annual_cost"] = emp.annual_salary_fte * emp.fte * ONCOST
cost = emp.groupby("job_family").agg(fte=("fte", "sum"), employee_cost=("annual_cost", "sum"))
cost["cost_per_fte"] = cost.employee_cost / cost.fte
cost = cost.join(ag.loc["FY2026"][["agency_cost", "agency_fte"]])
cost["agency_share_of_cost"] = cost.agency_cost / (cost.agency_cost + cost.employee_cost)
cost.round(3).to_csv(TABLES / "int_labour_cost_family_fy26.csv")
summary["employee_cost_annualised"] = round(float(emp.annual_cost.sum()))
summary["agency_cost_FY2026"] = round(float(ag_fy.loc["FY2026", "agency_cost"]))
summary["agency_fte_FY2026"] = round(float(ag_fy.loc["FY2026", "agency_fte"]), 1)
# agency cover ratio: agency FTE / vacant FTE (used by the scenario model)
vac_hist = pd.read_csv(SYNTH / "_truth" / "monthly_filled_fte_truth.csv", parse_dates=["month"])
vac_hist["vacant"] = (vac_hist.established_fte - vac_hist.filled_fte).clip(lower=0)
vac_hist["fy"] = fy_label(vac_hist.month)
# average agency FTE in FY2026 / average positive vacant FTE (summed over the family's cells) in FY2026
cov = agency[agency.fy == "FY2026"].groupby("job_family").agency_hours.sum() / (76 * 26)
cov = (cov / (vac_hist[vac_hist.fy == "FY2026"].groupby("job_family").vacant.sum() / 12)).round(3)
cov.rename("agency_cover_ratio").to_csv(TABLES / "int_agency_cover_ratio.csv")

# ============================================================ 5. EXTERNAL labour market (real data)
lf = pd.read_csv(PROCESSED / "lf_state_monthly.csv", parse_dates=["period_start"])
wa = lf[lf.region == "Western Australia"].set_index("period_start").sort_index()
au = lf[lf.region == "Australia"].set_index("period_start").sort_index()
ext = {}
ext["wa_unemployment_rate_latest"] = (str(wa.index[-1].date()), round(float(wa["Unemployment rate"].iloc[-1]), 2))
ext["aus_unemployment_rate_latest"] = (str(au.index[-1].date()), round(float(au["Unemployment rate"].iloc[-1]), 2))
ext["wa_participation_rate_latest"] = round(float(wa["Participation rate"].iloc[-1]), 2)
ext["wa_employed_000_latest"] = round(float(wa["Employed persons"].iloc[-1]), 1)
ext["wa_employment_growth_12m"] = round(float(wa["Employed persons"].iloc[-1] / wa["Employed persons"].iloc[-13] - 1), 4)
jv = pd.read_csv(PROCESSED / "jv_quarterly.csv", parse_dates=["period_start"])
# WA job vacancies are published in original terms only -> 4-quarter rolling mean removes seasonality
jvwa_orig = jv[(jv.region == "Western Australia") & (jv.sector == "Private and Public") & (jv.adjustment == "Original")
               & (jv.industry == "All Industries")].set_index("period_start").job_vacancies_000.sort_index()
jvwa = jvwa_orig.rolling(4).mean().dropna()
une = (wa["Labour Force"] - wa["Employed persons"]).resample("QS").mean()
vu = (jvwa / une.reindex(jvwa.index)).dropna()
vu_tbl = pd.DataFrame({"wa_job_vacancies_000_orig": jvwa_orig.reindex(jvwa.index), "wa_job_vacancies_000_4q_avg": jvwa, "wa_unemployed_000": une.reindex(jvwa.index), "v_u_ratio": vu})
vu_tbl.round(3).to_csv(TABLES / "ext_wa_vacancy_unemployment_ratio.csv")
ext["wa_jv_000_latest_original"] = (str(jvwa_orig.index[-1].date()), round(float(jvwa_orig.iloc[-1]), 1))
ext["wa_jv_000_latest_4q_avg"] = round(float(jvwa.iloc[-1]), 1)
ext["wa_v_u_ratio_latest"] = round(float(vu.iloc[-1]), 3)
ext["wa_v_u_ratio_2015_2019_avg"] = round(float(vu["2015":"2019"].mean()), 3)
ext["wa_v_u_ratio_peak"] = (str(vu.idxmax().date()), round(float(vu.max()), 3))
jvq = jv[(jv.region == "Australia") & (jv.industry == "Health Care and Social Assistance") & (jv.sector == "Private and Public")
         & (jv.adjustment == "Original")].set_index("period_start").job_vacancies_000.sort_index()
ext["aus_hcsa_job_vacancies_000_latest"] = (str(jvq.index[-1].date()), round(float(jvq.iloc[-1]), 1))
la = pd.read_csv(PROCESSED / "labour_account_health.csv", parse_dates=["period_start"])
laq = la[(la.industry_code == "Q") & (la.adjustment == "Seasonally Adjusted")].set_index("period_start").sort_index()
ext["aus_hcsa_vacant_job_pct_latest"] = round(float(laq["Jobs; Proportion of vacant jobs"].iloc[-1]), 3)
ext["aus_hcsa_vacant_job_pct_2019_avg"] = round(float(laq["Jobs; Proportion of vacant jobs"]["2019"].mean()), 3)
ext["aus_hcsa_filled_jobs_5y_cagr"] = round(float((laq["Jobs; Filled jobs"].iloc[-1] / laq["Jobs; Filled jobs"].iloc[-21]) ** (1 / 5) - 1), 4)
ext["aus_hcsa_labour_cost_per_hour_latest"] = round(float(laq["Payments; Average labour cost per hour worked"].iloc[-1]), 2)
wpi = pd.read_csv(PROCESSED / "wpi.csv")
w = wpi[(wpi.measure.str.contains("corresponding")) & (wpi.adjustment == "Original") & (wpi.sector == "Private and Public")]
ext["wpi_yoy_aus_hcsa_latest"] = (w[(w.region == "Australia") & (w.industry == "Health Care and Social Assistance")].sort_values("period").iloc[-1][["period", "value"]].tolist())
ext["wpi_yoy_wa_all_latest"] = (w[(w.region == "Western Australia")].sort_values("period").iloc[-1][["period", "value"]].tolist())
hcsa_wpi = w[(w.region == "Australia") & (w.industry == "Health Care and Social Assistance")].sort_values("period")
ext["wpi_yoy_aus_hcsa_avg_last8q"] = round(float(hcsa_wpi.value.tail(8).mean()), 2)
erp = pd.read_csv(PROCESSED / "erp_wa_age_bands.csv").set_index("period")
ext["wa_population_latest"] = (erp.index[-1], int(erp.total.iloc[-1]))
ext["wa_pop_5y_cagr"] = round(float((erp.total.iloc[-1] / erp.total.iloc[-21]) ** (1 / 5) - 1), 4)
ext["wa_pop_75plus_5y_cagr"] = round(float((erp["75+"].iloc[-1] / erp["75+"].iloc[-21]) ** (1 / 5) - 1), 4)
ext["wa_pop_65plus_share_latest"] = round(float((erp["65-74"].iloc[-1] + erp["75+"].iloc[-1]) / erp.total.iloc[-1]), 4)

# Census 2021: age profile of WA Health Care & Social Assistance workers (real) vs KHS (synthetic)
g54 = pd.read_csv(PROCESSED / "census2021_g54_wa.csv", dtype=str)
g54["value"] = g54.value.astype(float)
q = g54[(g54.sex_code == "3") & (g54.industry_code == "Q")]
age_ext = q[q.age_code != "_T"].pivot_table(index="age", columns="region", values="value")
age_ext = (age_ext / age_ext.sum()).round(4)
age_ext.to_csv(TABLES / "ext_census2021_hcsa_age_wa.csv")
ext["census2021_hcsa_wa_pct_55_plus"] = round(float(age_ext.loc[["55-64 years", "65-74 years", "75-84 years", "85 years and over"], "Western Australia"].sum()), 4)
ext["census2021_hcsa_rest_of_wa_pct_55_plus"] = round(float(age_ext.loc[["55-64 years", "65-74 years", "75-84 years", "85 years and over"], "Rest of WA"].sum()), 4)

# Job mobility (national HCSA, real) -> external benchmark for turnover
jm = pd.read_csv(PROCESSED / "job_mobility_industry.csv", parse_dates=["month"])
jm.round(4).to_csv(TABLES / "ext_job_mobility.csv", index=False)
h26 = jm[(jm.industry == "Health care and social assistance")].sort_values("month").iloc[-1]
ext["abs_hcsa_left_employment_rate_feb2026"] = round(float(h26.left_employment_rate), 4)
ext["abs_hcsa_job_changer_rate_feb2026"] = round(float(h26.job_changer_rate), 4)
ext["abs_hcsa_outflow_proxy_feb2026"] = round(float(h26.industry_outflow_proxy), 4)

# REOS recruitment difficulty (real)
reos = pd.read_csv(PROCESSED / "reos_recruitment_difficulty.csv", parse_dates=["quarter"])
last = reos[reos.quarter == reos.quarter.max()].set_index("series").recruitment_difficulty
ext["reos_recruitment_difficulty_latest"] = {"quarter": str(reos.quarter.max().date()), **last.round(3).to_dict()}
kf = pd.read_csv(PROCESSED / "osl_key_findings.csv")
ext["osl_key_findings_2025_26"] = kf.assign(value=kf.value.round(3)).to_dict("records")

# Occupation-level indicators for each job family (real)
ivi = pd.read_csv(PROCESSED / "ivi_4digit_wa_aus.csv", parse_dates=["month"], dtype={"anzsco": str})
eq = pd.read_csv(PROCESSED / "eq08_wa_health_occupations.csv", parse_dates=["month"], dtype={"anzsco": str})
osl = pd.read_csv(PROCESSED / "osl_2026_unit_group.csv", dtype={"anzsco": str})
proj = pd.read_csv(PROCESSED / "employment_projections_occupation.csv", dtype={"anzsco": str})
FAMILY_CODES = {"Registered Nurse": ["2544"], "Midwife": ["2541"], "Enrolled Nurse": ["4114"],
                "Medical Practitioner": [f"253{i}" for i in range(1, 10)],
                "Allied Health": [f"252{i}" for i in range(1, 8)],
                "Care Worker": ["4233", "4231"], "Administration": None, "Support Services": None}


def codes_for(f, available):
    c = FAMILY_CODES[f]
    if c is None:   # whole major group (5 clerical / 8 labourers)
        first = "5" if f == "Administration" else "8"
        return [x for x in available if len(x) == 4 and x.startswith(first)]
    return [x for x in c if x in set(available)]


rows = []
lm = ivi.month.max()
eq_last = eq.month.max()
for f in FAMS:
    cw = codes_for(f, ivi.anzsco.unique())
    s = ivi[(ivi.state == "WA") & ivi.anzsco.isin(cw)].groupby("month").ads.sum()
    s_au = ivi[(ivi.state == "AUST") & ivi.anzsco.isin(cw)].groupby("month").ads.sum()
    ce = codes_for(f, eq.anzsco.unique())
    e4 = eq[eq.anzsco.isin(ce)].groupby("month").employed_000.sum()
    emp_4q = e4[e4.index > eq_last - pd.DateOffset(months=12)].mean()       # 4-quarter average: EQ08 is volatile
    emp_4q_prev = e4[(e4.index <= eq_last - pd.DateOffset(months=12)) & (e4.index > eq_last - pd.DateOffset(months=24))].mean()
    ivi_12m = s[s.index > lm - pd.DateOffset(months=12)].mean()
    osl_r = osl[osl.anzsco.isin(cw)].rating_2026.value_counts()
    pj = proj[proj.anzsco.isin(ce if FAMILY_CODES[f] else [("5" if f == "Administration" else "8")])]
    pj = pj[pj.level.astype(str).isin(["4", "1"])]
    rows.append(dict(
        job_family=f, anzsco_codes=",".join(cw) if len(cw) < 12 else f"{cw[0][0]}xxx ({len(cw)} unit groups)",
        wa_ivi_latest_3mma=round(float(s.loc[lm]), 1), wa_ivi_yoy=round(float(s.loc[lm] / s.loc[lm - pd.DateOffset(years=1)] - 1), 4),
        wa_ivi_vs_2019=round(float(s.loc[lm] / s["2019"].mean() - 1), 4),
        aus_ivi_yoy=round(float(s_au.loc[lm] / s_au.loc[lm - pd.DateOffset(years=1)] - 1), 4),
        wa_employed_000_4q_avg=round(float(emp_4q), 1),
        wa_employment_growth_4q=round(float(emp_4q / emp_4q_prev - 1), 4),
        wa_ads_per_100_employed=round(float(ivi_12m / (emp_4q * 1000) * 100), 2),
        osl_2026_ratings=", ".join(f"{k}:{v}" for k, v in osl_r.items()),
        osl_share_in_shortage=round(float(osl_r.get("S", 0) / max(osl_r.sum(), 1)), 2),
        osl_regional_shortage=bool(osl_r.get("R", 0) > 0),
        jsa_proj_10y_cagr=round(float((pj.emp_2035_000.sum() / pj.emp_2025_000.sum()) ** .1 - 1), 4),
    ))
occ = pd.DataFrame(rows).set_index("job_family")
occ.to_csv(TABLES / "ext_occupation_indicators.csv")
ext["ivi_latest_month"] = str(lm.date())
ext["eq08_latest_month"] = str(eq_last.date())
save_json(ext, TABLES / "ext_summary.json")

# ============================================================ 6. RISK heatmap (job family x location)
# Score 0-100 per component (min-max across cells), then weighted. Provenance in brackets.
cell = recon.set_index(["job_family", "location"])[["vacancy_rate"]].copy()                         # [synthetic]
cell = cell.join(cell_rates[["turnover_rate"]])                                                     # [synthetic]
ttf_cell = ttf["median"].where(ttf["count"] >= 3)        # < 3 fills is too noisy: falls back to the median cell
cell = cell.join(ttf_cell.rename("ttf_median"))                                                     # [synthetic]
age55 = emp.groupby(["job_family", "location"]).age.apply(lambda a: (a >= 55).mean()).rename("pct_55_plus")
cell = cell.join(age55)                                                                             # [synthetic]
cell = cell.reset_index()
cell["ext_shortage"] = cell.job_family.map(occ.osl_share_in_shortage) + \
    np.where(cell.location.map(lambda l: LOCATIONS[l]["gccsa"]) == "Rest of WA", cell.job_family.map(occ.osl_regional_shortage).astype(float) * .5, 0)  # [real]
cell["ext_ads_intensity"] = cell.job_family.map(occ.wa_ads_per_100_employed)                       # [real]
WEIGHTS = {"vacancy_rate": .25, "turnover_rate": .15, "ttf_median": .15, "pct_55_plus": .10,
           "ext_shortage": .20, "ext_ads_intensity": .15}                                           # illustrative
for c in WEIGHTS:
    v = cell[c].fillna(cell[c].median())
    cell[c + "_score"] = ((v - v.min()) / (v.max() - v.min()) * 100).round(1)
cell["risk_score"] = sum(cell[c + "_score"] * w for c, w in WEIGHTS.items()).round(1)
cell["risk_band"] = pd.cut(cell.risk_score, [-1, 35, 55, 101], labels=["Low", "Medium", "High"])
cell = cell.merge(prof[["job_family", "location", "headcount", "fte"]], on=["job_family", "location"])
cell.sort_values("risk_score", ascending=False).to_csv(TABLES / "risk_heatmap_cells.csv", index=False)
save_json({"weights": WEIGHTS, "note": "weights are illustrative; vacancy/turnover/ttf/age are synthetic, "
           "ext_* are real public data at occupation (national OSL, WA IVI/EQ08) level"}, TABLES / "risk_method.json")

save_json(summary, TABLES / "int_summary.json")
print("INTERNAL (synthetic):", summary)
print("EXTERNAL (real):")
for k, v in ext.items():
    print(" ", k, v)
print(occ.to_string())
print(org_fy.to_string())
print(vac_fam.round(3).to_string())
print(cell.sort_values("risk_score", ascending=False).head(12)[["job_family", "location", "risk_score", "vacancy_rate", "turnover_rate", "ttf_median"]].to_string())
