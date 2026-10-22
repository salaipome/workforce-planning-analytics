"""Step 7 - Three-year stock-and-flow workforce planning model (FY2027-FY2029) with scenarios,
interventions, sensitivity analysis, Monte Carlo uncertainty and a backtest of the model itself.

Core identity (per job family x location, per year, headcount):
    HC_end = HC_start + Hires + Other inflows - Separations - Other outflows
    Other inflows  = graduate intake + EN->RN conversions in + net internal transfers (if > 0)
    Other outflows = EN->RN conversions out (+ net internal transfers if < 0)
    Supply FTE     = HC_end x FTE-per-head
    Demand FTE     = Demand FTE (prior year) x (1 + demand growth)       [FY2026 establishment = base]
    Required hires = max(0, (Demand FTE - HC_pre_hire x FTE-per-head) / FTE-per-head)
    Hires          = min(Required hires, recruitment capacity)
    Gap FTE        = Demand FTE - Supply FTE   (+ = shortage)
Provenance of every input is recorded in outputs/tables/model_assumptions.csv.
"""
import copy
import json

import numpy as np
import pandas as pd

from common import PROCESSED, SYNTH, TABLES, JOB_FAMILIES, LOCATIONS, PLAN_YEARS, save_json

rng = np.random.default_rng(7)
FAMS, LOCS = list(JOB_FAMILIES), list(LOCATIONS)
REGIONAL = [l for l in LOCS if LOCATIONS[l]["gccsa"] == "Rest of WA"]
CLINICAL = ["Registered Nurse", "Midwife", "Enrolled Nurse", "Medical Practitioner", "Allied Health", "Care Worker"]

# ------------------------------------------------------------------ measured inputs (synthetic internal data)
emp = pd.read_csv(PROCESSED / "employee_snapshot_clean.csv")
flows = pd.read_csv(TABLES / "int_stock_flow_history.csv")
mv = pd.read_csv(PROCESSED / "movements_clean.csv", parse_dates=["event_date"])
est = pd.read_csv(SYNTH / "finance_establishment.csv").merge(pd.read_csv(SYNTH / "cost_centre_map.csv"), on="cost_centre")
cover = pd.read_csv(TABLES / "int_agency_cover_ratio.csv").set_index("job_family").agency_cover_ratio
occ = pd.read_csv(TABLES / "ext_occupation_indicators.csv").set_index("job_family")
ext = json.load(open(TABLES / "ext_summary.json"))
proj_state = pd.read_csv(PROCESSED / "employment_projections_state.csv").set_index("state")

idx = pd.MultiIndex.from_product([FAMS, LOCS], names=["job_family", "location"])
base = pd.DataFrame(index=idx)
g = emp.groupby(["job_family", "location"])
base["hc0"] = g.size().reindex(idx).fillna(0)
base["fte0"] = g.fte.sum().reindex(idx).fillna(0)
base["fte_per_head"] = (base.fte0 / base.hc0).fillna(emp.fte.mean())
base["cost_per_fte"] = ((emp.annual_salary_fte * emp.fte).groupby([emp.job_family, emp.location]).sum() / g.fte.sum()).reindex(idx)
base["demand0"] = est[est.fy == "FY2026"].set_index(["job_family", "location"]).budgeted_fte.reindex(idx)
base["budget_fy2027"] = est[est.fy == "FY2027"].set_index(["job_family", "location"]).budgeted_fte.reindex(idx)

