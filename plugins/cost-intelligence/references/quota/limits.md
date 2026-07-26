# Quota Spending Limits

Methods for setting, retrieving, and unsetting per-user credit limits.

**Semantic keywords:** per-user limit, monthly limit, daily limit, spending limit, credit cap, unset limit

---

## SET_PER_USER_LIMIT

```sql
CALL {quota_fqn}!SET_PER_USER_LIMIT({input_limit});
CALL {quota_fqn}!SET_PER_USER_LIMIT({input_limit}, '{cycle}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `input_limit`: FLOAT — per-user credit limit
- `cycle`: VARCHAR (optional) — `'MONTHLY'` (default) or `'DAILY'`. When omitted, defaults to `'MONTHLY'`.

**Examples:**
```sql
-- Set monthly limit to 500 credits per user (default cycle)
CALL my_db.my_schema.my_quota!SET_PER_USER_LIMIT(500);

-- Explicitly set monthly limit
CALL my_db.my_schema.my_quota!SET_PER_USER_LIMIT(500, 'MONTHLY');

-- Set daily limit to 50 credits per user
CALL my_db.my_schema.my_quota!SET_PER_USER_LIMIT(50, 'DAILY');
```

> **Limitations**:
> - All users in scope share the same per-user limit — no per-user customization within one quota.
> - No collective/group cap across users — limits are per-user only.

---

## UNSET_PER_USER_LIMIT

```sql
CALL {quota_fqn}!UNSET_PER_USER_LIMIT('{cycle}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `cycle`: VARCHAR — `'MONTHLY'` or `'DAILY'`; clears the respective limit entirely

**Examples:**
```sql
-- Remove the monthly per-user limit
CALL my_db.my_schema.my_quota!UNSET_PER_USER_LIMIT('MONTHLY');

-- Remove the daily per-user limit
CALL my_db.my_schema.my_quota!UNSET_PER_USER_LIMIT('DAILY');
```

---

## GET_PER_USER_LIMIT

```sql
CALL {quota_fqn}!GET_PER_USER_LIMIT();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- NUMBER — the configured per-user credit limit.

> **Note**: `GET_PER_USER_LIMIT` returns only the monthly limit. It does not accept a cycle parameter and does not return the daily limit. To see both monthly and daily limits, use `GET_CONFIG` from the `status/SKILL.md` workflow instead.
