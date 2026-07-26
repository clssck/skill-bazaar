---
name: create-cortex-agent
description: "Create and administer Cortex Agents. Use for: creating agents, adding tools/skills, managing access grants, and agent administration. Covers the full agent creation workflow including tool selection, REST API creation, verification, optimization, and post-creation admin (granting access, troubleshooting)."
---

# Create Cortex Agent

## Prerequisites

- Active Snowflake connection
- CREATE AGENT privilege on the target schema
- Access to schemas containing Cortex Search Services and Semantic Views (if using existing tools)
- A role with appropriate privileges for agent creation

Whenever running scripts, make sure to use `uv`.

## User Configuration Required

The following information will be requested during the workflow:

**Step 1 - Administrative Setup:**

- **Target Database**: Where the agent will be created (e.g., `MY_DATABASE`)
- **Target Schema**: Schema for the agent (e.g., `AGENTS`)
- **Agent Name**: Name of the agent (e.g., `MY_SALES_AGENT`)
- **Role**: A role with CREATE AGENT privileges (e.g., `MY_AGENT_CREATOR_ROLE`)

**Step 2 - Requirements Gathering:**

- **Agent Purpose**: What questions or tasks should the agent handle?
- **Data Sources**: What data is available (semantic views, tables, etc.)?

**Step 3 - Tool Selection (if using existing tools):**

- **Tools Database**: Where your semantic views/search services are located (e.g., `DATA_DB`)
- **Tools Schema**: Schema containing your tools (e.g., `ANALYTICS`)

**Step 4 - Agent Creation:**

- **Connection Name**: Snowflake connection to use (default: `snowhouse`)

## Workflow Overview

This workflow creates a basic agent with placeholder content, with optional semantic view creation/optimization and agent-level optimization:

1. **Step 1:** Administrative setup (database, schema, agent name, role)
2. **Step 2:** Requirements gathering (understand analytics needs and data sources)
3. **Step 3:** Select or create tools (with semantic view optimization loop-back if needed)
4. **Step 4:** Create agent via REST API with placeholder descriptions
5. **Step 5:** Verify agent configuration
6. **Step 6 (Optional):** Agent and tool optimization and testing options

## Workflow Steps

### Step 1: Administrative Setup

**Goal:** Gather basic administrative configuration and create working directory for the agent

**Actions:**

1. **Ask the user for administrative configuration only:**

   ```
   Let's set up the basic administrative details for your agent.
   
   Where would you like to create your agent?
   - Database: [e.g., MY_DATABASE]
   - Schema: [e.g., AGENTS]
   - Agent Name: [e.g., MY_SALES_AGENT]
   
   What role should I use for agent creation?
   - Role: [e.g., MY_AGENT_CREATOR_ROLE]
   Note: This role must have CREATE AGENT privilege on <DATABASE>.<SCHEMA>
   ```

2. **Construct Fully Qualified Agent Name:**

   - Format: `<DATABASE>.<SCHEMA>.<AGENT_NAME>`
   - Example: `MY_DATABASE.AGENTS.MY_SALES_AGENT`

3. **Check if workspace directory exists:**

   - Check if `{DATABASE}_{SCHEMA}_{AGENT_NAME}/` directory exists
   - If exists: Reuse it and load existing metadata
   - If not: Create new directory structure using `init_agent_workspace.py`

4. **Create workspace (do NOT create directories manually):**

   **⚠️ ALWAYS use `init_agent_workspace.py` to create the workspace. Do NOT manually create directories with `mkdir`. The script creates required files including `metadata.yaml`.**

```bash
uv run python ../scripts/init_agent_workspace.py --agent-name <AGENT_NAME> --database <DATABASE> --schema <SCHEMA>

# Example:
uv run python ../scripts/init_agent_workspace.py --agent-name MY_SALES_AGENT --database MY_DATABASE --schema AGENTS
```

**Expected Directory Structure After Running Script:**

