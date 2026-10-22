-- 04  Core workforce metrics (definitions in docs/metric_definitions.md)
-- (a) Headcount vs FTE by job family
DROP TABLE IF EXISTS m_headcount_fte;
CREATE TABLE m_headcount_fte AS
SELECT job_family, COUNT(*) AS headcount, ROUND(SUM(fte), 1) AS fte, ROUND(SUM(fte) / COUNT(*), 3) AS fte_per_head
FROM hris_active GROUP BY job_family
UNION ALL SELECT 'TOTAL', COUNT(*), ROUND(SUM(fte), 1), ROUND(SUM(fte) / COUNT(*), 3) FROM hris_active;

-- (b) Turnover by financial year = separations / average headcount, rebuilt backwards from the closing stock
DROP TABLE IF EXISTS m_turnover_fy;
CREATE TABLE m_turnover_fy AS
WITH ev AS (
    SELECT DISTINCT event_id, event_type,
           'FY' || (CAST(SUBSTR(event_date, 1, 4) AS INTEGER) + (CAST(SUBSTR(event_date, 6, 2) AS INTEGER) >= 7)) AS fy
    FROM stg_movements
),
flows AS (
    SELECT fy, SUM(event_type = 'HIRE') AS hires, SUM(event_type = 'SEPARATION') AS separations
    FROM ev WHERE fy BETWEEN 'FY2023' AND 'FY2026' GROUP BY fy
),
stock AS (   -- closing(FY) = closing(FY2026) - net hires of every later FY (transfers/role changes net to 0 org-wide)
    SELECT f.fy, f.hires, f.separations,
           (SELECT COUNT(*) FROM hris_active)
             - COALESCE((SELECT SUM(hires - separations) FROM flows f2 WHERE f2.fy > f.fy), 0) AS closing
    FROM flows f
)
SELECT fy, hires, separations, closing - hires + separations AS opening, closing,
       ROUND(separations * 1.0 / ((closing - hires + separations + closing) / 2.0), 4) AS turnover_rate
FROM stock ORDER BY fy;

-- (c) Median and 90th percentile time-to-fill by job family, FY2026 fills (SQLite has no PERCENTILE_CONT)
DROP TABLE IF EXISTS m_time_to_fill;
CREATE TABLE m_time_to_fill AS
WITH r AS (
    SELECT DISTINCT requisition_id, job_family,
           CASE WHEN filled_date < open_date THEN julianday(open_date) - julianday(filled_date)   -- swapped dates
                ELSE julianday(filled_date) - julianday(open_date) END AS ttf
    FROM stg_requisitions
    WHERE status = 'Filled' AND filled_date IS NOT NULL
      AND MAX(filled_date, open_date) BETWEEN '2025-07-01' AND '2026-06-30'
),
ranked AS (
    SELECT job_family, ttf, ROW_NUMBER() OVER (PARTITION BY job_family ORDER BY ttf) AS rn,
           COUNT(*) OVER (PARTITION BY job_family) AS n
    FROM r
)
SELECT job_family, n AS fills,
       AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN ttf END) AS median_days,
       MIN(CASE WHEN rn >= 0.9 * n THEN ttf END) AS p90_days
FROM ranked GROUP BY job_family, n;
