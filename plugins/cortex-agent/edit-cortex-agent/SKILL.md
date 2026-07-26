---
name: edit-cortex-agent
description: "Edit an existing Cortex Agent's configuration (instructions, tools, comment, models, etc.) using REST API. Use for: edit agent, modify agent, update agent, change agent instructions, add tools to agent, remove tools from agent."
---

# Edit Cortex Agent

## Prerequisites

- Active Snowflake connection
- Agent must already exist
- USAGE privilege on the agent's schema
- Appropriate role with permissions to modify the agent

Whenever running scripts, make sure to use `uv`.

## User Configuration Required

The following information will be requested during the workflow:

**Step 1 - Agent Identification:**

- **Database**: Where the agent is located (e.g., `MY_DATABASE`)
- **Schema**: Schema containing the agent (e.g., `AGENTS`)
- **Agent Name**: Name of the agent to edit (e.g., `MY_SALES_AGENT`)
- **Role**: A role with privileges to modify the agent (e.g., `MY_AGENT_EDITOR_ROLE`)
- **Connection Name**: Snowflake connection to use (default: `snowhouse`)

**Step 2 - Edit Selection:**

- **What to edit**: Instructions, tools, comment, models, orchestration, etc.

## Workflow Overview

This workflow edits an existing agent's configuration:

1. **Step 1:** Identify agent and setup workspace
2. **Step 2:** Get current agent configuration
3. **Step 3:** Select what to edit
4. **Step 4:** Gather changes based on selection
5. **Step 5:** Apply changes via REST API
6. **Step 6:** Verify changes were applied

## Workflow Steps

### Step 1: Identify Agent and Setup Workspace

**Goal:** Locate the agent to edit and create a working directory

**Actions:**

1. **Ask the user for agent location:**

   ```
   Which agent would you like to edit?
   - Database: [e.g., MY_DATABASE]
   - Schema: [e.g., AGENTS]
   - Agent Name: [e.g., MY_SALES_AGENT]
   - Connection: [default: snowhouse]
   
   What role should I use for editing?
   - Role: [e.g., MY_AGENT_EDITOR_ROLE]
   Note: This role must have privileges to modify the agent on <DATABASE>.<SCHEMA>
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
├── versions/
│   └── vYYYYMMDD-HHMM/
│       ├── agent_metadata.json  ← Raw DESCRIBE AGENT output
│       ├── edit_spec.json       ← Will contain changes to apply
│       ├── full_agent_spec.json ← Merged result (written by prepare_agent_spec.py)
│       └── evals/
```

**Verify after running:** Check that `metadata.yaml` exists in the workspace root before proceeding.

**IMPORTANT:** After completing step 1, proceed to step 2. 

### Step 2: Get Current Agent Configuration

**Goal:** Retrieve and display the current agent configuration

**Actions:**

1. **Fetch current configuration via SQL:**

   ```sql
   DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```

   This returns a single row with columns: `name`, `database_name`, `schema_name`, `owner`, `comment`, `profile`, `agent_spec`, `created_on`.

