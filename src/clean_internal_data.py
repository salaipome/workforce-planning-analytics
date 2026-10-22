"""Step 4 - Clean, standardise and reconcile the (synthetic) internal workforce sources.

Sources: HRIS snapshot, HRIS movements, payroll fortnight, finance establishment, ATS requisitions.
Every rule writes before/after metrics and row-level exceptions. The cleaned snapshot is then scored
against the generator's hidden ground truth (data/synthetic/_truth), so detection accuracy is measured.
"""
import re

import numpy as np
import pandas as pd

from common import SYNTH, PROCESSED, TABLES, SNAPSHOT_DATE, HISTORY_START, JOB_FAMILIES, LOCATIONS, QualityLog, save_json

log = QualityLog("internal")
HOURS_PER_FTE_FN = 76

hris = pd.read_csv(SYNTH / "hris_employee_snapshot.csv", dtype={"employee_id": str, "person_id": str})
mov = pd.read_csv(SYNTH / "hris_movements.csv", dtype={"employee_id": str, "person_id": str})
pay = pd.read_csv(SYNTH / "payroll_fortnight.csv", dtype={"employee_id": str})
est = pd.read_csv(SYNTH / "finance_establishment.csv")
ccm = pd.read_csv(SYNTH / "cost_centre_map.csv")
ats = pd.read_csv(SYNTH / "ats_requisitions.csv", dtype={"filled_by": str})


def profile(df, name, stage):
    log.metric(name, "rows", stage, len(df))
    log.metric(name, "exact duplicate rows", stage, int(df.duplicated().sum()))
    nulls = df.isna().sum()
    for c in nulls[nulls > 0].index:
        log.metric(name, f"nulls: {c}", stage, int(nulls[c]))


# =============================================================== HRIS snapshot
profile(hris, "HRIS snapshot", "before")
log.metric("HRIS snapshot", "distinct location values", "before", hris.location.nunique())
log.metric("HRIS snapshot", "distinct job_family values", "before", hris.job_family.nunique())
log.metric("HRIS snapshot", "FTE outside (0, 1.0]", "before", int((~hris.fte.between(0.01, 1.0)).sum()))

h = hris.copy()
# R-H1 exact duplicates (double extract)
d = h.duplicated(keep="first")
for e in h.loc[d, "employee_id"]:
    log.exception("HRIS snapshot", "R-H1 exact duplicate", e, "", "removed")
h = h[~d]

# R-H2 location standardisation: trim, case-fold, expand abbreviations, strip suffixes, map to master list
LOC_CANON = {re.sub(r"\W", "", k.lower()): k for k in LOCATIONS}


def canon_location(v):
    s = str(v).strip().lower().replace("nth", "north").replace("sth", "south")
    s = re.sub(r"\b(campus|hospital|site)\b", "", s)
    return LOC_CANON.get(re.sub(r"\W", "", s))


h["location_raw"] = h.location
h["location"] = h.location.map(canon_location)
changed = h.location_raw != h.location
for _, r in h[changed].iterrows():
    log.exception("HRIS snapshot", "R-H2 location standardised", r.employee_id, f"{r.location_raw!r} -> {r.location}",
                  "mapped" if r.location else "UNMAPPED - review")

# R-H3 job family synonyms (maintained reference table, reviewed with HR) -> canonical family
FAMILY_SYNONYMS = {"rn": "Registered Nurse", "reg nurse": "Registered Nurse", "registered nurse - grad": "Registered Nurse",
                   "en": "Enrolled Nurse", "ain": "Care Worker", "personal care assistant": "Care Worker",
                   "doctor": "Medical Practitioner", "medical officer": "Medical Practitioner",
                   "allied health prof": "Allied Health", "physiotherapist": "Allied Health",
                   "admin": "Administration", "admin officer": "Administration", "support svcs": "Support Services",
                   "orderly": "Support Services", "midwifery": "Midwife"}
