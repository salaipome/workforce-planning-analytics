"""Step 2b - Parse the real JSA / ABS spreadsheet / WA Public Sector Commission files into tidy tables.

Each publisher lays its spreadsheets out differently (title blocks, multi-row headers, footnotes,
suppression markers such as "." or "nn%*"). Header rows are located by content, not position, so the
parser fails loudly if a future release changes the layout.

Outputs (data/processed/): ivi_4digit_wa_aus.csv, ivi_2digit_wa.csv, osl_2026_unit_group.csv,
employment_projections_occupation.csv, employment_projections_state.csv, reos_recruitment_difficulty.csv,
job_mobility_industry.csv, eq08_wa_health_occupations.csv, wa_psc_anzsco.csv, osl_key_findings.csv
"""
import re

import numpy as np
import openpyxl
import pandas as pd

from common import RAW, PROCESSED, QualityLog

log = QualityLog("external")
HEALTH_CODES = {"2544", "2541", "4114", "4231", "4233", "2524", "2525", "2723", "2725"}


def is_family_code(code):
    """Unit groups used for the fictional job families (medical 253x, allied 252x, admin 5xxx, labourers 8xxx)."""
    return code in HEALTH_CODES or code[:3] in {"253", "252"} or (len(code) == 4 and code[0] in "58")


def sheet_rows(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb[sheet].iter_rows(values_only=True))
    wb.close()
    return rows


def find_row(rows, predicate, what):
    for i, r in enumerate(rows):
        if predicate(r):
            return i
    raise ValueError(f"layout changed: could not find {what}")


# ------------------------------------------------------------- IVI 4-digit (3-month averages, unadjusted)
rows = sheet_rows(RAW / "jsa" / "ivi_anzsco4_states_sep2026.xlsx", "4 digit 3 month average")
h = find_row(rows, lambda r: r[0] == "ANZSCO_CODE", "IVI header")
ivi = pd.DataFrame(rows[h + 1:], columns=rows[h])
ivi["ANZSCO_CODE"] = ivi["ANZSCO_CODE"].astype(str)
ivi = ivi[ivi.state.isin(["WA", "AUST"])]
long = ivi.melt(id_vars=["ANZSCO_CODE", "ANZSCO_TITLE", "state"], var_name="month", value_name="ads")
raw_n = len(long)
long["suppressed"] = long.ads.astype(str).str.strip().eq(".")
long["ads"] = pd.to_numeric(long.ads, errors="coerce")
log.metric("JSA IVI 4-digit", "rows (WA+AUST, long)", "raw", raw_n)
log.metric("JSA IVI 4-digit", "suppressed cells ('.')", "raw", int(long.suppressed.sum()))
long["month"] = pd.to_datetime(long.month)
long = long[long.ANZSCO_CODE.map(is_family_code) | (long.ANZSCO_CODE == "0")]
long.rename(columns={"ANZSCO_CODE": "anzsco", "ANZSCO_TITLE": "title"}).to_csv(PROCESSED / "ivi_4digit_wa_aus.csv", index=False)
log.metric("JSA IVI 4-digit", "rows kept (family codes)", "clean", len(long))
log.metric("JSA IVI 4-digit", "month range", "clean", f"{long.month.min():%Y-%m} to {long.month.max():%Y-%m}")

# ------------------------------------------------------------- IVI 2-digit (trend)
rows = sheet_rows(RAW / "jsa" / "ivi_anzsco2_states_sep2026.xlsx", "Trend")
h = find_row(rows, lambda r: "ANZSCO_CODE" in [str(c) for c in r], "IVI2 header")
ivi2 = pd.DataFrame(rows[h + 1:], columns=rows[h]).dropna(subset=["ANZSCO_CODE"])
ivi2 = ivi2[ivi2.State == "WA"].melt(id_vars=["Level", "ANZSCO_CODE", "Title", "State"], var_name="month", value_name="ads")
ivi2["month"] = pd.to_datetime(ivi2.month, errors="coerce")
ivi2["ads"] = pd.to_numeric(ivi2.ads, errors="coerce")
ivi2.dropna(subset=["month"]).to_csv(PROCESSED / "ivi_2digit_wa.csv", index=False)

