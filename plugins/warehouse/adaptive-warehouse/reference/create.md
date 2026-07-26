# Create Adaptive Warehouse

## Eligibility Gate

⚠️ **MANDATORY before executing CREATE or ALTER** — Run both checks first:

**Check 1 — Region:**
```sql
SELECT CURRENT_REGION();
```

Refer to the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive) for the current list of supported cloud providers and regions — this changes as availability expands. If the result is not in a supported region, stop and inform the user.

**Check 2 — Account edition:**
```sql
SHOW ORGANIZATION ACCOUNTS LIKE CURRENT_ACCOUNT();
```

Look for the `edition` column. If ORGADMIN role is not available, ask the user to check in Snowsight: **Admin → Account**. Adaptive requires **Enterprise edition or above** (Enterprise, Business Critical, VPS).

If either check fails — unsupported region or insufficient edition — **stop and inform the user**. Do NOT generate CREATE or ALTER SQL.

> **Note:** For parameter or tuning questions ("what settings do you recommend?") you do NOT need to run these checks first — just answer directly.

## Gather Requirements

Ask the user for:
- Warehouse name
- `MAX_QUERY_PERFORMANCE_LEVEL` (optional)
- `QUERY_THROUGHPUT_MULTIPLIER` (optional)

**Parameter starting points:**

- **Migrating from a classic warehouse (ALTER):** Do not set these manually — Snowflake automatically derives both from your existing warehouse configuration (size, cluster count, QAS settings). Run the ALTER and tune afterward if needed.
- **Greenfield (CREATE):** Start with `MAX_QUERY_PERFORMANCE_LEVEL = XLARGE` and `QUERY_THROUGHPUT_MULTIPLIER = 2`.

**Tuning guidance:**
- Increase `QUERY_THROUGHPUT_MULTIPLIER` if you observe undesirable queueing
- Decrease `QUERY_THROUGHPUT_MULTIPLIER` to reduce costs, accepting increased queueing

## Generate CREATE Statement

Adaptive warehouses can be created via **Snowsight** or **SQL**.

**Snowsight:** Navigate to **Compute » Warehouses » +Warehouse**, select **Adaptive** in the Type dropdown. Optionally expand **Advanced** to configure parameters.

**SQL — Minimal (all defaults):**
```sql
CREATE ADAPTIVE WAREHOUSE {{warehouse_name}};
```

**SQL — With parameters:**
```sql
CREATE ADAPTIVE WAREHOUSE {{warehouse_name}}
  WITH MAX_QUERY_PERFORMANCE_LEVEL = {{level}}
       QUERY_THROUGHPUT_MULTIPLIER = {{multiplier}};
```

**SQL — Equivalent `CREATE WAREHOUSE` syntax:**
```sql
CREATE WAREHOUSE {{warehouse_name}}
  WITH WAREHOUSE_TYPE = 'ADAPTIVE'
       MAX_QUERY_PERFORMANCE_LEVEL = {{level}}
       QUERY_THROUGHPUT_MULTIPLIER = {{multiplier}};
```

**Note:** Standard warehouse properties (`WAREHOUSE_SIZE`, `MIN_CLUSTER_COUNT`, `MAX_CLUSTER_COUNT`, `SCALING_POLICY`) cannot be set on an adaptive warehouse.

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval before executing.

## Execute and Verify

1. Execute the approved CREATE statement
2. Verify:
   ```sql
   SHOW WAREHOUSES LIKE '{{warehouse_name}}';
   ```
   Confirm `type` column shows `ADAPTIVE`.