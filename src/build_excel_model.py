"""Step 8 - Build the Excel scenario model (live formulas) and verify it against the Python engine.

The workbook replicates the stock-and-flow model at job-family level. A scenario selector on the
'Scenarios' sheet drives every formula. After writing, the workbook is recalculated with the
`formulas` package for each scenario and compared cell-by-cell with scenario_model.run().
"""
import json

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import scenario_model as sm
from common import ROOT, TABLES, PLAN_YEARS

OUT = ROOT / "outputs" / "excel" / "KHS_workforce_scenario_model.xlsx"
FAMS = sm.FAMS
fin = sm.family_inputs()
occ = sm.occ
ext = json.load(open(TABLES / "ext_summary.json"))

BLUE = Font(color="1F4E9E")             # inputs
BOLD = Font(bold=True)
HDR = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
REAL_FILL = PatternFill("solid", fgColor="E2EFDA")
SYN_FILL = PatternFill("solid", fgColor="FCE4D6")
ILL_FILL = PatternFill("solid", fgColor="EDEDED")
thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
PROV_FILL = {"REAL": REAL_FILL, "SYNTHETIC": SYN_FILL, "ILLUSTRATIVE": ILL_FILL}

wb = Workbook()

# ------------------------------------------------------------------ README
ws = wb.active
ws.title = "README"
lines = [
    ("Kestrel Health Services - 3-year workforce scenario model (FY2027-FY2029)", BOLD),
    ("FICTIONAL ORGANISATION. Internal workforce figures are SYNTHETIC; labour-market inputs are REAL public data.", Font(bold=True, color="C00000")),
    ("", None),
    ("How to use", BOLD),
    ("1. Choose a scenario in Scenarios!C3 (A Baseline / B Growth / C Constraint).", None),
    ("2. Edit yellow cells (inputs) on 'Scenarios' and 'Inputs'. Every other number is a formula.", None),
    ("3. Results: 'Model' (family x year detail) and 'Summary' (totals and checks).", None),
    ("", None),
    ("Stock-and-flow identity", BOLD),
    ("HC end = HC start + Hires + Graduates + EN->RN in + Net transfers - Separations - EN->RN out", None),
    ("Required hires = MAX(0, (Demand FTE - HC pre-hire x FTE per head) / FTE per head);  Hires = MIN(Required, Capacity)", None),
    ("Gap FTE = Demand FTE - Supply FTE (positive = shortage). Agency covers a measured share of the shortage.", None),
    ("", None),
    ("Provenance colours", BOLD),
    ("Green = real public data (ABS / JSA)", None),
    ("Orange = synthetic internal data (measured from the simulated HRIS/ATS/payroll)", None),
    ("Grey = illustrative assumption - replace with organisation evidence", None),
    ("", None),
    ("Validation: the Python engine (src/scenario_model.py, family_inputs) reproduces every Model cell; see 'Checks'.", None),
]
for i, (t, f) in enumerate(lines, start=1):
    c = ws.cell(row=i, column=1, value=t)
    if f:
        c.font = f
ws.cell(row=15, column=1).fill = REAL_FILL
ws.cell(row=16, column=1).fill = SYN_FILL
ws.cell(row=17, column=1).fill = ILL_FILL
ws.column_dimensions["A"].width = 120

# ------------------------------------------------------------------ Scenarios
sc = wb.create_sheet("Scenarios")
sc["A1"] = "Scenario parameters"
sc["A1"].font = BOLD
sc["B3"] = "Selected scenario:"
sc["B3"].font = BOLD
sc["C3"] = "A Baseline"
sc["C3"].fill = INPUT_FILL
sc["C3"].font = Font(bold=True, color="1F4E9E")
dv = DataValidation(type="list", formula1='"A Baseline,B Growth,C Constraint"', allow_blank=False)
sc.add_data_validation(dv)
dv.add("C3")
heads = ["Parameter", "A Baseline", "B Growth", "C Constraint", "ACTIVE", "Provenance", "Evidence"]
for j, h in enumerate(heads, start=1):
    c = sc.cell(row=5, column=j, value=h)
    c.fill, c.font = HDR, HDR_FONT
