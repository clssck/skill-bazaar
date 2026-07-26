# Cortex Agent Versioning SQL Reference

---

## Cortex Agent Versioning Commands

This document covers SQL commands and syntax specific to Cortex Agent **versioning**. For base (non-versioned) agent commands, see the [official Snowflake SQL reference](https://docs.snowflake.com/en/sql-reference/commands-cortex-agent).

### Related Skills

| Skill | Description |
| :--- | :--- |
| `create-cortex-agent` | Create a new Cortex Agent |
| `edit-cortex-agent` | Edit an existing agent's configuration |
| `delete-cortex-agent` | Delete/drop an agent |
| `list-cortex-agents` | List agents in account/database/schema |
| `adhoc-testing-for-cortex-agent` | Interactive testing of agent responses |
| `evaluate-cortex-agent` | Run formal agent evaluations |
| `debug-single-query-for-cortex-agent` | Debug a specific agent query |
| `optimize-cortex-agent` | Improve agent performance |

| Command | Description |
| :--- | :--- |
| [CREATE AGENT (versioned)](#create-agent-versioned) | Creates a new agent with dual-version creation (`VERSION$1` + `LIVE`). |
| [ALTER AGENT SET](#alter-agent-set-agent-level-properties) | Sets agent-level properties including `DEFAULT_VERSION`. |
| [ALTER AGENT COMMIT](#alter-agent-commit) | Commits the current live version into a new committed version. |
| [ALTER AGENT ADD VERSION](#alter-agent-add-version) | Adds a new committed or live version. |
| [ALTER AGENT MODIFY VERSION](#alter-agent-modify-version) | Modifies properties of a committed version. |
| [ALTER AGENT MODIFY LIVE VERSION](#alter-agent-modify-live-version) | Modifies properties or specification of the live version. |
| [ALTER AGENT DROP VERSION](#alter-agent-drop-version) | Drops a specific version. |
| [DESCRIBE AGENT (versioned)](#describe-agent-versioned) | Describes agent properties with version-aware output. |
| [SHOW VERSIONS IN AGENT](#show-versions-in-agent) | Lists all versions of an agent. |
| [Stage Operations](#stage-operations) | LIST/GET files in versioned agent stages. |

---

# CREATE AGENT (versioned)

Creates a new [Cortex Agent](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents) with dual-version creation. When versioning is enabled, `CREATE AGENT` creates both a committed `VERSION$1` and a `LIVE` version.

**See also:**
[ALTER AGENT COMMIT](#alter-agent-commit), [ALTER AGENT ADD VERSION](#alter-agent-add-version), [SHOW VERSIONS IN AGENT](#show-versions-in-agent), [DESCRIBE AGENT](#describe-agent-versioned)

## Syntax

### From inline specification

```sql
CREATE [ OR REPLACE ] AGENT [ IF NOT EXISTS ] <name>
  [ COMMENT = '<comment>' ]
  [ PROFILE = '<profile_object>' ]
  FROM SPECIFICATION
  $$
  <specification_object>
  $$;
```

### From stage

```sql
CREATE [ OR REPLACE ] AGENT [ IF NOT EXISTS ] <name>
  [ COMMENT = '<comment>' ]
  [ PROFILE = '<profile_object>' ]
  FROM @<stage_name>/<path>;
```

## Parameters

### `<name>` (required)

Identifier for the agent; must be unique within the schema. See [Identifier requirements](https://docs.snowflake.com/en/sql-reference/identifiers-syntax).

### `COMMENT = '<comment>'`

Description of the agent.

### `PROFILE = '<profile_object>'`

JSON string containing agent profile information:

```
'{"display_name": "<display_name>", "avatar": "<avatar>", "color": "<color>"}'
```

### `FROM SPECIFICATION $$ <specification_object> $$`

Inline YAML or JSON agent specification. Maximum 100,000 bytes.

### `FROM @<stage_name>/<path>`

Creates the agent from a staged `agent_spec.yaml` file. Only `agent_spec.yaml` is copied; other files are ignored.

## Versioning Behavior

When agent versioning is enabled:

| Source | What Happens |
| :--- | :--- |
| `FROM SPECIFICATION $$...$$` | 1. Creates committed `VERSION$1` with `agent_spec.yaml`. 2. Creates `LIVE` version inheriting from `VERSION$1`. |
| `FROM @stage/path` | 1. Copies `agent_spec.yaml` from stage to committed `VERSION$1`. 2. Creates `LIVE` version inheriting from `VERSION$1`. |

## Access Control Requirements

| Privilege | Object | Description |
| :--- | :--- | :--- |
| `CREATE AGENT` | Schema | Required to create the Cortex Agent. |
| `USAGE` | Cortex Search service | Required to run Cortex Search services referenced by the agent. |
| `USAGE` | Database, schema, table | Required to access objects referenced in the agent's semantic model. |

## Usage Notes

- `CREATE OR REPLACE` and `IF NOT EXISTS` are mutually exclusive.
- `CREATE OR REPLACE` is atomic: the old object is deleted and the new object is created in a single transaction.

## Examples

### Create with inline specification (dual-version)

```sql
CREATE AGENT my_agent
  FROM SPECIFICATION
  $$
  models:
    orchestration: claude-4-sonnet
  instructions:
    system: "You are a helpful assistant."
  $$;

-- Verify both versions were created
SHOW VERSIONS IN AGENT my_agent;
-- Returns 2 rows: VERSION$1 and LIVE

-- Verify files in each version
LIST snow://agent/my_agent/versions/version$1/;
LIST snow://agent/my_agent/versions/live/;
```

### Create from stage (dual-version)

```sql
CREATE STAGE my_stage;

CREATE AGENT my_agent_from_stage FROM @my_stage/spec;

SHOW VERSIONS IN AGENT my_agent_from_stage;
```

---

# ALTER AGENT SET (agent-level properties)

Sets agent-level properties such as `COMMENT`, `PROFILE`, and `DEFAULT_VERSION`.

**See also:**
[ALTER AGENT MODIFY VERSION](#alter-agent-modify-version), [ALTER AGENT MODIFY LIVE VERSION](#alter-agent-modify-live-version)

## Syntax

```sql
ALTER AGENT [ IF EXISTS ] <name>
  SET { COMMENT = '<string>'
      | PROFILE = '<json_string>'
      | DEFAULT_VERSION = '<version_name>' }
      [ , ... ]
```

## Parameters

### `<name>` (required)

Identifier for the agent to alter.

### `IF EXISTS`

When specified, the command completes without error if the agent does not exist.

### `COMMENT = '<string>'`

Description of the agent.

### `PROFILE = '<json_string>'`

Agent profile as a JSON string. See [CREATE AGENT](#create-agent-versioned) for the structure.

### `DEFAULT_VERSION = '<version_name>'`

Sets which committed version is the "default" for run API resolution. Accepts:
- Version names: `'VERSION$1'`, `'VERSION$2'`, etc. — **pins** to that specific version
- Shortcuts: `'FIRST'`, `'LAST'` — **dynamic**, auto-updates as versions are added/removed

> **Note:** User-defined aliases (e.g., `'production'`, `'staging'`) are **not** currently supported for `DEFAULT_VERSION`. Use the system version ID (`VERSION$N`) or shortcuts (`FIRST`, `LAST`) instead.

**Pinned vs Dynamic behavior:**
- `SET DEFAULT_VERSION = 'VERSION$2'` — Pins DEFAULT to VERSION$2. Adding new versions won't change it.
- `SET DEFAULT_VERSION = 'LAST'` — DEFAULT always points to the latest committed version.
- `SET DEFAULT_VERSION = 'FIRST'` — DEFAULT always points to the first committed version.

**To reset DEFAULT to auto-follow latest:** Use `SET DEFAULT_VERSION = 'LAST'`.

> **Note:** There is no `UNSET DEFAULT_VERSION` syntax. Use `'LAST'` to restore auto-follow behavior.

## Mixing Rules

`COMMENT` and `PROFILE` can be mixed in the same `SET` clause. `DEFAULT_VERSION` can be set alongside them.

## Access Control Requirements

| Privilege | Object |
| :--- | :--- |
| `OWNERSHIP` or `MODIFY` | Agent |

## Examples

```sql
ALTER AGENT my_agent SET COMMENT = 'Updated agent description';

ALTER AGENT my_agent SET PROFILE = '{"display_name": "Production Bot", "avatar": "bot.png"}';

ALTER AGENT my_agent SET COMMENT = 'Multi-prop update', PROFILE = '{"display_name": "Bot"}';

-- Pin DEFAULT to specific version (won't auto-update)
ALTER AGENT my_agent SET DEFAULT_VERSION = 'VERSION$2';

-- Dynamic DEFAULT - always points to first version
ALTER AGENT my_agent SET DEFAULT_VERSION = 'FIRST';

-- Reset DEFAULT to auto-follow latest committed version
ALTER AGENT my_agent SET DEFAULT_VERSION = 'LAST';

-- NOTE: Aliases are NOT supported for DEFAULT_VERSION
-- ALTER AGENT my_agent SET DEFAULT_VERSION = 'production';  -- ERROR!

-- NOTE: Cannot UNSET or set to NULL
-- ALTER AGENT my_agent UNSET DEFAULT_VERSION;  -- SYNTAX ERROR!
-- ALTER AGENT my_agent SET DEFAULT_VERSION = NULL;  -- ERROR!
```

---

# ALTER AGENT COMMIT

Commits the current `LIVE` version, creating a new committed `VERSION$N`.

> **Important:** After `COMMIT`, the `LIVE` version is **destroyed**. To continue development, use `ALTER AGENT ... ADD LIVE VERSION <alias> FROM LAST` to create a new live version based on the latest committed version.

**See also:**
[ALTER AGENT ADD VERSION](#alter-agent-add-version), [SHOW VERSIONS IN AGENT](#show-versions-in-agent)

## Syntax

```sql
ALTER AGENT <name> COMMIT [ COMMENT = '<string>' ]
```

## Parameters

### `<name>` (required)

Identifier for the agent.

### `COMMENT = '<string>'`

Comment for the newly created committed version.

## Access Control Requirements

| Privilege | Object |
| :--- | :--- |
| `OWNERSHIP` or `MODIFY` | Agent |

## Usage Notes

- The committed version receives the next sequential system ID (e.g., `VERSION$2`, `VERSION$3`).
- **The `LIVE` version is destroyed after commit.** Use `ADD LIVE VERSION ... FROM LAST` to create a new live version for further development.

## Examples

```sql
ALTER AGENT my_agent COMMIT COMMENT = 'Initial production version';

-- Verify - LIVE is gone after commit!
SHOW VERSIONS IN AGENT my_agent;
-- Returns: VERSION$1, VERSION$2 (no LIVE)

-- To continue development, create a new LIVE version:
ALTER AGENT my_agent ADD LIVE VERSION dev FROM LAST;
```

---

# ALTER AGENT ADD VERSION

Adds a new version to the agent. Can create either a new `LIVE` version from the last committed version, or a new committed version from a stage.

**See also:**
[ALTER AGENT COMMIT](#alter-agent-commit), [ALTER AGENT DROP VERSION](#alter-agent-drop-version)

## Syntax

### Add a new live version from last committed

```sql
ALTER AGENT <name> ADD LIVE VERSION <alias> FROM LAST [ COMMENT = '<string>' ]
```

### Add a committed version from stage

```sql
ALTER AGENT <name> ADD VERSION <alias> FROM @<stage_name>/<path> [ COMMENT = '<string>' ]
```

## Parameters

### `<name>` (required)

Identifier for the agent.

### `<alias>`

User-defined alias for the new version. Unquoted identifiers are stored as uppercase. Double-quoted identifiers preserve case.

### `FROM LAST`

Creates the new live version based on the last committed version. The live version inherits the committed version's manifest.

### `FROM @<stage_name>/<path>`

Creates a new committed version with `agent_spec.yaml` copied from the specified stage location. The file `agent_spec.yaml` **must** exist in the source stage path or the command fails.

### `COMMENT = '<string>'`

Comment for the new version.

## Access Control Requirements

| Privilege | Object |
| :--- | :--- |
| `OWNERSHIP` or `MODIFY` | Agent |

## Usage Notes

- Only `agent_spec.yaml` is copied from the stage; other files are filtered out.
- Unquoted aliases are stored as uppercase (e.g., `v3_from_stage` becomes `V3_FROM_STAGE`).
- Double-quoted aliases preserve case (e.g., `"v4_case_sensitive"` stays lowercase).
- Each new version also receives a system version ID (e.g., `VERSION$3`, `VERSION$4`).

## Examples

### Add a new live version

```sql
ALTER AGENT my_agent ADD LIVE VERSION v2_dev FROM LAST COMMENT = 'Development iteration';

SHOW VERSIONS IN AGENT my_agent;
```

### Commit the new live version

```sql
ALTER AGENT my_agent COMMIT COMMENT = 'Second release';
```

### Add a committed version from stage

```sql
ALTER AGENT my_agent ADD VERSION v3_release FROM @my_stage/spec COMMENT = 'Release candidate';

-- Alias stored as uppercase V3_RELEASE
LIST snow://agent/my_agent/versions/V3_RELEASE/;

-- Also accessible by system version ID
LIST snow://agent/my_agent/versions/version$4/;
```

### Case-sensitive alias

```sql
ALTER AGENT my_agent ADD VERSION "v4_lowercase" FROM @my_stage/spec COMMENT = 'Case-sensitive alias';

-- Access with preserved case
LIST snow://agent/my_agent/versions/v4_lowercase/;
```

---

# ALTER AGENT MODIFY VERSION

Modifies properties of a **committed** version. Valid properties are `COMMENT` and `ALIAS`, which must be set separately (cannot be mixed in the same `SET` clause).

**See also:**
[ALTER AGENT MODIFY LIVE VERSION](#alter-agent-modify-live-version), [ALTER AGENT COMMIT](#alter-agent-commit)

## Syntax

### Set comment

```sql
ALTER AGENT [ IF EXISTS ] <name>
  MODIFY VERSION <version_name> SET COMMENT = '<string>'
```

### Set alias

```sql
ALTER AGENT [ IF EXISTS ] <name>
  MODIFY VERSION <version_name> SET ALIAS = <alias>
```

## Parameters

### `<name>` (required)

Identifier for the agent.

### `<version_name>`

The version to modify. Can be a system version ID (e.g., `VERSION$1`) or a user-defined alias. Double-quoted identifiers are case-sensitive.

### `COMMENT = '<string>'`

Sets the comment for the committed version.

### `ALIAS = <alias>`

Sets a user-defined alias for the committed version.

## Access Control Requirements

| Privilege | Object |
| :--- | :--- |
| `OWNERSHIP` or `MODIFY` | Agent |

## Usage Notes

- `COMMENT` and `ALIAS` **cannot** be mixed in the same `SET` clause.
- You **cannot** target the `LIVE` version with `MODIFY VERSION`. Use `MODIFY LIVE VERSION` instead. Using `MODIFY VERSION LIVE SET ...` returns an error: `Cannot modify live version with MODIFY VERSION. Use MODIFY LIVE VERSION instead.`

## Examples

```sql
ALTER AGENT my_agent MODIFY VERSION VERSION$1 SET COMMENT = 'Initial release';

ALTER AGENT my_agent MODIFY VERSION VERSION$1 SET ALIAS = production;

ALTER AGENT my_agent MODIFY VERSION "VERSION$2" SET COMMENT = 'Hotfix release';

ALTER AGENT my_agent MODIFY VERSION VERSION$2 SET ALIAS = staging;
```

---

# ALTER AGENT MODIFY LIVE VERSION

Modifies properties or specification of the `LIVE` version. Valid properties are `COMMENT`, `ALIAS`, and `SPECIFICATION`, with specific mixing rules.

**See also:**
[ALTER AGENT MODIFY VERSION](#alter-agent-modify-version), [ALTER AGENT COMMIT](#alter-agent-commit)

## Syntax

### Set comment

```sql
ALTER AGENT [ IF EXISTS ] <name>
  MODIFY LIVE VERSION SET COMMENT = '<string>'
```

### Set alias

```sql
ALTER AGENT [ IF EXISTS ] <name>
  MODIFY LIVE VERSION SET ALIAS = <alias>
```

### Set specification

```sql
ALTER AGENT [ IF EXISTS ] <name>
  MODIFY LIVE VERSION SET SPECIFICATION = <specification>
```

### Set comment and specification together

```sql
ALTER AGENT [ IF EXISTS ] <name>
  MODIFY LIVE VERSION SET
    COMMENT = '<string>',
    SPECIFICATION = <specification>
```

## Parameters

### `<name>` (required)

Identifier for the agent.

### `COMMENT = '<string>'`

Sets the comment for the live version.

### `ALIAS = <alias>`

Sets a user-defined alias for the live version.

### `SPECIFICATION = <specification>`

Updates the agent specification. Can be provided as:
- Dollar-quoted literal: `$$ ... $$`
- Single-quoted string: `'...'`

Maximum 100,000 bytes.

> **Important:** The new specification completely replaces the existing one. Fields not included in the new specification are removed.

## Mixing Rules

- `COMMENT` and `SPECIFICATION` **can** be mixed in the same `SET` clause.
- `ALIAS` **cannot** be mixed with `COMMENT` or `SPECIFICATION`.

## Access Control Requirements

| Privilege | Object |
| :--- | :--- |
| `OWNERSHIP` or `MODIFY` | Agent |

## Usage Notes

- `SPECIFICATION` is only valid with `MODIFY LIVE VERSION SET`. Using it with `ALTER AGENT SET` directly returns error `001420`: `invalid property 'SPECIFICATION' for 'CORTEX_AGENT'`.
- Both YAML and JSON formats are supported for specifications.
- Invalid specification fields result in an error.

## Examples

### Update specification (YAML)

```sql
ALTER AGENT my_agent MODIFY LIVE VERSION SET SPECIFICATION =
  $$
  models:
    orchestration: claude-4-sonnet
  orchestration:
    budget:
      seconds: 30
      tokens: 50000
  instructions:
    system: "You are a helpful assistant."
    response: "Always be concise and accurate."
    sample_questions:
      - question: "What is the status of my order?"
        answer: "I can help you check your order status."
  $$;
```

### Update specification (JSON)

```sql
ALTER AGENT my_agent MODIFY LIVE VERSION SET SPECIFICATION =
  '{"models":{"orchestration":"claude-4-sonnet"},"orchestration":{"budget":{"seconds":45,"tokens":80000}}}';
```

### Update comment and specification together

```sql
ALTER AGENT my_agent MODIFY LIVE VERSION SET
  COMMENT = 'Updated with new budget',
  SPECIFICATION = $$
  models:
    orchestration: claude-4-sonnet
  orchestration:
    budget:
      seconds: 60
      tokens: 100000
  $$;
```

### Set alias

```sql
ALTER AGENT my_agent MODIFY LIVE VERSION SET ALIAS = latest;
```

---

# ALTER AGENT DROP VERSION

Drops a specific version from the agent.

**See also:**
[ALTER AGENT ADD VERSION](#alter-agent-add-version), [SHOW VERSIONS IN AGENT](#show-versions-in-agent)

## Syntax

```sql
ALTER AGENT <name> DROP VERSION <version_name>
```

## Parameters

### `<name>` (required)

Identifier for the agent.

### `<version_name>`

The version to drop. Can be:
- A system version ID (e.g., `VERSION$2`)
- A user-defined alias (e.g., `staging`)
- A double-quoted identifier for case-sensitive names (e.g., `"v4_lowercase"`)

## Access Control Requirements

| Privilege | Object |
| :--- | :--- |
| `OWNERSHIP` or `MODIFY` | Agent |

## Usage Notes

- **Cannot** drop the default version. Error: `Version is default`.
- **Cannot** drop a committed version that is the base for an active live version. Error: `Version cannot be dropped if it is a base for another version`.
- **Cannot** drop a nonexistent version. Error: `Version does not exist`.

## Examples

```sql
ALTER AGENT my_agent DROP VERSION VERSION$2;

ALTER AGENT my_agent DROP VERSION staging;

ALTER AGENT my_agent DROP VERSION "v4_lowercase";
```

---

# DESCRIBE AGENT (versioned)

Describes the properties of a [Cortex Agent](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents). When versioning is enabled, the output includes additional version-related columns and the `agent_spec` column reflects version-aware resolution behavior.

`DESCRIBE` can be abbreviated to `DESC`.

**See also:**
[ALTER AGENT SET](#alter-agent-set-agent-level-properties), [SHOW VERSIONS IN AGENT](#show-versions-in-agent), [CREATE AGENT](#create-agent-versioned)

## Syntax

```sql
{ DESC | DESCRIBE } [ AS RESOURCE ] AGENT <name>
```

## Parameters

### `<name>` (required)

Specifies the name of the agent to describe. If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes.

### `AS RESOURCE`

When specified, the output is returned as a JSON object. The JSON includes `name`, `database_name`, `schema_name`, `created_on`, `owner`, and `agent_spec`. Note that the `AS RESOURCE` output does **not** include the `comment` field.

## Output

When versioning is enabled, the output includes the following columns:

| Column | Description |
| :--- | :--- |
| `name` | Name of the agent. |
| `database_name` | Database containing the agent. |
| `schema_name` | Schema containing the agent. |
| `owner` | Owner role of the agent. |
| `comment` | Comment text for the agent. |
| `profile` | Agent profile JSON (`display_name`, `avatar`, `color`). |
| `agent_spec` | Specification of the resolved version (see behavior below). |
| `created_on` | Timestamp when the agent was created. |
| `default_version_name` | Name of the default version for run API resolution. |
| `versions` | List of all version names. |
| `aliases` | List of user-defined version aliases. |

## Versioning Behavior for `agent_spec`

When an agent has committed versions, `DESCRIBE AGENT` resolves the `agent_spec` column as follows:

- If a **default version** is set (and it is not `VERSION$1`), the `agent_spec` reflects the **default version's** specification.
- If no explicit default is set but committed versions exist (beyond `VERSION$1`), the `agent_spec` prioritizes showing the **default version** (excluding `VERSION$1`) over the `LIVE` version.
- In other words, `DESCRIBE AGENT` prioritizes the default committed version over `LIVE` when displaying `agent_spec`, except for `VERSION$1`.

This means that after committing versions and setting a default, `DESCRIBE AGENT` shows the specification of the default committed version, not the potentially-modified live version.

## Access Control Requirements

| Privilege | Object | Notes |
| :--- | :--- | :--- |
| Any one of: `OWNERSHIP`, `USAGE`, `MONITOR`, or `OPERATE` | Agent | |

Operating on an object in a schema requires at least one privilege on the parent database and at least one privilege on the parent schema.

## Usage Notes

- To post-process the output, you can use the [pipe operator](https://docs.snowflake.com/en/sql-reference/operators-flow) (`->>`) or the [RESULT_SCAN](https://docs.snowflake.com/en/sql-reference/functions/result_scan) function.
- When referring to output columns, use double-quoted identifiers (e.g., `SELECT "agent_spec"`) because output column names are lowercase.
- To see the specification of a specific version, use `LIST` and `GET` on the versioned stage instead.

## Examples

```sql
DESCRIBE AGENT my_agent;

DESC AGENT my_agent;

DESCRIBE AS RESOURCE AGENT my_agent;

-- To see spec from a specific version (not the resolved default):
LIST snow://agent/my_agent/versions/live/;
GET snow://agent/my_agent/versions/live/agent_spec.yaml file:///tmp/;
```

---

# SHOW VERSIONS IN AGENT

Lists the versions of a versioned [Cortex Agent](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents).

**See also:**
[ALTER AGENT COMMIT](#alter-agent-commit), [ALTER AGENT ADD VERSION](#alter-agent-add-version), [ALTER AGENT DROP VERSION](#alter-agent-drop-version)

## Syntax

```sql
SHOW VERSIONS IN AGENT <name>
  [ LIMIT <rows> ]
```

## Parameters

### `<name>` (required)

Specifies the name of the agent whose versions to list.

### `LIMIT <rows>`

Optionally limits the maximum number of version rows returned.

## Output

| Column | Description |
| :--- | :--- |
| `version_name` | System version identifier (e.g., `VERSION$1`, `LIVE`). |
| `alias` | User-defined alias, if set. |
| `comment` | Comment for the version. |
| `created_on` | Timestamp when the version was created. |
| `agent_spec` | Agent specification for the version (when supported). |

## Access Control Requirements

| Privilege | Object | Notes |
| :--- | :--- | :--- |
| Any one of: `OWNERSHIP`, `USAGE`, `MONITOR`, or `OPERATE` | Agent | |

## Usage Notes

- The `agent_spec` column may not be included in all environments.

## Examples

```sql
SHOW VERSIONS IN AGENT my_agent;

SHOW VERSIONS IN AGENT my_agent LIMIT 5;
```

---

# Stage Operations

Each agent version has an internal versioned stage accessible via the `snow://agent/` URI scheme. You can `LIST`, `GET`, and `PUT` files to specific versions.

## URI Format

```
snow://agent/<agent_name>/versions/<version>/[<file_name>]
```

Where `<version>` can be:
- `live` — The live version.
- `version$N` — A committed version by system ID.
- A user-defined alias (case-sensitive if created with double quotes; otherwise uppercase).

## Syntax

### List files in a version

```sql
LIST snow://agent/<agent_name>/versions/<version>/;
```

### Download a file from a version

```sql
GET snow://agent/<agent_name>/versions/<version>/<file_name> file://<local_path>/;
```

### Extract a version's specification as text

```sql
SELECT LISTAGG(RTRIM($1), '\n') WITHIN GROUP (ORDER BY METADATA$FILE_ROW_NUMBER)
  AS agent_specification
FROM snow://agent/<agent_name>/versions/<version>/agent_spec.yaml
WHERE TRIM($1) <> '';
```

This reads the `agent_spec.yaml` file directly from the versioned stage and reconstructs it as a single text value. Unlike `DESCRIBE AGENT` (which resolves to the default version), this approach lets you explicitly extract the specification of **any** version — `live`, a committed version by ID, or by alias.

## Usage Notes

- The stage path is case-sensitive for version identifiers created with double-quoted aliases.
- Accessing an unquoted alias with lowercase letters will fail (e.g., `LIST .../versions/v3_from_stage/` fails because the alias is stored as `V3_FROM_STAGE`).

## Examples

```sql
-- List files in the live version
LIST snow://agent/my_agent/versions/live/;

-- List files in a committed version
LIST snow://agent/my_agent/versions/version$1/;

-- Download spec from live
GET snow://agent/my_agent/versions/live/agent_spec.yaml file:///tmp/agent_spec/;

-- Access by user-defined alias (uppercase)
LIST snow://agent/my_agent/versions/V3_RELEASE/;

-- Access by case-sensitive alias
LIST snow://agent/my_agent/versions/v4_lowercase/;

-- Extract the live version's spec as text
SELECT LISTAGG(RTRIM($1), '\n') WITHIN GROUP (ORDER BY METADATA$FILE_ROW_NUMBER)
  AS agent_specification
FROM snow://agent/my_agent/versions/live/agent_spec.yaml
WHERE TRIM($1) <> '';

-- Extract a committed version's spec by ID
SELECT LISTAGG(RTRIM($1), '\n') WITHIN GROUP (ORDER BY METADATA$FILE_ROW_NUMBER)
  AS agent_specification
FROM snow://agent/my_agent/versions/version$2/agent_spec.yaml
WHERE TRIM($1) <> '';
```

---

# Property Mutability Matrix

| Property | Agent-Level (`ALTER SET`) | Committed Version (`MODIFY VERSION`) | Live Version (`MODIFY LIVE VERSION`) |
| :--- | :---: | :---: | :---: |
| `COMMENT` | Yes | Yes | Yes |
| `PROFILE` | Yes | No | No |
| `DEFAULT_VERSION` | Yes | No | No |
| `ALIAS` | No | Yes | Yes |
| `SPECIFICATION` | No | No | Yes |

**Mixing rules:**
- `ALIAS` cannot be mixed with other properties in the same `SET` clause.
- `COMMENT` and `SPECIFICATION` can be mixed in `MODIFY LIVE VERSION SET`.
- `COMMENT` and `PROFILE` can be mixed in `ALTER AGENT SET`.

---

# Version Interaction Model

| Operation | Behavior |
| :--- | :--- |
| `CREATE AGENT FROM SPECIFICATION $$...$$` | Creates committed `VERSION$1` with `agent_spec.yaml`. Creates `LIVE` version inheriting from `VERSION$1`. |
| `CREATE AGENT FROM @stage/path` | Copies `agent_spec.yaml` from stage to committed `VERSION$1`. Creates `LIVE` inheriting from `VERSION$1`. |
| `ALTER AGENT COMMIT` | Snapshots current `LIVE` into new committed `VERSION$N`. **`LIVE` is destroyed.** Use `ADD LIVE VERSION ... FROM LAST` to create a new live version. |
| `ALTER AGENT ADD LIVE VERSION <alias> FROM LAST` | Creates new `LIVE` based on last committed version. |
| `ALTER AGENT ADD VERSION <alias> FROM @stage/path` | Creates new committed version from stage. `agent_spec.yaml` must exist. |
| `ALTER AGENT SET DEFAULT_VERSION` | Sets which committed version resolves for the `DEFAULT` shortcut. |
| `ALTER AGENT MODIFY LIVE VERSION SET SPECIFICATION` | Writes new `agent_spec.yaml` to live version storage, fully replacing the previous spec. |
| `DESCRIBE AGENT` | Shows spec of the default version (excluding `VERSION$1`) over `LIVE` when committed versions exist. |

---

# Common Errors (versioning-specific)

| Error Code | Message | Cause |
| :--- | :--- | :--- |
| — | `Unsupported feature 'AGENT VERSIONING'.` | Agent versioning is not enabled for this account. |
| — | `Cannot modify live version with MODIFY VERSION. Use MODIFY LIVE VERSION instead.` | Used `MODIFY VERSION LIVE SET ...` instead of `MODIFY LIVE VERSION SET ...`. |
| — | `Version is default` | Attempted to drop the default version. |
| — | `Version does not exist` | Attempted to drop or modify a nonexistent version. |
| — | `Version cannot be dropped if it is a base for another version` | Attempted to drop a committed version that is the base for an active live version. |
| — | `agent_spec.yaml not found in source stage` | `ADD VERSION ... FROM @stage` but the stage path has no `agent_spec.yaml`. |
| `001420` | `invalid property 'SPECIFICATION' for 'CORTEX_AGENT'` | Used `ALTER AGENT SET SPECIFICATION` instead of `MODIFY LIVE VERSION SET SPECIFICATION`. |
| `001420` | `invalid property 'ALIAS' for 'CORTEX_AGENT'` | Used `ALTER AGENT SET ALIAS` (ALIAS is version-level only). |

---

# End-to-End Walkthrough

```sql
USE SCHEMA my_db.my_schema;

-- 1. Create agent (dual-version: VERSION$1 + LIVE)
CREATE AGENT my_agent
  COMMENT = 'Data analyst agent'
  FROM SPECIFICATION
  $$
  models:
    orchestration: claude-4-sonnet
  instructions:
    system: "You are a data analyst assistant."
  $$;

-- 2. Verify dual-version creation
SHOW VERSIONS IN AGENT my_agent;
DESCRIBE AGENT my_agent;

-- 3. Modify the live version spec
ALTER AGENT my_agent MODIFY LIVE VERSION SET SPECIFICATION =
  $$
  models:
    orchestration: claude-4-sonnet
  instructions:
    system: "You are an improved data analyst assistant."
  orchestration:
    budget:
      seconds: 45
      tokens: 80000
  $$;

-- 4. Commit live as VERSION$2
ALTER AGENT my_agent COMMIT COMMENT = 'v2 with improved instructions';
SHOW VERSIONS IN AGENT my_agent;

-- 5. Set alias on committed version
ALTER AGENT my_