# attrition: FY2025-FY2026 cell rate, credibility-weighted toward the family rate (small cells are noisy)
fl = flows[flows.fy.isin(["FY2025", "FY2026"])]
cell = fl.groupby(["job_family", "location"])[["separations", "opening", "closing", "hires", "transfers_in", "transfers_out"]].sum()
cell["avg_hc"] = (cell.opening + cell.closing) / 2
famr = fl.groupby("job_family")[["separations", "opening", "closing"]].sum()
famr["rate"] = famr.separations / ((famr.opening + famr.closing) / 2)
K = 60  # credibility constant (person-years): illustrative
wgt = cell.avg_hc / (cell.avg_hc + K)
cell_rate = cell.separations / cell.avg_hc
base["attrition"] = (wgt * cell_rate + (1 - wgt) * cell.index.get_level_values(0).map(famr.rate).values).reindex(idx)
base["net_transfer"] = ((cell.transfers_in - cell.transfers_out) / 2).reindex(idx).fillna(0)   # per year
# demonstrated recruitment capacity: best annual external (non-graduate) hires FY2023-FY2026
mv["fy"] = "FY" + (mv.event_date.dt.year + (mv.event_date.dt.month >= 7)).astype(str)
ext_h = mv[(mv.event_type == "HIRE") & (mv.source == "External")].groupby(["fy", "job_family", "location"]).size().unstack("fy").fillna(0)
base["capacity"] = ext_h.max(axis=1).reindex(idx).fillna(0)
grads = mv[(mv.event_type == "HIRE") & (mv.source == "Graduate program")]
gshare = grads.groupby("location").size() / len(grads)
base["grad_share"] = [gshare.get(l, 0) if f == "Registered Nurse" else 0 for f, l in idx]
GRADS_PER_YEAR = round(len(grads) / 4)
# EN -> RN conversion rate (role changes out of EN / average EN headcount)
en = flows[flows.job_family == "Enrolled Nurse"]
EN_CONV = float(en.role_change_out.sum() / ((en.opening + en.closing) / 2).sum())
base = base.fillna({"cost_per_fte": emp.annual_salary_fte.mean()})

# ------------------------------------------------------------------ external (real) evidence for assumptions
wa_adj = (proj_state.loc["WA", "emp_2035_000"] / proj_state.loc["WA", "emp_2025_000"]) ** .1 / \
         (proj_state.loc["Australia", "emp_2035_000"] / proj_state.loc["Australia", "emp_2025_000"]) ** .1
DEMAND_G = {f: float((1 + occ.loc[f, "jsa_proj_10y_cagr"]) * wa_adj - 1) for f in FAMS}   # JSA 10-yr CAGR x WA adj.
WAGE_G = ext["wpi_yoy_aus_hcsa_avg_last8q"] / 100          # ABS WPI HCSA, average YoY of last 8 quarters
ONCOST = 1.25                                              # illustrative (12% SG is real; other on-costs assumed)
AGENCY_PREMIUM = 1.65                                      # illustrative
COST_PER_HIRE = {"metro": 6000, "regional": 14000}         # illustrative (advertising, agency fees, relocation)
HOURS_PER_FTE = 76 * 26
tight_ratio = flows[flows.fy == "FY2023"].separations.sum() / ((flows[flows.fy == "FY2023"].opening + flows[flows.fy == "FY2023"].closing) / 2).sum() / \
    (flows[flows.fy == "FY2026"].separations.sum() / ((flows[flows.fy == "FY2026"].opening + flows[flows.fy == "FY2026"].closing) / 2).sum())
osl_fill = {r["group"]: r["value"] for r in ext["osl_key_findings_2025_26"] if r["figure"].startswith("Figure 4")}
FILL_RATIO = osl_fill["Shortage"] / osl_fill["No shortage"]   # real: JSA OSL fill rates 2025-26

SCENARIOS = {
    "A Baseline": dict(demand_add={}, attr_mult=1.0, cap_mult={}, grads_mult=1.0, conv=EN_CONV, wage_g=WAGE_G,
                       premium=AGENCY_PREMIUM),
    "B Growth": dict(demand_add={f: (.02 if f in CLINICAL else .005) for f in FAMS}, attr_mult=1.0, cap_mult={},
                     grads_mult=1.0, conv=EN_CONV, wage_g=WAGE_G, premium=AGENCY_PREMIUM),
    "C Constraint": dict(demand_add={}, attr_mult=round(float(tight_ratio), 3),
                         cap_mult={f: round(float(FILL_RATIO), 3) for f in FAMS if occ.loc[f, "osl_share_in_shortage"] >= .5},
                         grads_mult=.75, conv=EN_CONV, wage_g=WAGE_G + .01, premium=AGENCY_PREMIUM),
}
INTERVENTIONS = {
    "M1 Retention programme (clinical attrition -15%)": dict(attr_family_mult={f: .85 for f in ["Registered Nurse", "Care Worker", "Allied Health", "Enrolled Nurse", "Midwife"]},
                                                         cost_fixed=1500 * 1300),
    "M2 Regional recruitment uplift (+30% capacity)": dict(cap_loc_mult={l: 1.3 for l in REGIONAL}, cost_fixed=2 * 130000),
    "M3 Grow-your-own (EN->RN 2x, +12 graduates)": dict(conv_mult=2.0, grads_add=12, cost_fixed=12 * 25000 + 15000 * 12),
    "M4 Agency panel (premium 1.65 -> 1.45)": dict(premium=1.45, cost_fixed=60000),
}


