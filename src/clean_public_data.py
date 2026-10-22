"""Step 2 - Profile, clean, standardise and validate the real ABS datasets.

Input : data/raw/abs/*.csv  (SDMX-CSV with "code: label" columns, one layout per dataflow)
Output: data/processed/public_observations.csv  - one tidy long table for all ABS series
        data/processed/<series>.csv               - analysis-ready extracts
        outputs/logs/quality_metrics_public.csv, exceptions_public.csv

Every check below is computed from the downloaded files; nothing is hard-coded.
"""
import numpy as np
import pandas as pd

from common import RAW, PROCESSED, QualityLog, fy_label

log = QualityLog("public")

STANDARD_DIMS = {  # raw SDMX column prefix -> standard column
    "MEASURE": "measure", "SEX": "sex", "SEXP": "sex", "AGE": "age", "AGEP": "age",
    "TSEST": "adjustment", "REGION": "region", "ASGS_2016": "region", "INDUSTRY": "industry",
    "INDP": "industry", "LABOURACCT_IND": "industry", "SECTOR": "sector", "INDEX": "index",
    "ESTIMATE_TYPE": "estimate_type", "OCCP": "occupation", "FREQ": "freq",
}


def period_start(period, freq):
    """Convert SDMX period strings (2026-09, 2026-Q3, 2026-S1, 2021) to a period-start date."""
    p = period.astype(str)
    out = pd.Series(pd.NaT, index=p.index)
    m = p.str.fullmatch(r"\d{4}-\d{2}")
    out[m] = pd.to_datetime(p[m] + "-01")
    q = p.str.fullmatch(r"\d{4}-Q[1-4]")
    out[q] = pd.PeriodIndex(p[q].str.replace("-", ""), freq="Q").start_time
    # AWE is biannual: S1 = May reference period, S2 = November reference period
    s = p.str.fullmatch(r"\d{4}-S[12]")
    out[s] = pd.to_datetime(p[s].str[:4] + np.where(p[s].str[-1] == "1", "-05-01", "-11-01"))
    a = p.str.fullmatch(r"\d{4}")
    out[a] = pd.to_datetime(p[a] + "-08-10")  # Census night 2021 = 10 Aug
    return out


def standardise(fname, dataset):
    raw = pd.read_csv(RAW / "abs" / fname, dtype=str)
    log.metric(dataset, "rows", "raw", len(raw))
    log.metric(dataset, "columns", "raw", raw.shape[1])
    df = pd.DataFrame({"dataset": dataset}, index=raw.index)
    for col in raw.columns:
        prefix = col.split(":")[0]
        if prefix in STANDARD_DIMS:
            std = STANDARD_DIMS[prefix]
            split = raw[col].str.split(": ", n=1, expand=True)
            df[std + "_code"] = split[0].str.strip()
            df[std] = split[1].str.strip() if split.shape[1] > 1 else split[0]
    df["period"] = raw["TIME_PERIOD: Time Period"].str.strip()
    df["period_start"] = period_start(df["period"], df.get("freq_code"))
    df["value"] = pd.to_numeric(raw["OBS_VALUE"], errors="coerce")
    df["unit"] = raw.get("UNIT_MEASURE: Unit of Measure", pd.Series("", index=raw.index)).str.split(": ").str[-1]
    mult = raw.get("UNIT_MULT: Unit of Multiplier")
    df["unit_mult"] = pd.to_numeric(mult.str.split(":").str[0], errors="coerce").fillna(0) if mult is not None else 0
    df["value_scaled"] = df["value"] * (10 ** df["unit_mult"])
    df["obs_status"] = raw.get("OBS_STATUS: Observation Status", pd.Series(np.nan, index=raw.index))

    # --- profiling: missing values, status flags, duplicates on the natural key
    nulls = df["value"].isna()
    log.metric(dataset, "missing_values", "raw", int(nulls.sum()))
    for _, r in df[nulls].iterrows():
        log.exception(dataset, "missing_value", f"{r.get('measure_code')}|{r.get('region_code')}|{r['period']}",
                      r["obs_status"], "dropped; documented as series gap")
    key = [c for c in df.columns if c.endswith("_code")] + ["period"]
    dups = df.duplicated(key, keep="first")
    log.metric(dataset, "duplicate_keys", "raw", int(dups.sum()))
    flagged = df["obs_status"].notna() & ~nulls
    log.metric(dataset, "flagged_observations(kept)", "raw", int(flagged.sum()),
               "; ".join(sorted(df.loc[flagged, "obs_status"].dropna().unique()))[:200])

    clean = df[~nulls & ~dups].copy()
    clean["fy"] = fy_label(clean["period_start"])
    log.metric(dataset, "rows", "clean", len(clean))
    log.metric(dataset, "period_min", "clean", clean["period"].min())
    log.metric(dataset, "period_max", "clean", clean["period"].max())
    return clean