```
MY_DATABASE_AGENTS_MY_SALES_AGENT/
├── metadata.yaml
│   # database: MY_DATABASE
│   # schema: AGENTS
│   # name: MY_SALES_AGENT
├── optimization_log.md
└── versions/
    └── vYYYYMMDD-HHMM/
        └── evals/
```

**Verify after running:** Check that `metadata.yaml` exists in the workspace root before proceeding.

**IMPORTANT:** After completing Step 1, ask the user if they want to proceed to Step 2 before continuing.

### Step 2: Requirements Gathering

**Goal:** Understand what the agent should do and what data sources are available

**Actions:**

1. **Ask the user about the agent's purpose and analytics requirements:**

   ```
   Now let's understand what your agent should do.
   
   What questions or tasks should this agent handle?
   Examples:
   - Usage statistics and trends?
   - Error/failure analysis?
   - Feature adoption metrics?
   - Performance metrics?
   - User behavior patterns?
   
   What data sources do you have available?
   - Do you have semantic views, tables, or other data sources?
   - What's the structure of the data (logs, metrics, events)?
   - What domain does this data cover?
   ```

2. **Discuss and clarify the agent's scope:**
   - Help the user articulate clear use cases
   - Identify potential data sources that would support those use cases
   - Document the requirements for tool selection in Step 3

3. **Store requirements information:**
   - Add notes to the workspace metadata about the agent's purpose
   - Document expected queries or use cases
   - List potential data sources to look for or create

**IMPORTANT:** After completing Step 2, ask the user if they want to proceed to Step 3 before continuing.

### Step 3: Select or Create Tools to Add

**Goal:** Identify which Cortex Search Services, Semantic Views, and/or Stored Procedures to include in the agent or create them as needed.

**Actions:**

1. **Ask the user if they want to use existing tools or create new tools:**

   - **Option A: Use existing tools** - Query and select from tools that already exist in Snowflake
   - **Option B: Create new tools** - Create new Semantic Views, Cortex Search Services, or Stored Procedures

2. **If the user chooses "Use existing tools":**
   
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

   f. Ask the user to select which tool(s) to include

   g. For selected tools, save their fully qualified names and configuration details to the workspace metadata

3. **If the user chooses "Create new tools":**

   - **Read the file `TOOL_CREATION.md`** in this directory for detailed instructions on creating:
     - Semantic Views
     - Cortex Search Services
     - Custom Tools (Stored Procedures)
   - After creating the tools, return to Step 2 to select the newly created tools

4. **If the user needs tools that don't exist after viewing existing tools:**
   - Ask if they want to create new tools
   - If yes, **read the file `TOOL_CREATION.md`** in this directory for detailed instructions on creating:
     - Semantic Views
     - Cortex Search Services
     - Custom Tools (Stored Procedures)
   - After creating tools, return to querying and selecting tools

**IMPORTANT:** After completing Step 3 and getting user confirmation, ask the user if they want to proceed to Step 4 before continuing.

### Step 4: Create Agent via REST API

**Goal:** Create the agent in Snowflake with placeholder tool descriptions

**Note:** This step uses the database, schema, and role provided in Step 1. If the user hasn't specified a connection name, ask for it now (default: snowhouse). If you need to verify access, you can check:

```sql
SHOW GRANTS ON SCHEMA <DATABASE>.<SCHEMA>;
-- Ensure the role has CREATE AGENT privilege
```

**Actions:**

1. Build agent specification JSON with placeholder content:

   ```json
   {
     "models": {
       "orchestration": "auto"
     },
     "orchestration": {
       "budget": {
         "seconds": 900,
         "tokens": 400000
       }
     },
     "instructions": {
       "orchestration": "<optional_orchestration_instructions>",
       "response": "<optional_response_instructions>"
     },
     "tools": [
       {
         "tool_spec": {
           "type": "cortex_analyst_text_to_sql",
           "name": "<tool_name>",
           "description": "Query data from <VIEW_NAME>"
         }
       }
     ],
     "tool_resources": {
       "<tool_name>": {
         "execution_environment": {
           "query_timeout": 299,
           "type": "warehouse",
           "warehouse": ""
         },
         "semantic_view": "<FULLY_QUALIFIED_VIEW_NAME>"
       }
     }
   }
   ```

   **CRITICAL FORMAT NOTE:** The `tool_resources` must be a separate top-level object in the agent spec, not nested inside each tool. Each tool is referenced by its name in the `tool_resources` object.

