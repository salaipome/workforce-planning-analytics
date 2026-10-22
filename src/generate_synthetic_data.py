"""Step 3 - Generate the SYNTHETIC internal data for the fictional "Kestrel Health Services" (KHS).

*** Everything this script writes is synthetic. KHS is not a real organisation. ***

Real public data supplies only two inputs, and both are labelled in the output metadata:
  * The market-tightness index: ABS Labour Account, Health Care & Social Assistance,
    proportion of vacant jobs (seasonally adjusted, quarterly). It scales time-to-fill and quit rates
    month by month, so the synthetic history moves with real labour market conditions.
  * The RN graduate intake month (February) follows the usual Australian graduate programme timing.
All other parameters (FAMILY, LOCATION and the defect rates) are illustrative assumptions.

Outputs in data/synthetic/ simulate the systems a workforce planning team would extract from:
  hris_employee_snapshot.csv   HRIS employee master as at 30 Jun 2026 (with injected defects)
  hris_movements.csv           HRIS events: HIRE, SEPARATION, TRANSFER, ROLE_CHANGE (Jul 2022 - Jun 2026)
  payroll_fortnight.csv        payroll for the fortnight ending 28 Jun 2026
  finance_establishment.csv    budgeted FTE by cost centre and FY (FY2023-FY2027)
  ats_requisitions.csv         recruitment requisitions (applicant tracking system)
  agency_usage.csv             monthly agency/contractor hours and cost
  cost_centre_map.csv          reference: cost centre -> job family, location
  _truth/                      clean ground truth + defect log (used only to score the cleaning step)
"""
import numpy as np
import pandas as pd

from common import JOB_FAMILIES, LOCATIONS, PROCESSED, SYNTH, HISTORY_START, SNAPSHOT_DATE, fy_label, save_json

rng = np.random.default_rng(20260630)
TRUTH = SYNTH / "_truth"
TRUTH.mkdir(exist_ok=True)

# ------------------------------------------------------------------ illustrative parameters
# share = share of FY2023 establishment FTE; sep = base annual separation rate; ttf = median days to fill;
# salary = FY2023 base salary per 1.0 FTE (AUD); ft = share full-time; growth = annual establishment growth
FAMILY = {
    "Registered Nurse":     dict(share=.32, sep=.15, ttf=52, salary=98000,  ft=.45, growth=.030, age_shift=0),
    "Midwife":              dict(share=.03, sep=.13, ttf=68, salary=101000, ft=.40, growth=.020, age_shift=2),
    "Enrolled Nurse":       dict(share=.075, sep=.15, ttf=42, salary=72000, ft=.40, growth=.020, age_shift=1),
    "Medical Practitioner": dict(share=.08, sep=.12, ttf=95, salary=215000, ft=.70, growth=.025, age_shift=1),
    "Allied Health":        dict(share=.09, sep=.16, ttf=62, salary=92000,  ft=.55, growth=.030, age_shift=-4),
    "Care Worker":          dict(share=.16, sep=.24, ttf=30, salary=62000,  ft=.25, growth=.045, age_shift=0),
    "Administration":       dict(share=.145, sep=.13, ttf=28, salary=70000, ft=.65, growth=.005, age_shift=2),
    "Support Services":     dict(share=.10, sep=.19, ttf=26, salary=60000,  ft=.50, growth=.010, age_shift=3),
}
# share of FTE; sep = separation multiplier; ttf = time-to-fill multiplier; cancel = requisition cancel prob.
LOCATION = {
    "Perth North": dict(share=.31, sep=1.00, ttf=1.00, cancel=.05),
    "Perth South": dict(share=.28, sep=0.95, ttf=1.00, cancel=.05),
    "Bunbury":     dict(share=.15, sep=1.05, ttf=1.20, cancel=.07),
    "Geraldton":   dict(share=.10, sep=1.20, ttf=1.40, cancel=.09),
    "Kalgoorlie":  dict(share=.085, sep=1.35, ttf=1.55, cancel=.11),
    "Broome":      dict(share=.075, sep=1.50, ttf=1.80, cancel=.13),
}
START_EST_FTE = 1570.0           # FY2023 establishment FTE (sized so headcount ends near 2,000)
SEP_SCALE = 0.68                 # calibration: overall turnover ~15-16%, inside the 10.8% (ABS HCSA
                                 # job-mobility outflow) to ~20% band; illustrative