FAMILY_SYNONYMS.update({k.lower(): k for k in JOB_FAMILIES})
h["job_family_raw"] = h.job_family
h["job_family"] = h.job_family.str.strip().str.lower().map(FAMILY_SYNONYMS)
for _, r in h[h.job_family_raw != h.job_family].iterrows():
    log.exception("HRIS snapshot", "R-H3 job family standardised", r.employee_id, f"{r.job_family_raw!r} -> {r.job_family}",
                  "mapped" if r.job_family else "UNMAPPED - review")
# cost centre is system-controlled: use it to confirm family/location (cross-field validation)
h = h.merge(ccm.rename(columns={"job_family": "cc_family", "location": "cc_location"}), on="cost_centre", how="left")
mismatch = (h.job_family != h.cc_family) | (h.location != h.cc_location)
log.metric("HRIS snapshot", "family/location disagree with cost centre after mapping", "after", int(mismatch.sum()))

# R-H4 dates: ISO and dd/mm/yyyy both present; parse explicitly, never let the parser guess
def parse_date(s):
    s = s.astype("string")
    iso = pd.to_datetime(s.where(s.str.fullmatch(r"\d{4}-\d{2}-\d{2}")), format="%Y-%m-%d", errors="coerce")
    au = pd.to_datetime(s.where(s.str.fullmatch(r"\d{2}/\d{2}/\d{4}")), format="%d/%m/%Y", errors="coerce")
    return iso.fillna(au)


n_au = int(h.hire_date.astype(str).str.fullmatch(r"\d{2}/\d{2}/\d{4}").sum())
log.metric("HRIS snapshot", "hire_date in dd/mm/yyyy", "before", n_au)
for c in ("hire_date", "date_of_birth", "termination_date"):
    h[c] = parse_date(h[c])
log.metric("HRIS snapshot", "hire_date unparseable", "after", int(h.hire_date.isna().sum()))

# R-H5 placeholder / implausible birth dates (age < 15 or > 80 at snapshot) -> null, excluded from age analysis
age = (SNAPSHOT_DATE - h.date_of_birth).dt.days / 365.25
bad = (age < 15) | (age > 80)
for e in h.loc[bad, "employee_id"]:
    log.exception("HRIS snapshot", "R-H5 implausible date_of_birth", e, "", "set to null")
h.loc[bad, "date_of_birth"] = pd.NaT

# R-H6 terminated but still Active: termination date on or before the snapshot -> not in active headcount
term = h.termination_date.notna() & (h.termination_date <= SNAPSHOT_DATE)
for e in h.loc[term, "employee_id"]:
    log.exception("HRIS snapshot", "R-H6 termination date populated but status Active", e, "", "status -> Terminated")
h.loc[term, "status"] = "Terminated"

# R-H7 same person, more than one active record (rehire without closing the old one): keep latest hire
act = h[h.status == "Active"].sort_values("hire_date")
stale = act.duplicated("person_id", keep="last")
for e in act.loc[stale, "employee_id"]:
    log.exception("HRIS snapshot", "R-H7 stale prior record for same person", e, "", "excluded from headcount")
h.loc[act.index[stale], "status"] = "Superseded"

# R-H8 FTE: decimal-shift outliers and missing values, repaired from payroll ordinary hours (independent source)
pay_fte = pay.groupby("employee_id").ordinary_hours.sum() / HOURS_PER_FTE_FN
h["fte_payroll"] = h.employee_id.map(pay_fte)
shift = h.fte > 1.0
for _, r in h[shift].iterrows():
    fix = r.fte / 10 if 0 < r.fte / 10 <= 1 else np.nan
    log.exception("HRIS snapshot", "R-H8a FTE > 1.0", r.employee_id, f"{r.fte} (payroll {r.fte_payroll:.2f})",
                  f"divided by 10 -> {fix}")
    h.loc[_, "fte"] = fix
