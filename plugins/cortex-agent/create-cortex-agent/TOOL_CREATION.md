# Creating Tools for Cortex Agents

If the user needs tools that don't currently exist, follow these steps to create them:

## Creating a Semantic View

**Prerequisites:**

- `CREATE SEMANTIC VIEW` privilege on the target schema
- Access to the underlying tables/views that will be used in the semantic view

**Steps:**

1. **Determine the target location** for the semantic view:

   - Or ask the user for their preferred database and schema

2. **Consult Snowflake documentation** for the latest instructions on creating semantic views:

   - Search for "Snowflake semantic views" or "CREATE SEMANTIC VIEW" in Snowflake documentation
   - Follow the official documentation for:
     - Creating semantic views via UI (recommended) or SQL
     - Defining logical tables, dimensions, facts, and metrics
     - Setting up relationships between tables
     - Best practices and syntax
       Offer two options:
       **Option 1: Create via Snowflake UI** (Recommended for first-time users)

   ```
    Let me guide you through creating a semantic view:
   1. Open Snowflake UI: https://app.snowflake.com/[ORG_NAME]/[ACCOUNT_NAME]/#/cortex/analyst
      Example: https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/cortex/analyst
   2. Click "Create New" (top right corner)
   3. Select "Create New Semantic View"
   4. Follow the wizard to create semantic views from tables, sample queries, tableau, etc. and (optionally) add verified queries.
   5. Save with name: <VIEW_NAME>
   6. Come back here and let me know when it's ready
   Once you've created it, I can help you audit and optimize it before adding to your agent.
   ```

   **Option 2: Create Semantic View using Cortex (CREATION MODE)**

   For automated semantic view generation using the FastGen API, use the **semantic-view skill's CREATION MODE** workflow instead of the manual steps above.

   **When to use CREATION MODE:**
   - You have SQL queries or table references to base the semantic view on
   - You want automated generation of dimensions, measures, metrics, and relationships
   - You want FastGen to automatically infer primary keys and create VQRs

   **To use CREATION MODE:**
   1. Return to the agent creation workflow
   2. Select "Create Semantic View using Cortex" when prompted
   3. Follow the CREATION MODE workflow which will guide you through:
      - Context gathering (semantic view name, database, schema, SQL queries/tables)
      - Automated FastGen API generation
      - Validation and optional enhancement
      - Testing and deployment options

   Use CREATION MODE whenever possible; fall back to the manual UI/YAML paths only if the automated workflow cannot handle the scenario.

3. **Verify the semantic view was created:**

   ```sql
   SHOW SEMANTIC VIEWS LIKE '<VIEW_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
   DESCRIBE SEMANTIC VIEW <DATABASE>.<SCHEMA>.<VIEW_NAME>;
   ```

4. **Grant necessary privileges** (if needed):
   ```sql
   GRANT REFERENCES ON SEMANTIC VIEW <DATABASE>.<SCHEMA>.<VIEW_NAME>
   TO ROLE <role_name>;
   ```

**Note:** Always refer to the latest Snowflake documentation for up-to-date syntax, features, and best practices when creating semantic views.

## Creating a Cortex Search Service

For creating Cortex Search Services, if we have the `cortex-search` skill available, use it, which provides comprehensive workflows for:

- Uploading documents to Snowflake stages (PDF, Markdown, URLs, Google Docs)
- Processing documents into searchable embeddings tables
- Creating Cortex Search Services with CDC support
- Setting up continuous sync from Google Shared Drive via Openflow

**To use:**

1. Load `cortex-search`
2. Follow the workflow for your use case (local documents or Google Drive CDC)

### Alternative: Create from Existing Table/View (Manual Process)

If you already have a table with text/vector data and just need to create the search service:

1. **Consult Snowflake documentation** for the latest instructions on creating Cortex Search Services:
   - Search for "Cortex Search Service" or "CREATE CORTEX SEARCH SERVICE" in Snowflake documentation

2. **Verify the search service was created:**

   ```sql
   SHOW CORTEX SEARCH SERVICES LIKE '<SERVICE_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
   DESCRIBE CORTEX SEARCH SERVICE <DATABASE>.<SCHEMA>.<SERVICE_NAME>;
   ```

3. **Grant necessary privileges** (if needed):
   ```sql
   GRANT USAGE ON CORTEX SEARCH SERVICE <DATABASE>.<SCHEMA>.<SERVICE_NAME>
   TO ROLE <role_name>;
   ```

**Note:** Always refer to the latest Snowflake documentation for up-to-date syntax, features, and best practices when creating Cortex Search Services.

## Creating a Custom Tool (Stored Procedure)

**Prerequisites:**

- `CREATE PROCEDURE` privilege on the target schema
- A stored procedure already created in Snowflake (or knowledge of how to create one)
- Understanding of the stored procedure's input parameters and return type

**Steps:**

1. **Create or identify the stored procedure** you want to use as a tool:

   - **Consult Snowflake documentation** for the latest instructions on creating stored procedures:
     - Search for "CREATE PROCEDURE" or "Snowflake stored procedures" in Snowflake documentation
     - Follow the official documentation for:
       - Syntax and supported languages (SQL, JavaScript, Python, Java, Scala)
       - Parameter definitions and return types
       - Best practices and examples

2. **Verify the stored procedure exists and understand its signature:**

   ```sql
   SHOW PROCEDURES LIKE '<PROCEDURE_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
   DESCRIBE PROCEDURE <DATABASE>.<SCHEMA>.<PROCEDURE_NAME>(<parameter_types>);
   ```

3. **Grant necessary privileges** (if needed):

   ```sql
   GRANT USAGE ON PROCEDURE <DATABASE>.<SCHEMA>.<PROCEDURE_NAME>(<parameter_types>)
   TO ROLE <role_name>;
   ```

4. **Define the tool specification** for your agent (see Step 3 in SKILL.md for examples):
   - **Tool name**: Choose a descriptive name for the tool
   - **Description**: Write a clear description of what the stored procedure does
   - **Input schema**: Define the JSON schema that matches the stored procedure's parameters
   - **Tool resources**: Configure the procedure identifier and execution environment

**Key Considerations:**

- The stored procedure must already exist before you can add it as a tool
- You need to define an `input_schema` in the tool specification that matches the procedure's parameters
- The stored procedure will be executed server-side using the execution environment (warehouse) specified in `tool_resources`
- Parameter types in the input schema should match Snowflake data types (DATE, VARCHAR, NUMBER, etc.)

**Note:** Always refer to the latest Snowflake documentation for up-to-date syntax, features, and best practices when creating stored procedures. See Step 3 in SKILL.md for examples of how to configure stored procedures as tools in your agent specification.

## After Creating Tools

Once tools are created:

1. **Verify they appear in the tool listings:**

   ```sql
   SHOW CORTEX SEARCH SERVICES IN SCHEMA <DATABASE>.<SCHEMA>;
   SHOW SEMANTIC VIEWS IN SCHEMA <DATABASE>.<SCHEMA>;
   SHOW PROCEDURES IN SCHEMA <DATABASE>.<SCHEMA>;
   ```

2. **Continue with Step 2** in SKILL.md to select the newly created tools for your agent

3. **Document the tool creation** in your workspace metadata for future reference
   - For stored procedures, also document the input schema and parameter types