INITIAL_FILL = 0.935             # filled share of establishment FTE at 1 Jul 2022
READVERTISE_P = 0.70             # share of cancelled requisitions re-advertised
REPLACE_P = 0.93                 # share of separations that trigger a replacement requisition
INTERNAL_FILL_P = 0.10           # share of requisitions filled by an internal transfer
EN_TO_RN_P = 0.07                # annual share of ENs who complete an RN conversion (role change each January)
GRAD_RN_PER_YEAR = 36            # RN graduates placed each February (fill open RN requisitions first)
AGENCY_COVER = {"Registered Nurse": .55, "Midwife": .55, "Enrolled Nurse": .40, "Medical Practitioner": .60,
                "Allied Health": .30, "Care Worker": .45, "Administration": .10, "Support Services": .25}
AGENCY_PREMIUM = 1.65            # agency cost per hour relative to employee base cost per hour
HOURS_PER_FTE_FN = 76            # ordinary hours per fortnight for 1.0 FTE
WAGE_GROWTH = {"FY2023": .000, "FY2024": .040, "FY2025": .042, "FY2026": .038, "FY2027": .035}  # cumulative steps

# ------------------------------------------------------------------ real market-tightness index
la = pd.read_csv(PROCESSED / "labour_account_health.csv")
vac = la[(la.industry_code == "Q") & (la.adjustment == "Seasonally Adjusted")] \
    .set_index("period_start")["Jobs; Proportion of vacant jobs"]
vac.index = pd.to_datetime(vac.index)
months = pd.date_range(HISTORY_START, SNAPSHOT_DATE, freq="MS")
vac_m = vac.resample("MS").ffill().reindex(months, method="ffill")
tight = (vac_m / vac_m.mean()) ** 0.6            # >1 = tighter than the 4-year average
tight_tbl = pd.DataFrame({"month": months, "abs_health_vacant_job_pct": vac_m.values, "tightness_index": tight.values})

fams, locs = list(FAMILY), list(LOCATION)
fys = ["FY2023", "FY2024", "FY2025", "FY2026", "FY2027"]

# ------------------------------------------------------------------ establishment (Finance)
cc_rows, est_rows = [], []
for i, f in enumerate(fams):
    for j, l in enumerate(locs):
        cc = f"CC{(i + 1) * 100 + j + 1}"
        cc_rows.append(dict(cost_centre=cc, job_family=f, location=l))
        loc_share = LOCATION[l]["share"]
        if f == "Midwife" and l in ("Kalgoorlie", "Broome"):
            loc_share *= 0.7
        base = START_EST_FTE * FAMILY[f]["share"] * loc_share
        g = FAMILY[f]["growth"] + (0.01 if l in ("Bunbury", "Broome") else 0)
        for k, fy in enumerate(fys):
            est_rows.append(dict(cost_centre=cc, fy=fy, budgeted_fte=round(base * (1 + g) ** k, 1)))
cc_map = pd.DataFrame(cc_rows)
est = pd.DataFrame(est_rows).merge(cc_map, on="cost_centre")
est_lookup = est.set_index(["fy", "job_family", "location"])["budgeted_fte"]

# ------------------------------------------------------------------ helpers
next_emp, next_person, next_req = [100001], [500001], [1]


def draw_contract(f, n):
    ft = FAMILY[f]["ft"]
    u = rng.random(n)
    etype = np.where(u < ft, "Permanent Full-time", np.where(u < ft + (1 - ft) * .70, "Permanent Part-time",
                     np.where(u < ft + (1 - ft) * .85, "Fixed-term", "Casual")))
    fte = np.where(etype == "Permanent Full-time", 1.0,
                   np.where(etype == "Casual", rng.choice([.2, .3, .4, .5], n), rng.choice([.4, .5, .6, .7, .8, .9], n)))
    fte = np.where((etype == "Fixed-term") & (rng.random(n) < .5), 1.0, fte)
    return etype, fte


# Age distribution of WA Health Care & Social Assistance workers, Census 2021 G54 (REAL), by GCCSA
g54 = pd.read_csv(PROCESSED / "census2021_g54_wa.csv", dtype=str)
g54 = g54[(g54.sex_code == "3") & (g54.industry_code == "Q") & (g54.age_code != "_T")]
g54["value"] = g54.value.astype(float)
AGE_BANDS = {"15_19": (18, 20), "20_24": (20, 25), "25_34": (25, 35), "35_44": (35, 45), "45_54": (45, 55),
             "55_64": (55, 65), "65_74": (65, 75), "75_84": (75, 76), "GE85": (75, 76)}