S = sm.SCENARIOS
cap_c = list(S["C Constraint"]["cap_mult"].values())[0] if S["C Constraint"]["cap_mult"] else 1
params = [
    ("Demand growth add-on: clinical (pp)", [0, .02, 0], "ILLUSTRATIVE", "Growth: service expansion, bounded by ABS HCSA filled jobs 5-yr CAGR"),
    ("Demand growth add-on: non-clinical (pp)", [0, .005, 0], "ILLUSTRATIVE", "Growth scenario only"),
    ("Attrition multiplier", [1, 1, S["C Constraint"]["attr_mult"]], "SYNTHETIC", "Constraint = KHS FY2023/FY2026 turnover ratio"),
    ("Capacity multiplier: OSL shortage occupations", [1, 1, cap_c], "REAL", "Constraint = JSA OSL 2026 fill rate shortage/no-shortage (57%/78%)"),
    ("Graduate intake multiplier", [1, 1, S["C Constraint"]["grads_mult"]], "ILLUSTRATIVE", "Constraint: fewer graduate placements"),
    ("Wage growth p.a.", [S[k]["wage_g"] for k in S], "REAL", "ABS WPI HCSA avg YoY last 8 quarters; Constraint +1pp (illustrative)"),
    ("Agency premium (x employee cost)", [S[k]["premium"] for k in S], "ILLUSTRATIVE", "Assumed"),
    ("EN->RN conversion rate p.a.", [S[k]["conv"] for k in S], "SYNTHETIC", "KHS role-change history"),
    ("Graduate RNs per year", [sm.GRADS_PER_YEAR] * 3, "SYNTHETIC", "KHS average FY2023-26"),
    ("On-cost factor", [sm.ONCOST] * 3, "ILLUSTRATIVE", "12% super guarantee (legislated) + other on-costs (assumed)"),
]
PROW = {}
for i, (name, vals, prov, evid) in enumerate(params, start=6):
    sc.cell(row=i, column=1, value=name)
    for j, v in enumerate(vals, start=2):
        c = sc.cell(row=i, column=j, value=float(v))
        c.fill, c.font = INPUT_FILL, BLUE
        c.number_format = "0.000"
    sc.cell(row=i, column=5, value=f"=INDEX(B{i}:D{i},MATCH($C$3,$B$5:$D$5,0))").font = BOLD
    sc.cell(row=i, column=5).number_format = "0.000"
    sc.cell(row=i, column=6, value=prov).fill = PROV_FILL[prov]
    sc.cell(row=i, column=7, value=evid)
    PROW[name] = f"Scenarios!$E${i}"
for col, w in zip("ABCDEFG", [44, 13, 13, 14, 12, 14, 70]):
    sc.column_dimensions[col].width = w
P = lambda k: PROW[k]

# ------------------------------------------------------------------ Inputs (family level)
inp = wb.create_sheet("Inputs")
cols = [("job_family", "Job family", None), ("hc0", "Headcount 30 Jun 2026", "SYNTHETIC"),
        ("fte_per_head", "FTE per head", "SYNTHETIC"), ("demand0", "Demand FTE FY2026 (establishment)", "SYNTHETIC"),
        ("base_g", "Base demand growth p.a.", "REAL"), ("clinical", "Clinical? (1/0)", None),
        ("attrition", "Attrition rate p.a.", "SYNTHETIC"), ("capacity", "Recruitment capacity (hires/yr)", "SYNTHETIC"),
        ("osl_flag", "OSL shortage occupation (1/0)", "REAL"), ("grad_share", "Graduate share", "SYNTHETIC"),
        ("net_transfer", "Net internal transfers p.a.", "SYNTHETIC"), ("cost_per_fte", "Base salary per FTE ($)", "SYNTHETIC"),
        ("cover", "Agency cover of shortage", "SYNTHETIC"), ("cost_per_hire", "Cost per hire ($)", "ILLUSTRATIVE")]
