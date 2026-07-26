# Quota Custom Actions

Configure custom actions (stored procedures triggered when a user breaches a per-user quota threshold).

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/custom-actions.md`

---

## Concepts

- **Custom Action**: A stored procedure executed when a user breaches a configured threshold. Applies uniformly to all users in the quota.
- **Invocation rules**:
  - Any user hitting the threshold triggers the custom action, regardless of the 24h rule.
  - For the **same user** re-violating: Projected → action once within 24h. Actual → action once per cycle.

---

## Workflow

### Step 1: Identify the Quota

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` to find the target quota.

---

### Step 2: Add Custom Action

Collect:
- **Stored procedure** (fully qualified name)
- **Parameters** (JSON array of additional arguments, or empty array)
- **Spend strategy**: `PROJECTED` or `ACTUAL`
- **Threshold value** (percentage at which to trigger)

```
What stored procedure should be called?
Are there additional parameters to pass (besides user context)?
Should it trigger on projected or actual spend?
At what threshold percentage should the custom action trigger?
```

Use `ADD_CUSTOM_ACTION` from reference file `references/quota/custom-actions.md`.

To remove, use `REMOVE_CUSTOM_ACTIONS` from reference file `references/quota/custom-actions.md`.

---

### Step 3: Verify

Use `GET_CUSTOM_ACTIONS` from reference file `references/quota/custom-actions.md`.

To validate the quota can execute its configured procedures, use `CONFIRM_CUSTOM_ACTIONS_ACCESS` from reference file `references/quota/custom-actions.md`.

Present results to the user.