2. **Save the raw DESCRIBE output to the workspace as-is:**

   Dump the entire DESCRIBE AGENT result as a JSON object to `agent_metadata.json`. Do NOT parse or extract the `agent_spec` column — save the full row wholesale. The `prepare_agent_spec.py` script will handle extraction later.

   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file agent_metadata.json --stdin
   <PASTE THE FULL DESCRIBE AGENT OUTPUT AS JSON HERE>
   EOF
   ```

   **Example `agent_metadata.json` content:**
   ```json
   {
     "name": "MY_SALES_AGENT",
     "database_name": "MY_DATABASE",
     "schema_name": "AGENTS",
     "owner": "AGENT_ADMIN_ROLE",
     "comment": "",
     "profile": null,
     "agent_spec": "{\"models\":{\"orchestration\":\"auto\"},\"tools\":[...]}",
     "created_on": "2026-03-01T12:00:00Z"
   }
   ```

3. **Present a summary** of the current configuration to the user:
   - Current instructions (orchestration, response, system, sample_questions)
   - Current tools and their descriptions
   - Current comment
   - Current model configuration

**IMPORTANT:** After completing Step 2, proceed to Step 3.

### Step 3: Select What to Edit

**Goal:** Understand what the user wants to modify

**Actions:**

1. **Present configurable options:**

   ```
   What would you like to edit?

   1. instructions - Agent instructions
      - orchestration: How the agent orchestrates responses
      - response: Response formatting instructions
      - system: System-level instructions
      - sample_questions: Example questions

   2. comment - Agent description

   3. models - Model configuration

   4. orchestration - Orchestration settings (budget, tokens)

   5. tools - Add, modify, or remove tool definitions

   6. tool_resources - Modify tool resources configuration

   7. experimental - Experimental flags

   8. profile - Agent profile settings

   Select option(s) or describe your changes:
   ```

2. **Route based on selection:**
   - **instructions** → Go to **Branch A**
   - **comment** → Go to **Branch B**
   - **tools / tool_resources** → Go to **Branch C**
   - **models / orchestration / experimental / profile** → Go to **Branch D**

### Branch A: Edit Instructions

**Goal:** Modify agent instructions

**Actions:**

1. **Ask which instruction field(s) to modify:**
   - `orchestration`: How the agent should orchestrate responses
   - `response`: Response formatting instructions
   - `system`: System-level instructions
   - `sample_questions`: Example questions the agent can answer

2. **Ask for the new value(s)** for the selected field(s).

3. **Build the agent spec JSON** with only the instructions changes:

   ```json
   {
     "instructions": {
       "<sub_key>": "<new_value>"
     }
   }
   ```

   **Example - Edit orchestration instructions:**
   ```json
   {
     "instructions": {
       "orchestration": "You are a helpful data analyst. Always explain your reasoning step by step."
     }
   }
   ```

   **Example - Edit multiple instruction fields:**
   ```json
   {
     "instructions": {
       "orchestration": "You are a sales analytics assistant.",
       "response": "Be concise. Use bullet points for lists.",
       "system": "Always verify data accuracy before presenting results."
     }
   }
   ```

4. **Save the edit spec to file (MANDATORY before applying):**

   Use `workspace_write.py` to save the changes to the workspace:

   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file edit_spec.json --stdin
   {"instructions": {"<sub_key>": "<new_value>"}}
   EOF
   ```

   **Example:**
   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn MY_DATABASE.AGENTS.MY_SALES_AGENT --file edit_spec.json --stdin
   {"instructions": {"orchestration": "You are a helpful data analyst. Always explain your reasoning step by step."}}
   EOF
   ```

5. **Go to Step 5** to apply changes.

### Branch B: Edit Comment

**Goal:** Update the agent's description/comment

**Actions:**

1. **Ask for the new comment text.**

2. **Build the agent spec JSON:**

   ```json
   {
     "comment": "<NEW_COMMENT>"
   }
   ```

3. **Save the edit spec to file (MANDATORY before applying):**

   Use `workspace_write.py` to save the changes:

   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file edit_spec.json --stdin
   {"comment": "<NEW_COMMENT>"}
   EOF
   ```

4. **Go to Step 5** to apply changes.

### Branch C: Edit Tools or Tool Resources

**Goal:** Add, modify, or remove tools from the agent

**Actions:**

1. **Ask the user what they want to do:**
   - Add an existing tool (from Snowflake)
   - Create a new tool (Semantic View, Cortex Search Service, or Stored Procedure)
   - Modify an existing tool's description
   - Remove a tool
   - Modify tool resources (warehouse, semantic view, etc.)

2. **If the user wants to add an existing tool:**

   a. **Ask for tools location:**

   ```
   Where are your semantic views and search services located?
   - Tools Database: [e.g., DATA_DB]
   - Tools Schema: [e.g., ANALYTICS]
   ```
   
   b. Query available **Cortex Search Services**:

   ```sql
   SHOW CORTEX SEARCH SERVICES IN SCHEMA <TOOLS_DATABASE>.<TOOLS_SCHEMA>;
   ```

   c. Query available **Semantic Views**:

   ```sql
   SHOW SEMANTIC VIEWS IN SCHEMA <TOOLS_DATABASE>.<TOOLS_SCHEMA>;
   ```

   d. Query available **Stored Procedures** (if the user wants custom tools):

   ```sql
   SHOW PROCEDURES IN SCHEMA <TOOLS_DATABASE>.<TOOLS_SCHEMA>;
   ```

   e. Present available tools to the user:

   - Show name and description/comment for each tool
   - Group by type (Cortex Search Services, Semantic Views, Stored Procedures)

   f. Ask the user to select which tool(s) to add

   g. For the selected tool, ask for:
   - **name**: Tool name for the agent
   - **description**: Tool description
   - **For cortex_analyst_text_to_sql**: warehouse
   - **For cortex_search**: id_column, title_column, max_results

