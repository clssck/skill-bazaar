---
name: list-cortex-agents
description: "List Cortex Agents in a Snowflake account, database, or schema. Use for: list agents, show agents, what agents exist, find agents."
---

# List Cortex Agents

## Prerequisites

- Active Snowflake connection

## Workflow

### Step 1: Determine Scope

Based on what the user provides, pick the most specific scope:

| User provides | Scope | SQL |
|---|---|---|
| Database + Schema | Schema | `SHOW AGENTS IN SCHEMA <DATABASE>.<SCHEMA>;` |
| Database only | Database | `SHOW AGENTS IN DATABASE <DATABASE>;` |
| Nothing / "all" | Account | `SHOW AGENTS IN ACCOUNT;` |

**Waterfall logic:**
1. If the user specifies both database and schema → use schema scope
2. If the user specifies only a database → use database scope
3. If the user specifies nothing (or says "all", "everything", "entire account") → use account scope

### Step 2: Execute Query

Run the appropriate SQL command via `snowflake_sql_execute`:

```sql
-- Schema scope (most specific)
SHOW AGENTS IN SCHEMA <DATABASE>.<SCHEMA>;

-- Database scope
SHOW AGENTS IN DATABASE <DATABASE>;

-- Account scope (broadest)
SHOW AGENTS IN ACCOUNT;
```

If a specific role is needed:

```sql
USE ROLE <ROLE>;
SHOW AGENTS IN ACCOUNT;
```

### Step 3: Present Results

Present the results in a readable format. Key columns to highlight:

- **name** — Agent name
- **database_name** — Database
- **schema_name** — Schema
- **comment** — Description
- **created_on** — When it was created

If no agents are found, inform the user:

```
No agents found in <scope>.
```

**List complete.**
