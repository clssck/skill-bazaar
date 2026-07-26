# Convert to Adaptive

## Eligibility Gate

⚠️ **MANDATORY before executing any ALTER** — Run both checks first. See `create.md` for full details.

**Check 1 — Region:**
```sql
SELECT CURRENT_REGION();
```

**Check 2 — Account edition:**
```sql
SHOW ORGANIZATION ACCOUNTS LIKE CURRENT_ACCOUNT();
```

If ORGADMIN role is not available, ask the user to check their edition in Snowsight: **Admin → Account**. Adaptive requires **Enterprise edition or above**.

If either check fails, stop and inform the user. Do NOT generate ALTER SQL.

## How Snowflake Sets Parameters on Migration

When converting an existing standard warehouse to adaptive, **you do not need to set `MAX_QUERY_PERFORMANCE_LEVEL` or `QUERY_THROUGHPUT_MULTIPLIER` yourself**. Both Gen1 and Gen2 standard warehouses can be migrated to adaptive. Snowflake automatically determines the recommended values by inspecting your current warehouse configuration — including warehouse size, multi-cluster count, and QAS settings.

Simply run the ALTER and Snowflake handles the parameter mapping. Adjust afterward if needed.

## Live Migration (No Downtime)

Converting to adaptive — and reverting back to standard — is a **zero-downtime, live operation**. Running queries are not interrupted. You do not need to suspend the warehouse before converting.

Warehouses can be converted via **Snowsight** or **SQL**.

**Snowsight:** Navigate to **Compute » Warehouses » `<warehouse_name>`**, select the **…** menu, then **Convert to Adaptive**, and confirm.

**SQL — Convert to adaptive:**
```sql
ALTER WAREHOUSE {{warehouse_name}} SET WAREHOUSE_TYPE = 'ADAPTIVE';
```

You may also set parameters at conversion time (only if you want to override Snowflake's auto-derived values):
```sql
ALTER WAREHOUSE {{warehouse_name}}
  SET WAREHOUSE_TYPE = 'ADAPTIVE'
      MAX_QUERY_PERFORMANCE_LEVEL = {{level}}
      QUERY_THROUGHPUT_MULTIPLIER = {{multiplier}};
```

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statement for approval before executing.

## Rollback

Any adaptive warehouse can be converted back to standard. Zero-downtime operation.

```sql
ALTER WAREHOUSE {{warehouse_name}} SET WAREHOUSE_TYPE = 'STANDARD';
```

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statement for approval before executing.

## Enable and Disable

Adaptive warehouses can be disabled to block all new query submissions without deleting the warehouse.

```sql
-- Disallow any queries from being submitted to this adaptive warehouse
ALTER WAREHOUSE {{warehouse_name}} DISABLE;

-- Re-allow query submissions
ALTER WAREHOUSE {{warehouse_name}} ENABLE;
```

The `STATE` column in `SHOW WAREHOUSES` reflects the current state: `ENABLED` or `DISABLED`. If `STATE = DISABLED`, check the `DISABLED_REASONS` column for context on why it was disabled.

**⚠️ MANDATORY STOPPING POINT**: Present DISABLE statement for approval before executing — a disabled warehouse blocks all queries on that warehouse.

## Bulk Migration

For migrating many warehouses at once, use `SYSTEM$BULK_UPDATE_WH`. Always run the dry run first.

| Parameter | Description | Example |
|-----------|-------------|---------|
| `property_name` | Warehouse property to update | `'WAREHOUSE_TYPE'` |
| `new_value` | New value for the property | `'ADAPTIVE'` or `'STANDARD'` |
| `property_filter` | JSON filter on warehouse properties | `'{"WAREHOUSE_TYPE": "STANDARD"}'` |
| `tag_filter` | JSON filter on tags | `'{"cost-centre": "sales"}'` |
| `execution_mode` | `'DRY_RUN'` or `'ACTIVE'` | `'DRY_RUN'` |

**Dry run (no changes made):**
```sql
SELECT SYSTEM$BULK_UPDATE_WH(
  'WAREHOUSE_TYPE',
  'ADAPTIVE',
  '{"WAREHOUSE_TYPE": "STANDARD"}',
  'DRY_RUN'
);
```

**Execute migration:**
```sql
SELECT SYSTEM$BULK_UPDATE_WH(
  'WAREHOUSE_TYPE',
  'ADAPTIVE',
  '{"WAREHOUSE_TYPE": "STANDARD"}',
  'ACTIVE'
);
```

**⚠️ MANDATORY STOPPING POINT**: Always show dry run results to the user and get explicit approval before running the ACTIVE migration.