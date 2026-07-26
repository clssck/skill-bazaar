# Quota Cycle-Start Actions

Methods for configuring the cycle-start (reset) action that runs at the beginning of each quota cycle.

**Semantic keywords:** cycle start, reset action, monthly reset, re-enable users, cycle boundary

---

## SET_CYCLE_START_ACTION

```sql
CALL {quota_fqn}!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', '{db}.{schema}.{procedure_name}({param_types})'),
    ARRAY_CONSTRUCT({args})
);
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `db`: the database containing the stored procedure
- `schema`: the schema containing the stored procedure
- `procedure_name`: the procedure name
- `param_types`: comma-separated parameter types. Must include the implicit first argument (STRING) that receives quota context.
- `args`: user-supplied arguments. Same implicit-first-arg rule as custom actions — count + 1 must match param_types.


Only one cycle-start action may be configured per quota. Setting a new one overwrites the previous.

**Examples:**
```sql
-- Simple: no user args
CALL my_db.my_schema.my_quota!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'my_db.my_schema.reenable_users_sp(STRING)'),
    ARRAY_CONSTRUCT()
);

-- With user args
CALL my_db.my_schema.my_quota!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'my_db.my_schema.reset_access_sp(STRING, NUMBER)'),
    ARRAY_CONSTRUCT(42)
);
```

---

## REMOVE_CYCLE_START_ACTION

```sql
CALL {quota_fqn}!REMOVE_CYCLE_START_ACTION();
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

---

## GET_CYCLE_START_ACTION

```sql
CALL {quota_fqn}!GET_CYCLE_START_ACTION();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `ACTION_ID` (VARCHAR) — unique identifier for the action
- `PROCEDURE_FQN` (VARCHAR) — fully qualified procedure name (e.g., `MY_DB.MY_SCHEMA.REENABLE_USERS_SP`)
- `PROCEDURE_ARGS` (ARRAY) — user-supplied arguments
- `LAST_TRIGGER_ATTEMPT_TIME` (TIMESTAMP_TZ) — last time this action was triggered
- `ADDED_TIMESTAMP` (TIMESTAMP_TZ) — when the action was configured