def run(scn, inputs=base, extra=None, years=PLAN_YEARS):
    """Run the stock-and-flow model; returns a cell x year DataFrame."""
    p = copy.deepcopy(SCENARIOS[scn]) if isinstance(scn, str) else copy.deepcopy(scn)
    extra = extra or {}
    x = inputs.copy()
    hc, dem = x.hc0.copy(), x.demand0.copy()
    out = []
    for t, yr in enumerate(years, start=1):
        fam = x.index.get_level_values(0)
        loc = x.index.get_level_values(1)
        gdem = np.array([DEMAND_G[f] + p["demand_add"].get(f, 0) + extra.get("demand_shift", 0) for f in fam])
        dem_new = dem * (1 + gdem)
        a = x.attrition * p["attr_mult"] * extra.get("attr_mult", 1) * \
            np.array([extra.get("attr_family_mult", {}).get(f, 1) for f in fam])
        seps = hc * a
        conv = p["conv"] * extra.get("conv_mult", 1)
        en_hc = pd.Series(np.where(fam == "Enrolled Nurse", hc, 0), index=x.index)
        conv_out = en_hc * conv
        conv_in = pd.Series(0.0, index=x.index)
        for l in x.index.get_level_values(1).unique():
            conv_in.loc[("Registered Nurse", l)] = conv_out.loc[("Enrolled Nurse", l)]
        grads = x.grad_share * (GRADS_PER_YEAR * p["grads_mult"] + extra.get("grads_add", 0))
        hc_pre = hc - seps - conv_out + conv_in + x.net_transfer + grads
        fph = x.fte_per_head * extra.get("fph_mult", 1)
        req = ((dem_new - hc_pre * fph) / fph).clip(lower=0)
        cap = x.capacity * np.array([p["cap_mult"].get(f, 1) for f in fam]) * extra.get("cap_mult", 1) * \
            np.array([extra.get("cap_loc_mult", {}).get(l, 1) for l in loc])
        hires = np.minimum(req, cap)
        hc_end = hc_pre + hires
        sup = hc_end * fph
        gap = dem_new - sup
        wage = (1 + p["wage_g"] + extra.get("wage_shift", 0)) ** t
        avg_fte = (hc * fph + sup) / 2
        emp_cost = avg_fte * x.cost_per_fte * wage * ONCOST
        cov = np.array([cover.get(f, 0.4) for f in fam])
        prem = extra.get("premium", p["premium"])
        ag_fte = gap.clip(lower=0) * cov
        ag_cost = ag_fte * HOURS_PER_FTE * (x.cost_per_fte * wage / HOURS_PER_FTE) * prem
        cph = x.cost_per_hire if "cost_per_hire" in x else \
            np.where(np.isin(loc, REGIONAL), COST_PER_HIRE["regional"], COST_PER_HIRE["metro"])
        rec_cost = hires * cph
        out.append(pd.DataFrame(dict(year=yr, demand_fte=dem_new, hc_start=hc, separations=seps, conv_in=conv_in,
                                     conv_out=conv_out, net_transfer=x.net_transfer, grads=grads, required_hires=req,
                                     capacity=cap, hires=hires, hc_end=hc_end, supply_fte=sup, gap_fte=gap,
                                     agency_fte=ag_fte, unfilled_fte=gap.clip(lower=0) - ag_fte,
                                     employee_cost=emp_cost, agency_cost=ag_cost, recruitment_cost=rec_cost),
                                index=x.index))
        hc, dem = hc_end, dem_new
    r = pd.concat(out).reset_index()
    r["total_cost"] = r.employee_cost + r.agency_cost + r.recruitment_cost
    return r


