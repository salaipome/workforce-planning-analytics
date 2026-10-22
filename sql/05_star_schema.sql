-- 05  Star schema for the Power BI model (see docs/dashboard_spec.md)
DROP TABLE IF EXISTS dim_job_family;
CREATE TABLE dim_job_family AS
SELECT DISTINCT job_family AS job_family_key, job_family, anzsco,
       CASE WHEN job_family IN ('Administration', 'Support Services') THEN 'Non-clinical' ELSE 'Clinical' END AS family_group
FROM ref_job_family;

DROP TABLE IF EXISTS dim_location;
CREATE TABLE dim_location AS SELECT location AS location_key, location, gccsa, remoteness FROM ref_location;

DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date AS
WITH RECURSIVE d(dt) AS (SELECT '2022-07-01' UNION ALL SELECT DATE(dt, '+1 day') FROM d WHERE dt < '2029-06-30')
SELECT dt AS date_key, CAST(SUBSTR(dt, 1, 4) AS INTEGER) AS year, CAST(SUBSTR(dt, 6, 2) AS INTEGER) AS month,
       'FY' || (CAST(SUBSTR(dt, 1, 4) AS INTEGER) + (CAST(SUBSTR(dt, 6, 2) AS INTEGER) >= 7)) AS financial_year
FROM d;

DROP TABLE IF EXISTS fact_workforce_snapshot;
CREATE TABLE fact_workforce_snapshot AS
SELECT '2026-06-30' AS date_key, employee_id, job_family AS job_family_key, location AS location_key,
       employment_type, fte, 1 AS headcount, annual_salary_fte * fte AS annual_salary_cost
FROM hris_active;

DROP TABLE IF EXISTS fact_movement;
CREATE TABLE fact_movement AS
SELECT DISTINCT event_id, event_date AS date_key, employee_id, event_type, job_family AS job_family_key,
       location AS location_key, from_job_family, from_location, reason, source
FROM stg_movements;

DROP TABLE IF EXISTS fact_requisition;
CREATE TABLE fact_requisition AS
SELECT DISTINCT requisition_id, job_family AS job_family_key, location AS location_key,
       MIN(open_date, COALESCE(filled_date, open_date)) AS open_date_key, status, reason, applicants,
       MAX(open_date, COALESCE(filled_date, open_date)) AS filled_date_key, source
FROM stg_requisitions;

DROP TABLE IF EXISTS fact_establishment;
CREATE TABLE fact_establishment AS
SELECT e.fy AS financial_year, c.job_family AS job_family_key, c.location AS location_key, e.budgeted_fte
FROM stg_establishment e JOIN ref_cost_centre c USING (cost_centre);
-- fact_forecast is loaded from outputs/tables/model_cells_all_scenarios.csv (scenario x year x family x location)