for j, (_, h, prov) in enumerate(cols, start=1):
    c = inp.cell(row=1, column=j, value=h)
    c.fill, c.font = HDR, HDR_FONT
    c.alignment = Alignment(wrap_text=True, vertical="top")
    if prov:
        inp.cell(row=2, column=j, value=prov).fill = PROV_FILL[prov]
inp.cell(row=2, column=1, value="Provenance ->")
ICOL = {k: get_column_letter(j) for j, (k, _, _) in enumerate(cols, start=1)}
IROW = {}
for i, f in enumerate(FAMS, start=3):
    r = fin.loc[(f, "All")]
    vals = dict(job_family=f, hc0=r.hc0, fte_per_head=r.fte_per_head, demand0=r.demand0, base_g=sm.DEMAND_G[f],
                clinical=int(f in sm.CLINICAL), attrition=r.attrition, capacity=r.capacity,
                osl_flag=int(f in S["C Constraint"]["cap_mult"]), grad_share=r.grad_share, net_transfer=r.net_transfer,
                cost_per_fte=r.cost_per_fte, cover=float(sm.cover.get(f, .4)), cost_per_hire=r.cost_per_hire)
    for j, (k, _, _) in enumerate(cols, start=1):
        v = vals[k]
        c = inp.cell(row=i, column=j, value=v if isinstance(v, str) else float(v))
        if k != "job_family":
            c.fill, c.font = INPUT_FILL, BLUE
            c.number_format = {"base_g": "0.00%", "attrition": "0.0%", "cover": "0.00", "cost_per_fte": "#,##0",
                               "cost_per_hire": "#,##0", "fte_per_head": "0.000"}.get(k, "0.0")
    IROW[f] = i
inp.row_dimensions[1].height = 45
for j in range(1, len(cols) + 1):
    inp.column_dimensions[get_column_letter(j)].width = 15 if j > 1 else 22
I = lambda k, f: f"Inputs!${ICOL[k]}${IROW[f]}"

# ------------------------------------------------------------------ Model (family x year, formulas)
m = wb.create_sheet("Model")
mcols = ["Year", "t", "Job family", "Demand growth", "Demand FTE", "HC start", "Attrition", "Separations",
         "EN->RN out", "EN->RN in", "Graduates", "Net transfers", "HC pre-hire", "FTE/head", "Required hires",
         "Capacity", "Hires", "HC end", "Supply FTE", "Gap FTE", "Shortage FTE", "Agency FTE", "Unfilled FTE",
         "Wage index", "Employee cost", "Agency cost", "Recruitment cost", "Total cost", "Identity check"]
for j, h in enumerate(mcols, start=1):
    c = m.cell(row=1, column=j, value=h)
    c.fill, c.font = HDR, HDR_FONT
    c.alignment = Alignment(wrap_text=True, vertical="top")
