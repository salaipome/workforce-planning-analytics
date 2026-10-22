"""Shared paths, reference mappings and data-quality logging helpers."""
import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
SYNTH = ROOT / "data" / "synthetic"
TABLES = ROOT / "outputs" / "tables"
CHARTS = ROOT / "outputs" / "charts"
LOGS = ROOT / "outputs" / "logs"
for p in (INTERIM, PROCESSED, SYNTH, TABLES, CHARTS, LOGS):
    p.mkdir(parents=True, exist_ok=True)

SNAPSHOT_DATE = pd.Timestamp("2026-06-30")       # synthetic HRIS snapshot (end FY2026)
HISTORY_START = pd.Timestamp("2022-07-01")       # start of synthetic movement history (FY2023)
PLAN_YEARS = ["FY2027", "FY2028", "FY2029"]

# Fictional organisation's job families -> ANZSCO 2022 codes used to join public data.
JOB_FAMILIES = {
    "Registered Nurse":        {"anzsco": "2544", "anzsco_title": "Registered Nurses"},
    "Midwife":                 {"anzsco": "2541", "anzsco_title": "Midwives"},
    "Enrolled Nurse":          {"anzsco": "4114", "anzsco_title": "Enrolled and Mothercraft Nurses"},
    "Medical Practitioner":    {"anzsco": "253",  "anzsco_title": "Medical Practitioners"},
    "Allied Health":           {"anzsco": "252",  "anzsco_title": "Health Therapy Professionals"},
    "Care Worker":             {"anzsco": "4233", "anzsco_title": "Nursing Support and Personal Care Workers"},
    "Administration":          {"anzsco": "5",    "anzsco_title": "Clerical and Administrative Workers"},
    "Support Services":        {"anzsco": "8",    "anzsco_title": "Labourers"},
}

# Fictional sites -> ABS Greater Capital City Statistical Area (GCCSA) and SA4 (ASGS 2021).
LOCATIONS = {
    "Perth North": {"gccsa": "Greater Perth", "sa4": "Perth - North West", "remote": "Major city"},
    "Perth South": {"gccsa": "Greater Perth", "sa4": "Perth - South East", "remote": "Major city"},
    "Bunbury":     {"gccsa": "Rest of WA",    "sa4": "Bunbury",             "remote": "Inner regional"},
    "Geraldton":   {"gccsa": "Rest of WA",    "sa4": "Western Australia - Outback (South)", "remote": "Outer regional"},
    "Kalgoorlie":  {"gccsa": "Rest of WA",    "sa4": "Western Australia - Outback (South)", "remote": "Remote"},
    "Broome":      {"gccsa": "Rest of WA",    "sa4": "Western Australia - Outback (North)", "remote": "Very remote"},
}


def fy_label(dates):
    """Australian financial year label (FY2026 = 1 Jul 2025 - 30 Jun 2026) for a datetime Series."""
    d = pd.to_datetime(pd.Series(dates))
    fy = (d.dt.year + (d.dt.month >= 7).astype(int)).astype("Int64")
    return ("FY" + fy.astype(str)).where(d.notna())


class QualityLog:
    """Collects data-quality metrics and row-level exceptions for one pipeline step."""

    def __init__(self, step):
        self.step = step
        self.metrics = []
        self.exceptions = []

    def metric(self, dataset, check, stage, value, note=""):
        self.metrics.append({"step": self.step, "dataset": dataset, "check": check,
                             "stage": stage, "value": value, "note": note})

    def exception(self, dataset, rule, record_key, detail, action):
        self.exceptions.append({"step": self.step, "dataset": dataset, "rule": rule,
                                "record_key": str(record_key), "detail": str(detail), "action": action})

    def save(self):
        pd.DataFrame(self.metrics).to_csv(LOGS / f"quality_metrics_{self.step}.csv", index=False)
        pd.DataFrame(self.exceptions, columns=["step", "dataset", "rule", "record_key", "detail", "action"]) \
            .to_csv(LOGS / f"exceptions_{self.step}.csv", index=False)


def save_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)
