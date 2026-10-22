#!/usr/bin/env bash
# Reproduce the whole project end to end (about 3-4 minutes; the download is ~80 MB).
# Usage: ./run_all.sh            (download + process)
#        ./run_all.sh --offline  (reuse files already in data/raw)
set -euo pipefail
cd "$(dirname "$0")/src"
PY="${PYTHON:-python3}"
if [[ "${1:-}" != "--offline" ]]; then
  "$PY" fetch_public_data.py                 # 1  real public data -> data/raw (+ manifest with SHA-256)
fi
"$PY" clean_public_data.py                   # 2  ABS SDMX -> tidy, validated
"$PY" parse_external_files.py                # 2b JSA / ABS xlsx / WA PSC -> tidy
"$PY" generate_synthetic_data.py             # 3  SYNTHETIC internal systems for the fictional organisation
"$PY" clean_internal_data.py                 # 4  clean + reconcile internal sources, score vs truth
"$PY" score_detection.py                     # 4b detection recall/precision per cleaning rule
"$PY" analyse_workforce.py                   # 5  metrics, external indicators, risk heatmap
"$PY" forecast_backtest.py                   # 6  backtest forecast methods on real series
"$PY" scenario_model.py                      # 7  3-year stock-and-flow scenarios, sensitivity, Monte Carlo
"$PY" -W ignore build_excel_model.py         # 8  Excel model with live formulas, verified vs Python
"$PY" run_sql.py                             # 9  SQL versions of the key transforms, cross-checked
"$PY" make_charts.py                         # 10 portfolio charts and dashboard wireframe
echo "Done. See outputs/ and docs/."