C = {h: get_column_letter(j) for j, h in enumerate(mcols, start=1)}
n = len(FAMS)
MROW = {}
row = 2
for t, yr in enumerate(PLAN_YEARS, start=1):
    for f in FAMS:
        r = row
        MROW[(yr, f)] = r
        prev = r - n
        en_r = MROW.get((yr, "Enrolled Nurse"))
        F = {}
        F["Year"] = yr
        F["t"] = t
        F["Job family"] = f
        F["Demand growth"] = f"={I('base_g', f)}+IF({I('clinical', f)}=1,{P('Demand growth add-on: clinical (pp)')},{P('Demand growth add-on: non-clinical (pp)')})"
        F["Demand FTE"] = f"={I('demand0', f) if t == 1 else C['Demand FTE'] + str(prev)}*(1+{C['Demand growth']}{r})"
        F["HC start"] = f"={I('hc0', f)}" if t == 1 else f"={C['HC end']}{prev}"
        F["Attrition"] = f"={I('attrition', f)}*{P('Attrition multiplier')}"
        F["Separations"] = f"={C['HC start']}{r}*{C['Attrition']}{r}"
        F["EN->RN out"] = f"={C['HC start']}{r}*{P('EN->RN conversion rate p.a.')}" if f == "Enrolled Nurse" else "=0"
        F["Graduates"] = f"={I('grad_share', f)}*{P('Graduate RNs per year')}*{P('Graduate intake multiplier')}"
        F["Net transfers"] = f"={I('net_transfer', f)}"
        F["HC pre-hire"] = (f"={C['HC start']}{r}-{C['Separations']}{r}-{C['EN->RN out']}{r}+{C['EN->RN in']}{r}"
                            f"+{C['Graduates']}{r}+{C['Net transfers']}{r}")
        F["FTE/head"] = f"={I('fte_per_head', f)}"
        F["Required hires"] = f"=MAX(0,({C['Demand FTE']}{r}-{C['HC pre-hire']}{r}*{C['FTE/head']}{r})/{C['FTE/head']}{r})"
        F["Capacity"] = f"={I('capacity', f)}*IF({I('osl_flag', f)}=1,{P('Capacity multiplier: OSL shortage occupations')},1)"
        F["Hires"] = f"=MIN({C['Required hires']}{r},{C['Capacity']}{r})"
        F["HC end"] = f"={C['HC pre-hire']}{r}+{C['Hires']}{r}"
        F["Supply FTE"] = f"={C['HC end']}{r}*{C['FTE/head']}{r}"
        F["Gap FTE"] = f"={C['Demand FTE']}{r}-{C['Supply FTE']}{r}"
        F["Shortage FTE"] = f"=MAX(0,{C['Gap FTE']}{r})"
        F["Agency FTE"] = f"={C['Shortage FTE']}{r}*{I('cover', f)}"
        F["Unfilled FTE"] = f"={C['Shortage FTE']}{r}-{C['Agency FTE']}{r}"
        F["Wage index"] = f"=(1+{P('Wage growth p.a.')})^{C['t']}{r}"
        F["Employee cost"] = (f"=(({C['HC start']}{r}*{C['FTE/head']}{r}+{C['Supply FTE']}{r})/2)*{I('cost_per_fte', f)}"
                              f"*{C['Wage index']}{r}*{P('On-cost factor')}")
        F["Agency cost"] = f"={C['Agency FTE']}{r}*{I('cost_per_fte', f)}*{C['Wage index']}{r}*{P('Agency premium (x employee cost)')}"
        F["Recruitment cost"] = f"={C['Hires']}{r}*{I('cost_per_hire', f)}"
        F["Total cost"] = f"={C['Employee cost']}{r}+{C['Agency cost']}{r}+{C['Recruitment cost']}{r}"
        F["Identity check"] = (f"={C['HC start']}{r}+{C['Hires']}{r}+{C['Graduates']}{r}+{C['EN->RN in']}{r}+{C['Net transfers']}{r}"
                               f"-{C['Separations']}{r}-{C['EN->RN out']}{r}-{C['HC end']}{r}")
        F["EN->RN in"] = "=0"
        for j, h in enumerate(mcols, start=1):
            c = m.cell(row=r, column=j, value=F[h])
            c.border = BOX
            c.number_format = {"Demand growth": "0.00%", "Attrition": "0.0%", "Wage index": "0.0000",
                               "Employee cost": "#,##0", "Agency cost": "#,##0", "Recruitment cost": "#,##0",
                               "Total cost": "#,##0", "Identity check": "0.000000"}.get(h, "#,##0.0")
        row += 1
    # EN->RN in for the RN row references this year's EN row
    rn, en = MROW[(yr, "Registered Nurse")], MROW[(yr, "Enrolled Nurse")]
    m[f"{C['EN->RN in']}{rn}"] = f"={C['EN->RN out']}{en}"
m.freeze_panes = "D2"
m.row_dimensions[1].height = 45
for j in range(1, len(mcols) + 1):
    m.column_dimensions[get_column_letter(j)].width = 12
m.column_dimensions["C"].width = 22
m.conditional_formatting.add(f"{C['Gap FTE']}2:{C['Gap FTE']}{row - 1}",
                             CellIsRule(operator="greaterThan", formula=["5"], fill=PatternFill("solid", fgColor="F8CBAD")))

