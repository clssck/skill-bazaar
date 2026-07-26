---
name: feature-store-migrate
description: "Migrate to Snowflake Feature Store from Feast, Tecton, or custom feature store platforms."
parent_skill: feature-store
path: machine-learning/feature-store/migrate
---

# Migration Guide

## When to Load

Parent skill routes here for MIGRATE intent: "migrate from Feast", "migrate from Tecton", "migration", "convert feature store", "move to Snowflake feature store".

## Prerequisites

- `../references/api-reference.md` loaded
- User has access to the source feature store configuration

---

## Concept Mapping

### Feast → Snowflake Feature Store

| Feast Concept | Snowflake Equivalent | Notes |
|---------------|---------------------|-------|
| Feature Store (repo) | `FeatureStore` (schema) | FS = a Snowflake schema |
| Entity | `Entity` | Same concept, register via `fs.register_entity()` |
| Feature View | `FeatureView` (managed) | With `refresh_freq` for auto-refresh |
| On-Demand Feature View | `FeatureView` (external) | With `refresh_freq=None` |
| Feature Service | `FeatureView.slice()` | Group features via slices |
| `get_historical_features()` | `fs.generate_dataset()` | Point-in-time retrieval |
| `get_online_features()` | `fs.read_feature_view(..., store_type=StoreType.ONLINE)` | Low-latency key lookup |
| Registry (SQLite/DB) | Snowflake metadata | Automatic, no external DB needed |
| Materialization job | Dynamic Table refresh | Automatic, no cron/Airflow needed |
| `feast apply` | `fs.register_entity()` / `fs.register_feature_view()` | Python API |
| `feast materialize` | Automatic via Dynamic Table | Set `refresh_freq` |
| `feature_store.yaml` | Python code (FeatureStore constructor) | No YAML config file |

### Tecton → Snowflake Feature Store

| Tecton Concept | Snowflake Equivalent | Notes |
|----------------|---------------------|-------|
| Workspace | `FeatureStore` (schema) | One schema per workspace |
| Entity | `Entity` | Same concept |
| Batch Feature View | `FeatureView` (managed) | Dynamic Table with `refresh_freq` |
| Stream Feature View | `FeatureView` (managed, short lag) | Use low `refresh_freq` (e.g., `"1 minute"`) |
| On-Demand Feature View | `FeatureView` (external, `refresh_freq=None`) | Or ODT at query time |
| Feature Service | `FeatureView.slice()` | Compose from multiple FVs |
| `get_features_for_events()` | `fs.generate_dataset()` | PIT retrieval |
| `get_online_features()` | `fs.read_feature_view(..., StoreType.ONLINE)` | Key-value lookup |
| Transformation (Python) | Snowpark DataFrame + SQL | In-warehouse computation |
| Materialization | Dynamic Table refresh | Automatic |

### Custom / In-House → Snowflake Feature Store

| Custom Concept | Snowflake Equivalent | Notes |
|----------------|---------------------|-------|
| Feature tables | Source tables → `FeatureView` | Register existing tables |
| ETL pipelines | `FeatureView` with `refresh_freq` | Or external FV if keeping existing ETL |
| Feature registry | Built-in (metadata on schema) | Automatic discovery and versioning |
| Training data joins | `fs.generate_dataset()` | PIT-correct by default |
| Serving layer | `OnlineConfig` + `StoreType.ONLINE` | Built-in low-latency serving |

---

## Migration Workflow

### Step 1: Inventory Source Feature Store

**Ask user:**
```
To plan the migration, I need to understand your current setup:
1. Which platform are you migrating from? (Feast / Tecton / Custom / Other)
2. How many entities do you have?
3. How many feature views/tables?
4. Do you use online serving?
5. Any custom transformations (UDFs, streaming)?
```

**⚠️ STOP**: Wait for user response.

---

### Step 2: Map Entities

For each entity in the source system, create the Snowflake equivalent:

```python
# Feast example:
# driver = Entity(name="driver", join_keys=["driver_id"])
# →
driver_entity = Entity(
    name="DRIVER",
    join_keys=["DRIVER_ID"],
    desc="Driver entity (migrated from Feast)"
)
fs.register_entity(driver_entity)
```

**Naming conversion:**
- Feast/Tecton: `snake_case` → Snowflake: `SCREAMING_SNAKE_CASE`
- Ensure join key column names match the source data columns in Snowflake