3. **If the user wants to create a new tool:**

   - **Read the file `TOOL_CREATION.md`** in the `create-cortex-agent` directory for detailed instructions on creating:
     - Semantic Views
     - Cortex Search Services
     - Custom Tools (Stored Procedures)
   - After creating the tool, return to step 2 to add the newly created tool

4. **Read current tools** from the DESCRIBE AGENT output (already in context from Step 2)

5. **Build the complete tools and tool_resources arrays** including existing tools plus changes:

   **Example - Add cortex_analyst_text_to_sql tool:**
   ```json
   {
     "tools": [
       // ... existing tools ...
       {
         "tool_spec": {
           "type": "cortex_analyst_text_to_sql",
           "name": "query_sales",
           "description": "Query sales data using natural language"
         }
       }
     ],
     "tool_resources": {
       // ... existing tool_resources ...
       "query_sales": {
         "execution_environment": {
           "type": "warehouse",
           "warehouse": "MY_WAREHOUSE"
         },
         "semantic_view": "MY_DATABASE.MY_SCHEMA.SALES_VIEW"
       }
     }
   }
   ```

   **Example - Add cortex_search tool:**
   ```json
   {
     "tools": [
       // ... existing tools ...
       {
         "tool_spec": {
           "type": "cortex_search",
           "name": "search_docs",
           "description": "Search documentation"
         }
       }
     ],
     "tool_resources": {
       // ... existing tool_resources ...
       "search_docs": {
         "search_service": "MY_DATABASE.MY_SCHEMA.DOCS_SEARCH",
         "id_column": "DOC_ID",
         "title_column": "TITLE",
         "max_results": 5
       }
     }
   }
   ```

6. **Save the edit spec to file (MANDATORY before applying):**

   Use `workspace_write.py` to save the changes. For complex JSON with tools, use `--stdin` with a heredoc:

   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file edit_spec.json --stdin
   {
     "tools": [
       {
         "tool_spec": {
           "type": "cortex_search",
           "name": "search_docs",
           "description": "Search documentation"
         }
       }
     ],
     "tool_resources": {
       "search_docs": {
         "search_service": "MY_DATABASE.MY_SCHEMA.DOCS_SEARCH",
         "id_column": "DOC_ID",
         "title_column": "TITLE",
         "max_results": 5
       }
     }
   }
   EOF
   ```

7. **Go to Step 5** to apply changes.

### Branch D: Edit Models, Orchestration, Experimental, or Profile

**Goal:** Modify model configuration, orchestration settings, experimental flags, or profile

**Actions:**

1. **Ask for the specific changes** based on selection:

   **For models:**
   ```json
   {
     "models": {
       "orchestration": "claude-3-5-sonnet"
     }
   }
   ```

   **For orchestration (budget settings):**
   ```json
   {
     "orchestration": {
       "budget": {
         "seconds": 900,
         "tokens": 400000
       }
     }
   }
   ```

   **For experimental:**
   ```json
   {
     "experimental": {
       "flag_name": "value"
     }
   }
   ```

   **For profile:**
   ```json
   {
     "profile": {
       "setting_name": "value"
     }
   }
   ```

2. **Save the edit spec to file (MANDATORY before applying):**

   Use `workspace_write.py` to save the changes:

   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file edit_spec.json --stdin
   {"models": {"orchestration": "claude-3-5-sonnet"}}
   EOF
   ```

3. **Go to Step 5** to apply changes.

### Pre-Step-5 Checklist (MANDATORY)

**⛔ STOP - Do NOT proceed to Step 5 until you verify:**

The `workspace_write.py` script should have printed:
- ✓ The path to the created `edit_spec.json` file

If you did NOT see this output, go back and run the `workspace_write.py` command.

**If `edit_spec.json` does not exist, the workflow will fail.**

### Step 5: Apply Changes

**Goal:** Apply the changes to the agent

**⚠️ CHECKPOINT**: Before applying changes, show the user what will be changed:

```
I will apply the following changes to agent <DATABASE>.<SCHEMA>.<AGENT_NAME>:

[Show the contents of edit_spec.json]
```

**If the user has already given explicit permission to apply changes** (e.g., "apply the changes", "I give you permission", "proceed with the edit"), **proceed immediately without asking for confirmation.**

Otherwise, ask: "Do you want to proceed? (yes/no)" and wait for confirmation. If user says "no", return to Step 3.