# ------------------------------------------------------------------ Summary
su = wb.create_sheet("Summary")
su["A1"] = "Summary - selected scenario:"
su["A1"].font = BOLD
su["C1"] = "=Scenarios!C3"
su["C1"].font = Font(bold=True, color="C00000")
metrics = ["Demand FTE", "Supply FTE", "Gap FTE", "Shortage FTE", "Required hires", "Capacity", "Hires", "Separations",
           "HC end", "Agency FTE", "Unfilled FTE", "Employee cost", "Agency cost", "Recruitment cost", "Total cost"]
su.cell(row=3, column=1, value="Metric").fill = HDR
su.cell(row=3, column=1).font = HDR_FONT
for j, yr in enumerate(PLAN_YEARS, start=2):
    c = su.cell(row=3, column=j, value=yr)
    c.fill, c.font = HDR, HDR_FONT
SROW = {}
for i, k in enumerate(metrics, start=4):
    su.cell(row=i, column=1, value=k)
    SROW[k] = i
    for j, yr in enumerate(PLAN_YEARS, start=2):
        col = C[k]
        c = su.cell(row=i, column=j, value=f'=SUMIFS(Model!${col}:${col},Model!$A:$A,"{yr}")')
        c.number_format = "#,##0" if "cost" in k else "#,##0.0"
i = len(metrics) + 4
su.cell(row=i, column=1, value="Gap % of demand")
su.cell(row=i + 1, column=1, value="Capacity utilisation (required / capacity)")
for j, yr in enumerate(PLAN_YEARS, start=2):
    L = get_column_letter(j)
    su.cell(row=i, column=j, value=f"={L}{SROW['Gap FTE']}/{L}{SROW['Demand FTE']}").number_format = "0.0%"
    su.cell(row=i + 1, column=j, value=f"={L}{SROW['Required hires']}/{L}{SROW['Capacity']}").number_format = "0%"
su.cell(row=i + 3, column=1, value="3-year total cost").font = BOLD
su.cell(row=i + 3, column=2, value=f"=SUM(B{SROW['Total cost']}:D{SROW['Total cost']})").number_format = "#,##0"
su.cell(row=i + 4, column=1, value="Max |stock-flow identity error| (should be 0)").font = BOLD
su.cell(row=i + 4, column=2, value=f"=MAX(Model!{C['Identity check']}2:{C['Identity check']}{row - 1})-MIN(Model!{C['Identity check']}2:{C['Identity check']}{row - 1})")
su.column_dimensions["A"].width = 46
for L in "BCD":
    su.column_dimensions[L].width = 16

# ------------------------------------------------------------------ Sensitivity + Evidence (values from Python, labelled)
se = wb.create_sheet("Sensitivity")
se["A1"] = "Sensitivity (computed by src/scenario_model.py at job family x location level; values, not formulas)"
se["A1"].font = BOLD
tor = pd.read_csv(TABLES / "model_sensitivity_tornado.csv")
for j, h in enumerate(["Assumption", "FY2029 shortage FTE (low)", "FY2029 shortage FTE (high)", "Swing (FTE)",
                       "3-yr cost low ($)", "3-yr cost high ($)"], start=1):
    c = se.cell(row=3, column=j, value=h)
    c.fill, c.font = HDR, HDR_FONT
for i, r in enumerate(tor.itertuples(), start=4):
    for j, v in enumerate([r.assumption, r.shortage_low, r.shortage_high, r.shortage_swing, r.cost_low, r.cost_high], start=1):
        c = se.cell(row=i, column=j, value=v)
        c.number_format = "#,##0" if j >= 5 else "0.0"
mc = pd.read_csv(TABLES / "model_monte_carlo_summary.csv", index_col=0)
k = len(tor) + 6
se.cell(row=k, column=1, value="Monte Carlo (2,000 draws, Baseline structure)").font = BOLD
for j, h in enumerate(["Outcome", "P10", "P50", "P90"], start=1):
    c = se.cell(row=k + 1, column=j, value=h)
    c.fill, c.font = HDR, HDR_FONT
