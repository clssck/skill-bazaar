# View Quotas

View quota configuration, spending data, and manage quota lifecycle (list, inspect, drop).

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/lifecycle.md`
- `references/quota/limits.md`
- `references/quota/notifications.md`
- `references/quota/custom-actions.md`
- `references/quota/cycle-start-actions.md`
- `references/quota/spending.md`
- `references/quota/enforcement.md`
- `references/quota/exclusions.md`

---

## Workflow

### Step 1: Identify Intent

Determine what the user wants to view or do:
- List all quotas
- View a specific quota's configuration
- View user spending data
- View users in scope
- Drop a quota

---

### Step 2: List All Quotas

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` from reference file `references/quota/lifecycle.md`.

---

### Step 3: View Quota Configuration

Retrieve the full configuration using these methods from the reference files:
- `GET_QUOTA_SCOPE` — user scope (from reference file `references/quota/lifecycle.md`)
- `GET_PER_USER_LIMIT` — spending limits (from reference file `references/quota/limits.md`)
- `GET_NOTIFICATION_THRESHOLDS` — thresholds (from reference file `references/quota/notifications.md`)
- `GET_CUSTOM_ACTIONS` — custom actions (from reference file `references/quota/custom-actions.md`)
- `GET_CYCLE_START_ACTION` — cycle-start action (from reference file `references/quota/cycle-start-actions.md`)
- `GET_NOTIFICATION_INTEGRATIONS` — notification integrations (from reference file `references/quota/notifications.md`)
- `GET_ADMIN_EMAILS` — admin emails (from reference file `references/quota/notifications.md`)
- `GET_REFRESH_TIER` — refresh tier (from reference file `references/quota/lifecycle.md`)
- `GET_CONFIG` — also shows `BLOCK_ENFORCEMENT_ENABLED` and `PER_USER_LIMIT_DAILY` when enforcement is enabled (from reference file `references/quota/lifecycle.md`)
- `GET_ACTIVE_BLOCKS` — currently blocked users (from reference file `references/quota/enforcement.md`)

Present results as a summary table:

```
| Setting                 | Value                              |
|-------------------------|------------------------------------|
| Quota Name              | {quota_fqn}                        |
| Per-User Limit          | {limit} credits                    |
| User Scope              | {tags + operator or "ALL_USERS"}   |
| Notification Thresholds | {list or "None configured"}        |
| Custom Actions          | {list or "None configured"}        |
| Cycle-Start Action      | {SP name or "None configured"}     |
| Admin Notifications     | {integration/emails or "None"}     |
| Refresh Tier            | {tier}                             |
| Block Enforcement       | {enabled/disabled or "Not available"} |
| Daily Per-User Limit    | {limit or "Not set"}               |
| Active Blocks           | {count or "None"}                  |
```

---

### Step 4: View User Spending (Optional)

Use `GET_PER_USER_USAGE_PREVIEW` or `GET_SPENDING_DETAILS_BY_USERS` from reference file `references/quota/spending.md`.

---

### Step 5: View Users in Scope (Optional)

Use `GET_USERS` from reference file `references/quota/lifecycle.md`.

---

### Step 6: Suggest Next Steps

- Create a new quota (load `create/SKILL.md`)
- Drop / delete this quota (load `drop/SKILL.md`)
- Configure custom actions (load `custom-actions/SKILL.md`)
- Configure cycle-start reset action (load `cycle-start-actions/SKILL.md`)
- Configure notifications and thresholds (load `notifications/SKILL.md`)