CENSUS_AGE = {r: (lambda d: d / d.sum())(g54[g54.region == r].set_index("age_code").value.reindex(list(AGE_BANDS)).fillna(0))
              for r in ("Greater Perth", "Rest of WA")}


def draw_age(f, l, n, hires=False):
    """Census-calibrated age at entry; new hires skew younger (illustrative 0.75 weight on <35 bands)."""
    p = CENSUS_AGE[LOCATIONS[l]["gccsa"]].copy()
    if hires:
        p[["15_19", "20_24", "25_34"]] *= 1.6
        p[["55_64", "65_74", "75_84", "GE85"]] *= 0.5
        p /= p.sum()
    bands = rng.choice(list(AGE_BANDS), n, p=p.values)
    age = np.array([rng.uniform(*AGE_BANDS[b]) for b in bands]) + FAMILY[f]["age_shift"]
    return np.clip(age, 19, 74)


def new_people(f, l, n, when, age_shift=0.0, hire_dates=None, hires=False):
    etype, fte = draw_contract(f, n)
    age = np.clip(draw_age(f, l, n, hires) + age_shift, 19, 74)
    ids = np.arange(next_emp[0], next_emp[0] + n)
    pids = np.arange(next_person[0], next_person[0] + n)
    next_emp[0] += n
    next_person[0] += n
    level = rng.choice([1, 2, 3, 4], n, p=[.35, .35, .2, .1])
    return pd.DataFrame(dict(
        employee_id=ids, person_id=pids, job_family=f, location=l, employment_type=etype, fte=fte,
        date_of_birth=[when - pd.Timedelta(days=int(a * 365.25)) for a in age],
        hire_date=hire_dates if hire_dates is not None else when,
        gender=rng.choice(["Female", "Male", "Non-binary/Not stated"], n,
                          p=[.88, .11, .01] if f in ("Registered Nurse", "Midwife", "Enrolled Nurse", "Care Worker")
                          else [.62, .37, .01]),
        classification_level=level, status="Active", termination_date=pd.NaT, separation_reason=None))


# ------------------------------------------------------------------ initial workforce at 1 Jul 2022
parts = []
for f in fams:
    for l in locs:
        target = est_lookup[("FY2023", f, l)] * INITIAL_FILL
        n = 0
        while True:
            n += 1
            et, fte = draw_contract(f, n)
            if fte.sum() >= target or n > 400:
                break
        tenure = rng.gamma(1.6, 3.2, n)   # years, long right tail
        hire = [HISTORY_START - pd.Timedelta(days=int(t * 365.25) + 1) for t in tenure]  # all before day 1
        p = new_people(f, l, n, HISTORY_START, hire_dates=hire)
        earliest = p.date_of_birth + pd.DateOffset(years=19)       # nobody hired before age 19
        earliest = earliest.clip(upper=HISTORY_START - pd.Timedelta(days=1))
        p["hire_date"] = np.maximum(pd.to_datetime(p.hire_date).values, pd.to_datetime(earliest).values)
        parts.append(p)
emp = pd.concat(parts, ignore_index=True)
print("initial headcount 1 Jul 2022:", len(emp), "FTE:", round(emp.fte.sum(), 1))
events, reqs = [], []


def open_req(f, l, when, reason, tight_now):
    q = next_req[0]
    next_req[0] += 1
    med = FAMILY[f]["ttf"] * LOCATION[l]["ttf"] * tight_now
    ttf = max(7, int(rng.lognormal(np.log(med), 0.45)))
    cancel = rng.random() < LOCATION[l]["cancel"] * tight_now
    applicants = max(0, int(rng.poisson(14 / (LOCATION[l]["ttf"] * tight_now) ** 1.5)))
    reqs.append(dict(requisition_id=f"REQ{q:06d}", job_family=f, location=l, open_date=when, reason=reason,
                     planned_close=when + pd.Timedelta(days=ttf), cancelled=cancel, applicants=applicants,
                     status="Open", filled_date=pd.NaT, filled_by=None, source=None,
                     cancel_date=when + pd.Timedelta(days=int(ttf * .7)) if cancel else pd.NaT))


