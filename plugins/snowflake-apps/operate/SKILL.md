---
name: snowflake-apps-operate
description: "Post-deploy operations for Snowflake Apps: logs, status, suspend/resume, upgrade, rollback. Use when the user wants to monitor, troubleshoot, or manage a running app service."
---

# Operate Snowflake App

Use this skill when the user wants to monitor, troubleshoot, or manage a deployed Snowflake App service.

> Operations below use SQL, which works in any environment. Some also have a `snow app` CLI equivalent — prefer it when available, and fall back to SQL if the CLI is unavailable or its session token has expired.

> **Confirm first**: Always confirm with the user before any destructive or user-visible operation — suspend, restart, upgrade, rollback, drop, rename, teardown, or persistent property changes. These take the service offline or cause a brief interruption for all users.

## Check Service Status

### Quick status

```sql
DESCRIBE APPLICATION SERVICE <database>.<schema>.<app_name>;
```

Key columns:

| Column | What to look for |
|--------|------------------|
| `status` | `RUNNING` = healthy; `SUSPENDED` = paused; `SUSPENDING` = transitioning to suspended; `FAILED` = fatal error; `PENDING` = starting up; `DONE` = job service completed; `DELETING` = drop in progress; `INTERNAL_ERROR` = platform-level error |
| `url` | Public endpoint; empty or "provisioning in progress" = not ready yet |
| `is_upgrading` | `true` during an upgrade; if stuck, the upgrade may have failed |
| `compute_pool` | Empty string when managed pools are active (expected) |
| `source` | JSON: `artifactRepository`, `package`, `version`, `alias` |
| `auto_resume` | `true` = resumes automatically; default is `true` |
| `auto_suspend_secs` | `0` = never auto-suspend; minimum non-zero value is 300 |

### List all services

```sql
-- All services in a schema
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema>;

-- Filter by name pattern
SHOW APPLICATION SERVICES LIKE '<pattern>' IN SCHEMA <database>.<schema>;

-- All in account
SHOW APPLICATION SERVICES IN ACCOUNT;

-- Additional filter options
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema> STARTS WITH '<prefix>';
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema> LIMIT 10;
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema> LIMIT 10 FROM '<name>'; -- exclusive resume
```

`SHOW APPLICATION SERVICES` returns 21 columns:
`created_on`, `name`, `status`, `database_name`, `schema_name`, `query_warehouse`, `compute_pool`, `url`, `privatelink_url`, `owner`, `owner_role_type`, `created_by`, `source`, `resumed_on`, `suspended_on`, `is_upgrading`, `auto_resume`, `auto_suspend_secs`, `external_access_integrations`, `comment`, `additional_properties`

> Application services are invisible in `SHOW SERVICES`. Always use `SHOW APPLICATION SERVICES`.

---

## View Logs

### SQL

```sql
-- Single-argument form (returns recent logs)
CALL SYSTEM$GET_APPLICATION_SERVICE_LOGS('<database>.<schema>.<app_name>');

-- With explicit line count
CALL SYSTEM$GET_APPLICATION_SERVICE_LOGS('<database>.<schema>.<app_name>', 500);
```

Requires `MONITOR` privilege on the application service.

### Structured logs from event table

When an event table is configured (`ALTER ACCOUNT SET EVENT_TABLE = <fqn>`), use this function to query structured log, metric, and event records:

```sql
-- LOG records (container stdout/stderr)
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'LOG'
);

-- With time window
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'LOG',
    '<start_timestamp>',
    '<end_timestamp>'
);

-- METRIC records (CPU, memory, custom metrics)
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'METRIC'
);

-- EVENT records (container lifecycle events)
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'EVENT'
);
```

Returns a JSON array-of-arrays. Column order per record type:

| Type | Columns |
|------|---------|
| `LOG` | `TIMESTAMP, INSTANCE_ID, CONTAINER_NAME, LOG, RECORD_ATTRIBUTES` |
| `METRIC` | `TIMESTAMP, METRIC_NAME, VALUE, UNIT, INSTANCE_ID, CONTAINER_NAME, RESOURCE, RECORD, RECORD_ATTRIBUTES` |
| `EVENT` | `TIMESTAMP, SEVERITY, EVENT_NAME, EVENT_DETAILS, INSTANCE_ID, CONTAINER_NAME, RECORD, RECORD_ATTRIBUTES` |

For large result sets, pass `'true'` as the fifth argument to get a query UUID instead of inline data, then retrieve the full results with `RESULT_SCAN`:

```sql
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>', 'LOG',
    '1970-01-01 00:00:00', '2999-12-31 23:59:59', 'true'
);
-- Returns a UUID string; retrieve full results:
SELECT * FROM TABLE(RESULT_SCAN('<uuid>'));
```

Requires `MONITOR` privilege on the application service. The function queries the event table via the service's internal owner role; callers do not need direct access to the event table itself.

