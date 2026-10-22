"""Step 9 - Run the SQL scripts in sql/ on SQLite and cross-check them against the pandas pipeline.

Builds data/processed/workforce.db from the raw (synthetic) source extracts plus reference tables,
executes sql/01..05 in order, exports key result tables to outputs/tables/sql_*.csv and asserts that
SQL and Python agree on headcount, FTE, vacancy and turnover.
"""
import json
import sqlite3

import pandas as pd

from common import ROOT, SYNTH, PROCESSED, TABLES, JOB_FAMILIES, LOCATIONS

DB = PROCESSED / "workforce.db"
DB.unlink(missing_ok=True)
con = sqlite3.connect(DB)

# staging tables = raw extracts, loaded as text/numbers exactly as received
pd.read_csv(SYNTH / "hris_employee_snapshot.csv", dtype={"employee_id": str, "person_id": str}).to_sql("stg_hris_snapshot", con, index=False)
pd.read_csv(SYNTH / "payroll_fortnight.csv", dtype={"employee_id": str}).to_sql("stg_payroll", con, index=False)
pd.read_csv(SYNTH / "hris_movements.csv", dtype={"employee_id": str}).to_sql("stg_movements", con, index=False)
pd.read_csv(SYNTH / "ats_requisitions.csv", dtype={"filled_by": str}).to_sql("stg_requisitions", con, index=False)
pd.read_csv(SYNTH / "finance_establishment.csv").to_sql("stg_establishment", con, index=False)
pd.read_csv(SYNTH / "cost_centre_map.csv").to_sql("ref_cost_centre", con, index=False)

# reference / mapping tables (maintained with HR - the same synonyms the Python step uses)
loc_alias = {k.lower(): k for k in LOCATIONS}
pd.DataFrame({"alias": list(loc_alias), "location": list(loc_alias.values())}).to_sql("ref_location_alias", con, index=False)
fam_alias = {"rn": "Registered Nurse", "reg nurse": "Registered Nurse", "registered nurse - grad": "Registered Nurse",
             "en": "Enrolled Nurse", "ain": "Care Worker", "personal care assistant": "Care Worker",
             "doctor": "Medical Practitioner", "medical officer": "Medical Practitioner", "allied health prof": "Allied Health",
             "physiotherapist": "Allied Health", "admin": "Administration", "admin officer": "Administration",
             "support svcs": "Support Services", "orderly": "Support Services", "midwifery": "Midwife"}
fam_alias.update({k.lower(): k for k in JOB_FAMILIES})
pd.DataFrame({"alias": list(fam_alias), "job_family": list(fam_alias.values())}).to_sql("ref_job_family_alias", con, index=False)
pd.DataFrame([{"job_family": k, "anzsco": v["anzsco"]} for k, v in JOB_FAMILIES.items()]).to_sql("ref_job_family", con, index=False)
pd.DataFrame([{"location": k, "gccsa": v["gccsa"], "remoteness": v["remote"]} for k, v in LOCATIONS.items()]).to_sql("ref_location", con, index=False)

for f in sorted((ROOT / "sql").glob("*.sql")):
    con.executescript(f.read_text())
    print("ran", f.name)

q = lambda s: pd.read_sql(s, con)
exports = ["dq_results", "recon_establishment", "m_headcount_fte", "m_turnover_fy", "m_time_to_fill"]
for t in exports:
    q(f"SELECT * FROM {t}").to_csv(TABLES / f"sql_{t}.csv", index=False)
recon = q("SELECT recon_status, COUNT(*) AS n FROM recon_hris_payroll GROUP BY recon_status")
recon.to_csv(TABLES / "sql_recon_hris_payroll.csv", index=False)

# ---------------------------------------------------------------- cross-check against pandas outputs
py = json.load(open(TABLES / "int_summary.json"))
py_turn = pd.read_csv(TABLES / "int_turnover_org_fy.csv").set_index("fy")
sql_hc = q("SELECT headcount, fte FROM m_headcount_fte WHERE job_family='TOTAL'").iloc[0]
sql_turn = q("SELECT * FROM m_turnover_fy").set_index("fy")
sql_vac = q("SELECT SUM(vacant_fte) v, SUM(budgeted_fte) b FROM recon_establishment").iloc[0]
checks = [
    ("headcount", int(sql_hc.headcount), py["headcount"]),
    ("FTE", round(float(sql_hc.fte), 1), py["fte"]),
    ("vacancy rate", round(float(sql_vac.v / sql_vac.b), 4), py["vacancy_rate"]),
] + [(f"turnover {fy}", float(sql_turn.loc[fy, "turnover_rate"]), float(py_turn.loc[fy, "turnover_rate"])) for fy in sql_turn.index]
ck = pd.DataFrame(checks, columns=["metric", "sql", "python"])
ck["abs_diff"] = (ck.sql - ck.python).abs()
ck["match"] = ck.abs_diff <= ck.python.abs() * 0.002 + 1e-9
ck.to_csv(TABLES / "sql_vs_python_check.csv", index=False)
print(q("SELECT * FROM dq_results").to_string())
print(recon.to_string())
print(ck.to_string())
con.close()
