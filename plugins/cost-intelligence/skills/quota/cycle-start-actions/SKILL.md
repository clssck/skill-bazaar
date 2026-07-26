# Quota Cycle-Start Actions

Configure the cycle-start (reset) action that runs automatically at the beginning of each quota cycle. Intended to restore states affected by quota limits (e.g., re-enable users, reset access).

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/cycle-start-actions.md`

---

## Workflow

### Step 1: Identify the Quota

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` to find the target quota.

---

### Step 2: Set Cycle-Start Action

Collect:
- **Stored procedure** (fully qualified name)
- **Parameters** (JSON array, or empty)

```
What stored procedure should run at the start of each cycle?
Are there additional parameters to pass?
```

Use `SET_CYCLE_START_ACTION` from reference file `references/quota/cycle-start-actions.md`.

To remove, use `REMOVE_CYCLE_START_ACTION` from reference file `references/quota/cycle-start-actions.md`.

---

### Step 3: Verify

Use `GET_CYCLE_START_ACTION` from reference file `references/quota/cycle-start-actions.md`.

Present results to the user.