2. Save the specification to the workspace using `workspace_write.py`:

   ```bash
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file agent_spec.json --stdin
   <PASTE THE SPEC JSON HERE>
   EOF

   # Example:
   cat << 'EOF' | uv run python ../scripts/workspace_write.py --fqn MY_DATABASE.AGENTS.MY_SALES_AGENT --file agent_spec.json --stdin
   {"models": {"orchestration": "auto"}, "tools": [...], "tool_resources": {...}}
   EOF
   ```

3. Prepare and validate the spec, then create the agent via SQL:

   ```bash
   uv run python ../scripts/prepare_agent_spec.py --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```

   This validates the spec and prints it to stdout. Use the output to execute the CREATE statement via `sql_execute`:

   ```sql
   CREATE OR REPLACE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>
   FROM SPECIFICATION $spec$
   <PASTE THE VALIDATED SPEC JSON FROM prepare_agent_spec.py OUTPUT>
   $spec$;
   ```

   **Example:**
   ```sql
   CREATE OR REPLACE AGENT MY_DATABASE.AGENTS.MY_SALES_AGENT
   FROM SPECIFICATION $spec$
   {
     "models": {"orchestration": "auto"},
     "tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "query_sales", "description": "Query sales data"}}],
     "tool_resources": {"query_sales": {"execution_environment": {"type": "warehouse", "warehouse": ""}, "semantic_view": "MY_DATABASE.ANALYTICS.SALES_VIEW"}}
   }
   $spec$;
   ```

**IMPORTANT:** Use `$spec$` as the dollar-quote delimiter (not `$$`) to avoid conflicts if the spec JSON contains `$$`.

**Example Agent Spec with Semantic Views:**

```json
{
  "models": {
    "orchestration": "auto"
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "query_sales",
        "description": "Query data from SALES_SEMANTIC_VIEW"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "query_customers",
        "description": "Query data from CUSTOMERS_VIEW"
      }
    }
  ],
  "tool_resources": {
    "query_sales": {
      "execution_environment": {
        "query_timeout": 299,
        "type": "warehouse",
        "warehouse": ""
      },
      "semantic_view": "<TOOLS_DATABASE>.<TOOLS_SCHEMA>.SALES_SEMANTIC_VIEW"
    },
    "query_customers": {
      "execution_environment": {
        "query_timeout": 299,
        "type": "warehouse",
        "warehouse": ""
      },
      "semantic_view": "<TOOLS_DATABASE>.<TOOLS_SCHEMA>.CUSTOMERS_VIEW"
    }
  }
}
```

**Example Agent Spec with Cortex Search Service:**

```json
{
  "models": {
    "orchestration": "auto"
  },
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
      "execution_environment": {
        "query_timeout": 299,
        "type": "warehouse",
        "warehouse": ""
      },
      "search_service": "ENG_CORTEXSEARCH.SNOWFLAKE_INTELLIGENCE.DOCS_SEARCH"
    }
  }
}
```

**Example Agent Spec with Stored Procedure (Custom Tool):**

```json
{
  "models": {
    "orchestration": "auto"
  },
  "tools": [
    {
      "tool_spec": {
        "type": "generic",
        "name": "calculate_metrics",
        "description": "Calculate business metrics for a given date range and metric type",
        "input_schema": {
          "type": "object",
          "properties": {
            "start_date": {
              "type": "string",
              "format": "date",
              "description": "Start date for metric calculation"
            },
            "end_date": {
              "type": "string",
              "format": "date",
              "description": "End date for metric calculation"
            },
            "metric_type": {
              "type": "string",
              "description": "Type of metric to calculate"
            }
          },
          "required": ["start_date", "end_date", "metric_type"]
        }
      }
    }
  ],
  "tool_resources": {
    "calculate_metrics": {
      "type": "procedure",
      "identifier": "MY_DATABASE.MY_SCHEMA.CALCULATE_METRICS",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "MY_WAREHOUSE",
        "query_timeout": 300
      }
    }
  }
}
```