# ------------------------------------------------------------- OSL 2026 (national ratings)
rows = sheet_rows(RAW / "jsa" / "osl_2026_unit_group.xlsx", "2026 Unit group Shortage List")
h = find_row(rows, lambda r: r[0] == "Unit group Code", "OSL header")
osl = pd.DataFrame([r[:6] for r in rows[h + 1:]],
                   columns=["anzsco", "title", "rating_2026", "shortage_driver", "skill_level", "major_group"])
osl = osl.dropna(subset=["anzsco"])
osl["anzsco"] = osl.anzsco.astype(str).str.replace(r"\.0$", "", regex=True)   # None rows make the column float
osl = osl[osl.anzsco.str.fullmatch(r"\d{4}")]
osl.to_csv(PROCESSED / "osl_2026_unit_group.csv", index=False)
log.metric("JSA OSL 2026", "unit groups", "clean", len(osl),
           "; ".join(f"{k}={v}" for k, v in osl.rating_2026.value_counts().items()))

# ------------------------------------------------------------- OSL key findings (fill rate, duration)
kf = []
for fig in ("Figure 4", "Figure 5", "Figure 6"):
    rows = sheet_rows(RAW / "jsa" / "osl_2026_key_findings_tables.xlsx", fig)
    title = next(r[0] for r in rows if r[0] and str(r[0]).startswith(fig))
    for r in rows:
        if r[0] in ("Shortage", "No shortage", "All occupations") and isinstance(r[1], (int, float)):
            kf.append(dict(figure=title.strip(), group=r[0], value=r[1]))
pd.DataFrame(kf).to_csv(PROCESSED / "osl_key_findings.csv", index=False)

# ------------------------------------------------------------- Employment projections
path = RAW / "jsa" / "employment_projections_2025_2035.xlsx"
rows = sheet_rows(path, "Table_6 Occupation Unit Group")
h = find_row(rows, lambda r: r[2] == "ANZSCO Code", "projections header")
proj = pd.DataFrame([r[:14] for r in rows[h + 2:]])
proj = proj.iloc[:, :12]
proj.columns = ["level", "nfd", "anzsco", "occupation", "skill_level", "emp_2025_000", "emp_2030_000",
                "emp_2035_000", "chg5_000", "chg5_pct", "chg10_000", "chg10_pct"]
proj = proj.dropna(subset=["anzsco"])
proj["anzsco"] = proj.anzsco.astype(str).str.replace(r"\.0$", "", regex=True)
for c in proj.columns[5:]:
    proj[c] = pd.to_numeric(proj[c], errors="coerce")
proj["cagr_10y"] = (proj.emp_2035_000 / proj.emp_2025_000) ** (1 / 10) - 1
proj.to_csv(PROCESSED / "employment_projections_occupation.csv", index=False)
rows = sheet_rows(path, "Table_4 State & Territory")
h = find_row(rows, lambda r: r[0] == "State/Territory", "state projections header")
st = pd.DataFrame([r[:4] for r in rows[h + 2:] if r[0]], columns=["state", "emp_2025_000", "emp_2030_000", "emp_2035_000"])
st = st[pd.to_numeric(st.emp_2025_000, errors="coerce").notna()]
st.to_csv(PROCESSED / "employment_projections_state.csv", index=False)
# check: Table_6 4-digit rows should sum to the major-group totals (level 1) within rounding
lvl = proj.level.astype(str)
s4 = proj[(lvl == "4") & (proj.nfd == "N")].emp_2025_000.sum()
s1 = proj[lvl == "1"].emp_2025_000.sum()
log.metric("JSA Employment Projections", "4-digit sum / major-group sum (2025)", "validation",
           round(s4 / s1, 4), "NFD rows excluded; <1 means NFD employment sits outside unit groups")

# ------------------------------------------------------------- REOS recruitment difficulty (quarterly)
rows = sheet_rows(RAW / "jsa" / "reos_sep2026.xlsx", "3.2 Recruitment Difficulty (Q)")
hdr = find_row(rows, lambda r: r[0] == "Quarter", "REOS header")
cols = [str(c).strip() if c else "" for c in rows[hdr - 1]]
cols[1] = "All recruiting employers"
want = {c: i for i, c in enumerate(cols) if c in ("All recruiting employers", "Western Australia",
                                                     "Health Care and Social Assistance")}
recs = []
small_sample = 0
for r in rows[hdr + 1:]:
    if not hasattr(r[0], "year"):
        continue
    for name, i in want.items():
        v = r[i]
        if isinstance(v, str) and v.endswith("*"):
            small_sample += 1
            v = float(v.rstrip("%*")) / 100
        recs.append(dict(quarter=r[0], series=name, recruitment_difficulty=v))