# Vacancies that already exist on 1 Jul 2022 have requisitions opened in the preceding 0-60 days
for f in fams:
    for l in locs:
        cell = emp[(emp.job_family == f) & (emp.location == l)]
        gap = est_lookup[("FY2023", f, l)] - cell.fte.sum()
        for _ in range(int(round(max(gap, 0) / cell.fte.mean()))):
            open_req(f, l, HISTORY_START - pd.Timedelta(days=int(rng.integers(0, 60))), "Replacement", float(tight.iloc[0]))


def hazard(df, m, tight_now):
    base = df.job_family.map(lambda f: FAMILY[f]["sep"]).values
    locm = df.location.map(lambda l: LOCATION[l]["sep"]).values
    tenure = (m - pd.to_datetime(df.hire_date)).dt.days.values / 365.25
    age = (m - pd.to_datetime(df.date_of_birth)).dt.days.values / 365.25
    mult = np.where(tenure < 1, 1.7, np.where(tenure < 3, 1.1, 0.8))
    mult *= np.where(age >= 62, 2.2, np.where(age >= 55, 1.3, 1.0))
    mult *= np.where(df.employment_type.values == "Casual", 1.4, 1.0)
    annual = SEP_SCALE * base * locm * mult * tight_now ** 0.8
    return 1 - (1 - np.clip(annual, 0, .95)) ** (1 / 12)


def add_event(eid, pid, etype, date, f, l, **kw):
    events.append(dict(employee_id=eid, person_id=pid, event_type=etype, event_date=date, job_family=f,
                       location=l, **kw))


# ------------------------------------------------------------------ monthly simulation
for m_i, m in enumerate(months):
    t = float(tight.iloc[m_i])
    fy = fy_label(pd.Series([m])).iloc[0]
    month_end = m + pd.offsets.MonthEnd(0)
    active = emp.status == "Active"

    # 1. New positions at the start of each FY (establishment growth) -> requisitions
    if m.month == 7 and m > HISTORY_START:
        prev = f"FY{int(fy[2:]) - 1}"
        for f in fams:
            for l in locs:
                delta = est_lookup[(fy, f, l)] - est_lookup[(prev, f, l)]
                avg_fte = emp.loc[active & (emp.job_family == f), "fte"].mean()
                for _ in range(int(round(max(delta, 0) / avg_fte))):
                    open_req(f, l, m + pd.Timedelta(days=int(rng.integers(0, 20))), "New position", t)

    # 2. Separations
    act = emp[active]
    p = hazard(act, m, t)
    leave = act.index[rng.random(len(act)) < p]
    for idx in leave:
        r = emp.loc[idx]
        day = m + pd.Timedelta(days=int(rng.integers(0, month_end.day)))
        age = (day - r.date_of_birth).days / 365.25
        if age >= 60 and rng.random() < .65:
            reason = "Retirement"
        elif r.employment_type == "Fixed-term" and rng.random() < .5:
            reason = "End of contract"
        else:
            reason = rng.choice(["Resignation", "Resignation", "Resignation", "Resignation", "Dismissal", "Other"],
                                p=[.22, .22, .22, .22, .04, .08])
        emp.loc[idx, ["status", "termination_date", "separation_reason"]] = ["Terminated", day, reason]
        add_event(r.employee_id, r.person_id, "SEPARATION", day, r.job_family, r.location, reason=reason)
        if rng.random() < REPLACE_P:
            open_req(r.job_family, r.location, day - pd.Timedelta(days=int(rng.integers(0, 21))), "Replacement", t)

    # 3. EN -> RN conversions each January (internal outflow from EN, inflow to RN)
    if m.month == 1:
        ens = emp.index[(emp.status == "Active") & (emp.job_family == "Enrolled Nurse")]
        conv = ens[rng.random(len(ens)) < EN_TO_RN_P]
        for idx in conv:
            r = emp.loc[idx]
            emp.loc[idx, "job_family"] = "Registered Nurse"
            add_event(r.employee_id, r.person_id, "ROLE_CHANGE", m + pd.Timedelta(days=14), "Registered Nurse",
                      r.location, from_job_family="Enrolled Nurse", from_location=r.location)
            open_req("Enrolled Nurse", r.location, m + pd.Timedelta(days=14), "Replacement", t)

    # 4. Fill requisitions whose close date falls in this month (FIFO); February RN graduates first
    req_df_idx = [i for i, q in enumerate(reqs) if q["status"] == "Open"]
    grads_left = GRAD_RN_PER_YEAR if m.month == 2 else 0
    for i in req_df_idx:
        q = reqs[i]
        if q["cancelled"] and q["cancel_date"] <= month_end:
            q["status"] = "Cancelled"
            if rng.random() < READVERTISE_P:      # position re-advertised after a cancelled round
                open_req(q["job_family"], q["location"], q["cancel_date"] + pd.Timedelta(days=int(rng.integers(14, 45))),
                         "Re-advertised", t)
            continue
        is_grad = grads_left > 0 and q["job_family"] == "Registered Nurse" and q["location"] in \
            ("Perth North", "Perth South", "Bunbury", "Geraldton")
        if not (q["planned_close"] <= month_end or is_grad):
            continue
        fill_day = min(max(q["planned_close"], m), month_end) if not is_grad else max(q["open_date"], m + pd.Timedelta(days=3))
        if is_grad:
            grads_left -= 1
        q["status"], q["filled_date"] = "Filled", fill_day
        internal_pool = emp.index[(emp.status == "Active") & (emp.job_family == q["job_family"]) &
                                  (emp.location != q["location"])]
        if not is_grad and rng.random() < INTERNAL_FILL_P and len(internal_pool):
            idx = rng.choice(internal_pool)
            r = emp.loc[idx]
            emp.loc[idx, "location"] = q["location"]
            q["filled_by"], q["source"] = int(r.employee_id), "Internal transfer"
            add_event(r.employee_id, r.person_id, "TRANSFER", fill_day, r.job_family, q["location"],
                      from_job_family=r.job_family, from_location=r.location)
            open_req(r.job_family, r.location, fill_day, "Replacement (internal move)", t)
        else:
            newp = new_people(q["job_family"], q["location"], 1, fill_day, age_shift=0 if not is_grad else -6, hires=True)
            if is_grad:
                newp["employment_type"], newp["fte"] = "Fixed-term", 1.0
            emp = pd.concat([emp, newp], ignore_index=True)
            r = newp.iloc[0]
            q["filled_by"], q["source"] = int(r.employee_id), "Graduate program" if is_grad else "External"
            add_event(r.employee_id, r.person_id, "HIRE", fill_day, r.job_family, r.location,
                      source=q["source"], requisition_id=q["requisition_id"])

