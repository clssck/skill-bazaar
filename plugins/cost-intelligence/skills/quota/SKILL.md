# Quota Management Skill

Manage Snowflake Quotas to monitor and control per-user spending. Quotas define monthly per-user credit limits within a specified database and schema, with notifications and custom actions when thresholds are breached.

> **Quota Syntax Warning**
> Quotas are **class instances**, NOT standard objects. Never use `SHOW QUOTAS` — it will fail.
> - Correct: `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN SCHEMA <db.schema>` or `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN ACCOUNT`
> - Wrong: `SHOW QUOTAS LIKE '...'`

> **Scope Homogeneity Rule**
> A quota's scope must be homogeneous in usage unit:
> - **AI-credit domains**: AI Functions, Cortex Agents, Snowflake Intelligence, Cortex Code — OR
> - **Credit (compute) domains**: Warehouses
> - **Never mix** AI-credit and compute domains in the same quota.
> If the user tries to combine them, the error is raised at config time. They need separate quotas for each usage unit.

> **Quota vs Budget Disambiguation**
> - **Budget**: Monitors spending, sends alerts — does NOT limit usage. Can track resources and tags.
> - **Quota**: Monitors per-user spending, sends notifications, and triggers custom actions when thresholds are breached. Scoped to users (via user tags), not resources.
> If the user asks about "spending limits" generically, clarify: "Do you want alerting only (budget) or per-user spending controls with notifications and custom actions (quota)?"

---

## Key Concepts

- **Per-user limit**: A single scalar credit limit applied equally to every user in scope.
- **Monthly cycle**: UTC calendar month, aligned with Snowflake billing. Resets on 1st of each month at 00:00 UTC.
- **User scope**: Defined via user tags. Resolved dynamically at evaluation time.
- **Refresh latency**: Measurement interval depends on the configured refresh tier.

---

## Routing

Detect user intent and **load the corresponding sub-skill or reference file** before proceeding.

| Intent | Keywords | Route |
|--------|----------|-------|
| **Create** a new quota | "create quota", "new quota", "set up quota" | `create/SKILL.md` |
| **Set/change user scope** | "set users", "user tags", "quota scope", "ALL_USERS" | `references/quota/lifecycle.md` |
| **Set/change limit** | "spending limit", "per-user limit", "monthly limit", "set limit", "change limit" | `references/quota/limits.md` |
| **View shared resources** | "view shared resources", "list resources", "which resources" | `view-shared-resources/SKILL.md` |
| **Add/remove shared resources** | "add resource", "remove resource", "domain scope" | `references/quota/shared-resources.md` |
| **View exclusions** | "view exclusions", "who is excluded", "excluded users", "list excluded" | `view-exclusions/SKILL.md` |
| **Exclude users** | "exclude users", "exempt users" | `references/quota/exclusions.md` |
| **Notifications & thresholds** | "notification", "threshold", "admin email", "notify user", "projected spend", "actual spend" | `notifications/SKILL.md` |
| **Custom actions** | "custom action", "stored procedure", "trigger SP" | `custom-actions/SKILL.md` |
| **Block enforcement** | "enforcement", "block", "suspend", "daily limit", "active blocks", "enforcement history", "unblock" | `references/quota/enforcement.md` |
| **Cycle-start actions** | "cycle start", "reset action", "cycle reset", "monthly reset", "re-enable users" | `cycle-start-actions/SKILL.md` |
| **View / status / spending** | "show quota", "list quotas", "quota config", "quota status", "get limit", "get scope", "spending summary", "user spending", "usage details", "spending details" | `status/SKILL.md` |
| **Drop / delete** | "drop quota", "delete quota", "remove quota" | `drop/SKILL.md` |

If the intent is ambiguous, ask the user:
```
What would you like to do with quotas?
1. Create a new quota (define per-user spending controls)
2. Set up notifications and thresholds
3. Configure custom actions (stored procedures triggered on breach)
4. Configure cycle-start reset actions
5. View quota status or spending data
6. Drop / delete a quota
7. Configure block enforcement (enable blocking, daily limits, view blocks, exclude users)
8. View or manage shared resources
9. View or manage user exclusions
```

**Do NOT execute any SQL until you have loaded the appropriate sub-skill or reference file.**

---

## Interaction Rules (applies to all sub-skills)

- **Privileges**: Quota methods require a class role on the quota instance. Write operations (SET, ADD, REMOVE) require the **ADMIN** role (`GRANT snowflake.core.QUOTA ROLE {quota_fqn}!ADMIN TO ...`). Read operations (GET) require at minimum the **VIEWER** role (`GRANT snowflake.core.QUOTA ROLE {quota_fqn}!VIEWER TO ...`).
- **Confirm before executing**: Confirm collected values with the user before running SQL. Get explicit approval for the full script.
- **Tag resolution**: If the user provides only a tag name, resolve it to fully qualified form by querying `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES` (e.g., `SELECT TAG_DATABASE, TAG_SCHEMA, TAG_NAME FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES WHERE TAG_NAME ILIKE '<user_tag>' AND DOMAIN = 'USER' LIMIT 1`).
- **Check allowed values**: After resolving a tag's FQN, always run `SHOW TAGS LIKE '...' IN SCHEMA ...` to check for allowed values before using a tag value.
- **Sequential execution**: CREATE must complete before any method calls. Execute statements one at a time.