def family_inputs(cells=base):
    """Collapse cell inputs to job-family level (used by the Excel model and its validation)."""
    c = cells.copy()
    c["regional"] = np.isin(c.index.get_level_values(1), REGIONAL)
    c["cph"] = np.where(c.regional, COST_PER_HIRE["regional"], COST_PER_HIRE["metro"])
    f = pd.DataFrame({
        "hc0": c.hc0.groupby(level=0).sum(),
        "fte0": c.fte0.groupby(level=0).sum(),
        "demand0": c.demand0.groupby(level=0).sum(),
        "attrition": (c.attrition * c.hc0).groupby(level=0).sum() / c.hc0.groupby(level=0).sum(),
        "net_transfer": c.net_transfer.groupby(level=0).sum(),
        "capacity": c.capacity.groupby(level=0).sum(),
        "grad_share": c.grad_share.groupby(level=0).sum(),
        "cost_per_fte": (c.cost_per_fte * c.fte0).groupby(level=0).sum() / c.fte0.groupby(level=0).sum(),
        "cost_per_hire": (c.cph * c.capacity).groupby(level=0).sum() / c.capacity.groupby(level=0).sum(),
    }).reindex(FAMS)
    f["fte_per_head"] = f.fte0 / f.hc0
    f.index = pd.MultiIndex.from_arrays([f.index, ["All"] * len(f)], names=["job_family", "location"])
    return f


def summarise(r, by=("year",)):
    s = r.groupby(list(by))[["demand_fte", "supply_fte", "gap_fte", "required_hires", "capacity", "hires", "separations",
                             "grads", "conv_in", "agency_fte", "unfilled_fte", "employee_cost", "agency_cost",
                             "recruitment_cost", "total_cost", "hc_end"]].sum()
    s["shortage_fte"] = r.assign(sh=r.gap_fte.clip(lower=0)).groupby(list(by)).sh.sum()
    s["gap_pct"] = s.gap_fte / s.demand_fte
    s["unmet_hiring"] = s.required_hires - s.hires
    s["capacity_utilisation"] = s.required_hires / s.capacity
    return s