**Example Agent Spec with Multiple Tool Types:**

```json
{
  "models": {
    "orchestration": "auto"
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "query_sales_data",
        "description": "Query sales data using natural language"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_search",
        "name": "search_docs",
        "description": "Search product documentation"
      }
    },
    {
      "tool_spec": {
        "type": "generic",
        "name": "calculate_metrics",
        "description": "Calculate business metrics",
        "input_schema": {
          "type": "object",
          "properties": {
            "start_date": {
              "type": "string",
              "format": "date"
            },
            "end_date": {
              "type": "string",
              "format": "date"
            }
          },
          "required": ["start_date", "end_date"]
        }
      }
    }
  ],
  "tool_resources": {
    "query_sales_data": {
      "execution_environment": {
        "query_timeout": 299,
        "type": "warehouse",
        "warehouse": ""
      },
      "semantic_view": "MY_DATABASE.MY_SCHEMA.SALES_SEMANTIC_VIEW"
    },
    "search_docs": {
      "execution_environment": {
        "query_timeout": 299,
        "type": "warehouse",
        "warehouse": ""
      },
      "search_service": "MY_DATABASE.MY_SCHEMA.DOCS_SEARCH"
    },
    "calculate_metrics": {
      "type": "procedure",
      "identifier": "MY_DATABASE.MY_SCHEMA.CALCULATE_METRICS",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "MY_WAREHOUSE",
        "query_timeout": 300
      }
    }
  }
}
```

**Output:**

- Agent created in Snowflake
- Agent has basic placeholder tool descriptions
- Agent is functional but not optimized

**Next:** Proceed to Step 5 to verify the agent was created correctly

### Step 5: Verify Agent Configuration

**Goal:** Confirm the agent was created successfully with all tools configured

**Actions:**

1. Verify agent exists:

   ```sql
   SHOW AGENTS LIKE '<AGENT_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
   ```

2. Test the agent with a simple query to verify it works:

   ```bash
   uv run python ../scripts/test_agent.py --agent-name <AGENT_NAME> \
     --question "What can you do?" \
     --workspace <WORKSPACE_DIR> \
     --output-name test_verification.json \
     --database <DATABASE> \
     --schema <SCHEMA> \
     --connection <CONNECTION_NAME>

   # Example (using values from Step 1):
   uv run python ../scripts/test_agent.py --agent-name MY_SALES_AGENT \
     --question "What can you do?" \
     --workspace MY_DATABASE_AGENTS_MY_SALES_AGENT \
     --output-name test_verification.json \
     --database MY_DATABASE \
     --schema AGENTS \
     --connection snowhouse
   ```

   Review the response to ensure:

   - No error messages (like "No tool resources provided" or "failed to connect to Cortex API")
   - Agent responds successfully with a description of its capabilities
   - Agent lists the tools/data sources it can query
   - Basic functionality is working

**Example Verification:**

```sql
-- Check agent exists
SHOW AGENTS LIKE 'MY_SALES_AGENT' IN SCHEMA MY_DATABASE.AGENTS;

-- View full configuration
DESCRIBE AGENT MY_DATABASE.AGENTS.MY_SALES_AGENT;

-- Expected agent_spec:
-- {"models":{"orchestration":"auto"},"tools":[{"tool_spec":{"type":"cortex_analyst_text_to_sql","name":"query_sales","description":"Query data from SALES_SEMANTIC_VIEW"}},...]}
```

**Verification Checklist:**

- ✅ Agent exists in target schema
- ✅ Agent responds to "What can you do?" without errors
- ✅ Agent lists the tools/data sources it can query
- ✅ Basic functionality is working

3. **Grant access to other users/roles (if needed):**

   Ask the user if other roles need access to the agent. If yes, read `ACCESS_MANAGEMENT.md` for GRANT/REVOKE instructions.