miss = h.fte.isna()
src_pay = miss & h.fte_payroll.notna() & (h.fte_payroll > 0)
h["fte_imputed"] = np.where(src_pay, "payroll hours", np.where(miss, "job family median", ""))
h.loc[src_pay, "fte"] = (h.loc[src_pay, "fte_payroll"] * 10).round() / 10   # payroll hours vary +/-3%: round to 0.1
med = h[h.status == "Active"].groupby("job_family").fte.median()
h.loc[miss & ~src_pay, "fte"] = h.loc[miss & ~src_pay, "job_family"].map(med)
for _, r in h[miss].iterrows():
    log.exception("HRIS snapshot", "R-H8b missing FTE", r.employee_id, "", f"imputed from {r.fte_imputed}")

# R-H9 missing employment type: FTE 1.0 is ambiguous (full-time permanent or fixed-term), so flag not guess
mt = h.employment_type.isna()
for e in h.loc[mt, "employee_id"]:
    log.exception("HRIS snapshot", "R-H9 missing employment type", e, "", "set 'Unknown' - HR to confirm")
h.loc[mt, "employment_type"] = "Unknown"

clean = h[h.status == "Active"].copy()
clean["age"] = ((SNAPSHOT_DATE - clean.date_of_birth).dt.days / 365.25).round(1)
clean["tenure_years"] = ((SNAPSHOT_DATE - clean.hire_date).dt.days / 365.25).round(2)
clean["gccsa"] = clean.location.map(lambda l: LOCATIONS[l]["gccsa"])
clean["remoteness"] = clean.location.map(lambda l: LOCATIONS[l]["remote"])
clean["anzsco"] = clean.job_family.map(lambda f: JOB_FAMILIES[f]["anzsco"])
keep = ["employee_id", "person_id", "job_family", "anzsco", "location", "gccsa", "remoteness", "cost_centre",
        "employment_type", "fte", "fte_imputed", "classification_level", "annual_salary_fte", "date_of_birth", "age",
        "gender", "hire_date", "tenure_years", "record_source"]
clean[keep].to_csv(PROCESSED / "employee_snapshot_clean.csv", index=False)
profile(clean[keep], "HRIS snapshot", "after")
log.metric("HRIS snapshot", "distinct location values", "after", clean.location.nunique())
log.metric("HRIS snapshot", "distinct job_family values", "after", clean.job_family.nunique())
log.metric("HRIS snapshot", "FTE outside (0, 1.0]", "after", int((~clean.fte.between(0.01, 1.0)).sum()))
log.metric("HRIS snapshot", "active headcount", "after", len(clean))
log.metric("HRIS snapshot", "active FTE", "after", round(clean.fte.sum(), 1))

# =============================================================== movements
profile(mov, "HRIS movements", "before")
mv = mov.drop_duplicates("event_id").copy()
log.metric("HRIS movements", "duplicate event_id removed", "after", len(mov) - len(mv))
mv["event_date"] = pd.to_datetime(mv.event_date)
mv.to_csv(PROCESSED / "movements_clean.csv", index=False)

# =============================================================== requisitions (ATS)
profile(ats, "ATS requisitions", "before")
a = ats.drop_duplicates("requisition_id").copy()
log.metric("ATS requisitions", "duplicate requisition_id removed", "after", len(ats) - len(a))
for c in ("open_date", "filled_date", "cancel_date"):
    a[c] = pd.to_datetime(a[c])
sw = a.filled_date < a.open_date
for r in a.loc[sw, "requisition_id"]:
    log.exception("ATS requisitions", "R-A1 filled_date before open_date", r, "", "dates swapped back")
a.loc[sw, ["open_date", "filled_date"]] = a.loc[sw, ["filled_date", "open_date"]].values
# R-A2 Filled with no date: recover from the HIRE / TRANSFER event linked to the same requisition or employee
nd = (a.status == "Filled") & a.filled_date.isna()
hire_by_req = mv[mv.event_type == "HIRE"].set_index("requisition_id").event_date
hire_by_emp = mv[mv.event_type.isin(["HIRE", "TRANSFER"])].drop_duplicates("employee_id", keep="last") \
    .set_index("employee_id").event_date