---

## Suspend and Resume

```sql
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> SUSPEND;
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> RESUME;
```

Requires `OPERATE` privilege (or `OWNERSHIP`).

### Auto-suspend and auto-resume

```sql
-- Enable auto-suspend after 10 minutes idle (minimum non-zero: 300 seconds)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    SET AUTO_SUSPEND_SECS = 600;

-- Disable auto-suspend (resets to 0 = never)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UNSET AUTO_SUSPEND_SECS;

-- Disable auto-resume
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    SET AUTO_RESUME = FALSE;

-- Re-enable auto-resume (resets to true)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UNSET AUTO_RESUME;
```

---

## Upgrade

```sql
-- Upgrade to the latest version (re-resolves the stored alias)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> UPGRADE;

-- Upgrade to a specific version or alias
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UPGRADE TO VERSION <version_or_alias>;
```

Requires `OPERATE` privilege (or `OWNERSHIP`). During upgrade, `is_upgrading = 'true'` in DESCRIBE output. The service URL does not change.

---

## Modify Properties

```sql
-- Set one or more properties
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> SET
    QUERY_WAREHOUSE = <warehouse>
    AUTO_SUSPEND_SECS = 600
    COMMENT = 'my comment';

-- Set external access integrations
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> SET
    EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>);

-- WARNING: SET EXTERNAL_ACCESS_INTEGRATIONS replaces the entire list.
-- If the service already has EAIs configured, include all of them in
-- the new list or they will be silently removed.

-- Unset properties (reverts to defaults)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UNSET QUERY_WAREHOUSE;

-- IF EXISTS variant (succeeds silently when service does not exist)
ALTER APPLICATION SERVICE IF EXISTS <database>.<schema>.<app_name>
    SET COMMENT = 'test';
```

UNSET defaults:

| Property | Default after UNSET |
|----------|--------------------|
| `AUTO_RESUME` | `true` |
| `AUTO_SUSPEND_SECS` | `0` (disabled) |
| `COMMENT` | `NULL` |
| `QUERY_WAREHOUSE` | `NULL` |
| `EXTERNAL_ACCESS_INTEGRATIONS` | `[]` |

Requires `OPERATE` privilege for SET/UNSET. `OWNERSHIP` allows all operations.

---

## Rename

The service URL does not change, but any stored references to the service by its old fully-qualified name will break.

```sql
ALTER APPLICATION SERVICE <old_fqn> RENAME TO <new_fqn>;
```

- Works cross-schema and cross-database
- The public URL **does not change** after rename
- Cannot rename into or out of a personal database (`USER$.PUBLIC`)

Requires `OWNERSHIP` privilege.

---

## Share / Grant Access

Use `APPLICATION SERVICE` as the object type — not `SERVICE`. `SERVICE` targets plain SPCS services and fails with "does not exist or not authorized" even when the app exists.

```sql
-- Allow a role to open the app (access the endpoint)
GRANT USAGE ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <role>;

-- Allow a role to view logs and status
GRANT MONITOR ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <role>;

-- Allow a role to suspend/resume/upgrade
GRANT OPERATE ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <role>;
```

For the full pre-deploy and post-deploy grant list, see `../references/permissions.md`.

---

## Open the App

Requires `USAGE` privilege on the application service. Get the URL via SHOW:

```sql
SHOW APPLICATION SERVICES LIKE '<app_name>' IN SCHEMA <database>.<schema>;
-- Read the 'url' column from the result
```

---

## Drop

There is no `UNDROP APPLICATION SERVICE`; dropped services cannot be recovered.

```sql
DROP APPLICATION SERVICE IF EXISTS <database>.<schema>.<app_name>;
```

Requires `OWNERSHIP` privilege.

---

## Restart

Restart = SUSPEND then RESUME (see [Suspend and Resume](#suspend-and-resume) above). Requires `OPERATE` privilege (or `OWNERSHIP`).

---

## Rollback

Rolling back means upgrading to an earlier version. First check available versions:

```sql
SHOW VERSIONS IN ARTIFACT REPOSITORY <database>.<schema>.<repo_name>
  FOR PACKAGE <package_name>;
```

Then upgrade to the target version:

```sql
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UPGRADE TO VERSION <version_string>;
```

Requires `OPERATE` privilege (or `OWNERSHIP`). The `version_string` comes from the `version` column of the SHOW VERSIONS output.

---

## Teardown

Drops the application service and cannot be undone. Requires `OWNERSHIP` of the application service. Use the SQL `DROP` above; a `snow app teardown` CLI command also exists where the CLI is available (it additionally clears the code stage or workspace subdirectory — the artifact repository and its built packages are not deleted).

---

## Common Issues

See `references/debugging.md` for the full debugging guide covering deploy failures, RBAC diagnostics, build log retrieval, and the end-to-end debugging checklist.
