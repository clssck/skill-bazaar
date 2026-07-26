---
name: openflow-setup-main
description: Initialize Openflow CLI access. Ensures tooling, cache, and profiles are ready. Use when setting up for the first time, switching connections, or troubleshooting connectivity.
---

# Openflow Setup

This reference ensures the environment is ready for Openflow operations. Follow the steps in order; each step fills in what's missing.

## Step 1: Verify Tooling

```bash
which snow && which nipyapi && which python3
```

| Result | Action |
|--------|--------|
| Any tool missing | **STOP.** Load `references/setup-tooling.md` and follow its instructions. Do NOT install tools using general knowledge -- the reference contains required configuration (e.g., package extras, install method) that differs from standard installation. Return here after tooling is verified. |
| All found | Continue to Step 1b |

### Step 1b: Ensure Tooling in Cache

If a cache file exists but has no `tooling` section, add it now with the commands you just verified:

```bash
# Check if tooling section exists
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json 2>/dev/null | jq '.tooling'
```

| Result | Action |
|--------|--------|
| Returns null | Update the cache with tooling section (see below) |
| Returns object | Continue to Step 2 |

**Update cache with tooling:**
```bash
jq '.tooling = {preferred: "nipyapi", python_command: "python3", pip_command: "<PIP_CMD>", updated_at: "<TIMESTAMP>"}' \
  ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json > tmp && mv tmp ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json
```

Replace `<PIP_CMD>` with `uv pip` if uv is installed, otherwise `pip3`.

## Step 2: Check Cache and Select Connection

```bash
ls ~/.snowflake/cortex/memory/openflow_infrastructure_*.json 2>/dev/null
```

| Result | Action |
|--------|--------|
| No cache files | Go to Step 2a (select connection and discover) |
| One cache file | Use that connection, continue to Step 3 |
| Multiple cache files | Ask user: "Which connection?" then continue to Step 3 |

### Step 2a: Select Snowflake Connection (No Cache)

```bash
snow connection list --format json | jq -r '.[] | "\(.connection_name)\(if .is_default then " (default)" else "" end)"'
```

| Result | Action |
|--------|--------|
| Single connection | Use it |
| Multiple connections | Ask: "Which Snowflake connection for Openflow?" |

Test the selected connection:

```bash
snow connection test -c <CONNECTION>
```

| Result | Action |
|--------|--------|
| Success | Continue to Step 2b |
| Fails | STOP. Tell user: "Fix Snowflake connection with `snow connection add` or check credentials and networking" |

### Step 2b: Discover Infrastructure

Load `references/setup-discovery.md` to find deployments and runtimes, then continue to Step 3.

## Step 3: Validate Cache Contents

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json | jq '{
  runtimes: [.deployments[].runtimes[] | {name: .runtime_name, profile: .nipyapi_profile}]
}'
```

| Result | Action |
|--------|--------|
| No runtimes listed | Load `references/setup-discovery.md`, then continue |
| Runtimes exist but no `nipyapi_profile` values | Go to Step 4 |
| Runtimes with profiles | Continue to Step 5 |

## Step 4: Create Profiles

Load `references/setup-auth.md` to create nipyapi profiles, then continue to Step 5.

## Step 5: Select Runtime

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json | jq -r '.deployments[].runtimes[] | "\(.runtime_name): \(.nipyapi_profile)"'
```

| Result | Action |
|--------|--------|
| Single runtime | Use that profile |
| Multiple runtimes | Ask: "Which runtime do you want to work with?" |

## Step 6: Verify Connectivity

```bash
nipyapi --profile <PROFILE> system get_nifi_version_info
```

| Result | Action |
|--------|--------|
| Returns NiFi version | **Setup complete.** Return to main skill. |
| 401/403 error | Token expired. Load `references/setup-auth.md` to refresh PAT. |
| Connection refused | Runtime may be stopped. Offer to resume: `ALTER OPENFLOW RUNTIME <db>.<schema>.<name> RESUME;` (ask user permission first). If unavailable or pre-SOM, check Openflow Control Plane UI. |
| "Cannot find key: --profile" | nipyapi outdated. Load `references/setup-tooling.md` to reinstall. |

## Setup Complete

The environment is ready:
- Connection name is in the cache `connection` field
- Profile name is in the cache `nipyapi_profile` field for the selected runtime

Return to the main skill for routing, or to `references/core-session.md` if validating session state.

## Related References

- `references/setup-tooling.md` - Install missing tools
- `references/setup-discovery.md` - Discover Openflow infrastructure
- `references/setup-auth.md` - Create nipyapi profiles
- `references/core-session.md` - Cache schema and session workflow