# ------------------------------------------------------------------ assemble clean truth tables
emp["hire_date"] = pd.to_datetime(emp["hire_date"])
truth_snapshot = emp[(emp.status == "Active")].copy()
for col in ("date_of_birth", "hire_date", "termination_date"):
    emp[col] = pd.to_datetime(emp[col]).dt.date
sal = emp.job_family.map(lambda f: FAMILY[f]["salary"]) * (1 + (emp.classification_level - 1) * .07)
emp["annual_salary_fte"] = (sal * np.prod([1 + v for v in WAGE_GROWTH.values() if v])).round(-2)
cc_lookup = cc_map.set_index(["job_family", "location"])["cost_centre"]
emp["cost_centre"] = [cc_lookup[(f, l)] for f, l in zip(emp.job_family, emp.location)]
emp["record_source"] = "SYNTHETIC"

mov = pd.DataFrame(events).sort_values("event_date").reset_index(drop=True)
mov["event_id"] = [f"EV{i:07d}" for i in range(1, len(mov) + 1)]
req = pd.DataFrame(reqs)
req["filled_by"] = req.filled_by.astype("Int64")
req.loc[(req.status == "Open") & req.cancelled & (req.cancel_date <= SNAPSHOT_DATE), "status"] = "Cancelled"
req["time_to_fill_days"] = (pd.to_datetime(req.filled_date) - pd.to_datetime(req.open_date)).dt.days
req = req.drop(columns=["planned_close", "cancelled"])
req["cancel_date"] = req["cancel_date"].where(req.status == "Cancelled")

active = emp[emp.status == "Active"].copy()
snap_cols = ["employee_id", "person_id", "job_family", "location", "cost_centre",
             "employment_type", "fte", "classification_level", "annual_salary_fte", "date_of_birth", "gender",
             "hire_date", "status", "termination_date", "separation_reason", "record_source"]
truth = active[snap_cols].copy()