def check(dataset, rule, ok_mask, frame, key_cols, detail_col, tol_note):
    """Record a reconciliation rule: pass rate as a metric, failures as exceptions."""
    n_fail = int((~ok_mask).sum())
    log.metric(dataset, rule, "validation", f"{len(ok_mask) - n_fail}/{len(ok_mask)} pass", tol_note)
    for _, r in frame[~ok_mask].iterrows():
        log.exception(dataset, rule, "|".join(str(r[k]) for k in key_cols), round(r[detail_col], 3),
                      "kept; flagged for analyst review")


frames = {
    "lf": standardise("abs_lf_state_monthly.csv", "ABS Labour Force"),
    "jv": standardise("abs_jv_quarterly.csv", "ABS Job Vacancies"),
    "awe": standardise("abs_awe.csv", "ABS Average Weekly Earnings"),
    "wpi": standardise("abs_wpi.csv", "ABS Wage Price Index"),
    "la": pd.concat([standardise("abs_labour_account_health.csv", "ABS Labour Account"),
                     standardise("abs_labour_account_health_subdiv.csv", "ABS Labour Account (subdivisions)")],
                    ignore_index=True),
    "erp": standardise("abs_erp_wa_by_age.csv", "ABS Estimated Resident Population"),
    "g54": standardise("abs_census2021_g54_ind_age_wa.csv", "Census 2021 G54"),
    "g56": standardise("abs_census2021_g56_ind_occ_wa.csv", "Census 2021 G56"),
    "g60": standardise("abs_census2021_g60_occ_age_wa.csv", "Census 2021 G60"),
}

# ---------------------------------------------------------------- validation rules
# R1 Labour Force identity: full-time + part-time = employed (seasonally adjusted; tolerance 0.5k
#    because SA components are adjusted independently)
lf = frames["lf"]
w = lf.pivot_table(index=["region_code", "period"], columns="measure_code", values="value").reset_index()
# WA seasonally adjusted part-time employment (M2) is not published in this dataflow: test where present,
# then derive WA part-time as Employed - Full-time and record the derivation.
has_pt = w["M2"].notna()
log.metric("ABS Labour Force", "regions missing SA part-time (M2)", "profile",
           ", ".join(sorted(w.loc[~has_pt, "region_code"].unique())), "derived as M3 - M1")
w["diff"] = w["M1"] + w["M2"] - w["M3"]
check("ABS Labour Force", "R1 FT+PT=Employed (|diff|<=0.5k)", w.loc[has_pt, "diff"].abs() <= 0.5, w[has_pt],
      ["region_code", "period"], "diff", "SA components adjusted separately")
derived = lf[(lf.measure_code == "M1") & (lf.region_code == "5")].copy()
emp = lf[(lf.measure_code == "M3") & (lf.region_code == "5")].set_index("period")["value"]
derived["value"] = emp.reindex(derived["period"]).values - derived["value"].values
derived["value_scaled"] = derived["value"] * 10 ** derived["unit_mult"]
derived["measure_code"], derived["measure"] = "M2", "Employed - part-time (derived: employed - full-time)"
derived["obs_status"] = "derived"
lf = pd.concat([lf, derived], ignore_index=True)
frames["lf"] = lf
# R2 unemployment rate recomputed from levels: UR = (LF - Employed)/LF
w["ur_calc"] = (w["M9"] - w["M3"]) / w["M9"] * 100
w["ur_diff"] = w["ur_calc"] - w["M13"]
check("ABS Labour Force", "R2 UR recomputed within 0.1pp", w["ur_diff"].abs() <= 0.1, w,
      ["region_code", "period"], "ur_diff", "rounding tolerance")

# R3 Job vacancies: sum of 8 states/territories vs Australia (original series, all sectors)
jv = frames["jv"]
jvo = jv[(jv.measure_code == "M1") & (jv.adjustment_code == "10") & (jv.sector_code == "7") & (jv.industry_code == "TOT")]
st = jvo[jvo.region_code != "AUS"].groupby("period")["value"].sum()
au = jvo[jvo.region_code == "AUS"].set_index("period")["value"]
r3 = pd.DataFrame({"states": st, "aus": au}).dropna().reset_index()
r3["pct_diff"] = (r3["states"] / r3["aus"] - 1) * 100
check("ABS Job Vacancies", "R3 sum(states)=AUS within 1%", r3["pct_diff"].abs() <= 1, r3, ["period"], "pct_diff",
      "states are independently estimated; small non-additivity expected")
# R4 sum of industries vs all industries (Australia, original)
jvi = jv[(jv.measure_code == "M1") & (jv.adjustment_code == "10") & (jv.sector_code == "7") & (jv.region_code == "AUS")]
ind = jvi[jvi.industry_code != "TOT"].groupby("period")["value"].sum()
tot = jvi[jvi.industry_code == "TOT"].set_index("period")["value"]
r4 = pd.DataFrame({"ind": ind, "tot": tot}).dropna().reset_index()
r4["pct_diff"] = (r4["ind"] / r4["tot"] - 1) * 100
check("ABS Job Vacancies", "R4 sum(industries)=total within 1%", r4["pct_diff"].abs() <= 1, r4, ["period"],
      "pct_diff", "ABS JV excludes Agriculture (A); total covers published industries")

