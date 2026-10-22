-- 03  Reconcile HRIS vs payroll vs finance establishment
-- (a) HRIS active vs payroll fortnight: full outer join, classify every unmatched record
DROP TABLE IF EXISTS recon_hris_payroll;
CREATE TABLE recon_hris_payroll AS
SELECT
    COALESCE(h.employee_id, p.employee_id) AS employee_id,
    CASE
        WHEN h.employee_id IS NOT NULL AND p.employee_id IS NOT NULL THEN 'Matched'
        WHEN h.employee_id IS NULL AND p.employee_id LIKE 'C%' THEN 'Payroll only - contractor'
        WHEN h.employee_id IS NULL AND EXISTS (SELECT 1 FROM stg_movements m
                                               WHERE m.employee_id = p.employee_id AND m.event_type = 'SEPARATION')
             THEN 'Payroll only - final pay after separation'
        WHEN h.employee_id IS NULL THEN 'Payroll only - UNEXPLAINED'
        ELSE 'HRIS only - not paid this fortnight'
    END AS recon_status
FROM hris_active h
FULL OUTER JOIN (SELECT DISTINCT employee_id FROM stg_payroll) p ON p.employee_id = h.employee_id;

-- (b) Establishment (budget FTE) vs filled FTE by job family x location, with open requisitions
DROP TABLE IF EXISTS recon_establishment;
CREATE TABLE recon_establishment AS
WITH filled AS (
    SELECT cost_centre, COUNT(*) AS headcount, SUM(fte) AS filled_fte FROM hris_active GROUP BY cost_centre
),
open_req AS (
    SELECT job_family, location, COUNT(DISTINCT requisition_id) AS open_requisitions
    FROM stg_requisitions WHERE status = 'Open' GROUP BY job_family, location
)
SELECT c.job_family, c.location, e.budgeted_fte,
       COALESCE(f.headcount, 0) AS headcount, ROUND(COALESCE(f.filled_fte, 0), 1) AS filled_fte,
       ROUND(e.budgeted_fte - COALESCE(f.filled_fte, 0), 1) AS vacant_fte,
       ROUND((e.budgeted_fte - COALESCE(f.filled_fte, 0)) / e.budgeted_fte, 4) AS vacancy_rate,
       COALESCE(o.open_requisitions, 0) AS open_requisitions
FROM stg_establishment e
JOIN ref_cost_centre c ON c.cost_centre = e.cost_centre
LEFT JOIN filled f ON f.cost_centre = e.cost_centre
LEFT JOIN open_req o ON o.job_family = c.job_family AND o.location = c.location
WHERE e.fy = 'FY2026';