# ------------------------------------------------------------------ payroll (fortnight ending 28 Jun 2026)
pay = active[["employee_id", "cost_centre", "fte", "annual_salary_fte"]].copy()
pay["ordinary_hours"] = (pay.fte * HOURS_PER_FTE_FN * rng.normal(1, .03, len(pay))).clip(0).round(2)
pay["overtime_hours"] = np.where(rng.random(len(pay)) < .18, rng.gamma(2, 2.5, len(pay)), 0).round(2)
hourly = pay.annual_salary_fte / 52.14 / 38
pay["gross_pay"] = (hourly * (pay.ordinary_hours + 1.5 * pay.overtime_hours)).round(2)
pay["pay_period_end"] = "2026-06-28"

# ------------------------------------------------------------------ agency usage (monthly)
ag = []
filled_hist = []
emp_dt = emp.assign(hd=pd.to_datetime(emp.hire_date), td=pd.to_datetime(emp.termination_date))
for m in months:
    fy = fy_label(pd.Series([m])).iloc[0]
    me = m + pd.offsets.MonthEnd(0)
    on = emp_dt[(emp_dt.hd <= me) & (emp_dt.td.isna() | (emp_dt.td > me))]
    # Job family/location at month end is approximated by the current record (moves are rare)
    filled = on.groupby(["job_family", "location"])["fte"].sum()
    for f in fams:
        for l in locs:
            e_fte = est_lookup[(fy, f, l)]
            gap = max(0.0, e_fte - filled.get((f, l), 0.0))
            a_fte = gap * AGENCY_COVER[f] * rng.uniform(.8, 1.2)
            hours = a_fte * HOURS_PER_FTE_FN * 26 / 12
            rate = FAMILY[f]["salary"] / 52.14 / 38 * AGENCY_PREMIUM
            ag.append(dict(month=m.date(), job_family=f, location=l, agency_hours=round(hours, 1),
                           agency_cost=round(hours * rate, 2), record_source="SYNTHETIC"))
            filled_hist.append(dict(month=m.date(), job_family=f, location=l, filled_fte=round(filled.get((f, l), 0), 2),
                                    established_fte=e_fte))
agency = pd.DataFrame(ag)

# ------------------------------------------------------------------ inject documented defects
defects = []


def log_defect(table, kind, key, detail):
    defects.append(dict(table=table, defect_type=kind, record_key=str(key), detail=detail))


snap = truth.copy()
snap["hire_date"] = pd.to_datetime(snap.hire_date).dt.strftime("%Y-%m-%d")
snap["date_of_birth"] = pd.to_datetime(snap.date_of_birth).dt.strftime("%Y-%m-%d")
snap["termination_date"] = None
n = len(snap)
pick = lambda k: rng.choice(snap.index, k, replace=False)

for idx in pick(int(n * .08)):        # location free-text variants
    v = rng.choice(["upper", "abbrev", "space", "suffix"])
    loc = snap.at[idx, "location"]
    new = {"upper": loc.upper(), "abbrev": loc.replace("North", "Nth").replace("South", "Sth"),
           "space": f"  {loc.lower()} ", "suffix": f"{loc} Campus"}[v]
    if new == loc:          # e.g. "Nth" abbreviation of a site without North/South: no defect created
        continue
    snap.at[idx, "location"] = new
    log_defect("hris_employee_snapshot", "location_variant", snap.at[idx, "employee_id"], new)
variants = {"Registered Nurse": ["RN", "Reg Nurse", "Registered Nurse - Grad"], "Enrolled Nurse": ["EN"],
            "Care Worker": ["AIN", "Personal Care Assistant"], "Medical Practitioner": ["Doctor", "Medical Officer"],
            "Allied Health": ["Allied Health Prof", "Physiotherapist"], "Administration": ["Admin", "Admin Officer"],
            "Support Services": ["Support Svcs", "Orderly"], "Midwife": ["Midwifery"]}
for idx in pick(int(n * .10)):
    fam = snap.at[idx, "job_family"]
    new = rng.choice(variants[fam])
    snap.at[idx, "job_family"] = new
    log_defect("hris_employee_snapshot", "job_family_variant", snap.at[idx, "employee_id"], new)
for idx in pick(int(n * .02)):
    snap.at[idx, "fte"] = np.nan
    log_defect("hris_employee_snapshot", "missing_fte", snap.at[idx, "employee_id"], "")
