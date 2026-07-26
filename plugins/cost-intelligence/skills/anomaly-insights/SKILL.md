# Anomaly Insights Skill

Investigate and manage notifications for Snowflake cost anomalies using the `SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS` class.

---

## Step 1: Determine Intent

| Intent | Keywords |
|--------|----------|
| **View / investigate** anomalies | "anomalies", "spike", "unusual spending", "what caused", "which day", "contributors", "investigate", "anomaly trends", "top warehouses", "top queries" |
| **Manage notifications** | "notification", "alert", "email", "notify", "set notification", "add email", "remove email" |

If intent is ambiguous, ask:
```
What would you like to do?
1. Investigate cost anomalies (view anomaly data, drill into spikes)
2. Manage anomaly notification emails
```

---

## Step 2: Determine Access Level

Run all four queries to check which application roles have been granted to the current role:

```sql
SHOW GRANTS OF APPLICATION ROLE SNOWFLAKE.APP_ORGANIZATION_BILLING_VIEWER;
```
```sql
SHOW GRANTS OF APPLICATION ROLE SNOWFLAKE.ORGANIZATION_BILLING_VIEWER;
```
```sql
SHOW GRANTS OF APPLICATION ROLE SNOWFLAKE.APP_USAGE_VIEWER;
```
```sql
SHOW GRANTS OF APPLICATION ROLE SNOWFLAKE.APP_USAGE_ADMIN;
```

For each result, check whether `CURRENT_ROLE()` appears in the `grantee_name` column **and** `granted_to = 'ROLE'`. If so, the current role has that application role.

Record three flags:

- **has_org_access**: `APP_ORGANIZATION_BILLING_VIEWER` or `ORGANIZATION_BILLING_VIEWER` is granted
- **has_account_access**: `APP_USAGE_VIEWER` or `APP_USAGE_ADMIN` is granted
- **has_account_admin**: `APP_USAGE_ADMIN` is granted (subset of `has_account_access`; required for managing account-level notifications)

If **neither** `has_org_access` nor `has_account_access` is true → the user cannot use the `ANOMALY_INSIGHTS` procedures. However, they may still be able to query the `SNOWFLAKE.ACCOUNT_USAGE.ANOMALIES_DAILY` view directly if their role has been granted `APP_USAGE_VIEWER` or `APP_USAGE_ADMIN`. Set a flag **`fallback_view_only = true`** and continue to Step 3 (scope will be forced to **This account** with credits only).

---

## Step 3: Determine Scope

Decide what the user is asking about. There are three possible scopes:

| Scope | Signals |
|-------|---------|
| **All accounts (org-wide)** | "org", "organization", "all accounts", "cross-account", "org-wide" |
| **Specific other account** | User names a particular account (e.g. "account XYZ"), "another account", "different account" |
| **This account** | "my account", "this account", "account-level" |

**Apply these rules in order:**

1. User explicitly asks for **this account** → scope = **This account**
2. User explicitly asks for **a specific other account** → scope = **Specific account** (record the account name)
3. User explicitly asks for **org-wide** AND `has_org_access` → scope = **All accounts**
4. User explicitly asks for **org-wide** or **specific account** BUT `has_org_access` is false → inform the user they lack org-level privileges, fall back to scope = **This account**
5. **Scope is unclear** AND `has_org_access` → **ask the user**:
   "Would you like to see anomalies for this account only, or across all accounts in your organization?"
   Then set scope based on their answer.
6. **Scope is unclear** AND NOT `has_org_access` → scope = **This account**
7. **`fallback_view_only` is true** → scope is forced to **This account** (inform the user if they asked for org-wide or a specific account that they lack the required privileges for those scopes)

---

## Step 4: Resolve Procedure

Two procedures exist for fetching anomaly data, plus a **fallback view**. They differ in **unit** and **access requirements**:

| Source | Unit | Required Access | Supports |
|--------|------|-----------------|----------|
| `GET_ACCOUNT_ANOMALIES_IN_CREDITS` | Credits | `has_account_access` | This account only |
| `GET_DAILY_CONSUMPTION_ANOMALY_DATA` | Currency (USD, etc.) | `has_org_access` | This account, all accounts, or a specific account |
| `SNOWFLAKE.ACCOUNT_USAGE.ANOMALIES_DAILY` view | Credits | `APP_USAGE_VIEWER` or `APP_USAGE_ADMIN` | This account only (last resort) |

Use the scope from Step 3 and the access flags from Step 2 to select the procedure:

| Scope | `has_org_access` | `has_account_access` | `fallback_view_only` | Source | 3rd Argument |
|-------|-------------------|----------------------|----------------------|--------|--------------|
| **All accounts** | true | — | — | `GET_DAILY_CONSUMPTION_ANOMALY_DATA` | `NULL` |
| **Specific account** | true | — | — | `GET_DAILY_CONSUMPTION_ANOMALY_DATA` | `'<account_name>'` |
| **This account** | true | — | — | `GET_DAILY_CONSUMPTION_ANOMALY_DATA` | `'<current_account>'` ★ |
| **This account** | false | true | — | `GET_ACCOUNT_ANOMALIES_IN_CREDITS` | n/a |
| **This account** | false | false | true | `ANOMALIES_DAILY` view | n/a |

★ When using `GET_DAILY_CONSUMPTION_ANOMALY_DATA` for the current account, resolve the account name first:

```sql
SELECT CURRENT_ACCOUNT_NAME();
```

Then pass that value as the 3rd argument.

> **Note:** When the user has org-level access and asks about "this account", prefer `GET_DAILY_CONSUMPTION_ANOMALY_DATA` because it provides currency values. Only use `GET_ACCOUNT_ANOMALIES_IN_CREDITS` when the user explicitly requests credits or lacks org-level access.

---

## Step 5: Route to Sub-Skill

Pass the resolved **scope**, **procedure**, and **3rd argument** (if applicable) as context when loading the sub-skill.

| Intent | Load |
|--------|------|
| View / investigate | `view-anomalies/SKILL.md` |
| Notify | Route using the role-based rules below |

For **Notify** intent, route based on the user's **access flags** (not scope):

1. User has **both** `has_account_admin` **and** `has_org_access` → **ask the user**:
   "Which notification list would you like to manage?"
   - Account-level notifications (alerts when this account's spend is anomalous)
   - Org-level notifications (alerts when aggregate spend across all accounts is anomalous)
   Then route based on their answer.
2. User has only `has_org_access` → `notify-org-anomalies/SKILL.md`
3. User has only `has_account_admin` → `notify-account-anomalies/SKILL.md`
4. User has `has_account_access` but **not** `has_account_admin` (i.e. `APP_USAGE_VIEWER` only), and **no** `has_org_access` → inform the user they lack privileges to manage either notification list and stop.

**Do NOT execute any further SQL until you have loaded the appropriate sub-skill.**

---

## Reference Files

| Topic | File |
|-------|------|
| Top contributing resources per anomaly day (`ANOMALIES_DAILY` + `METERING_HISTORY`) | `references/queries/anomalies.md` |
