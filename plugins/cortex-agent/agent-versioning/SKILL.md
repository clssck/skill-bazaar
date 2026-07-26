---
name: agent-versioning
description: "Cortex Agent versioning: commit versions, set aliases, set default version, run versioned agents. Use when: commit LIVE version, VERSION$, SHOW VERSIONS, set alias, default version, versioned run API, ALTER AGENT COMMIT, drop version. NOT for creating new agents (use create-cortex-agent) or modifying LIVE spec (use edit-cortex-agent)."
---

# Cortex Agent Versioning

## Setup

1. **Load** `references/sql-reference.md` when working with SQL commands (CREATE, ALTER, SHOW VERSIONS, DESCRIBE, stage ops)
2. **⚠️ MANDATORY — Load** `references/versioned-run-api.md` BEFORE writing any code that calls the versioned run REST API. The endpoint format is non-obvious (`/versions/{version}:run` is a path segment, NOT a query parameter). Skipping this reference is the #1 cause of broken versioned-run scripts.

## Prerequisites

- Agent versioning must be enabled for the account
- `CREATE AGENT` or `OWNERSHIP`/`MODIFY` privilege on the agent
- Snowflake connection configured

## Core Concepts

### Version Types

| Type | Description |
|------|-------------|
| `VERSION$N` | Committed (immutable) version with system ID |
| `LIVE` | Mutable working version for iterative changes |
| `DEFAULT` | The version `agent:run` and `DESCRIBE AGENT` resolve to (once committed versions exist) |

### Version Lifecycle

```
CREATE AGENT → VERSION$1 + LIVE
       ↓
Modify LIVE (SET SPECIFICATION)
       ↓
COMMIT → VERSION$N (snapshot of LIVE)
       ↓
SET ALIAS (e.g., production) + SET DEFAULT_VERSION
       ↓
Run via REST: versions/production:run or versions/DEFAULT:run
```

### Key Behavior Change

Once an agent has committed versions beyond `VERSION$1`:
- `agent:run` (unversioned) resolves to **DEFAULT**, not LIVE
- `DESCRIBE AGENT` shows the **DEFAULT** version spec, not LIVE
- To always target LIVE, use `versions/LIVE:run` or read from the stage directly

## Workflow

### Step 1: Determine Intent

> **Routing note**: Creating a new agent and modifying the LIVE spec are NOT handled here.
> - To **create** a versioned agent → use `create-cortex-agent/SKILL.md`
> - To **modify the LIVE spec** of an existing agent → use `edit-cortex-agent/SKILL.md`
> - This skill only handles versioning operations on an existing agent (commit, alias, default, run, list, drop).

| Intent | Actions | Reference |
|--------|---------|-----------|
| **Commit a version** | `ALTER AGENT COMMIT` | `references/sql-reference.md` |
| **Set alias/default** | `ALTER AGENT MODIFY VERSION ... SET ALIAS` + `ALTER AGENT SET DEFAULT_VERSION` | `references/sql-reference.md` |
| **Run a specific version** | REST `POST .../versions/{version}:run` | `references/versioned-run-api.md` |
| **List/inspect versions** | `SHOW VERSIONS IN AGENT` / `DESCRIBE AGENT` / stage ops | `references/sql-reference.md` |
| **Drop a version** | `ALTER AGENT DROP VERSION` | `references/sql-reference.md` |
| **Troubleshoot** | See Common Errors below | Both references |

### Step 2: Execute

**⚠️ MANDATORY STOPPING POINT**: Before executing any `ALTER AGENT` that modifies spec, drops versions, or commits a version, present the SQL to the user and wait for explicit approval. Do NOT proceed until user responds.

**Load** the appropriate reference file based on intent and follow the documented syntax.

**SQL Quick Reference:**

```sql
-- Commit live → new VERSION$N
ALTER AGENT my_agent COMMIT COMMENT = 'Release notes';

-- Set alias on committed version
ALTER AGENT my_agent MODIFY VERSION VERSION$2 SET ALIAS = production;

-- Set default
ALTER AGENT my_agent SET DEFAULT_VERSION = 'production';

-- List versions
SHOW VERSIONS IN AGENT my_agent;

-- Read any version's spec from stage
SELECT LISTAGG(RTRIM($1), '\n') WITHIN GROUP (ORDER BY METADATA$FILE_ROW_NUMBER)
  AS agent_specification
FROM snow://agent/my_agent/versions/live/agent_spec.yaml
WHERE TRIM($1) <> '';
```

> Note: To create a versioned agent (`CREATE AGENT ... FROM SPECIFICATION`) or modify the LIVE spec (`ALTER AGENT MODIFY LIVE VERSION SET SPECIFICATION`), use `create-cortex-agent` or `edit-cortex-agent` instead.

**REST Quick Reference:**

```
POST /api/v2/databases/{db}/schemas/{schema}/agents/{name}/versions/{version}:run
```

`{version}` accepts: `VERSION$N`, user alias (e.g., `production`), or shortcuts (`FIRST`, `LAST`, `DEFAULT`, `LIVE`).

URL-encode `$` as `%24` (e.g., `VERSION%242`).

### Step 3: Validate

After any versioning operation:

1. Run `SHOW VERSIONS IN AGENT <name>;` to confirm version state
2. Run `DESCRIBE AGENT <name>;` to check which spec is resolved as default
3. For REST runs, verify the response contains expected `run_id` and content

## Property Mutability Matrix

| Property | Agent-Level (`ALTER SET`) | Committed (`MODIFY VERSION`) | Live (`MODIFY LIVE VERSION`) |
|----------|:---:|:---:|:---:|
| `COMMENT` | Yes | Yes | Yes |
| `PROFILE` | Yes | No | No |
| `DEFAULT_VERSION` | Yes | No | No |
| `ALIAS` | No | Yes | Yes |
| `SPECIFICATION` | No | No | Yes |

Mixing rules: `ALIAS` cannot be mixed with other properties. `COMMENT` + `SPECIFICATION` can be mixed in `MODIFY LIVE VERSION`.

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Unsupported feature 'AGENT VERSIONING'` | Agent versioning is not enabled for this account | Contact account admin to enable agent versioning |
| `Cannot modify live version with MODIFY VERSION` | Used `MODIFY VERSION LIVE SET` | Use `MODIFY LIVE VERSION SET` instead |
| `Version is default` | Tried to drop the default version | Change default first, then drop |
| `Version cannot be dropped if it is a base for another version` | Committed version is base for LIVE | Drop dependent LIVE first |
| `invalid property 'SPECIFICATION' for 'CORTEX_AGENT'` (001420) | Used `ALTER AGENT SET SPECIFICATION` | Use `ALTER AGENT MODIFY LIVE VERSION SET SPECIFICATION` |
| `invalid property 'ALIAS' for 'CORTEX_AGENT'` (001420) | Used `ALTER AGENT SET ALIAS` | ALIAS is version-level: use `MODIFY VERSION SET ALIAS` |
| HTTP 404 on versioned run | Version doesn't exist or unresolved | Check `SHOW VERSIONS IN AGENT` for valid names |
| HTTP 403 on versioned run | Versioned run API is not enabled for this account | Contact account admin to enable versioned run API |

## Stopping Points

- **⚠️ MANDATORY**: Before executing any `ALTER AGENT` that modifies spec or drops versions — present SQL and wait for approval
- **⚠️ MANDATORY**: Before committing a version to production — confirm intent with user

## Output

- Versioned agent with committed versions, aliases, and default set
- REST API calls targeting specific versions
- Validation via `SHOW VERSIONS` and `DESCRIBE AGENT`