reos = pd.DataFrame(recs)
reos.to_csv(PROCESSED / "reos_recruitment_difficulty.csv", index=False)
log.metric("JSA REOS", "series found", "clean", ", ".join(want))
log.metric("JSA REOS", "small-sample values ('nn%*') converted", "clean", small_sample, "flag: use with caution")

# ------------------------------------------------------------- ABS Job Mobility Table 4 (by industry)
rows = sheet_rows(RAW / "abs" / "abs_job_mobility_feb2026_table04.xlsx", "Data 4")
ind_row = rows[5]
industries = {}
for i, c in enumerate(ind_row):
    if c:
        industries[str(c).strip()] = i     # first column of each industry block: '000
jm = []
for r in rows[7:]:
    if r[1] != "People aged 15 years and over":
        continue
    if r[2] not in ("Employed 12 months ago", "Not currently employed", "Changed jobs in last 12 months"):
        continue
    for name in ("Health care and social assistance", "Total all industries", "Total"):
        if name in industries:
            jm.append(dict(month=r[0], industry=name, category=r[2], persons_000=r[industries[name]],
                           rse=r[industries[name] + 1]))
jm = pd.DataFrame(jm).drop_duplicates(["month", "industry", "category"], keep="first")
jmw = jm.pivot_table(index=["month", "industry"], columns="category", values="persons_000").reset_index()
jmw["left_employment_rate"] = jmw["Not currently employed"] / jmw["Employed 12 months ago"]
jmw["job_changer_rate"] = jmw["Changed jobs in last 12 months"] / jmw["Employed 12 months ago"]
jmw["industry_outflow_proxy"] = jmw.left_employment_rate + jmw.job_changer_rate
jmw.to_csv(PROCESSED / "job_mobility_industry.csv", index=False)
log.metric("ABS Job Mobility", "industries parsed", "clean", ", ".join(jmw.industry.unique()))

# ------------------------------------------------------------- ABS EQ08 (WA, family unit groups)
wb = openpyxl.load_workbook(RAW / "abs" / "abs_lf_detailed_eq08_mar2026.xlsx", read_only=True)
recs, n_raw = [], 0
for r in wb["Data 1"].iter_rows(min_row=5, values_only=True):
    n_raw += 1
    if r[2] not in ("Western Australia",) or not r[3]:
        continue
    code = str(r[3]).split(" ")[0]
    if is_family_code(code):
        recs.append(dict(month=r[0], sex=r[1], anzsco=code, title=str(r[3])[len(code) + 1:],
                         employed_000=r[4], hours_000=r[5]))
wb.close()
eq = pd.DataFrame(recs)
eq = eq.groupby(["month", "anzsco", "title"], as_index=False)[["employed_000", "hours_000"]].sum()
eq.to_csv(PROCESSED / "eq08_wa_health_occupations.csv", index=False)
log.metric("ABS EQ08", "rows scanned", "raw", n_raw)
log.metric("ABS EQ08", "WA family-code rows (persons)", "clean", len(eq),
           f"{eq.month.min():%Y-%m} to {eq.month.max():%Y-%m}")

# ------------------------------------------------------------- WA Public Sector Commission (ANZSCO sheet)
rows = sheet_rows(RAW / "other" / "wa_psc_sots_bulletin_2025_26.xlsx", "ANZSCO")
h = find_row(rows, lambda r: "Total Headcount" in [str(c).strip() for c in r], "WA PSC header")
# two-row header: group label on row h, sub-label on row h+1 (forward-fill the group label)
hdr, group = [], ""
for i, (top, sub) in enumerate(zip(rows[h], rows[h + 1])):
    group = str(top).strip() if top else group
    hdr.append(f"{group} | {sub}" if sub else group)
psc = pd.DataFrame(rows[h + 2:], columns=hdr)
psc = psc[pd.to_numeric(psc.iloc[:, 0], errors="coerce").notna()]
psc.to_csv(PROCESSED / "wa_psc_anzsco.csv", index=False)
log.metric("WA PSC bulletin", "ANZSCO unit-group rows", "clean", len(psc), "|".join(hdr[:8]))

log.save()
print(pd.DataFrame(log.metrics).to_string())
