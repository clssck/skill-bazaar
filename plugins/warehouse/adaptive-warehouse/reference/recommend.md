# Warehouse Candidate Recommendation for Adaptive

## Workflow

### Step 1: Ask the User

Before running any query, ask:

> "Would you like me to scan your account and recommend which warehouses are good candidates for Adaptive Warehouse?"

**Only proceed after explicit "yes."**

---

### Step 2: Verify Eligibility

Run both checks and ask the user to confirm before proceeding.

**Check 1 — Region:**
```sql
SELECT CURRENT_REGION();
```

Show the result to the user and ask:

> "Your account is in region `<result>`. Please confirm this region supports Adaptive Warehouse by checking the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive) for the current list of supported cloud providers and regions. Does your region appear in the supported list?"

⚠️ **If the user says their region is not supported — stop.** Do not proceed to the classification query.

**Check 2 — Account edition:**
```sql
SHOW ORGANIZATION ACCOUNTS LIKE CURRENT_ACCOUNT();
```

Look for the `edition` column. If the ORGADMIN role is unavailable, ask the user to check **Snowsight → Admin → Account**. Adaptive requires **Enterprise edition or above**.

⚠️ **If either check fails — unsupported region or insufficient edition — stop immediately.** Inform the user that Adaptive Warehouses are not available for their account and do not proceed to the classification query.

---

### Step 3: Run the Classification Query

The query is two steps — `SHOW WAREHOUSES` first, then the classification CTE using `RESULT_SCAN`.

**Step 3a — Snapshot the warehouse inventory:**
```sql
SHOW WAREHOUSES;
```

**Step 3b — Classify warehouses (run immediately after Step 3a):**
```sql
WITH wh_inventory AS (
    SELECT
        "name"                    AS warehouse_name,
        "type"                    AS warehouse_type,
        "size"                    AS size,
        "max_cluster_count"       AS max_cluster_count,
        "enable_query_acceleration" AS qas_enabled,
        "resource_constraint"     AS resource_constraint
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    WHERE UPPER("name") NOT LIKE 'SYSTEM$%'
      AND UPPER("name") != 'STREAMLIT_NOTEBOOK_WH'
),
job_stats AS (
    SELECT
        warehouse_name,
        COUNT(DISTINCT DATE_TRUNC('day', start_time)) AS days_with_jobs,
        COUNT(*)                                      AS total_jobs,
        ROUND(COUNT(*) / 14.0, 0)                    AS avg_daily_jobs
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD(day, -14, CURRENT_DATE())
      AND start_time <  CURRENT_DATE()
      AND warehouse_name IS NOT NULL
      AND execution_time > 0
    GROUP BY warehouse_name
),
classified AS (
    SELECT
        w.warehouse_name,
        w.warehouse_type,
        w.size,
        w.max_cluster_count,
        w.qas_enabled,
        COALESCE(j.days_with_jobs, 0)  AS days_with_jobs,
        COALESCE(j.avg_daily_jobs, 0)  AS avg_daily_jobs,
        CASE
            WHEN w.warehouse_type IN ('ADAPTIVE_FACADE', 'ADAPTIVE_POOL')
                THEN 'Already Adaptive'
            WHEN w.size IN ('X5LARGE', 'X6LARGE')
                THEN 'Not a Candidate — Size too large (5XL/6XL)'
            WHEN w.warehouse_type LIKE 'SOW_MEMORY%' OR w.warehouse_type = 'HIGH_MEMORY'
                THEN 'Not a Candidate — Snowpark-Optimized warehouse'
            WHEN w.warehouse_type = 'INTERACTIVE'
                THEN 'Not a Candidate — Interactive warehouse'
            WHEN COALESCE(j.avg_daily_jobs, 0) < 100
                THEN 'Not a Candidate — Low job volume (< 100 jobs/day)'
            WHEN COALESCE(j.days_with_jobs, 0) < 14
                THEN 'Not a Candidate — Insufficient history (< 14 active days)'
            ELSE 'Candidate'
        END AS status
    FROM wh_inventory w
    LEFT JOIN job_stats j
        ON UPPER(w.warehouse_name) = UPPER(j.warehouse_name)
)
SELECT
    warehouse_name,
    warehouse_type,
    size,
    max_cluster_count,
    qas_enabled,
    days_with_jobs,
    avg_daily_jobs,
    status
FROM classified
ORDER BY
    CASE status
        WHEN 'Candidate'        THEN 0
        WHEN 'Already Adaptive' THEN 1
        ELSE 2
    END,
    warehouse_name;
```

---

### Step 4: Present the Results

After running, summarize the output for the user:

- Lead with the **Candidate** count: "X of your warehouses are recommended candidates for Adaptive."
- List the candidate warehouse names, size, and avg daily jobs.
- Briefly explain why non-candidates were excluded (group by reason).

**Example summary format:**

> **X warehouses are Adaptive candidates:**
> - `WAREHOUSE_A` (LARGE, ~350 jobs/day)
> - `WAREHOUSE_B` (MEDIUM, ~180 jobs/day)
>
> **Excluded:**
> - 2 warehouses — Low job volume
> - 1 warehouse — Already Adaptive
> - 1 warehouse — Snowpark-Optimized

---

### Step 5: HTAP Check

After presenting candidates, always ask:

> "Do any of these recommended warehouses primarily serve key-value or HTAP workloads (e.g., high-throughput transactional queries against key-value tables)? If so, those are not good candidates and should stay on Standard."

If the user confirms a warehouse is HTAP-heavy, remove it from the recommended list. Do **not** proceed with conversion for those warehouses.

---

## Classification Criteria

| Check | Threshold | Result |
|-------|-----------|--------|
| Already adaptive | `type IN ('ADAPTIVE_FACADE', 'ADAPTIVE_POOL')` | Already Adaptive |
| Size | `X5LARGE` or `X6LARGE` | Not a Candidate |
| Snowpark-Optimized | `type LIKE 'SOW_MEMORY%'` or `= 'HIGH_MEMORY'` | Not a Candidate |
| Interactive | `type = 'INTERACTIVE'` | Not a Candidate |
| Job volume | `avg_daily_jobs < 100` (over last 14 days) | Not a Candidate |
| History | `days_with_jobs < 14` (out of last 14 days) | Not a Candidate |
| — | All other Standard warehouses | **Candidate** |

> **Note on HTAP:** HTAP (key-value store access) workloads are not an optimal fit for Adaptive Warehouse. This query cannot detect HTAP usage from customer-accessible data, so HTAP-heavy warehouses will not be automatically excluded. If the user knows a warehouse is primarily HTAP, advise them to keep it on Standard.

---

## Next Steps After Candidate Identification

Once candidates are identified, offer to:

1. **Convert a specific warehouse** → Load `reference/convert.md`
2. **Explain what to expect** → Load `reference/tuning.md`
3. **Set up a switchback experiment** → Tell the user to ask their account team or Snowflake SE for access to the Adaptive Switchback dashboard
