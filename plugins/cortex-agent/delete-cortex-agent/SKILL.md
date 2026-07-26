---
name: delete-cortex-agent
description: "Delete (DROP) an existing Cortex Agent. Use for: delete agent, drop agent, remove agent, destroy agent, clean up agent. Backs up the agent spec before dropping to enable recovery."
---

# Delete Cortex Agent

## Prerequisites

- Active Snowflake connection
- Agent must already exist
- USAGE privilege on the agent's schema
- Appropriate role with permissions to drop the agent

Whenever running scripts, make sure to use `uv`.

## User Configuration Required

The following information will be requested during the workflow:

**Step 1 - Agent Identification:**

- **Database**: Where the agent is located (e.g., `MY_DATABASE`)
- **Schema**: Schema containing the agent (e.g., `AGENTS`)
- **Agent Name**: Name of the agent to delete (e.g., `MY_SALES_AGENT`)
- **Role**: A role with privileges to drop the agent (e.g., `MY_AGENT_ADMIN_ROLE`)
- **Connection Name**: Snowflake connection to use (default: `snowhouse`)

## Workflow Overview

This workflow safely deletes an existing agent with backup:

1. **Step 1:** Identify agent and setup workspace
2. **Step 2:** Get and save current agent configuration (backup)
3. **Step 3:** Production safety check and confirmation
4. **Step 4:** Drop agent
5. **Step 5:** Verify deletion

## Workflow Steps

### Step 1: Identify Agent and Setup Workspace

**Goal:** Locate the agent to delete and create a working directory for the backup

**Actions:**

1. **Ask the user for agent location:**

   ```
   Which agent would you like to delete?
   - Database: [e.g., MY_DATABASE]
   - Schema: [e.g., AGENTS]
   - Agent Name: [e.g., MY_SALES_AGENT]
   - Connection: [default: snowhouse]
   
   What role should I use?
   - Role: [e.g., MY_AGENT_ADMIN_ROLE]
   Note: This role must have privileges to drop the agent on <DATABASE>.<SCHEMA>
   ```

   If the user only provides the agent name, help them find it:

   ```sql
   SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
   ```

2. **Construct Fully Qualified Agent Name:**

   - Format: `<DATABASE>.<SCHEMA>.<AGENT_NAME>`
   - Example: `MY_DATABASE.AGENTS.MY_SALES_AGENT`

3. **Create workspace (MANDATORY - do NOT create directories manually):**

   **⚠️ ALWAYS use `init_agent_workspace.py` to create the workspace. Do NOT manually create directories with `mkdir`. The script creates required files including `metadata.yaml`.**

```bash
uv run python ../scripts/init_agent_workspace.py --agent-name <AGENT_NAME> --database <DATABASE> --schema <SCHEMA>

# Example:
uv run python ../scripts/init_agent_workspace.py --agent-name MY_SALES_AGENT --database MY_DATABASE --schema AGENTS
```

**Expected Directory Structure After Running Script:**

```
{DATABASE}_{SCHEMA}_{AGENT_NAME}/
├── metadata.yaml          ← REQUIRED: Created by init_agent_workspace.py
├── optimization_log.md    ← Created by init_agent_workspace.py
└── versions/
    └── vYYYYMMDD-HHMM/
        ├── current_agent_spec.json   ← Will contain backup (Step 2)
        └── evals/
```

**Verify after running:** Check that `metadata.yaml` exists in the workspace root before proceeding.

**IMPORTANT:** After completing Step 1, proceed to Step 2.

### Step 2: Get and Save Current Agent Configuration (Backup)

**Goal:** Retrieve and save the full agent configuration so it can be recovered if needed

**Actions:**

1. **Fetch current configuration:**

   ```bash
   uv run python ../scripts/get_agent_config.py --agent-name <AGENT_NAME> \
     --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION> \
     --workspace <WORKSPACE_DIR> \
     --output-name current_agent_spec.json

   # Example:
   uv run python ../scripts/get_agent_config.py --agent-name MY_SALES_AGENT \
     --database MY_DATABASE --schema AGENTS --connection snowhouse \
     --workspace MY_DATABASE_AGENTS_MY_SALES_AGENT \
     --output-name current_agent_spec.json
   ```

2. **Read and present a summary** of the current configuration to the user:
   - Current instructions (orchestration, response, system, sample_questions)
   - Current tools and their descriptions
   - Current comment
   - Current model configuration