# R5 ERP: the AGE dimension mixes single years, 5-year groups and a total - summing all rows would
#    triple count. Keep single years only and reconcile to the published total.
erp = frames["erp"]
# AGE codes: 0..100 single years, "8599" = 85 and over (overlaps 85..100), "Axx" 5-year groups, "TOT".
single = erp[erp.age_code.str.fullmatch(r"\d{1,3}")]
total = erp[erp.age_code == "TOT"].set_index("period")["value"]
log.metric("ABS Estimated Resident Population", "age levels in AGE dimension", "profile",
           f"single={single.age_code.nunique()}, groups={erp.age_code.str.startswith('A').sum() // max(erp.period.nunique(),1)}, total=1")
naive = erp.groupby("period")["value"].sum()
log.metric("ABS Estimated Resident Population", "naive sum / published total (all rows)", "profile",
           round(float((naive / total).median()), 3), "demonstrates double counting if levels are not filtered")
r5 = pd.DataFrame({"single": single.groupby("period")["value"].sum(), "total": total}).dropna().reset_index()
r5["diff"] = r5["single"] - r5["total"]
check("ABS Estimated Resident Population", "R5 sum(single ages)=total", r5["diff"].abs() < 1, r5, ["period"], "diff",
      "exact")

# R6 Census G54: Greater Perth + Rest of WA vs WA (persons, total age, each industry)
g = frames["g54"]
gp = g[(g.sex_code == "3") & (g.age_code == "_T")].pivot_table(index="industry_code", columns="region_code", values="value")
gp["pct_gap"] = (gp["5GPER"] + gp["5RWAU"]) / gp["5"] * 100 - 100
gp = gp.reset_index()
check("Census 2021 G54", "R6 Perth+Rest of WA within -1.5%..+0.1% of WA", gp["pct_gap"].between(-1.5, 0.1), gp,
      ["industry_code"], "pct_gap",
      "WA total also contains Migratory/Offshore/Shipping and No usual address; cells are perturbed")
# R7 Census G56 occupations sum to industry total (WA)
g56 = frames["g56"]
gw = g56[g56.region_code == "5"]
occ_sum = gw[gw.occupation_code != "_T"].groupby("industry_code")["value"].sum()
occ_tot = gw[gw.occupation_code == "_T"].set_index("industry_code")["value"]
r7 = pd.DataFrame({"sum": occ_sum, "tot": occ_tot}).dropna().reset_index()
r7["diff"] = r7["sum"] - r7["tot"]
check("Census 2021 G56", "R7 sum(occupations)=industry total (|diff|<=10)", r7["diff"].abs() <= 10, r7,
      ["industry_code"], "diff", "perturbation")

# ---------------------------------------------------------------- outputs
allobs = pd.concat(frames.values(), ignore_index=True)
allobs.to_csv(PROCESSED / "public_observations.csv", index=False)
log.metric("ALL", "tidy rows written", "clean", len(allobs))

# Analysis-ready extracts -----------------------------------------------------
lfw = lf.pivot_table(index=["region", "period", "period_start"], columns="measure", values="value").reset_index()
lfw.to_csv(PROCESSED / "lf_state_monthly.csv", index=False)

jv_out = jv[(jv.measure_code == "M1") & (jv.sector_code.isin(["7", "1", "2"]))][
    ["region", "sector", "industry", "adjustment", "period", "period_start", "value"]]
jv_out.rename(columns={"value": "job_vacancies_000"}).to_csv(PROCESSED / "jv_quarterly.csv", index=False)

la = frames["la"]
la_out = la.pivot_table(index=["industry_code", "industry", "adjustment", "period", "period_start"], columns="measure",
                        values="value_scaled").reset_index()
la_out.to_csv(PROCESSED / "labour_account_health.csv", index=False)

wpi = frames["wpi"]
wpi[["region", "sector", "industry", "adjustment", "measure", "period", "period_start", "value"]] \
    .to_csv(PROCESSED / "wpi.csv", index=False)
awe = frames["awe"]
awe[["region", "industry", "measure", "adjustment", "period", "period_start", "value"]] \
    .to_csv(PROCESSED / "awe.csv", index=False)

single = single.assign(age_num=single.age_code.astype(int))
erp_out = single.assign(band=pd.cut(single.age_num, [-1, 14, 64, 74, 200], labels=["0-14", "15-64", "65-74", "75+"])) \
    .groupby(["period", "period_start", "band"], observed=True)["value"].sum().unstack().reset_index()
erp_out["total"] = erp_out[["0-14", "15-64", "65-74", "75+"]].sum(axis=1)
erp_out.to_csv(PROCESSED / "erp_wa_age_bands.csv", index=False)

for k in ("g54", "g56", "g60"):
    frames[k].to_csv(PROCESSED / f"census2021_{k}_wa.csv", index=False)

log.save()
print(pd.DataFrame(log.metrics).to_string())
print("exceptions:", len(log.exceptions))
