# Quota Lifecycle & Configuration

Methods for creating, dropping, listing quotas, and managing configuration/refresh settings.

**Semantic keywords:** create quota, drop quota, list quotas, show quota, refresh tier, get config

---

## Create

```sql
USE SCHEMA {database}.{schema};
CREATE SNOWFLAKE.CORE.QUOTA {quota_name}();
```

## Drop

```sql
DROP SNOWFLAKE.CORE.QUOTA {database}.{schema}.{quota_name};
```

## List

```sql
SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN ACCOUNT;
SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN SCHEMA {database}.{schema};
```

---

## User Scope

### SET_USER_TAGS

Atomic, idempotent — overwrites all existing tags. The full desired set of tags must be provided each time; to add a tag, include all existing tags plus the new one.

```sql
CALL {quota_fqn}!SET_USER_TAGS(
    [
        [(SELECT SYSTEM$REFERENCE('TAG', '{db}.{schema}.{tag_name}', 'SESSION', 'APPLYBUDGET')), '{tag_value}']
    ],
    '{operator}'
);
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `db`: the database containing the tag
- `schema`: the schema containing the tag
- `tag_name`: the tag name (e.g., `TEAM_TAG`, `ENV_TAG`)
- `tag_value`: the tag value to match (e.g., `'finance'`, `'prod'`)
- `operator`: VARCHAR — determines how multiple tags combine


**Operators:**
- `UNION` (default): Users matching ANY tag are included
- `INTERSECTION`: Users must match ALL tags
- `ALL_USERS`: Every user in the account is in scope. Any tags passed alongside this operator are stored but have no filtering effect.

**Examples:**
```sql
-- Two tags with UNION (users matching either tag are included)
CALL my_db.my_schema.my_quota!SET_USER_TAGS(
    [
        [(SELECT SYSTEM$REFERENCE('TAG', 'my_db.tags.team_tag', 'SESSION', 'APPLYBUDGET')), 'finance'],
        [(SELECT SYSTEM$REFERENCE('TAG', 'my_db.tags.env_tag', 'SESSION', 'APPLYBUDGET')), 'prod']
    ],
    'UNION'
);

-- All users in account
CALL my_db.my_schema.my_quota!SET_USER_TAGS([], 'ALL_USERS');

-- Clear all tags (no users in scope)
CALL my_db.my_schema.my_quota!SET_USER_TAGS([], 'UNION');
```

### GET_QUOTA_SCOPE

```sql
CALL {quota_fqn}!GET_QUOTA_SCOPE();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- VARIANT — a JSON object describing the quota's user scope. Structure:

```json
{
  "user_tags": {
    "operator": "UNION",        // or "INTERSECTION" or "ALL_USERS"
    "tags": [
      {
        "tagName": "TEAM_TAG",
        "tagDatabase": "MY_DB",
        "tagSchema": "TAGS",
        "tagId": 12345,
        "tagValues": ["finance"]
      },
      {
        "tagName": "ENV_TAG",
        "tagDatabase": "MY_DB",
        "tagSchema": "TAGS",
        "tagId": 12346,
        "tagValues": ["prod"]
      }
    ]
  }
}
```

When no tags are configured, `tags` is an empty array. The object does not contain `resource_tags`, `resources`, or `shared_resources` fields (those are budget-only).

### GET_USERS

```sql
CALL {quota_fqn}!GET_USERS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `USER_ID` (NUMBER) — the user's ID
- `USER_NAME` (VARCHAR) — the user's name

---

## Configuration

### GET_CONFIG

```sql
CALL {quota_fqn}!GET_CONFIG();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `QUOTA_ID` (NUMBER) — the quota's local identifier
- `PER_USER_LIMIT` (NUMBER) — the configured per-user credit limit (NULL if not set)
- `REFRESH_TIER` (VARCHAR) — the measurement interval (default `TIER_6H`)
- `USER_TAG_MODE` (VARCHAR) — the operator for user tags (`UNION`, `INTERSECTION`, or `ALL_USERS`)
- `ADMIN_EMAILS` (VARCHAR) — comma-separated admin email addresses (NULL if not set)
- `ADMIN_LAST_SENT_AT` (TIMESTAMP_TZ) — last time an admin notification was sent
- `BLOCK_ENFORCEMENT_ENABLED` (BOOLEAN) — whether block enforcement is enabled for this quota instance
- `PER_USER_LIMIT_DAILY` (NUMBER) — the configured daily per-user credit limit (NULL if not set)

> **Note**: The `BLOCK_ENFORCEMENT_ENABLED` and `PER_USER_LIMIT_DAILY` columns are only visible when the account parameter `ENABLE_QUOTA_BLOCK_ENFORCEMENT` is TRUE. When the parameter is not set, these columns are hidden from the response.

### SET_REFRESH_TIER

```sql
CALL {quota_fqn}!SET_REFRESH_TIER('{refresh_tier}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `refresh_tier`: VARCHAR — `'TIER_1H'` (30 min measurement interval) or `'TIER_6H'` (6 hour interval)


> **Note**: Notifications and threshold evaluations are delayed by up to the refresh interval. There is no real-time or event-driven evaluation.

### GET_REFRESH_TIER

```sql
CALL {quota_fqn}!GET_REFRESH_TIER();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- VARCHAR — the currently configured refresh tier (e.g., `TIER_1H` or `TIER_6H`).