**⚠️ CRITICAL - MERGE BEHAVIOR:**

The `prepare_agent_spec.py` script automatically extracts the `agent_spec` from `agent_metadata.json` and deep-merges `edit_spec.json` with it to preserve existing values.

**How the merge works:**
- For nested objects like `instructions`: Your changes are deep-merged with existing values
- For arrays like `tools`: Your array replaces the existing array (include ALL tools)
- For simple values like `comment`: Your value replaces the existing value

**Example - Updating only `response` instructions:**
```
edit_spec.json:           {"instructions": {"response": "new value"}}
agent_metadata.json spec: {"instructions": {"orchestration": "existing", "response": "old"}}
                                    ↓ merge
Result sent to SQL:       {"instructions": {"orchestration": "existing", "response": "new value"}}
```

**⚠️ WARNING:** Do NOT include empty or null values in `edit_spec.json`:
```json
{"instructions": {"response": "new value", "orchestration": ""}}
```
This will **CLEAR** the orchestration instructions even with merge!

**Actions:**

1. **Prepare the merged spec:**

   ```bash
   uv run python ../scripts/prepare_agent_spec.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```

   This will:
   - Read `agent_metadata.json` and `edit_spec.json` from the latest version folder
   - Extract the `agent_spec` from the metadata
   - Deep-merge the changes with the current config
   - Validate the merged result
   - Write `full_agent_spec.json` to the workspace
   - Print the merged spec JSON to stdout

2. **Apply via SQL** using the output from `prepare_agent_spec.py`:

   ```sql
   ALTER AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> MODIFY LIVE VERSION SET
   SPECIFICATION = $spec$
   <PASTE THE MERGED SPEC JSON FROM prepare_agent_spec.py OUTPUT>
   $spec$;
   ```

   **Example:**
   ```sql
   ALTER AGENT MY_DATABASE.AGENTS.MY_SALES_AGENT MODIFY LIVE VERSION SET
   SPECIFICATION = $spec$
   {
     "instructions": {"orchestration": "existing instructions", "response": "new value"},
     "models": {"orchestration": "auto"},
     "tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "query_sales", "description": "Query sales data"}}],
     "tool_resources": {"query_sales": {"execution_environment": {"type": "warehouse", "warehouse": ""}, "semantic_view": "MY_DATABASE.ANALYTICS.SALES_VIEW"}}
   }
   $spec$;
   ```

   **IMPORTANT:** Use `$spec$` as the dollar-quote delimiter (not `$$`) to avoid conflicts.

3. **Check the output** for success or error messages.

**IMPORTANT:** After completing Step 5, proceed to Step 6.

### Step 6: Verify Changes

**Goal:** Confirm the edit was applied successfully

**Actions:**

1. **Fetch updated configuration via SQL:**

   ```sql
   DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```

   Extract and parse the `agent_spec` value (same unwrap as Step 2).