### Step 6: Agent and Tool Optimization and Testing (Optional)

**IMPORTANT:** After completing Step 5, ask the user which optimization/testing option they would like to pursue (or if they want to skip this step).

**Goal:** Optimize and test the agent using various methods

**Present the user with four options:**

**Option 1: Audit agent against best practices**

- Use the `best-practices` skill to check the agent configuration against best practices
- Review recommendations for tool descriptions, instructions, and overall agent design
- Make manual improvements based on the audit results

**Option 2: Test agent with sample queries**

- Use the `adhoc-testing-and-dataset-curation-for-cortex-agent` skill
- Test the agent with ad-hoc sample queries
- Validate agent functionality and identify potential issues
- Optionally curate a dataset from test queries

**Option 3: Systematic optimization with dataset**

- Use the `optimize-cortex-agent` skill
- Create or use an existing dataset for systematic evaluation
- Automatically generate production-quality tool descriptions and instructions
- Run comprehensive optimization based on evaluation results

**Option 4: Optimize semantic views**

- Optimize semantic views used by the agent
- Follow the semantic view optimization workflow (see below)
- Audit and improve semantic view components (dimensions, metrics, relationships, VQRs)
- Update semantic views in Snowflake before using them in the agent

**User Prompt:**

```
Your agent is now created with basic placeholder descriptions. How would you like to proceed?

1. Audit agent against best practices
2. Test agent with sample queries (adhoc testing)
3. Systematic optimization with dataset
4. Optimize semantic views
5. Skip optimization/testing for now

Please select an option (1-5):
```

**If User Selects Option 1:**

1. Inform the user you will use the `best-practices` skill
2. Follow the `best-practices` skill to audit the agent
3. Present audit results and recommendations
4. Ask if they want to make improvements based on the audit

**If User Selects Option 2:**

1. Inform the user you will use the `adhoc-testing-and-dataset-curation-for-cortex-agent` skill
2. Follow the skill to test the agent with sample queries
3. Review test results and identify any issues
4. Optionally help curate a dataset from successful test queries

**If User Selects Option 3:**

1. Inform the user you will use the `optimize-cortex-agent` skill
2. Follow the skill to:
   - Create or identify a dataset for evaluation
   - Run systematic evaluation
   - Generate optimized tool descriptions and instructions
   - Update the agent with improvements
3. Review optimization results

**If User Selects Option 4:**

1. List the cortex analyst tools available in the agent.
2. Follow the workflow described below:

   - Show the pause message with agent context:

     ```
     Great! Let's audit and optimize this semantic view for to your agent.

     **⏸️ PAUSING AGENT CREATION**
     - Agent: [AGENT_NAME] (workspace: [PATH])
     - Status: Tool selection in progress
     - Selected tools so far: [LIST]
     - Current tool being optimized: [SEMANTIC_VIEW_NAME]

     I'll now walk you through the semantic view optimization workflow:
     1. Download the semantic view YAML
     2. Audit for best practices (duplicates, inconsistencies, missing descriptions)
     3. Optimize components (dimensions, metrics, relationships, VQRs)
     4. Upload the improved YAML back to Snowflake

     Ready to start the audit? (Yes/No)
     ```

   - **If user says YES:**

     - **Load** the `semantic-view` skills 
     - Follow the audit workflow from `audit/SKILL.md`
     - Follow optimization workflow from `optimization/SKILL.md`
     - When semantic view optimization is complete, show summary:

       ```
       ✅ SEMANTIC VIEW OPTIMIZATION COMPLETE

       Semantic View: [NAME]
       Changes made:
       - Added descriptions to 12 columns
       - Fixed 3 relationship issues
       - Optimized 5 VQRs
       - Updated custom instructions

       **▶️ RESUMING AGENT CREATION**
       - Agent: [AGENT_NAME]
       - Returning to: Step 6 (Agent and Tool Optimization)
       - Optimized semantic view "[NAME]" is now ready
       ```

   - **If user says NO:**
     - Skip semantic view optimization
     - Return to Step 6 options

3. After optimization, ask if they want to proceed with other optimization options or finish

