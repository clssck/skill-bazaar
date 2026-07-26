# Quota Block Enforcement

Methods for managing block enforcement — the ability to automatically suspend users who exceed their per-user limit.

**Semantic keywords:** block enforcement, suspend user, active blocks, enforcement history, quota enforcement

---

## SET_BLOCK_ENFORCEMENT_ENABLED

```sql
CALL {quota_fqn}!SET_BLOCK_ENFORCEMENT_ENABLED({input_enabled});
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.
> **Parameter Gate**: Requires account parameter `ENABLE_QUOTA_BLOCK_ENFORCEMENT` to be TRUE. Raises "Operation not supported" if the parameter is not set.

**Parameters:**
- `input_enabled`: BOOLEAN — `TRUE` to enable block enforcement, `FALSE` to disable it

**Examples:**
```sql
-- Enable block enforcement
CALL my_db.my_schema.my_quota!SET_BLOCK_ENFORCEMENT_ENABLED(TRUE);

-- Disable block enforcement
CALL my_db.my_schema.my_quota!SET_BLOCK_ENFORCEMENT_ENABLED(FALSE);
```

---

## GET_ACTIVE_BLOCKS

```sql
CALL {quota_fqn}!GET_ACTIVE_BLOCKS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:** TABLE
- `DOMAIN` (VARCHAR) — the resource domain
- `INSTANCE` (VARCHAR) — the resource instance
- `USER_ID` (NUMBER) — the blocked user's ID
- `USER_NAME` (VARCHAR) — the blocked user's name
- `CYCLE` (VARCHAR) — the enforcement cycle (`'MONTHLY'` or `'DAILY'`)
- `BLOCKED_UNTIL` (TIMESTAMP_LTZ(9)) — when the block expires

> **Known limitation**: This method currently returns empty results due to an internal issue (SNOW-3674000). Until resolved, use `GET_ENFORCEMENT_HISTORY` to see recent block/unblock actions instead.

**Examples:**
```sql
-- View all currently blocked users
CALL my_db.my_schema.my_quota!GET_ACTIVE_BLOCKS();
```

---

## GET_ENFORCEMENT_HISTORY

```sql
CALL {quota_fqn}!GET_ENFORCEMENT_HISTORY('{start_date}', '{end_date}');
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Parameters:**
- `start_date`: DATE — start of the date range
- `end_date`: DATE — end of the date range

**Returns:** TABLE
- `ACTION_AT` (TIMESTAMP_LTZ(9)) — when the enforcement action occurred
- `ACTION` (VARCHAR) — the type of action (e.g., 'BLOCK', 'UNBLOCK')
- `USER_ID` (NUMBER) — the affected user's ID
- `USER_NAME` (VARCHAR) — the affected user's name
- `CYCLE` (VARCHAR) — the enforcement cycle
- `PER_USER_LIMIT` (NUMBER) — the limit that was breached
- `CREDITS` (NUMBER) — the credits consumed at the time of action

**Examples:**
```sql
-- View enforcement history for January 2025
CALL my_db.my_schema.my_quota!GET_ENFORCEMENT_HISTORY('2025-01-01', '2025-01-31');
```