2. **Save the raw DESCRIBE output to the workspace:**

   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file updated_agent_metadata.json --stdin
   <PASTE THE FULL DESCRIBE AGENT OUTPUT AS JSON HERE>
   EOF
   ```

3. **Compare** with previous configuration to confirm changes were applied.

4. **Optionally test the agent** with a simple query:

   ```bash
   uv run python ../scripts/test_agent.py --agent-name <AGENT_NAME> \
     --question "What can you do?" \
     --workspace <WORKSPACE_DIR> \
     --output-name test_verification.json \
     --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>

   # Example:
   uv run python ../scripts/test_agent.py --agent-name MY_SALES_AGENT \
     --question "What can you do?" \
     --workspace MY_DATABASE_AGENTS_MY_SALES_AGENT \
     --output-name test_verification.json \
     --database MY_DATABASE --schema AGENTS --connection snowhouse
   ```

**Verification Checklist:**

- ✅ SQL command succeeded without errors
- ✅ Changes reflected in updated agent spec
- ✅ Agent responds correctly to test query (if tested)

**Agent edit complete.**

## Valid Agent Spec Keys

| Key | Type | Description |
|-----|------|-------------|
| `instructions` | object | Agent instructions |
| `models` | object | Model configuration |
| `orchestration` | object | Orchestration settings |
| `tools` | array | Tool definitions |
| `tool_resources` | object | Resources for tools |
| `comment` | string | Agent description |
| `profile` | object | Agent profile settings |
| `experimental` | object | Experimental flags |

### Instructions Sub-Keys

| Key | Description |
|-----|-------------|
| `orchestration` | How the agent should orchestrate responses |
| `response` | Response formatting instructions |
| `system` | System-level instructions |
| `sample_questions` | Example questions the agent can answer |

## Technical Notes

### Edit Method

This workflow uses `sql_execute` to run `ALTER AGENT` SQL directly:

- The current spec is fetched via `DESCRIBE AGENT` and saved to the workspace
- Partial changes are saved as `edit_spec.json`
- `prepare_agent_spec.py` deep-merges changes with the current config and validates
- The merged spec is applied via `ALTER AGENT ... MODIFY LIVE VERSION SET SPECIFICATION = $spec$ ... $spec$`
- Dollar-quote delimiter `$spec$` is used instead of `$$` to avoid conflicts

### Partial Updates

When editing, you only need to include the fields you want to change. The `prepare_agent_spec.py` script will merge your changes with the existing configuration.

**Example - Only update instructions:**
```json
{
  "instructions": {
    "response": "Always include a summary at the end."
  }
}
```

**Example - Only update comment:**
```json
{
  "comment": "Sales analytics agent - v2.0"
}
```

### Tool Types Reference

| Type | Use Case | Required tool_resources |
|------|----------|------------------------|
| `cortex_analyst_text_to_sql` | Semantic views | `semantic_view`, `execution_environment` |
| `cortex_search` | Search services | `search_service`, `id_column`, `title_column`, `max_results` |
| `generic` | Stored procedures | `type: "procedure"`, `identifier`, `execution_environment`, `input_schema` |

## Troubleshooting

### Agent Not Found

**Symptom:** "agent does not exist" or HTTP 404

**Solution:**

```sql
SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
```

Verify the database, schema, and agent name are correct.

### Permission Issues

**Symptom:** "insufficient privileges" when running ALTER AGENT or DESCRIBE AGENT

**Solution:**

1. Check current role and switch if needed:
   ```sql
   SELECT CURRENT_ROLE();
   USE ROLE <role_with_agent_privileges>;
   ```

2. Verify your role has appropriate privileges:
   ```sql
   SHOW GRANTS ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```

3. If needed, request grants from admin:
   ```sql
   GRANT USAGE ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> TO ROLE <your_role>;
   ```

### Invalid Keys Error

**Symptom:** "Invalid keys: <key>"

**Solution:** Only use valid keys: `comment`, `experimental`, `instructions`, `models`, `orchestration`, `profile`, `tool_resources`, `tools`

### JSON Validation Failed

**Symptom:** "JSON validation failed" with specific errors

**Solution:** Check the error message and fix the JSON structure:
- `instructions` must be an object, not a string
- `tools` must be an array with `tool_spec` wrappers
- `tool_resources` must be a top-level object, not nested in tools

## Examples

### Edit Instructions Only

```json
{
  "instructions": {
    "orchestration": "You are a helpful data analyst. Always explain your reasoning.",
    "response": "Be concise. Use bullet points for lists."
  }
}
```

### Edit Comment Only

```json
{
  "comment": "Sales analytics agent - v2.0. Owner: analytics-team@company.com"
}
```

### Edit Model Configuration

```json
{
  "models": {
    "orchestration": "claude-3-5-sonnet"
  }
}
```

### Add a New Tool

```json
{
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "existing_tool",
        "description": "Existing tool description"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "new_sales_tool",
        "description": "Query sales data using natural language"
      }
    }
  ],
  "tool_resources": {
    "existing_tool": {
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "MY_WH"
      },
      "semantic_view": "DB.SCHEMA.EXISTING_VIEW"
    },
    "new_sales_tool": {
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "MY_WH"
      },
      "semantic_view": "DB.SCHEMA.SALES_VIEW"
    }
  }
}
```

### Edit Multiple Fields

```json
{
  "comment": "Updated agent - v2.1",
  "instructions": {
    "orchestration": "Focus on sales metrics.",
    "response": "Include charts when relevant."
  },
  "orchestration": {
    "budget": {
      "seconds": 600,
      "tokens": 300000
    }
  }
}
```

## Notes

- **Partial updates**: You only need to include fields you want to change
- **Tool modifications**: When editing tools, include ALL tools (existing + new/modified)
- **Workspace tracking**: All edits are tracked in the workspace directory
- **Rollback**: Keep `agent_metadata.json` to restore previous configuration if needed
