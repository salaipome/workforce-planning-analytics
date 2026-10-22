"""Step 10 - Portfolio charts (static PNG) generated from the computed tables.

Every chart footer states its provenance: REAL public data, SYNTHETIC case-study data, or MODEL output.
Palette: validated reference categorical order (blue, orange, aqua, ...) and a single-hue blue ramp.
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from common import CHARTS, PROCESSED, TABLES, JOB_FAMILIES, LOCATIONS  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0"
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SCN = {"A Baseline": S1, "B Growth": S2, "C Constraint": S3}
BLUES = LinearSegmentedColormap.from_list("blues", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": .6, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.axisbelow": True, "legend.frameon": False})
REAL = "Source: REAL public data - "
SYN = "SYNTHETIC case-study data (fictional Kestrel Health Services) - not real-world results"


def save(fig, name, foot):
    import textwrap
    wrapped = "\n".join(textwrap.wrap(foot, int(fig.get_figwidth() * 17)))
    fig.text(.01, .01, wrapped, fontsize=7.5, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, .03 + .025 * wrapped.count("\n") + .01, 1, 1))
    fig.savefig(CHARTS / name, dpi=160)
    plt.close(fig)
    print("chart", name)


# 1 ---------------------------------------------------------------- WA labour market tightness (real)
vu = pd.read_csv(TABLES / "ext_wa_vacancy_unemployment_ratio.csv", parse_dates=["period_start"]).set_index("period_start")
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(vu.index, vu.v_u_ratio, color=S1, lw=2)
avg = vu.loc["2015":"2019", "v_u_ratio"].mean()
ax.axhline(avg, color=MUTED, lw=1)
ax.text(vu.index[2], avg + .03, f"2015-19 average {avg:.2f}", color=INK2, fontsize=8.5)
ax.annotate(f"{vu.v_u_ratio.iloc[-1]:.2f}  ({vu.index[-1]:%b %Y})", (vu.index[-1], vu.v_u_ratio.iloc[-1]),
            xytext=(-120, 25), textcoords="offset points", color=INK, fontsize=9, arrowprops=dict(arrowstyle="-", color=MUTED))
ax.set_title("WA labour market is still tighter than pre-COVID: job vacancies per unemployed person")
ax.set_ylabel("Vacancies / unemployed")
save(fig, "01_wa_vacancy_unemployment_ratio.png",
     REAL + "ABS Job Vacancies (WA, original, 4-quarter mean) / ABS Labour Force (WA unemployed, SA)")

# 2 ---------------------------------------------------------------- IVI indexed (real)
ivi = pd.read_csv(PROCESSED / "ivi_4digit_wa_aus.csv", parse_dates=["month"], dtype={"anzsco": str})
groups = {"Registered Nurses (2544)": ["2544"], "Medical Practitioners (253x)": [f"253{i}" for i in range(1, 10)],
          "Health Therapy (252x)": [f"252{i}" for i in range(1, 8)], "Carers & Aides (4231, 4233)": ["4231", "4233"]}
fig, ax = plt.subplots(figsize=(9, 4.4))
for (name, codes), col in zip(groups.items(), [S1, S2, S3, S4]):
    s = ivi[(ivi.state == "WA") & ivi.anzsco.isin(codes)].groupby("month").ads.sum()
    s = s / s["2019"].mean() * 100
    s = s["2017":]
    ax.plot(s.index, s, color=col, lw=2, label=name)
    ax.text(s.index[-1] + pd.Timedelta(days=20), s.iloc[-1], f"{s.iloc[-1]:.0f}", color=INK2, fontsize=8.5, va="center")
ax.axhline(100, color=MUTED, lw=1)
ax.set_title("WA online job ads for health occupations, indexed (2019 average = 100)")
ax.set_ylabel("Index")
ax.legend(loc="upper left", fontsize=8.5)
save(fig, "02_wa_ivi_health_occupations.png",
     REAL + "Jobs and Skills Australia Internet Vacancy Index, ANZSCO 4-digit, WA, 3-month average (to Sep 2026)")

# 3 ---------------------------------------------------------------- backtest (real)
bt = pd.read_csv(TABLES / "backtest_summary.csv")
names = {"hcsa_filled_jobs": "AUS Health Care & Social\nAssistance filled jobs", "wa_employed": "WA employed persons",
         "wa_rn_employed_4q_avg": "WA Registered Nurses\n(EQ08, 4-qtr mean)"}
fig, axes = plt.subplots(1, 3, figsize=(11, 4), sharey=False)
for ax, (key, title) in zip(axes, names.items()):
    d = bt[(bt.series == key) & (bt.horizon_q == 12)].sort_values("MAPE")
    cols = [S1 if i == 0 else "#b7d3f6" for i in range(len(d))]
    ax.barh(d.method, d.MAPE * 100, color=cols, height=.6)
    for y, v in enumerate(d.MAPE * 100):
        ax.text(v + .1, y, f"{v:.1f}%", va="center", fontsize=8.5, color=INK2)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("MAPE, 12 quarters ahead")
    ax.grid(axis="y", visible=False)
fig.suptitle("Rolling-origin backtest: forecast error of five methods (lower is better)", fontweight="bold")
save(fig, "03_backtest_mape.png", REAL + "ABS Labour Account, ABS Labour Force, ABS Labour Force Detailed EQ08; errors computed in src/forecast_backtest.py")

# 4 ---------------------------------------------------------------- turnover by family (synthetic) vs benchmark (real)
tf = pd.read_csv(TABLES / "int_turnover_family_fy.csv")
d = tf[tf.fy == "FY2026"].sort_values("turnover_rate")
ext = json.load(open(TABLES / "ext_summary.json"))
fig, ax = plt.subplots(figsize=(8.5, 4.2))
ax.barh(d.job_family, d.turnover_rate * 100, color=S1, height=.6)
for y, v in enumerate(d.turnover_rate * 100):
    ax.text(v + .3, y, f"{v:.1f}%", va="center", fontsize=8.5, color=INK2)
b = ext["abs_hcsa_outflow_proxy_feb2026"] * 100
ax.axvline(b, color=S2, lw=2)
ax.text(b + .3, -.9, f"ABS HCSA job-mobility outflow {b:.1f}% (real)", color=INK2, fontsize=8.5)
ax.set_title("FY2026 turnover by job family (separations / average headcount)")
ax.set_xlabel("%")
ax.grid(axis="y", visible=False)
save(fig, "04_turnover_by_family.png", SYN + "; benchmark line: ABS Job Mobility Feb 2026 (REAL)")

# 5 ---------------------------------------------------------------- stock & flow waterfall FY2026 (synthetic)
fl = pd.read_csv(TABLES / "int_turnover_org_fy.csv").set_index("fy").loc["FY2026"]
steps = [("Opening\n1 Jul 2025", fl.opening, "total"), ("Hires", fl.hires, "up"), ("Separations", -fl.separations, "down"),
         ("Closing\n30 Jun 2026", fl.closing, "total")]
fig, ax = plt.subplots(figsize=(7.5, 4.2))
run = 0
for i, (lab, v, kind) in enumerate(steps):
    if kind == "total":
        ax.bar(i, v, color="#86b6ef", width=.6)
        run = v
        ax.text(i, v + 15, f"{v:,.0f}", ha="center", fontsize=9)
    else:
        bottom = run if v > 0 else run + v
        ax.bar(i, abs(v), bottom=bottom, color=S1 if v > 0 else S2, width=.6)
        ax.text(i, run + max(v, 0) + 15, f"{v:+,.0f}", ha="center", fontsize=9)
        run += v
ax.set_xticks(range(len(steps)), [s[0] for s in steps])
ax.set_ylim(1500, fl.opening + fl.hires + 120)
ax.set_title("FY2026 headcount stock and flow")
ax.grid(axis="x", visible=False)
save(fig, "05_stock_flow_fy2026.png", SYN + " (axis starts at 1,500)")

# 6 ---------------------------------------------------------------- scenarios: shortage FTE + hiring (model)
sm = pd.read_csv(TABLES / "model_scenario_summary.csv")
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
for s, g in sm.groupby("scenario"):
    axes[0].plot(g.year, g.shortage_fte, marker="o", ms=7, lw=2, color=SCN[s], label=s)
    axes[0].text(2.08, g.shortage_fte.iloc[-1], f"{g.shortage_fte.iloc[-1]:.0f}", color=INK2, fontsize=9, va="center")
    axes[1].plot(g.year, g.required_hires, marker="o", ms=7, lw=2, color=SCN[s], label=s)
cap = sm[sm.scenario == "A Baseline"].capacity.iloc[0]
cap_c = sm[sm.scenario == "C Constraint"].capacity.iloc[0]
axes[1].axhline(cap, color=MUTED, lw=1)
axes[1].text(-.1, cap + 6, f"demonstrated capacity {cap:.0f}/yr", fontsize=8.5, color=INK2)
axes[1].axhline(cap_c, color=MUTED, lw=1)
axes[1].text(-.1, cap_c - 18, f"constrained capacity {cap_c:.0f}/yr", fontsize=8.5, color=INK2)
axes[0].set_title("Shortage FTE (demand above supply)")
axes[1].set_title("Hires required to close the gap")
axes[0].legend(fontsize=8.5)
for ax in axes:
    ax.grid(axis="x", visible=False)
save(fig, "06_scenario_shortage_and_hiring.png", "MODEL output on SYNTHETIC internal data + REAL external assumptions (src/scenario_model.py)")

# 7 ---------------------------------------------------------------- risk heatmap (mixed provenance)
rk = pd.read_csv(TABLES / "risk_heatmap_cells.csv")
mat = rk.pivot(index="job_family", columns="location", values="risk_score").reindex(index=list(JOB_FAMILIES), columns=list(LOCATIONS))
fig, ax = plt.subplots(figsize=(9, 5))
im = ax.imshow(mat.values, cmap=BLUES, vmin=0, vmax=100, aspect="auto")
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        v = mat.values[i, j]
        ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9, color="white" if v > 55 else INK)
ax.set_xticks(range(mat.shape[1]), mat.columns)
ax.set_yticks(range(mat.shape[0]), mat.index)
ax.grid(False)
cb = fig.colorbar(im, ax=ax, fraction=.03)
cb.set_label("Risk score (0-100)")
ax.set_title("Workforce risk by job family and location")
save(fig, "07_risk_heatmap.png", "Score = 60% SYNTHETIC internal metrics (vacancy, turnover, time-to-fill, age 55+) + 40% REAL "
     "occupation indicators (JSA OSL 2026, WA IVI per employed); weights illustrative")

# 8 ---------------------------------------------------------------- tornado (model)
tor = pd.read_csv(TABLES / "model_sensitivity_tornado.csv").sort_values("shortage_swing")
base = tor.base_shortage.iloc[0]
fig, ax = plt.subplots(figsize=(9, 4.2))
for y, r in enumerate(tor.itertuples()):
    lo, hi = sorted([r.shortage_low, r.shortage_high])
    ax.barh(y, hi - lo, left=lo, color=S1, height=.55)
    ax.text(hi + 1, y, f"{r.shortage_low:.0f} / {r.shortage_high:.0f}", va="center", fontsize=8.5, color=INK2)
ax.axvline(base, color=INK, lw=1)
ax.text(base + 1, -.75, f"Baseline {base:.0f} FTE", fontsize=8.5)
ax.set_yticks(range(len(tor)), tor.assumption)
ax.set_xlabel("FY2029 shortage FTE (low / high case)")
ax.set_title("Which assumptions move the FY2029 shortage most?")
ax.grid(axis="y", visible=False)
save(fig, "08_sensitivity_tornado.png", "MODEL output (Baseline scenario, one assumption varied at a time)")

# 9 ---------------------------------------------------------------- Monte Carlo (model)
mc = pd.read_csv(TABLES / "model_monte_carlo.csv")
q = mc.shortage_FY2029.quantile([.1, .5, .9])
fig, ax = plt.subplots(figsize=(8.5, 4))
ax.hist(mc.shortage_FY2029, bins=40, color=S1, edgecolor=SURFACE, linewidth=1)
for p, v in q.items():
    ax.axvline(v, color=INK, lw=1)
    ax.text(v, ax.get_ylim()[1] * .92, f" P{int(p * 100)} {v:.0f}", fontsize=8.5)
ax.set_xlabel("FY2029 shortage FTE")
ax.set_ylabel("Draws")
ax.set_title("Uncertainty in the FY2029 shortage (2,000 simulations)")
ax.grid(axis="x", visible=False)
save(fig, "09_monte_carlo_shortage.png", "MODEL output: attrition x tri(0.85,1,1.25), demand +/- N(0,0.75pp), capacity x tri(0.7,1,1.15), conversion x U(0.5,1.5)")

# 10 --------------------------------------------------------------- interventions (model)
iv = pd.read_csv(TABLES / "model_interventions.csv")
fig, ax = plt.subplots(figsize=(9.5, 4.2))
ref = iv.reference_shortage_FY2029.iloc[0]
d = iv.sort_values("shortage_fte_FY2029", ascending=False)
ax.barh(d.intervention, d.shortage_fte_FY2029, color=[S3 if "combined" in n else S1 for n in d.intervention], height=.55)
for y, v in enumerate(d.shortage_fte_FY2029):
    ax.text(v + 2, y, f"{v:.0f}", va="center", fontsize=8.5, color=INK2)
ax.axvline(ref, color=INK, lw=1)
ax.text(ref, -.75, f" Constraint, no action: {ref:.0f}", fontsize=8.5)
ax.set_xlabel("FY2029 shortage FTE under the Constraint scenario")
ax.set_title("Testing mitigation options against the Constraint scenario")
ax.grid(axis="y", visible=False)
save(fig, "10_interventions.png", "MODEL output; intervention effects and costs are ILLUSTRATIVE assumptions")

# 11 --------------------------------------------------------------- data quality before/after (synthetic)
dq = pd.read_csv(TABLES / "sql_dq_results.csv")
dq = dq[dq.rule.isin(["exact duplicate rows", "terminated but Active", "distinct location values",
                      "distinct job family values", "FTE missing or > 1.0", "hire_date not ISO"])]
fig, ax = plt.subplots(figsize=(9, 4))
y = np.arange(len(dq))
ax.barh(y - .17, dq.raw_value, height=.32, color=S2, label="Raw extract")
ax.barh(y + .17, dq.clean_value, height=.32, color=S1, label="After pipeline")
for i, (a, b) in enumerate(zip(dq.raw_value, dq.clean_value)):
    ax.text(a + 3, i - .17, f"{a:.0f}", va="center", fontsize=8, color=INK2)
    ax.text(b + 3, i + .17, f"{b:.0f}", va="center", fontsize=8, color=INK2)
ax.set_yticks(y, dq.rule)
ax.invert_yaxis()
ax.legend(loc="lower right")
ax.set_title("HRIS data-quality issues before and after cleaning")
ax.grid(axis="y", visible=False)
save(fig, "11_data_quality_before_after.png", SYN + "; counts computed by sql/02_quality_checks.sql")

# 12 --------------------------------------------------------------- Power BI wireframe (design, not a report)
fig, ax = plt.subplots(figsize=(13, 7.5))
ax.set_xlim(0, 100)
ax.set_ylim(0, 60)
ax.axis("off")


def box(x, y, w, h, title, body="", fill="#f3f2ee"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.8", fc=fill, ec="#c9c8c2", lw=1))
    ax.text(x + 1, y + h - 1.8, title, fontsize=9.5, weight="bold", va="top")
    if body:
        ax.text(x + 1, y + h - 4.3, body, fontsize=8, color=INK2, va="top")


ax.text(0, 59, "Page 1 - Executive overview  (WIREFRAME - design specification, not a built Power BI report)", fontsize=12, weight="bold")
box(0, 50, 100, 5.5, "Slicers:  Scenario  |  Financial year  |  Job family  |  Location / GCCSA  |  Employment type", fill="#e8f0fb")
kpis = ["Headcount", "FTE", "Vacancy rate", "Turnover (12m)", "Median time-to-fill", "Agency FTE", "FY2029 shortage FTE"]
for i, k in enumerate(kpis):
    box(i * 14.3, 41, 13.3, 7.5, k, "value | vs LY | target")
box(0, 21, 49, 18.5, "Demand vs supply FTE, FY2023-FY2029", "Line: demand FTE; area: supply FTE;\nshaded = forecast; scenario from slicer")
box(51, 21, 49, 18.5, "Risk heatmap: job family x location", "Matrix with conditional formatting on risk score;\ndrill-through to cell detail page")
box(0, 1, 32, 18, "Recruitment pipeline", "Open reqs by age band; fill rate;\nmedian / P90 time-to-fill by location")
box(34, 1, 32, 18, "Workforce movement", "Hires, separations, transfers by month;\nturnover vs ABS benchmark line")
box(68, 1, 32, 18, "Scenario & assumption controls", "What-if parameters: attrition x, demand +pp,\ncapacity x; tornado of key drivers")
save(fig, "12_dashboard_wireframe.png", "Wireframe for docs/dashboard_spec.md")
