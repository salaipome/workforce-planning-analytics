"""Step 1 - Download the public (real) datasets used in the project.

Every file lands in data/raw/ untouched, and a manifest (data/raw/manifest.csv)
records the URL, retrieval time, HTTP status, byte size and SHA-256 so the run
can be audited and repeated.

ABS series come from the ABS Data API (SDMX REST, CSV output with labels):
https://data.api.abs.gov.au  -- documentation:
https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide

Usage:  python src/fetch_public_data.py            (all sources)
        python src/fetch_public_data.py --only abs
"""
import argparse
import csv
import datetime as dt
import hashlib
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ABS_API = "https://data.api.abs.gov.au/rest/data"
CSV_LABELS = "application/vnd.sdmx.data+csv;labels=both"

# (file name, dataflow, key, start period, description)
# Key order follows each dataflow's data structure definition (DSD).
ABS_QUERIES = [
    # LF: MEASURE.SEX.AGE.TSEST.REGION.FREQ  (M3 employed, M1 FT, M2 PT, M9 labour force,
    # M12 participation rate, M13 unemployment rate; 1599 all ages; 20 seasonally adjusted)
    ("abs_lf_state_monthly.csv", "ABS,LF,1.0.0",
     "M1+M2+M3+M9+M12+M13.3.1599.20.5+AUS.M", "2005-01",
     "Labour Force, Australia - WA and Australia, monthly, seasonally adjusted"),
    # JV: MEASURE.SECTOR.INDUSTRY.TSEST.REGION.FREQ - all series (small)
    ("abs_jv_quarterly.csv", "ABS,JV,1.0", "all", "2005-Q1",
     "Job Vacancies, Australia - by state, sector and (national) industry"),
    # AWE: earnings only (ESTIMATE_TYPE 1), persons
    ("abs_awe.csv", "ABS,AWE,1.0.0", "1+2+3.1.3.7.TOT+Q..5+AUS.", "2012",
     "Average Weekly Earnings - WA/AUS all industries; AUS Health Care & Social Assistance"),
    # WPI: INDEX THRPEB, all sectors, TOT + Q
    ("abs_wpi.csv", "ABS,WPI,1.2.0", "1+3.THRPEB.7+1+2.TOT+Q..5+AUS.Q", "2005-Q1",
     "Wage Price Index - total hourly rates of pay excluding bonuses"),
    # LABOUR_ACCT_Q: MEASURE.REGION.IND.TSEST.FREQ (national only), seasonally adjusted
    ("abs_labour_account_health.csv", "ABS,LABOUR_ACCT_Q,1.1",
     "M3+M4+M6+M9+M10+M11+M12+M13+M14+M28+M31+M38.AUS.TOTAL+Q.20.Q",
     "1994-Q3",
     "Labour Account Australia - filled jobs, vacancies, hours, labour cost: all industries and Health Care & Social Assistance (SA)"),
    # Subdivisions (Hospitals 84, Medical & other 85, Residential care 86, Social assistance 87) are
    # published in original terms only.
    ("abs_labour_account_health_subdiv.csv", "ABS,LABOUR_ACCT_Q,1.1",
     "M3+M4+M6+M9+M10+M11+M12+M28+M38.AUS.84XX+85XX+86XX+87XX.10.Q", "1994-Q3",
     "Labour Account Australia - Health Care & Social Assistance subdivisions (original)"),
    # ERP_Q: MEASURE.SEX.AGE.REGION.FREQ - all single ages for WA (to derive 65+ / 75+)
    ("abs_erp_wa_by_age.csv", "ABS,ERP_Q,1.0.0", "1.3..5.Q", "2011-Q3",
     "Estimated Resident Population - WA by single year of age, quarterly"),
    # Census 2021 G54: SEXP.INDP.AGEP.REGION.REGION_TYPE.STATE
    ("abs_census2021_g54_ind_age_wa.csv", "ABS,C21_G54_SA2,1.0.0",
     "...5+5GPER+5RWAU..5", None,
     "Census 2021 G54 Industry of employment by age by sex - WA, Greater Perth, Rest of WA"),
    # Census 2021 G56: INDP.OCCP.REGION.REGION_TYPE.STATE
    ("abs_census2021_g56_ind_occ_wa.csv", "ABS,C21_G56_SA2,1.0.0",
     "..5+5GPER+5RWAU..5", None,
     "Census 2021 G56 Industry of employment by occupation - WA, Greater Perth, Rest of WA"),
    # Census 2021 G60: SEXP.AGEP.OCCP.REGION.REGION_TYPE.STATE
    ("abs_census2021_g60_occ_age_wa.csv", "ABS,C21_G60_SA2,1.0.0",
     "...5+5GPER+5RWAU..5", None,
     "Census 2021 G60 Occupation by age by sex - WA, Greater Perth, Rest of WA"),
]

# Non-API files (Jobs and Skills Australia, etc.) are listed in
# data/raw/other_sources.csv: file,url,description. Only links verified with an
# HTTP 200 response are kept there (see docs/source_register.md).
OTHER_LIST = RAW / "other_sources.csv"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, accept=None, retries=3):
    headers = {"User-Agent": "workforce-planning-portfolio/1.0 (research)"}
    if accept:
        headers["Accept"] = accept
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
                f.write(r.read())
                return r.status
        except Exception as e:  # network hiccups: retry with backoff
            if attempt == retries:
                print(f"  FAILED {url}: {e}", file=sys.stderr)
                return getattr(e, "code", "error")
            time.sleep(5 * attempt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["abs", "other"])
    args = ap.parse_args()
    rows = []
    if args.only in (None, "abs"):
        for fname, flow, key, start, desc in ABS_QUERIES:
            url = f"{ABS_API}/{flow}/{key}"
            if start:
                url += f"?startPeriod={start}"
            dest = RAW / "abs" / fname
            print("ABS", fname)
            status = download(url, dest, accept=CSV_LABELS)
            rows.append((fname, "ABS Data API", url, status, desc, dest))
    if args.only in (None, "other") and OTHER_LIST.exists():
        with open(OTHER_LIST, newline="") as f:
            for rec in csv.DictReader(f):
                dest = RAW / rec["folder"] / rec["file"]
                print("FILE", rec["file"])
                status = download(rec["url"], dest)
                rows.append((rec["file"], rec["publisher"], rec["url"], status, rec["description"], dest))

    man = RAW / "manifest.csv"
    if args.only and man.exists():   # keep the other group's rows from an earlier run
        prev = list(csv.DictReader(open(man, newline="")))
        keep = {r[0] for r in rows}
        rows_prev = [p for p in prev if p["file"] not in keep]
    else:
        rows_prev = []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with open(man, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "publisher", "url", "http_status", "retrieved_utc", "bytes", "sha256", "description"])
        for p in rows_prev:
            w.writerow([p[k] for k in ["file", "publisher", "url", "http_status", "retrieved_utc", "bytes", "sha256",
                                       "description"]])
        for fname, pub, url, status, desc, dest in rows:
            ok = dest.exists() and status == 200
            w.writerow([fname, pub, url, status, now,
                        dest.stat().st_size if ok else 0, sha256(dest) if ok else "", desc])
    print("manifest ->", man)


if __name__ == "__main__":
    main()
