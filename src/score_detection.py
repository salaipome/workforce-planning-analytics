"""Measure detection recall/precision of each cleaning rule against the injected-defect log (synthetic only)."""
import pandas as pd

from common import SYNTH, TABLES, LOGS

d = pd.read_csv(SYNTH / "_truth" / "defect_log.csv", dtype=str)
e = pd.read_csv(LOGS / "exceptions_internal.csv", dtype=str)
e = e[~e.action.str.startswith("mapped") | e.rule.str.startswith("R-H2") | e.rule.str.startswith("R-H3")]
RULES = {"exact_duplicate": "R-H1", "location_variant": "R-H2", "job_family_variant": "R-H3",
         "dob_placeholder": "R-H5", "terminated_but_active": "R-H6", "stale_prior_record_same_person": "R-H7",
         "fte_decimal_shift": "R-H8a", "missing_fte": "R-H8b", "missing_employment_type": "R-H9",
         "dates_swapped": "R-A1", "filled_without_date": "R-A2"}
rows = []
for kind, rule in RULES.items():
    inj = set(d[d.defect_type == kind].record_key)
    det = set(e[e.rule.str.startswith(rule + " ")].record_key)
    tp = len(inj & det)
    rows.append(dict(defect_type=kind, rule=rule, injected=len(inj), flagged=len(det), true_positives=tp,
                     recall=round(tp / len(inj), 3) if inj else None, precision=round(tp / len(det), 3) if det else None))
out = pd.DataFrame(rows)
out.to_csv(TABLES / "cleaning_detection_scores.csv", index=False)
print(out.to_string())
