-- 01  Standardise the raw HRIS snapshot (SQLite dialect; T-SQL notes inline)
-- Input : stg_hris_snapshot (raw CSV, SYNTHETIC), ref_location_alias, ref_job_family_alias
-- Output: hris_standardised (one row per raw record, standardised fields + rule flags)

DROP TABLE IF EXISTS hris_standardised;
CREATE TABLE hris_standardised AS
WITH base AS (
    SELECT
        s.*,
        -- normalise free text: trim, lower case, expand Nth/Sth, drop "campus"
        TRIM(REPLACE(REPLACE(REPLACE(LOWER(TRIM(s.location)), 'nth', 'north'), 'sth', 'south'), ' campus', '')) AS location_key,
        LOWER(TRIM(s.job_family)) AS job_family_key,
        -- dates arrive as YYYY-MM-DD or DD/MM/YYYY; parse explicitly (T-SQL: TRY_CONVERT(date, x, 103))
        CASE
            WHEN s.hire_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN s.hire_date
            WHEN s.hire_date GLOB '[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]'
                THEN SUBSTR(s.hire_date, 7, 4) || '-' || SUBSTR(s.hire_date, 4, 2) || '-' || SUBSTR(s.hire_date, 1, 2)
        END AS hire_date_iso,
        ROW_NUMBER() OVER (PARTITION BY s.employee_id, s.job_family, s.location, s.fte, s.hire_date, s.date_of_birth
                           ORDER BY s.employee_id) AS dup_rank
    FROM stg_hris_snapshot s
)
SELECT
    b.employee_id, b.person_id, b.cost_centre, b.employment_type, b.gender, b.classification_level,
    b.annual_salary_fte, b.status AS status_raw, b.termination_date,
    COALESCE(l.location, 'UNMAPPED')     AS location,
    COALESCE(j.job_family, 'UNMAPPED')   AS job_family,
    b.hire_date_iso                      AS hire_date,
    CASE WHEN b.date_of_birth <= '1910-01-01' THEN NULL ELSE b.date_of_birth END AS date_of_birth,
    b.fte                                AS fte_raw,
    b.dup_rank > 1                       AS is_exact_duplicate,
    (b.termination_date IS NOT NULL AND b.termination_date <= '2026-06-30') AS is_terminated,
    b.fte IS NULL                        AS fte_missing,
    b.fte > 1.0                          AS fte_out_of_range
FROM base b
LEFT JOIN ref_location_alias   l ON l.alias = b.location_key
LEFT JOIN ref_job_family_alias j ON j.alias = b.job_family_key;

-- Stale prior records: same person with >1 surviving active record -> keep the latest hire
DROP TABLE IF EXISTS hris_active;
CREATE TABLE hris_active AS
WITH live AS (
    SELECT h.*,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY hire_date DESC) AS person_rank
    FROM hris_standardised h
    WHERE NOT is_exact_duplicate AND NOT is_terminated
),
pay AS (   -- paid FTE from payroll ordinary hours (76 h = 1.0 FTE per fortnight)
    SELECT employee_id, SUM(ordinary_hours) / 76.0 AS paid_fte
    FROM stg_payroll GROUP BY employee_id
)
SELECT
    l.employee_id, l.person_id, l.job_family, l.location, l.cost_centre, l.employment_type, l.gender,
    l.hire_date, l.date_of_birth, l.annual_salary_fte,
    CASE
        WHEN l.fte_out_of_range AND l.fte_raw / 10.0 <= 1.0 THEN l.fte_raw / 10.0       -- decimal shift
        WHEN l.fte_missing AND p.paid_fte > 0 THEN ROUND(p.paid_fte, 1)                 -- impute from payroll
        ELSE l.fte_raw
    END AS fte,
    CASE WHEN l.fte_missing THEN CASE WHEN p.paid_fte > 0 THEN 'payroll hours' ELSE 'unresolved' END END AS fte_imputed
FROM live l
LEFT JOIN pay p ON p.employee_id = l.employee_id
WHERE l.person_rank = 1;