for idx in pick(10):
    snap.at[idx, "fte"] = snap.at[idx, "fte"] * 10
    log_defect("hris_employee_snapshot", "fte_decimal_shift", snap.at[idx, "employee_id"], snap.at[idx, "fte"])
for idx in pick(int(n * .15)):
    d = pd.to_datetime(snap.at[idx, "hire_date"])
    snap.at[idx, "hire_date"] = d.strftime("%d/%m/%Y")
    log_defect("hris_employee_snapshot", "date_format_ddmmyyyy", snap.at[idx, "employee_id"], snap.at[idx, "hire_date"])
for idx in pick(6):
    snap.at[idx, "date_of_birth"] = "1900-01-01"
    log_defect("hris_employee_snapshot", "dob_placeholder", snap.at[idx, "employee_id"], "1900-01-01")
for idx in pick(int(n * .01)):
    snap.at[idx, "employment_type"] = None
    log_defect("hris_employee_snapshot", "missing_employment_type", snap.at[idx, "employee_id"], "")
# exact duplicate rows (double extract)
dups = snap.loc[pick(25)].copy()
for e in dups.employee_id:
    log_defect("hris_employee_snapshot", "exact_duplicate", e, "")
# separated employees still flagged Active (late termination processing), termination date populated
recent_terms = emp[(emp.status == "Terminated") &
                   (pd.to_datetime(emp.termination_date) > SNAPSHOT_DATE - pd.Timedelta(days=60))].sample(30, random_state=1)
stale = recent_terms[snap_cols].copy()
stale["status"] = "Active"
stale["hire_date"] = pd.to_datetime(stale.hire_date).dt.strftime("%Y-%m-%d")
stale["date_of_birth"] = pd.to_datetime(stale.date_of_birth).dt.strftime("%Y-%m-%d")
stale["termination_date"] = pd.to_datetime(stale.termination_date).dt.strftime("%Y-%m-%d")
for e in stale.employee_id:
    log_defect("hris_employee_snapshot", "terminated_but_active", e, "termination_date populated")
# rehire with a new employee_id: the old record for the same person was never closed
rehire_src = snap.sample(12, random_state=2)
old = rehire_src.copy()
old["employee_id"] = [int(x) for x in rng.integers(90000, 99999, 12)]
old["hire_date"] = (pd.to_datetime(rehire_src.hire_date, format="mixed", dayfirst=True) - pd.Timedelta(days=900)).dt.strftime("%Y-%m-%d")
for e in old.employee_id:
    log_defect("hris_employee_snapshot", "stale_prior_record_same_person", e, "older employee_id for an active person")
snap = pd.concat([snap, dups, stale, old], ignore_index=True).sample(frac=1, random_state=3).reset_index(drop=True)

# payroll defects: LWOP employees missing, final pays for leavers, contractors without an HRIS record
lwop = pay.sample(int(len(pay) * .015), random_state=4)
for e in lwop.employee_id:
    log_defect("payroll_fortnight", "on_unpaid_leave_not_paid", e, "")
pay = pay.drop(lwop.index)
final = recent_terms.head(20)[["employee_id", "cost_centre", "fte", "annual_salary_fte"]].copy()
final["ordinary_hours"], final["overtime_hours"] = 0.0, 0.0
final["gross_pay"] = (final.annual_salary_fte / 26 * rng.uniform(.5, 2.5, len(final))).round(2)   # leave payout
final["pay_period_end"] = "2026-06-28"
for e in final.employee_id:
    log_defect("payroll_fortnight", "final_pay_terminated", e, "leave payout")
contractors = pd.DataFrame(dict(employee_id=[f"C{9000 + i}" for i in range(18)],
                                cost_centre=rng.choice(cc_map.cost_centre, 18), fte=1.0, annual_salary_fte=np.nan,
                                ordinary_hours=76.0, overtime_hours=0.0,
                                gross_pay=rng.uniform(5500, 9500, 18).round(2), pay_period_end="2026-06-28"))
for e in contractors.employee_id:
    log_defect("payroll_fortnight", "payroll_only_contractor", e, "no HRIS record")
pay = pd.concat([pay, final, contractors], ignore_index=True)
pay["employee_id"] = pay.employee_id.astype(str)
pay["record_source"] = "SYNTHETIC"

# requisition defects
req_out = req.copy()
for c in ("open_date", "filled_date", "cancel_date"):
    req_out[c] = pd.to_datetime(req_out[c]).dt.strftime("%Y-%m-%d")