**If User Selects Option 5:**

- Skip optimization/testing
- Agent remains with placeholder descriptions
- User can optimize later using any of the above options (1-4)

## Technical Notes

### Agent Creation Method

This workflow uses `sql_execute` to run `CREATE OR REPLACE AGENT` SQL directly:

- The spec is saved to the workspace via `workspace_write.py`
- The spec is validated via `prepare_agent_spec.py` (prints ready-to-use JSON to stdout)
- The agent is created via `sql_execute` with `CREATE OR REPLACE AGENT ... FROM SPECIFICATION $spec$ ... $spec$`
- Dollar-quote delimiter `$spec$` is used instead of `$$` to avoid conflicts

### Agent Specification Format

The agent specification JSON follows this structure:

```json
{
  "models": {
    "orchestration": "auto"
  },
  "orchestration": {
    "budget": {
      "seconds": 900,
      "tokens": 400000
    }
  },
  "instructions": {
    "orchestration": "<optional_orchestration_instructions>",
    "response": "<optional_response_instructions>"
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql" | "cortex_search" | "generic",
        "name": "<tool_name>",
        "description": "<tool_description>"
      }
    }
  ],
  "tool_resources": {
    "<tool_name>": {
      "execution_environment": {
        "query_timeout": 299,
        "type": "warehouse",
        "warehouse": ""
      },
      "semantic_view": "<fully_qualified_view_name>" |
      "semantic_model_file": "@<database>.<schema>.<stage>/<model_file>.yaml" |
      "search_service": "<fully_qualified_service_name>" |
      "type": "procedure",
      "identifier": "<fully_qualified_procedure_name>"
    }
  }
}
```

**Key Structure Notes:**

- `models`: Object with `orchestration` field (not array)
- `orchestration`: Optional object with `budget` settings (seconds and tokens)
- `instructions`: Optional object with `orchestration` and `response` instruction strings
- `tools`: Array of tool specifications, each with a `tool_spec` object containing type, name, and description
- `tool_resources`: **Separate top-level object** (not nested in tools) that maps tool names to their resources and execution environments
- `tool_spec.type`: Use `cortex_analyst_text_to_sql` for semantic views/models, `cortex_search` for search services, `generic` for stored procedures
- `tool_resources` options:
  - `semantic_view`: Fully qualified semantic view name (e.g., `"DATABASE.SCHEMA.VIEW_NAME"`)
  - `semantic_model_file`: Stage path to semantic model YAML file (e.g., `"@DATABASE.SCHEMA.STAGE/file.yaml"`)
  - `search_service`: Fully qualified search service name (e.g., `"DATABASE.SCHEMA.SERVICE_NAME"`)
  - For stored procedures: `type: "procedure"` and `identifier: "DATABASE.SCHEMA.PROCEDURE_NAME"`

### SQL Usage in Workflow

SQL is used for:

- Setting role context (`USE ROLE`)
- Querying available tools (`SHOW SEMANTIC VIEWS`, `SHOW CORTEX SEARCH SERVICES`)
- Verifying agent configuration (`DESCRIBE AGENT`, `SHOW AGENTS`)
- Testing queries (optional, via `test_agent.py` which uses SQL internally)

## Troubleshooting

### Permission Issues

**Symptom:** "insufficient privileges to operate on schema" or REST API 401/403 errors

**Root Cause:** The role specified in `--role` parameter lacks CREATE AGENT privileges.

**Solution:**

1. **Verify the role has required privileges:**

   ```sql
   SHOW GRANTS ON SCHEMA <DATABASE>.<SCHEMA>;
   -- Look for CREATE AGENT and USAGE grants for your role
   ```

2. **If the role lacks privileges**, grant them:

   ```sql
   -- Grant CREATE AGENT privilege on the schema
   GRANT CREATE AGENT ON SCHEMA <DATABASE>.<SCHEMA> TO ROLE <your_role>;

   -- Grant USAGE on the database and schema
   GRANT USAGE ON DATABASE <DATABASE> TO ROLE <your_role>;
   GRANT USAGE ON SCHEMA <DATABASE>.<SCHEMA> TO ROLE <your_role>;
   ```

