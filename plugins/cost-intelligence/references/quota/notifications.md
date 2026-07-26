# Quota Notifications

Methods for configuring notification thresholds, integrations, and admin emails.

**Semantic keywords:** notification threshold, projected spend, actual spend, admin email, notification integration, notify user

---

## ADD_NOTIFICATION_THRESHOLD

```sql
CALL {quota_fqn}!ADD_NOTIFICATION_THRESHOLD({threshold}, '{spend_strategy}', {notify_user});
```

> **Prerequisites**:
> 1. The caller must have the **ADMIN** role on the quota instance.
> 2. Maximum 10 notification thresholds per quota.

**Parameters:**
- `threshold`: NUMBER — percentage of per-user limit (e.g., 50, 80, 100)
- `spend_strategy`: VARCHAR — `'PROJECTED'` or `'ACTUAL'`
- `notify_user`: BOOLEAN — whether to notify the user via email (`TRUE` or `FALSE`)


**Examples:**
```sql
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(50, 'PROJECTED', TRUE);
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(80, 'ACTUAL', TRUE);
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_THRESHOLD(90, 'ACTUAL', FALSE);
```

## REMOVE_NOTIFICATION_THRESHOLD

```sql
CALL {quota_fqn}!REMOVE_NOTIFICATION_THRESHOLD({threshold}, '{spend_strategy}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `threshold`: NUMBER — the threshold percentage to remove
- `spend_strategy`: VARCHAR — `'PROJECTED'` or `'ACTUAL'`


## GET_NOTIFICATION_THRESHOLDS

```sql
CALL {quota_fqn}!GET_NOTIFICATION_THRESHOLDS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `THRESHOLD` (NUMBER) — the configured threshold percentage
- `SPEND_STRATEGY` (VARCHAR) — `PROJECTED` or `ACTUAL`
- `NOTIFY_USER` (BOOLEAN) — whether the user is notified when breached
- `ADDED_TIMESTAMP` (TIMESTAMP_TZ) — when the threshold was configured

---

## ADD_NOTIFICATION_INTEGRATION

```sql
CALL {quota_fqn}!ADD_NOTIFICATION_INTEGRATION('{integration_name}');
```

> **Prerequisites**:
> 1. The caller must have the **ADMIN** role on the quota instance.
> 2. The integration must be granted to the Snowflake database: `GRANT USAGE ON INTEGRATION {name} TO DATABASE SNOWFLAKE;`

**Parameters:**
- `integration_name`: STRING — name of a notification integration (SNS or webhook type only; email integrations are not supported here)


**Examples:**
```sql
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_INTEGRATION('my_sns_integration');
CALL my_db.my_schema.my_quota!ADD_NOTIFICATION_INTEGRATION('my_slack_webhook');
```

## REMOVE_NOTIFICATION_INTEGRATION

```sql
CALL {quota_fqn}!REMOVE_NOTIFICATION_INTEGRATION('{integration_name}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `integration_name`: STRING — name of the integration to remove


## GET_NOTIFICATION_INTEGRATIONS

```sql
CALL {quota_fqn}!GET_NOTIFICATION_INTEGRATIONS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `INTEGRATION_NAME` (STRING) — name of the configured notification integration
- `LAST_NOTIFICATION_TIME` (TIMESTAMP_TZ) — last time a notification was sent via this integration
- `ADDED_TIMESTAMP` (TIMESTAMP_TZ) — when the integration was configured

---

## SET_ADMIN_EMAILS

```sql
CALL {quota_fqn}!SET_ADMIN_EMAILS('{admin_emails}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `admin_emails`: VARCHAR — comma-separated list of email addresses (e.g., `'admin1@company.com, admin2@company.com'`)


## GET_ADMIN_EMAILS

```sql
CALL {quota_fqn}!GET_ADMIN_EMAILS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- VARCHAR — comma-separated list of configured admin email addresses