rdup = req_out.sample(int(len(req_out) * .02), random_state=5)
for r in rdup.requisition_id:
    log_defect("ats_requisitions", "duplicate_requisition", r, "")
filled_ix = req_out.index[req_out.status == "Filled"]
swap = rng.choice(filled_ix, 10, replace=False)
for i in swap:
    req_out.loc[i, ["open_date", "filled_date"]] = req_out.loc[i, ["filled_date", "open_date"]].values
    log_defect("ats_requisitions", "dates_swapped", req_out.at[i, "requisition_id"], "filled_date < open_date")
nofill = rng.choice(np.setdiff1d(filled_ix, swap), 15, replace=False)
for i in nofill:
    req_out.at[i, "filled_date"] = None
    log_defect("ats_requisitions", "filled_without_date", req_out.at[i, "requisition_id"], "")
req_out = pd.concat([req_out, rdup], ignore_index=True)
req_out["time_to_fill_days"] = np.nan       # ATS export does not carry it; derived in cleaning
req_out["record_source"] = "SYNTHETIC"

mov_out = mov.copy()
mdup = mov_out.sample(20, random_state=6)
for e in mdup.event_id:
    log_defect("hris_movements", "duplicate_event", e, "")
mov_out = pd.concat([mov_out, mdup], ignore_index=True).sort_values("event_date").reset_index(drop=True)
mov_out["record_source"] = "SYNTHETIC"

# ------------------------------------------------------------------ write
snap.to_csv(SYNTH / "hris_employee_snapshot.csv", index=False)
mov_out.to_csv(SYNTH / "hris_movements.csv", index=False)
pay.to_csv(SYNTH / "payroll_fortnight.csv", index=False)
est[["cost_centre", "fy", "budgeted_fte"]].assign(record_source="SYNTHETIC").to_csv(SYNTH / "finance_establishment.csv", index=False)
req_out.to_csv(SYNTH / "ats_requisitions.csv", index=False)
agency.to_csv(SYNTH / "agency_usage.csv", index=False)
cc_map.to_csv(SYNTH / "cost_centre_map.csv", index=False)
truth.to_csv(TRUTH / "employee_snapshot_truth.csv", index=False)
emp[snap_cols].to_csv(TRUTH / "all_employees_truth.csv", index=False)
req.to_csv(TRUTH / "requisitions_truth.csv", index=False)
pd.DataFrame(filled_hist).to_csv(TRUTH / "monthly_filled_fte_truth.csv", index=False)
pd.DataFrame(defects).to_csv(TRUTH / "defect_log.csv", index=False)
tight_tbl.to_csv(SYNTH / "market_tightness_index.csv", index=False)
save_json({"organisation": "Kestrel Health Services (FICTIONAL)", "seed": 20260630,
           "real_inputs": ["ABS Labour Account Q industry proportion of vacant jobs (SA) -> tightness index",
                           "ABS Census 2021 G54 WA Health Care & Social Assistance age distribution by GCCSA -> age at entry"],
           "illustrative_parameters": {"FAMILY": FAMILY, "LOCATION": LOCATION, "START_EST_FTE": START_EST_FTE,
                                       "INITIAL_FILL": INITIAL_FILL, "REPLACE_P": REPLACE_P,
                                       "INTERNAL_FILL_P": INTERNAL_FILL_P, "READVERTISE_P": READVERTISE_P, "EN_TO_RN_P": EN_TO_RN_P,
                                       "GRAD_RN_PER_YEAR": GRAD_RN_PER_YEAR, "AGENCY_COVER": AGENCY_COVER,
                                       "AGENCY_PREMIUM": AGENCY_PREMIUM, "WAGE_GROWTH": WAGE_GROWTH}},
          SYNTH / "synthetic_metadata.json")

print("true active headcount 30 Jun 2026:", len(truth), " FTE:", round(truth.fte.sum(), 1))
print("snapshot rows (with defects):", len(snap), " events:", len(mov_out), " requisitions:", len(req_out))
print("payroll rows:", len(pay), " defects injected:", len(defects))
print(pd.DataFrame(defects).groupby(["table", "defect_type"]).size())
print(truth.groupby("job_family").size())
print(mov.groupby([fy_label(pd.to_datetime(mov.event_date)), "event_type"]).size().unstack())
