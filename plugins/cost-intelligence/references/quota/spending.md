# Quota Spending Data

Methods for viewing per-user spending and usage attribution.

**Semantic keywords:** spending details, user spending, usage preview, credits spend, per-user usage

---

## GET_PER_USER_USAGE_PREVIEW

Returns per-user usage attribution for a given date window, broken down by service and entity at hourly granularity.

```sql
CALL {quota_fqn}!GET_PER_USER_USAGE_PREVIEW('{window_start}'::DATE, '{window_end}'::DATE);
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Parameters:**
- `window_start`: DATE — start of the date range (e.g., `'2024-01-01'`)
- `window_end`: DATE — end of the date range (e.g., `'2024-01-31'`)


**Returns:**
- `USER_ID` (NUMBER) — the user's ID
- `USER_NAME` (VARCHAR) — the user's name
- `SERVICE_TYPE` (VARCHAR) — the resource type (e.g., `AI FUNCTION`, `CORTEX AGENT`, `WAREHOUSE`)
- `ENTITY_TYPE` (VARCHAR) — the entity classification
- `ENTITY_NAME` (VARCHAR) — the entity's name (e.g., `AI_COMPLETE`, `MY_WAREHOUSE`)
- `ENTITY_ID` (NUMBER) — the entity's ID
- `CREDITS_SPEND` (FLOAT) — credits consumed in this hour
- `USAGE_HOUR` (TIMESTAMP_LTZ) — the hour of usage

**Example:**
```sql
CALL my_db.my_schema.my_quota!GET_PER_USER_USAGE_PREVIEW('2024-06-01'::DATE, '2024-06-15'::DATE);
```

---

## GET_SPENDING_DETAILS_BY_USERS

Returns granular spending records by user and resource.

```sql
CALL {quota_fqn}!GET_SPENDING_DETAILS_BY_USERS('{start_date}'::DATE, '{end_date}'::DATE);
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Parameters:**
- `start_date`: DATE — start of the date range (e.g., `'2024-01-01'`)
- `end_date`: DATE — end of the date range (e.g., `'2024-01-31'`)


**Returns:**
- `USER_ID` (NUMBER) — the user's ID
- `USER_NAME` (VARCHAR) — the user's name
- `SERVICE_TYPE` (VARCHAR) — the resource type (e.g., `AI FUNCTION`, `CORTEX AGENT`, `WAREHOUSE`)
- `ENTITY_TYPE` (VARCHAR) — the entity classification
- `ENTITY_NAME` (VARCHAR) — the entity's name (e.g., `AI_COMPLETE`, `MY_WAREHOUSE`)
- `CREDITS_SPEND` (FLOAT) — credits consumed
- `USAGE_TIMESTAMP` (TIMESTAMP_TZ) — timestamp of usage

**Example:**
```sql
CALL my_db.my_schema.my_quota!GET_SPENDING_DETAILS_BY_USERS('2024-06-01'::DATE, '2024-06-30'::DATE);
```