3. **Confirm backup was saved:**
   ```
   ✅ Agent configuration backed up to:
     <WORKSPACE_DIR>/versions/<VERSION>/current_agent_spec.json
   
   This backup can be used to recreate the agent if needed.
   ```


**IMPORTANT:** After completing Step 2, proceed to Step 3.

### Step 3: Production Safety Check and Confirmation

**Goal:** Ensure the user understands the consequences and explicitly confirms deletion

**Actions:**

1. **⚠️ Production safety check.** Ask the user explicitly:

   ```
   ⚠️ WARNING: DROP AGENT is irreversible. The agent and its configuration
   will be permanently deleted from Snowflake.

   Agent: <DATABASE>.<SCHEMA>.<AGENT_NAME>

   Is this a production agent? (yes/no)
   ```

2. **If the user says YES (production agent):**

   ```
   ⚠️ This is a production agent. The full spec has been backed up to:
     <WORKSPACE_DIR>/versions/<VERSION>/current_agent_spec.json

   You can use this backup with create_or_alter_agent.py to recreate the agent later.

   To confirm permanent deletion of a PRODUCTION agent, type "DROP" exactly:
   ```

   **Only proceed if the user explicitly types "DROP".** Any other response → abort and inform the user the agent was NOT deleted.

3. **If the user says NO (not production):**

   ```
   The agent spec has been backed up to:
     <WORKSPACE_DIR>/versions/<VERSION>/current_agent_spec.json

   Confirm you want to drop <DATABASE>.<SCHEMA>.<AGENT_NAME>? (yes/no)
   ```

   **Only proceed if the user says "yes".** If "no" → abort.

4. **If the user aborts at any point:**

   ```
   ❌ Deletion cancelled. Agent <DATABASE>.<SCHEMA>.<AGENT_NAME> was NOT deleted.
   The backup is still available at:
     <WORKSPACE_DIR>/versions/<VERSION>/current_agent_spec.json
   ```

**IMPORTANT:** After completing Step 3 with explicit confirmation, proceed to Step 4.

### Step 4: Drop Agent

**Goal:** Execute the DROP AGENT command

**Actions:**

1. **Execute the drop:**

   ```sql
   DROP AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```

   If a specific role is needed:

   ```sql
   USE ROLE <ROLE>;
   DROP AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```

2. **Check the output** for success or error messages.

**IMPORTANT:** After completing Step 4, proceed to Step 5.

### Step 5: Verify Deletion

**Goal:** Confirm the agent has been deleted

**Actions:**

1. **Verify agent no longer exists:**

   ```sql
   SHOW AGENTS LIKE '<AGENT_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
   ```

   Confirm the agent no longer appears in results.

2. **Present final summary:**

   ```
   ✅ Agent <DATABASE>.<SCHEMA>.<AGENT_NAME> has been deleted.

   Backup saved at:
     <WORKSPACE_DIR>/versions/<VERSION>/current_agent_spec.json

   To recreate this agent from backup, use:
     uv run python ../scripts/create_or_alter_agent.py create \
       --agent-name <AGENT_NAME> \
       --config-file <WORKSPACE_DIR>/versions/<VERSION>/current_agent_spec.json \
       --database <DATABASE> --schema <SCHEMA> --role <ROLE>
   ```

**Agent deletion complete.**

## Troubleshooting

### Agent Not Found

**Symptom:** "agent does not exist" or HTTP 404

**Solution:**

```sql
SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
```

Verify the database, schema, and agent name are correct.

### Permission Issues

**Symptom:** "insufficient privileges" or "Unauthorized"

**Solution:**

1. Verify your role has appropriate privileges:
   ```sql
   SHOW GRANTS ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```

2. If needed, request grants from admin:
   ```sql
   GRANT OWNERSHIP ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> TO ROLE <your_role>;
   ```

### Recovery from Accidental Deletion

If you need to recreate a deleted agent, use the backup:

```bash
uv run python ../scripts/create_or_alter_agent.py create \
  --agent-name <AGENT_NAME> \
  --config-file <WORKSPACE_DIR>/versions/<VERSION>/current_agent_spec.json \
  --database <DATABASE> --schema <SCHEMA> --role <ROLE>
```

This will recreate the agent with the exact same configuration that was saved before deletion.