---

### Step 3: Map Feature Views

For each source feature view:

1. **Identify the source data** in Snowflake (must be loaded first)
2. **Write the transformation** as a Snowpark DataFrame or SQL
3. **Choose pipeline type**: managed (Dynamic Table) or external
4. **Register** in Snowflake Feature Store

```python
# Feast example transformation → Snowpark SQL
feature_df = session.sql("""
    SELECT
        DRIVER_ID,
        EVENT_TS,
        CONV_RATE,
        ACC_RATE,
        AVG_DAILY_TRIPS
    FROM RAW_DB.PUBLIC.DRIVER_STATS
""")

driver_fv = FeatureView(
    name="DRIVER_STATS_FV",
    entities=[driver_entity],
    feature_df=feature_df,
    timestamp_col="EVENT_TS",
    refresh_freq="1 hour",
    desc="Driver statistics (migrated from Feast driver_hourly_stats)",
)

fs.register_feature_view(driver_fv, version="V01", block=True)
```

**⚠️ MANDATORY CHECKPOINT**: For each feature view migration, present the configuration before registering.

---

### Step 4: Migrate Training Pipeline

Replace source platform's historical retrieval with Snowflake's:

```python
# Feast: store.get_historical_features(entity_df, features)
# →
dataset = fs.generate_dataset(
    name="DRIVER_TRAINING",
    spine_df=entity_df,
    features=[driver_fv],
    spine_timestamp_col="EVENT_TS",
    spine_label_cols=["LABEL"],
    version="V01",
)
```

---

### Step 5: Migrate Online Serving (if applicable)

Replace source platform's online retrieval:

```python
# Feast: store.get_online_features(features, entity_rows)
# →
from snowflake.ml.feature_store import OnlineConfig

config = OnlineConfig(enable=True, target_lag="15s")
fs.update_feature_view("DRIVER_STATS_FV", "V01", online_config=config)

# Read online
result = fs.read_feature_view(
    "DRIVER_STATS_FV", "V01",
    keys=[[driver_id]],
    store_type=StoreType.ONLINE,
)
```

---

### Step 6: Validate Migration

**Dual-run validation** — run both old and new systems in parallel:

1. **Schema comparison**: Verify all features exist with correct types
2. **Value comparison**: Compare feature values for a sample of entities
3. **Training comparison**: Generate training dataset from both systems and compare metrics
4. **Latency comparison**: Measure online retrieval latency

```python
# Validate feature values match
old_features = fetch_from_old_system(entity_keys)
new_features = fs.read_feature_view("DRIVER_STATS_FV", "V01", keys=entity_keys)

# Compare column-by-column
for col in feature_columns:
    old_vals = old_features[col]
    new_vals = new_features[col]
    assert np.allclose(old_vals, new_vals, rtol=1e-5), f"Mismatch in {col}"
```

**Consumer switchover process:**
1. Deploy new Snowflake-based feature pipeline alongside old system
2. Validate feature parity (schema, values, latency)
3. Switch consumers one at a time to new system
4. Monitor for 1-2 weeks
5. Decommission old system

---

## Important Considerations

- **Data must be in Snowflake** before migration. Load source data first.
- **Streaming features** (Kafka, Kinesis): Use Snowpipe Streaming to ingest, then register as managed FV with short `refresh_freq`.
- **Custom UDFs**: Rewrite in Snowpark Python UDFs or Snowflake SQL.
- **External orchestration** (Airflow, Dagster, dbt): Can still trigger `ALTER DYNAMIC TABLE REFRESH`, or let DT auto-refresh. For dbt, register the dbt-produced table as an external feature view (`refresh_freq=None`).
- **Feature parity**: Not all source features may translate 1:1. Document any gaps.

---

## Stopping Points

- ✋ Step 1: Source system inventory
- ✋ Step 3: Before registering each feature view
- ✋ Step 5: Before enabling online serving
- ✋ Step 6: After validation, before decommissioning old system

## Output

- Migrated entities and feature views in Snowflake
- Updated training pipeline using `generate_dataset`
- Online serving configured (if applicable)
- Validation report comparing old vs new system

## Next Skill

- If user wants to audit migrated features → **Load** `monitor/SKILL.md`
- If user wants lineage analysis → **Load** `lineage/SKILL.md`