for i, (name, r) in enumerate(mc.iterrows(), start=k + 2):
    se.cell(row=i, column=1, value=name)
    for j, v in enumerate(r.values, start=2):
        se.cell(row=i, column=j, value=float(v)).number_format = "#,##0.0"
se.column_dimensions["A"].width = 40
for L in "BCDEF":
    se.column_dimensions[L].width = 18

ev = wb.create_sheet("Evidence")
ev["A1"] = "Real public data behind the assumptions (see docs/source_register.md for links)"
ev["A1"].font = BOLD
A = pd.read_csv(TABLES / "model_assumptions.csv")
for j, h in enumerate(A.columns, start=1):
    c = ev.cell(row=3, column=j, value=h)
    c.fill, c.font = HDR, HDR_FONT
for i, r in enumerate(A.itertuples(index=False), start=4):
    for j, v in enumerate(r, start=1):
        c = ev.cell(row=i, column=j, value=v)
        if j == 3:
            c.fill = PROV_FILL[str(v).split(" ")[0]]
for L, w in zip("ABCD", [40, 80, 22, 90]):
    ev.column_dimensions[L].width = w

# ------------------------------------------------------------------ Checks sheet (Python reference values)
ck = wb.create_sheet("Checks")
ck["A1"] = "Python engine reference values (family level) - Summary sheet should match for the selected scenario"
ck["A1"].font = BOLD
ref_rows = []
for s in sm.SCENARIOS:
    r = sm.summarise(sm.run(s, inputs=fin))
    for yr in PLAN_YEARS:
        ref_rows.append(dict(scenario=s, year=yr, **{k: float(r.loc[yr, k.lower().replace(" ", "_")]) if k.lower().replace(" ", "_") in r.columns else np.nan
                                                    for k in ["Demand FTE", "Supply FTE", "Gap FTE", "Hires", "Agency cost", "Total cost"]}))
ref = pd.DataFrame(ref_rows)
for j, h in enumerate(ref.columns, start=1):
    c = ck.cell(row=3, column=j, value=h)
    c.fill, c.font = HDR, HDR_FONT
for i, r in enumerate(ref.itertuples(index=False), start=4):
    for j, v in enumerate(r, start=1):
        ck.cell(row=i, column=j, value=v).number_format = "#,##0.00"
for L in "ABCDEFGH":
    ck.column_dimensions[L].width = 16
OUT.parent.mkdir(parents=True, exist_ok=True)
wb.save(OUT)
print("saved", OUT)

# ------------------------------------------------------------------ verify formulas by recalculation
import formulas  # noqa: E402

xl = formulas.ExcelModel().loads(str(OUT)).finish()
fname = OUT.name
results = []
for s in sm.SCENARIOS:
    sol = xl.calculate(inputs={f"'[{fname}]SCENARIOS'!C3": s})
    get = lambda ref_: float(np.asarray(sol[f"'[{fname}]{ref_}"].value).ravel()[0])
    r_py = sm.run(s, inputs=fin).set_index(["year", "job_family"])
    for yr in PLAN_YEARS:
        for f in FAMS:
            rr = MROW[(yr, f)]
            for col, pycol in [("Demand FTE", "demand_fte"), ("HC end", "hc_end"), ("Hires", "hires"), ("Gap FTE", "gap_fte"),
                               ("Agency cost", "agency_cost"), ("Total cost", "total_cost")]:
                xv = get(f"MODEL'!{C[col]}{rr}")
                pv = float(r_py.loc[(yr, f), pycol])
                results.append(dict(scenario=s, year=yr, job_family=f, metric=col, excel=xv, python=pv,
                                    abs_diff=abs(xv - pv), rel_diff=abs(xv - pv) / max(abs(pv), 1e-9)))
chk = pd.DataFrame(results)
chk["match"] = (chk.abs_diff <= 1e-4) | (chk.rel_diff <= 1e-9)   # near-zero values make relative error meaningless
chk.to_csv(TABLES / "excel_vs_python_check.csv", index=False)
print("cells compared:", len(chk), " all match:", bool(chk.match.all()), " max abs diff:", chk.abs_diff.max())