3. **Contact your Snowflake admin** if you need privileges granted

**IMPORTANT:** Always specify the `--role` parameter with a role that has CREATE AGENT privileges (as provided in Step 1).

### Tool Not Found

**Symptom:** "semantic view / search service does not exist" error

**Solution:**

- Verify the fully qualified name is correct
- Check you have USAGE privileges on the tools database and schema:
  ```sql
  GRANT USAGE ON DATABASE <TOOLS_DATABASE> TO ROLE <your_role>;
  GRANT USAGE ON SCHEMA <TOOLS_DATABASE>.<TOOLS_SCHEMA> TO ROLE <your_role>;
  ```
- For semantic views, ensure REFERENCES privilege:
  ```sql
  GRANT REFERENCES ON <TOOLS_DATABASE>.<TOOLS_SCHEMA>.<semantic_view> TO ROLE <your_role>;
  ```

### Agent Creation via SQL Fails

**Symptom:** "insufficient privileges" when running CREATE OR REPLACE AGENT

**Root Cause:** The session's current role lacks CREATE AGENT privileges.

**Solution:**

1. **Check current role** and switch if needed:

   ```sql
   SELECT CURRENT_ROLE();
   USE ROLE <role_with_create_agent>;
   ```

2. Verify the role has CREATE AGENT privileges (see Permission Issues section above)

3. Validate the agent specification JSON is well-formed:

   - Tools must have `tool_spec` wrapper
   - Models must be object with `orchestration` field
   - Tool types must be `cortex_analyst_text_to_sql` or `cortex_search`

4. Ensure the target database and schema exist

5. If issues persist, verify grants:
   ```sql
   SHOW GRANTS ON SCHEMA <DATABASE>.<SCHEMA>;
   ```

## Best Practices

1. **Start Simple**: Create agent with one tool first, then add more as needed
2. **Test Tools Independently**: Verify semantic views and search services work before adding to agent
3. **Document Tool Purpose**: Add clear descriptions for each tool explaining when to use it
4. **Set Appropriate Timeouts**: For complex semantic views, increase query timeout
5. **Grant Minimal Privileges**: Only grant access to roles that need the agent
6. **Use Descriptive Names**: Choose agent and tool names that clearly indicate their purpose
7. **Track in Metadata**: Keep workspace metadata.yaml updated with agent configuration

## Notes

- **Configuration**: All database, schema, and role information is collected in Step 1 for flexibility across environments
- **Tool Naming**: Use descriptive, lowercase tool names with underscores (e.g., `sales_data_tool`)
- **Warehouse Selection**: Choose warehouses appropriate for the expected query workload
- **Access Control**: All queries run with the user's credentials; RBAC policies apply automatically
- **Environment Flexibility**: This workflow adapts to any Snowflake environment by parameterizing all database/schema/role references

---

## Additional Tool Types

### Tool Types

- `cortex_analyst_text_to_sql` - Structured data queries via semantic views
- `cortex_search` - Unstructured/document search
- `data_to_chart` - Visualization generation
- `code_interpreter` - Containerized sandbox for code execution
- `generic` - Custom UDFs/procedures (specify `function` or `procedure` in tool_resources)

### Adding Code Interpreter (Sandbox)

The `code_interpreter` tool enables a containerized sandbox environment where the agent can execute code (e.g., bash, Python). This requires a compute pool to be configured on the account and PrPr parameters to be enabled.

```json
{
  "tools": [
    {
      "tool_spec": {
        "type": "code_interpreter",
        "name": "code_interpreter"
      }
    }
  ],
  "tool_resources": {
    "code_interpreter": {
      "enabled": "true"
    }
  }
}
```

The compute pool, database, schema, and other sandbox infrastructure settings are configured at the account level via GS parameters, not in the agent spec. Contact your account administrator to ensure the sandbox compute pool is provisioned.

### Adding Skills

See `ADD_SKILLS.md` for detailed instructions on adding server-side skills to agents.