rec = a.loc[nd, "requisition_id"].map(hire_by_req)
rec = rec.fillna(a.loc[nd, "filled_by"].map(hire_by_emp))
a.loc[nd, "filled_date"] = rec
for r, v in zip(a.loc[nd, "requisition_id"], rec):
    log.exception("ATS requisitions", "R-A2 Filled without filled_date", r, v,
                  "recovered from HRIS movement" if pd.notna(v) else "left null - excluded from time-to-fill")
a["time_to_fill_days"] = (a.filled_date - a.open_date).dt.days
a.to_csv(PROCESSED / "requisitions_clean.csv", index=False)
log.metric("ATS requisitions", "Filled with missing filled_date", "after", int(((a.status == "Filled") & a.filled_date.isna()).sum()))
log.metric("ATS requisitions", "negative time-to-fill", "after", int((a.time_to_fill_days < 0).sum()))

# =============================================================== reconciliation 1: HRIS vs payroll
hr_ids, pay_ids = set(clean.employee_id), set(pay.employee_id)
terminated_ids = set(mv.loc[mv.event_type == "SEPARATION", "employee_id"])
payroll_only = pay[~pay.employee_id.isin(hr_ids)].copy()
payroll_only["explanation"] = np.where(payroll_only.employee_id.str.startswith("C"), "Contractor paid via payroll (no HRIS record)",
                              np.where(payroll_only.employee_id.isin(terminated_ids), "Final pay after separation",
                                       "UNEXPLAINED"))
hris_only = clean[~clean.employee_id.isin(pay_ids)].copy()
hris_only["explanation"] = np.where(hris_only.hire_date > pd.Timestamp("2026-06-28"),
                                    "Started after pay period end (28 Jun 2026)",
                                    "Not paid this fortnight (likely leave without pay) - confirm with payroll")
recon_pay = pd.DataFrame([
    dict(item="HRIS active headcount (clean)", count=len(hr_ids)),
    dict(item="Payroll records in fortnight", count=len(pay_ids)),
    dict(item="Matched (in both)", count=len(hr_ids & pay_ids)),
    dict(item="Payroll only: final pay after separation", count=int((payroll_only.explanation == "Final pay after separation").sum())),
    dict(item="Payroll only: contractor via payroll", count=int(payroll_only.explanation.str.startswith("Contractor").sum())),
    dict(item="Payroll only: unexplained", count=int((payroll_only.explanation == "UNEXPLAINED").sum())),
    dict(item="HRIS only: started after pay period end", count=int(hris_only.explanation.str.startswith("Started").sum())),
    dict(item="HRIS only: not paid (leave without pay?)", count=int(hris_only.explanation.str.startswith("Not paid").sum())),
])
recon_pay.to_csv(TABLES / "recon_hris_vs_payroll.csv", index=False)
pd.concat([payroll_only[["employee_id", "cost_centre", "gross_pay", "explanation"]].assign(side="payroll only"),
           hris_only[["employee_id", "cost_centre", "explanation"]].assign(side="HRIS only")]) \
    .to_csv(TABLES / "recon_hris_vs_payroll_exceptions.csv", index=False)

# FTE agreement for matched employees (HRIS contracted FTE vs paid ordinary hours / 76)
m = clean[clean.employee_id.isin(pay_ids)].assign(paid_fte=lambda x: x.employee_id.map(pay_fte))
m["abs_diff"] = (m.fte - m.paid_fte).abs()
log.metric("Reconciliation", "matched employees with |HRIS FTE - paid FTE| > 0.1", "after", int((m.abs_diff > .1).sum()),
           f"mean abs diff {m.abs_diff.mean():.3f}")

