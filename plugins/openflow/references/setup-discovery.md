---
name: openflow-setup-discovery
description: Discover Openflow deployments and runtimes for the current Snowflake connection. Load when cache is missing or incomplete.
---

# Infrastructure Discovery

Discover Openflow deployments and runtimes, then write results to cache.

## Prerequisites

The setup workflow has already selected `CONNECTION`. Use that value with `-c <CONNECTION>` for all `snow sql` commands.

For diagnostic queries (Alternative Discovery section), you may also need the `event_table` from the cache. If the cache exists, check:

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json | jq '.deployments[].event_table'
```

## Step 1: Find Deployments and Runtimes

Run both queries together before drawing any conclusions:

```bash
snow sql -c <CONNECTION> -q "SHOW OPENFLOW DEPLOYMENTS;" --format json
snow sql -c <CONNECTION> -q "SHOW OPENFLOW RUNTIMES IN ACCOUNT;" --format json
```

| Deployments | Runtimes | Action |
|-------------|----------|--------|
| Found | Found | Extract info from both, continue to Step 2 |
| Found | Empty | Unusual. Ask: "I found deployments but no runtimes. Is a runtime being provisioned or recently removed?" |
| Empty | Found | Ask: "I found runtimes but no deployments. Do you believe OpenFlow is deployed in this account? The account may have a non-standard configuration." |
| Empty | Empty | Ask: "I did not find OpenFlow deployments or runtimes in this account. Do you believe OpenFlow should be deployed here? If so, check Ingestion > OpenFlow in Snowsight." |
| Permissions error | any | User/Role lacks grants. Tell user to check Openflow permissions in Snowflake. |

**Never conclude "not deployed" without asking the user first.** Queries may return empty due to role permissions, deployment state, or non-standard configurations.

**Note for pre-SOM accounts:** If `SHOW OPENFLOW DEPLOYMENTS` returns an error, the account may use the legacy integration model. Use `SHOW OPENFLOW DATA PLANE INTEGRATIONS` and `SHOW OPENFLOW RUNTIME INTEGRATIONS` instead and follow the legacy discovery path.

### Deployment Details

For each deployment from `SHOW OPENFLOW DEPLOYMENTS`, note:
- `name` — deployment name
- `type` — `SNOWFLAKE` (SPCS) or `BYOC`
- `key` — deployment key (internal identifier)
- `custom_ingress_hostname` — BYOC custom ingress host (may be null)

## Step 2: Extract Runtime Details

For each runtime from `SHOW OPENFLOW RUNTIMES IN ACCOUNT`, describe it to get the URL and role:

```bash
snow sql -c <CONNECTION> -q "DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>;" --format json
```

Extract from `DESCRIBE` output:
- `server_url` — full NiFi server URL (e.g. `https://host:443/runtime-key/nifi/`)
- `execute_as_role` — the Snowflake role used for managed token auth
- `key` — runtime key used in API paths

Construct the NiFi API URL by replacing the trailing `nifi/` with `nifi-api`:
```
https://host:443/runtime-key/nifi-api
```

Note: runtimes are schema-qualified objects (`<database>.<schema>.<name>`). Use the `database_name` and `schema_name` from `SHOW OPENFLOW RUNTIMES IN ACCOUNT` to construct the full name.

### Detect Deployment Type from URL

| Pattern | Type |
|---------|------|
| Host starts with `of--` | SPCS |
| Host contains `snowflake-customer.app` | BYOC |

## Step 3: Write Cache

Create cache directory if not exists:

```bash
mkdir -p ~/.snowflake/cortex/memory
```

Update the cache file with the `deployments` section (merge with existing cache):

```bash
jq '.discovered_at = "<ISO_TIMESTAMP>" | .deployments = [<DEPLOYMENTS_ARRAY>]' \
  ~/.snowflake/cortex/memory/openflow_infrastructure_${CONNECTION}.json > tmp && mv tmp ~/.snowflake/cortex/memory/openflow_infrastructure_${CONNECTION}.json
```

**Deployments structure:**

```json
{
  "deployment_name": "<name>",
  "deployment_type": "<spcs|byoc>",
  "deployment_key": "<key>",
  "event_table": "<table>",
  "runtimes": [
    {
      "runtime_name": "<db>.<schema>.<name>",
      "runtime_key": "<key>",
      "execute_as_role": "<role>",
      "url": "https://<host>/<key>/nifi-api",
      "nipyapi_profile": "<profile-name>"
    }
  ]
}
```

Notes:
- Runtime name is schema-qualified: `<database>.<schema>.<name>`
- `execute_as_role` is the managed token role (from `DESCRIBE OPENFLOW RUNTIME`)
- `nipyapi_profile` is added by the auth step, not discovery
- `tooling` section is managed by setup-tooling, not discovery
- See `references/core-session.md` for full cache schema

### Legacy Cache Fields (pre-SOM accounts)

Existing caches written before SOM will use different field names. When reading a cache, both schemas are valid:

| Legacy field | SOM field | Notes |
|---|---|---|
| `data_plane_integration` | `deployment_name` | Deployment identifier |
| `data_plane_id` | `deployment_key` | Internal key |
| `runtime_integration` | `runtime_name` | Runtime identifier (SOM name is schema-qualified) |
| `runtime_role` | `execute_as_role` | Role for Snowflake auth |
| `admin_role` | _(removed)_ | No equivalent in SOM |

If you read a cache with legacy fields, treat them as valid and do not re-discover unless the user asks. If you need to refresh the cache on a SOM account, write the new schema — old fields will be replaced when you overwrite the `deployments` array.

## Alternative: Discovery from Event Table

If `SHOW OPENFLOW RUNTIMES IN ACCOUNT` returns unexpected results, query the event table directly:

```sql
SELECT DISTINCT
  RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING as namespace,
  REGEXP_SUBSTR(RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING, 'runtime-(.+)', 1, 1, 'e', 1) as runtime_name
FROM <event_table>
WHERE RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING ILIKE 'runtime-%'
  AND TIMESTAMP >= DATEADD(day, -7, CURRENT_TIMESTAMP())
```

**Note:** This may reveal:
- Incompletely deployed runtimes that emitted events before failing
- Previously removed runtimes that still have event history
- Runtimes not yet registered as integrations

Compare results with the integration list to identify discrepancies for investigation. See `references/platform-diagnostics.md` for runtime troubleshooting.

## Next Step

After writing cache, **continue** to `references/setup-main.md` Step 3 to validate the cache and create nipyapi profiles.

Do not stop here - the setup is not complete until profiles are created and connectivity is verified.
