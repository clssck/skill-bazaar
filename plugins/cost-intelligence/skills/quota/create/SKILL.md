# Create Quota

Step-by-step workflow for creating a new Snowflake Quota — includes lifecycle, user scope, limits, and optional refresh tier configuration.

> **See**: Parent `SKILL.md` for routing, guardrails, scope homogeneity rule, and interaction rules.

## Reference Files

- `references/quota/lifecycle.md`
- `references/quota/limits.md`
- `references/quota/shared-resources.md`
- `references/quota/enforcement.md`
- `references/quota/exclusions.md`

---

## Workflow

> **⚠️ Execution order**: All method calls (SET_USER_TAGS, SET_PER_USER_LIMIT, etc.) require the quota to exist first. Always execute `CREATE SNOWFLAKE.CORE.QUOTA` before any method calls — otherwise you'll get "Object does not exist" errors.

### Step 1: Quota Identity

Collect (confirm pre-provided values rather than re-asking):
- **Quota name** — Object name
- **Database.Schema** — Location for the quota instance

Use `CREATE SNOWFLAKE.CORE.QUOTA` from reference file `references/quota/lifecycle.md`.

---

### Step 2: Set User Scope

Users in scope are defined via user tags. This determines which users the quota monitors.

#### Option A: Tag-Based Selection (specific user groups)

Collect tag key/value pairs:
- Resolve any short tag name to its fully qualified form per parent skill rules.
- Ask "Would you like to add another user tag?" and repeat until done.

Then ask for the operator:
```
How should multiple tags be combined?
- UNION (default): Users matching ANY tag are included
- INTERSECTION: Users must match ALL tags
```

Use `SET_USER_TAGS` from reference file `references/quota/lifecycle.md`.

#### Option B: ALL_USERS (account-wide)

Monitors every user in the account.

```
Should this quota apply to ALL users in the account?
```

Use `SET_USER_TAGS` with `ALL_USERS` operator from reference file `references/quota/lifecycle.md`.

---

### Step 3: Set Per-User Limits

The per-user limit is required for the quota to evaluate thresholds.

```
What monthly per-user credit limit would you like to set?
```

Optionally, a daily limit can also be set for enforcement purposes using the 'DAILY' cycle.

Use `SET_PER_USER_LIMIT` from reference file `references/quota/limits.md`.

---

### Step 4: Set Refresh Tier (Optional)

The refresh tier controls how frequently the measurement task evaluates thresholds.

```
Would you like to configure a faster refresh tier?
- TIER_6H (default): measurement every 6 hours
- TIER_1H: measurement every 30 minutes, lower latency for notifications
```

Use `SET_REFRESH_TIER` from reference file `references/quota/lifecycle.md`.

---

### Step 5: Add Shared Resources (Optional)

If the user wants to scope the quota to specific resource domains (e.g., AI Functions, Warehouses, Cortex Agents):

Use `ADD_SHARED_RESOURCE` from reference file `references/quota/shared-resources.md`.

---

### Step 6: Enable Block Enforcement (Optional)

If the user wants automatic user blocking when limits are breached:

1. Set a daily per-user limit using `SET_PER_USER_LIMIT` with `'DAILY'` cycle from reference file `references/quota/limits.md`
2. Enable enforcement using `SET_BLOCK_ENFORCEMENT_ENABLED` from reference file `references/quota/enforcement.md`
3. Optionally exclude users using `EXCLUDE_USERS` from reference file `references/quota/exclusions.md` (only when scope is ALL_USERS)

---

### Step 7: Verify

Use `GET_QUOTA_SCOPE` and `GET_PER_USER_LIMIT` from reference file `references/quota/lifecycle.md` and `limits.md`.

Present the result to the user.

---

### Step 8: Suggest Next Steps

- Configure notification thresholds (load `notifications/SKILL.md`)
- Configure custom actions — stored procedures on breach (load `custom-actions/SKILL.md`)
- Configure cycle-start reset action (load `cycle-start-actions/SKILL.md`)