if __name__ == "__main__":
    # -------------------------------------------------------------- scenarios
    results, allcells = {}, []
    for s in SCENARIOS:
        r = run(s)
        allcells.append(r.assign(scenario=s))
        results[s] = summarise(r)
    cells = pd.concat(allcells)
    cells.round(3).to_csv(TABLES / "model_cells_all_scenarios.csv", index=False)
    comp = pd.concat({k: v for k, v in results.items()}, names=["scenario"]).round(3)
    comp.to_csv(TABLES / "model_scenario_summary.csv")
    fam_view = cells.groupby(["scenario", "year", "job_family"])[["demand_fte", "supply_fte", "gap_fte", "required_hires", "hires", "capacity"]].sum()
    fam_view["shortage_fte"] = cells.assign(sh=cells.gap_fte.clip(lower=0)).groupby(["scenario", "year", "job_family"]).sh.sum()
    fam_view.round(2).to_csv(TABLES / "model_family_summary.csv")
    loc_view = cells.groupby(["scenario", "year", "location"])[["demand_fte", "supply_fte", "gap_fte", "required_hires", "hires", "capacity"]].sum()
    loc_view["shortage_fte"] = cells.assign(sh=cells.gap_fte.clip(lower=0)).groupby(["scenario", "year", "location"]).sh.sum()
    loc_view.round(2).to_csv(TABLES / "model_location_summary.csv")

    # validation checks on the model
    checks = []
    for s, r in cells.groupby("scenario"):
        ident = (r.hc_start + r.hires + r.grads + r.conv_in + r.net_transfer - r.separations - r.conv_out - r.hc_end).abs().max()
        checks.append(dict(scenario=s, check="stock-flow identity max |error| (heads)", value=round(float(ident), 9)))
        checks.append(dict(scenario=s, check="hires <= capacity (all cells)", value=bool((r.hires <= r.capacity + 1e-9).all())))
        checks.append(dict(scenario=s, check="hires <= required (all cells)", value=bool((r.hires <= r.required_hires + 1e-9).all())))
        checks.append(dict(scenario=s, check="no negative headcount", value=bool((r.hc_end >= 0).all())))
        checks.append(dict(scenario=s, check="EN->RN conversions net to zero", value=round(float(r.conv_in.sum() - r.conv_out.sum()), 9)))
    fy27 = cells[(cells.scenario == "A Baseline") & (cells.year == "FY2027")]
    checks.append(dict(scenario="A Baseline", check="FY2027 modelled demand vs Finance FY2027 budget (%)",
                       value=round(float(fy27.demand_fte.sum() / base.budget_fy2027.sum() - 1) * 100, 2)))
    pd.DataFrame(checks).to_csv(TABLES / "model_validation_checks.csv", index=False)

    # -------------------------------------------------------------- interventions (tested on Constraint)
    ref = summarise(run("C Constraint"))
    iv_rows = []
    combo = {}
    for name, ex in INTERVENTIONS.items():
        r = summarise(run("C Constraint", extra=ex))
        cost = ex["cost_fixed"] * 3
        d_short = ref.shortage_fte.sum() - r.shortage_fte.sum()
        d_cost = (r.total_cost.sum() + cost) - ref.total_cost.sum()
        iv_rows.append(dict(intervention=name, shortage_fte_FY2029=r.shortage_fte.iloc[-1], shortage_reduction_fte_years=d_short,
                            agency_cost_3y=r.agency_cost.sum(), programme_cost_3y=cost, net_cost_change_3y=d_cost,
                            unfilled_fte_FY2029=r.unfilled_fte.iloc[-1]))
        for k, v in ex.items():
            if k == "cost_fixed":
                combo[k] = combo.get(k, 0) + v
            elif isinstance(v, dict):
                combo.setdefault(k, {}).update(v)
            else:
                combo[k] = v
    r = summarise(run("C Constraint", extra=combo))
    cost = combo["cost_fixed"] * 3
    iv_rows.append(dict(intervention="All four combined", shortage_fte_FY2029=r.shortage_fte.iloc[-1],
                        shortage_reduction_fte_years=ref.shortage_fte.sum() - r.shortage_fte.sum(),
                        agency_cost_3y=r.agency_cost.sum(), programme_cost_3y=cost,
                        net_cost_change_3y=(r.total_cost.sum() + cost) - ref.total_cost.sum(),
                        unfilled_fte_FY2029=r.unfilled_fte.iloc[-1]))
    iv = pd.DataFrame(iv_rows)
    iv.insert(1, "reference_shortage_FY2029", ref.shortage_fte.iloc[-1])
    iv.round(1).to_csv(TABLES / "model_interventions.csv", index=False)
    combo_cells = run("C Constraint", extra=combo).assign(scenario="C Constraint + interventions")
    combo_cells.round(3).to_csv(TABLES / "model_cells_constraint_with_interventions.csv", index=False)

    # -------------------------------------------------------------- sensitivity (tornado on Baseline FY2029 shortage)
    def outcome(extra=None, scn="A Baseline", premium=None):
        s = SCENARIOS[scn].copy()
        if premium:
            s["premium"] = premium
        r = summarise(run(s, extra=extra))
        return r.shortage_fte.iloc[-1], r.total_cost.sum()

    b_short, b_cost = outcome()
    SENS = [("Attrition rate x0.8 / x1.2", {"attr_mult": .8}, {"attr_mult": 1.2}),
            ("Demand growth -1pp / +1pp", {"demand_shift": -.01}, {"demand_shift": .01}),
            ("Recruitment capacity x0.8 / x1.2", {"cap_mult": .8}, {"cap_mult": 1.2}),
            ("EN->RN conversion x0 / x2", {"conv_mult": 0}, {"conv_mult": 2}),
            ("FTE per head x0.95 / x1.05", {"fph_mult": .95}, {"fph_mult": 1.05}),
            ("Wage growth -1pp / +1pp", {"wage_shift": -.01}, {"wage_shift": .01}),
            ("Agency premium 1.3 / 2.0", {"premium": 1.3}, {"premium": 2.0})]
    tor = []
    for name, lo, hi in SENS:
        ls, lc = outcome(lo)
        hs, hc_ = outcome(hi)
        tor.append(dict(assumption=name, shortage_low=ls, shortage_high=hs, cost_low=lc, cost_high=hc_,
                        shortage_swing=abs(hs - ls), cost_swing=abs(hc_ - lc)))
    tor = pd.DataFrame(tor).sort_values("shortage_swing", ascending=False)
    tor["base_shortage"], tor["base_cost"] = b_short, b_cost
    tor.round(2).to_csv(TABLES / "model_sensitivity_tornado.csv", index=False)

    # -------------------------------------------------------------- Monte Carlo (Baseline structure, uncertain inputs)
    mc = []
    for i in range(2000):
        ex = {"attr_mult": rng.triangular(.85, 1.0, 1.25), "demand_shift": rng.normal(0, .0075),
              "cap_mult": rng.triangular(.7, 1.0, 1.15), "conv_mult": rng.uniform(.5, 1.5)}
        r = summarise(run("A Baseline", extra=ex))
        mc.append(dict(draw=i, **ex, shortage_FY2029=r.shortage_fte.iloc[-1], gap_FY2029=r.gap_fte.iloc[-1],
                       agency_cost_3y=r.agency_cost.sum(), total_cost_3y=r.total_cost.sum()))
    mc = pd.DataFrame(mc)
    mc.to_csv(TABLES / "model_monte_carlo.csv", index=False)
    mcs = mc[["shortage_FY2029", "gap_FY2029", "agency_cost_3y", "total_cost_3y"]].quantile([.1, .5, .9]).T
    mcs.columns = ["P10", "P50", "P90"]
    mcs.round(1).to_csv(TABLES / "model_monte_carlo_summary.csv")

    # -------------------------------------------------------------- backtest of the model on synthetic history
    # Start: rebuilt stock at 30 Jun 2024; rates from FY2023-FY2024; demand = actual FY2025/FY2026 establishment.
    fl24 = flows[flows.fy.isin(["FY2023", "FY2024"])]
    b = pd.DataFrame(index=idx)
    b["hc0"] = flows[flows.fy == "FY2024"].set_index(["job_family", "location"]).closing.reindex(idx)
    b["fte_per_head"] = base.fte_per_head
    b["cost_per_fte"] = base.cost_per_fte
    b["demand0"] = est[est.fy == "FY2024"].set_index(["job_family", "location"]).budgeted_fte.reindex(idx)
    c24 = fl24.groupby(["job_family", "location"])[["separations", "opening", "closing", "transfers_in", "transfers_out"]].sum()
    avg24 = (c24.opening + c24.closing) / 2
    fr24 = fl24.groupby("job_family")[["separations", "opening", "closing"]].sum()
    fr24 = fr24.separations / ((fr24.opening + fr24.closing) / 2)
    w24 = avg24 / (avg24 + K)
    b["attrition"] = (w24 * c24.separations / avg24 + (1 - w24) * c24.index.get_level_values(0).map(fr24).values).reindex(idx)
    b["net_transfer"] = ((c24.transfers_in - c24.transfers_out) / 2).reindex(idx).fillna(0)
    b["capacity"] = ext_h[["FY2023", "FY2024"]].max(axis=1).reindex(idx).fillna(0)
    b["grad_share"] = base.grad_share
    actual_dem = est.pivot_table(index=["job_family", "location"], columns="fy", values="budgeted_fte").reindex(idx)
    saved = dict(DEMAND_G)
    bt_rows = []
    hc_model = b.hc0.copy()
    bb = b.copy()
    for yr in ["FY2025", "FY2026"]:
        growth = (actual_dem[yr] / bb.demand0 - 1)
        cell_g = growth.groupby(level=0).mean()
        DEMAND_G.update(cell_g.to_dict())
        r = run({"demand_add": {}, "attr_mult": 1, "cap_mult": {}, "grads_mult": 1, "conv": EN_CONV, "wage_g": WAGE_G,
                 "premium": AGENCY_PREMIUM}, inputs=bb, years=[yr])
        r = r.set_index(["job_family", "location"])
        bb = bb.assign(hc0=r.hc_end, demand0=actual_dem[yr])
        act = flows[flows.fy == yr].set_index(["job_family", "location"]).closing.reindex(idx)
        for f in FAMS:
            bt_rows.append(dict(year=yr, job_family=f, actual_hc=act.loc[f].sum(), model_hc=r.hc_end.loc[f].sum(),
                                naive_hc=b.hc0.loc[f].sum()))
    DEMAND_G.clear()
    DEMAND_G.update(saved)
    mbt = pd.DataFrame(bt_rows)
    mbt["model_ape"] = (mbt.model_hc / mbt.actual_hc - 1).abs()
    mbt["naive_ape"] = (mbt.naive_hc / mbt.actual_hc - 1).abs()
    mbt.round(4).to_csv(TABLES / "model_backtest_synthetic.csv", index=False)
    org = mbt.groupby("year")[["actual_hc", "model_hc", "naive_hc"]].sum()
    org["model_ape"] = (org.model_hc / org.actual_hc - 1).abs()
    org["naive_ape"] = (org.naive_hc / org.actual_hc - 1).abs()
    org.round(4).to_csv(TABLES / "model_backtest_synthetic_org.csv")

    # -------------------------------------------------------------- assumptions register
    A = [
        ("Demand growth (baseline)", "JSA Employment Projections 2025-35 10-yr CAGR by occupation x WA/AUS adjustment",
         "REAL", "; ".join(f"{f}: {v:.2%}" for f, v in DEMAND_G.items())),
        ("WA adjustment factor", "JSA projections Table 4 (WA vs AUS 10-yr growth)", "REAL", f"{wa_adj:.4f}"),
        ("Demand uplift (Growth scenario)", "Service expansion; bounded by ABS HCSA filled-jobs 5-yr CAGR "
         f"{ext['aus_hcsa_filled_jobs_5y_cagr']:.1%}", "ILLUSTRATIVE", "+2.0pp clinical, +0.5pp non-clinical"),
        ("Attrition rate", "KHS FY2025-26 cell rates, credibility-weighted (K=60) to family rate", "SYNTHETIC (measured)",
         f"org avg {float((base.attrition * base.hc0).sum() / base.hc0.sum()):.1%}"),
        ("Attrition multiplier (Constraint)", "KHS FY2023 (tight market) / FY2026 turnover", "SYNTHETIC (measured)", f"{tight_ratio:.3f}"),
        ("Recruitment capacity", "Best annual external hires FY2023-26 per cell (demonstrated throughput)", "SYNTHETIC (measured)",
         f"{base.capacity.sum():.0f} hires/yr"),
        ("Capacity multiplier (Constraint, shortage occupations)", "JSA OSL 2026 fill rate shortage/no-shortage "
         f"{osl_fill['Shortage']:.0%}/{osl_fill['No shortage']:.0%}", "REAL", f"{FILL_RATIO:.3f}"),
        ("Graduate RN intake", "KHS average FY2023-26", "SYNTHETIC (measured)", f"{GRADS_PER_YEAR}/yr; Constraint x0.75 (illustrative)"),
        ("EN->RN conversion", "KHS role changes / EN headcount", "SYNTHETIC (measured)", f"{EN_CONV:.2%}/yr"),
        ("Wage growth", "ABS WPI HCSA YoY, average of last 8 quarters", "REAL", f"{WAGE_G:.2%}/yr; Constraint +1pp (illustrative)"),
        ("On-cost factor", "12% super guarantee (legislated) + payroll tax/workers comp/leave (assumed)", "ILLUSTRATIVE", f"{ONCOST}"),
        ("Agency premium", "Assumed agency cost per hour vs employee cost", "ILLUSTRATIVE", f"{AGENCY_PREMIUM}"),
        ("Agency cover of shortage", "KHS FY2026 agency FTE / vacant FTE by family", "SYNTHETIC (measured)",
         "; ".join(f"{k}: {v:.2f}" for k, v in cover.items())),
        ("Cost per hire", "Assumed", "ILLUSTRATIVE", f"metro ${COST_PER_HIRE['metro']:,}, regional ${COST_PER_HIRE['regional']:,}"),
        ("Productivity", "No productivity change assumed (tested via FTE-per-head sensitivity)", "ILLUSTRATIVE", "0%"),
        ("Intervention effects and costs", "Assumed programme effects for option testing", "ILLUSTRATIVE",
         "; ".join(f"{k}: ${v['cost_fixed']:,}/yr" for k, v in INTERVENTIONS.items())),
    ]
    pd.DataFrame(A, columns=["assumption", "evidence", "provenance", "value"]).to_csv(TABLES / "model_assumptions.csv", index=False)
    base.round(4).to_csv(TABLES / "model_inputs_cells.csv")
    save_json({"DEMAND_G": DEMAND_G, "WAGE_G": WAGE_G, "EN_CONV": EN_CONV, "GRADS_PER_YEAR": GRADS_PER_YEAR,
               "ONCOST": ONCOST, "AGENCY_PREMIUM": AGENCY_PREMIUM, "COST_PER_HIRE": COST_PER_HIRE,
               "SCENARIOS": SCENARIOS, "FILL_RATIO": FILL_RATIO, "tight_ratio": tight_ratio,
               "agency_cover": cover.to_dict()}, TABLES / "model_parameters.json")

    print(comp[["demand_fte", "supply_fte", "gap_fte", "shortage_fte", "gap_pct", "required_hires", "hires", "capacity",
                "capacity_utilisation", "agency_cost", "total_cost"]].to_string())
    print(pd.DataFrame(checks).to_string())
    print(iv.round(1).to_string())
    print(tor[["assumption", "shortage_low", "shortage_high", "shortage_swing", "cost_swing"]].round(1).to_string())
    print(mcs.round(1))
    print(org.round(4))
    print(fam_view.loc["A Baseline"].loc["FY2029"].round(1))
