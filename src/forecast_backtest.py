"""Step 6 - Compare forecast methods on REAL public series with rolling-origin backtests.

Question: which simple, explainable method should drive the 3-year demand-growth assumption?
Series (all real):
  hcsa_filled_jobs  ABS Labour Account, Health Care & Social Assistance filled jobs, AUS, SA, quarterly
  wa_employed       ABS Labour Force, WA employed persons, SA, monthly -> quarterly mean
  wa_rn_employed    ABS EQ08, WA Registered Nurses (2544), original, quarterly -> 4-quarter mean
Methods: naive, drift (full history), 5-year CAGR, linear trend (last 20 quarters), Holt damped trend.
Origins: every 4 quarters; horizons 4, 8, 12 quarters ahead. Errors: APE, signed % error, MASE.
"""
import itertools

import numpy as np
import pandas as pd

from common import PROCESSED, TABLES, save_json

la = pd.read_csv(PROCESSED / "labour_account_health.csv", parse_dates=["period_start"])
s1 = la[(la.industry_code == "Q") & (la.adjustment == "Seasonally Adjusted")].set_index("period_start")["Jobs; Filled jobs"].sort_index()
lf = pd.read_csv(PROCESSED / "lf_state_monthly.csv", parse_dates=["period_start"])
s2 = lf[lf.region == "Western Australia"].set_index("period_start")["Employed persons"].sort_index().resample("QS").mean()
eq = pd.read_csv(PROCESSED / "eq08_wa_health_occupations.csv", parse_dates=["month"], dtype={"anzsco": str})
s3 = eq[eq.anzsco == "2544"].set_index("month").employed_000.sort_index()
s3.index = s3.index.to_period("Q").to_timestamp()
s3 = s3.rolling(4).mean().dropna()
SERIES = {"hcsa_filled_jobs": s1.dropna(), "wa_employed": s2.dropna(), "wa_rn_employed_4q_avg": s3}


def holt_damped(y, h):
    """Holt's linear method with damped trend; parameters chosen by in-sample one-step SSE (grid search)."""
    best = None
    for a, b, phi in itertools.product([.2, .4, .6, .8, .95], [.05, .1, .2, .3], [.8, .9, .95, .98]):
        l, t, sse = y[0], y[1] - y[0], 0.0
        for v in y[1:]:
            f = l + phi * t
            sse += (v - f) ** 2
            l_new = a * v + (1 - a) * (l + phi * t)
            t = b * (l_new - l) + (1 - b) * phi * t
            l = l_new
        if best is None or sse < best[0]:
            best = (sse, l, t, phi)
    _, l, t, phi = best
    return np.array([l + sum(phi ** i for i in range(1, k + 1)) * t for k in range(1, h + 1)])


def forecast(y, h, method):
    y = np.asarray(y, float)
    k = np.arange(1, h + 1)
    if method == "naive":
        return np.repeat(y[-1], h)
    if method == "drift":
        return y[-1] + k * (y[-1] - y[0]) / (len(y) - 1)
    if method == "cagr_5y":
        g = (y[-1] / y[-21]) ** (1 / 20) - 1
        return y[-1] * (1 + g) ** k
    if method == "linear_20q":
        x = np.arange(20)
        b, a = np.polyfit(x, y[-20:], 1)
        return a + b * (19 + k)
    if method == "holt_damped":
        return holt_damped(y, h)
    raise ValueError(method)


METHODS = ["naive", "drift", "cagr_5y", "linear_20q", "holt_damped"]
H = [4, 8, 12]
recs = []
for name, s in SERIES.items():
    v = s.values
    idx = s.index
    scale = np.mean(np.abs(np.diff(v)))      # MASE scale: in-sample mean absolute 1-step naive error
    first = 28                                # need >= 7 years of history at the first origin
    for o in range(first, len(v) - max(H), 4):
        train = v[: o + 1]
        for m in METHODS:
            f = forecast(train, max(H), m)
            for h in H:
                actual = v[o + h]
                recs.append(dict(series=name, origin=idx[o], method=m, horizon_q=h, forecast=f[h - 1], actual=actual,
                                 ape=abs(f[h - 1] / actual - 1), pct_error=f[h - 1] / actual - 1,
                                 ase=abs(f[h - 1] - actual) / scale,
                                 covid_window=bool((idx[o] < pd.Timestamp("2021-07-01")) and (idx[o + h] >= pd.Timestamp("2020-01-01")))))
bt = pd.DataFrame(recs)
bt.to_csv(TABLES / "backtest_forecasts.csv", index=False)
summ = bt.groupby(["series", "method", "horizon_q"]).agg(origins=("ape", "size"), MAPE=("ape", "mean"),
                                                        bias=("pct_error", "mean"), MASE=("ase", "mean")).reset_index()
summ_nocovid = bt[~bt.covid_window].groupby(["series", "method", "horizon_q"]).agg(MAPE_ex_covid=("ape", "mean")).reset_index()
summ = summ.merge(summ_nocovid, on=["series", "method", "horizon_q"])
summ["rank_MAPE"] = summ.groupby(["series", "horizon_q"]).MAPE.rank()
summ.round(4).to_csv(TABLES / "backtest_summary.csv", index=False)
best = summ[summ.horizon_q == 12].sort_values(["series", "MAPE"]).groupby("series").head(2)
print(summ.pivot_table(index=["series", "method"], columns="horizon_q", values="MAPE").round(4).to_string())
print(best.round(4).to_string())

# Forward 3-year view (to mid-2029) from each method for the HCSA series, for context in the report
fwd = {m: forecast(SERIES["hcsa_filled_jobs"].values, 12, m)[-1] / SERIES["hcsa_filled_jobs"].values[-1] - 1 for m in METHODS}
save_json({"last_obs": str(SERIES["hcsa_filled_jobs"].index[-1].date()),
           "three_year_growth_by_method": {k: round(float(v), 4) for k, v in fwd.items()},
           "best_12q_by_series": best[["series", "method", "MAPE", "bias"]].round(4).to_dict("records")},
          TABLES / "backtest_forward_view.json")
print(fwd)
