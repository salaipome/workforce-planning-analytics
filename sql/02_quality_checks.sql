-- 02  Data-quality rule results (one row per rule): before = raw, after = hris_active
DROP TABLE IF EXISTS dq_results;
CREATE TABLE dq_results AS
SELECT 'rows' AS rule, (SELECT COUNT(*) FROM stg_hris_snapshot) AS raw_value, (SELECT COUNT(*) FROM hris_active) AS clean_value
UNION ALL SELECT 'exact duplicate rows',
       (SELECT SUM(is_exact_duplicate) FROM hris_standardised), 0
UNION ALL SELECT 'terminated but Active',
       (SELECT SUM(is_terminated) FROM hris_standardised WHERE NOT is_exact_duplicate), 0
UNION ALL SELECT 'distinct location values',
       (SELECT COUNT(DISTINCT location) FROM stg_hris_snapshot), (SELECT COUNT(DISTINCT location) FROM hris_active)
UNION ALL SELECT 'distinct job family values',
       (SELECT COUNT(DISTINCT job_family) FROM stg_hris_snapshot), (SELECT COUNT(DISTINCT job_family) FROM hris_active)
UNION ALL SELECT 'unmapped location / job family',
       (SELECT COUNT(*) FROM hris_standardised WHERE location = 'UNMAPPED' OR job_family = 'UNMAPPED'),
       (SELECT COUNT(*) FROM hris_active WHERE location = 'UNMAPPED' OR job_family = 'UNMAPPED')
UNION ALL SELECT 'FTE missing or > 1.0',
       (SELECT COUNT(*) FROM stg_hris_snapshot WHERE fte IS NULL OR fte > 1.0),
       (SELECT COUNT(*) FROM hris_active WHERE fte IS NULL OR fte > 1.0)
UNION ALL SELECT 'hire_date not ISO',
       (SELECT COUNT(*) FROM stg_hris_snapshot WHERE hire_date NOT GLOB '[0-9][0-9][0-9][0-9]-*'),
       (SELECT COUNT(*) FROM hris_active WHERE hire_date IS NULL)
UNION ALL SELECT 'total FTE',
       (SELECT ROUND(SUM(fte), 1) FROM stg_hris_snapshot), (SELECT ROUND(SUM(fte), 1) FROM hris_active);

-- Exception log for analyst review
DROP TABLE IF EXISTS dq_exceptions;
CREATE TABLE dq_exceptions AS
SELECT employee_id, 'exact duplicate' AS rule FROM hris_standardised WHERE is_exact_duplicate
UNION ALL SELECT employee_id, 'terminated but Active' FROM hris_standardised WHERE is_terminated AND NOT is_exact_duplicate
UNION ALL SELECT employee_id, 'FTE > 1.0' FROM hris_standardised WHERE fte_out_of_range AND NOT is_exact_duplicate
UNION ALL SELECT employee_id, 'FTE missing' FROM hris_standardised WHERE fte_missing AND NOT is_exact_duplicate
UNION ALL SELECT employee_id, 'implausible date of birth' FROM hris_standardised WHERE date_of_birth IS NULL AND NOT is_exact_duplicate;