# =============================================================== reconciliation 2: HRIS filled FTE vs establishment
est26 = est[est.fy == "FY2026"].merge(ccm, on="cost_centre")
filled = clean.groupby("cost_centre").agg(headcount=("employee_id", "size"), filled_fte=("fte", "sum")).reset_index()
open_req = a[(a.status == "Open")].groupby(["job_family", "location"]).size().rename("open_requisitions").reset_index()
rc = est26.merge(filled, on="cost_centre", how="left").merge(open_req, on=["job_family", "location"], how="left").fillna(
    {"headcount": 0, "filled_fte": 0, "open_requisitions": 0})
rc["vacant_fte"] = (rc.budgeted_fte - rc.filled_fte).round(1)
rc["vacancy_rate"] = (rc.vacant_fte / rc.budgeted_fte).round(4)
rc["avg_fte_per_head"] = (rc.filled_fte / rc.headcount).round(3)
rc["open_req_fte_equiv"] = (rc.open_requisitions * rc.avg_fte_per_head).round(1)
rc["unrequisitioned_vacant_fte"] = (rc.vacant_fte - rc.open_req_fte_equiv).round(1)
rc.to_csv(TABLES / "recon_establishment_vs_filled.csv", index=False)
log.metric("Reconciliation", "establishment FTE FY2026", "after", round(rc.budgeted_fte.sum(), 1))
log.metric("Reconciliation", "filled FTE (HRIS clean)", "after", round(rc.filled_fte.sum(), 1))
log.metric("Reconciliation", "vacant FTE", "after", round(rc.vacant_fte.sum(), 1))
log.metric("Reconciliation", "cost centres over establishment", "after", int((rc.vacant_fte < 0).sum()))

# =============================================================== reconciliation 3: movements vs snapshot
recent = clean[clean.hire_date >= HISTORY_START]
hired_ids = set(mv.loc[mv.event_type == "HIRE", "employee_id"])
no_event = recent[~recent.employee_id.isin(hired_ids)]
log.metric("Reconciliation", "snapshot staff hired since 1 Jul 2022 with no HIRE event", "after", len(no_event))
sep_in_snapshot = clean[clean.employee_id.isin(terminated_ids)]
log.metric("Reconciliation", "SEPARATION event but still active in clean snapshot", "after", len(sep_in_snapshot))

# =============================================================== score cleaning against hidden truth
truth = pd.read_csv(SYNTH / "_truth" / "employee_snapshot_truth.csv", dtype={"employee_id": str})
t = truth.set_index("employee_id")
c = clean.set_index("employee_id")
common = t.index.intersection(c.index)
score = dict(
    true_headcount=len(t), cleaned_headcount=len(c), raw_rows=len(hris),
    raw_active_rows=int((hris.status == "Active").sum()),
    false_inclusions=int(len(c.index.difference(t.index))), missed_employees=int(len(t.index.difference(c.index))),
    job_family_accuracy=round(float((t.loc[common, "job_family"] == c.loc[common, "job_family"]).mean()), 4),
    location_accuracy=round(float((t.loc[common, "location"] == c.loc[common, "location"]).mean()), 4),
    fte_exact_accuracy=round(float((np.isclose(t.loc[common, "fte"], c.loc[common, "fte"], atol=.051)).mean()), 4),
    true_fte=round(float(t.fte.sum()), 1), cleaned_fte=round(float(c.fte.sum()), 1),
    raw_fte_naive=round(float(pd.to_numeric(hris.fte, errors="coerce").sum()), 1),
    hire_date_accuracy=round(float((pd.to_datetime(t.loc[common, "hire_date"]) == c.loc[common, "hire_date"]).mean()), 4),
)
save_json(score, TABLES / "cleaning_scorecard.json")
log.save()
print(pd.DataFrame(log.metrics).to_string())
print(recon_pay.to_string())
print(score)
