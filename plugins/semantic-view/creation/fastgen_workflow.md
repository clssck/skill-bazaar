---
name: fastgen-workflow
description: FastGen system function workflow for automated semantic model generation from SQL queries and table metadata
---

# FastGen Workflow

## Overview

This workflow uses the FastGen system function to automatically generate semantic models from SQL queries and table metadata. FastGen will:

- Extract table metadata from Snowflake
- Infer primary keys and relationships
- Generate dimensions, measures, and metrics
- Create VQRs from SQL queries

## Prerequisites

- Semantic view name defined
- Snowflake context (database, schema) configured
- SQL context and business information gathered

## Phase 2: Generate and Validate FastGen Request

### Step 2.1: Extract Tables and Columns from SQL

Analyze user-provided SQL queries and extract:

- **Tables**: All references in `database.schema.table` format
- **Columns**: From SELECT, WHERE, GROUP BY, JOIN clauses
- **SQL Queries**: Complete executable statements (clean up placeholders)

**For each table, execute `DESCRIBE TABLE` to get complete column list:**

```sql
DESCRIBE TABLE <database>.<schema>.<table>;
```

Example: `ANALYTICS.LOGS.USAGE_LOGS` → columns: `[ACCOUNT_ID, LOGGED_AT, USER_ID, TOKENS_USED]`

### Step 2.2: Build FastGen Request JSON

**⚠️ CRITICAL**: Read [fastgen_request_spec.md](fastgen_request_spec.md) first to understand the system function schema.

Construct request JSON with `json_proto` wrapper. Key fields:

- `name`: Semantic view name (Step 1.1)
- `database`: Target database for semantic view
- `schema`: Target schema for semantic view
- `tables`: Array with `database`, `schema`, `table`, `columnNames` per table (camelCase!)
- `sqlSource.queries`: Array of SQL queries (optional, can be empty if only tables provided)
- `semanticDescription`: High-level description of the model (optional)
- `metadata.warehouse`: Current warehouse from Snowflake session

**Note**: All unquoted identifiers auto-normalize to UPPERCASE (Snowflake default).

**Keep in mind while calling the system function:**
- Wrap in `json_proto` object
- Use `columnNames`, `sqlSource`, `sqlText`, `correspondingQuestion` (camelCase)
- Use top-level `database`/`schema` fields instead of `extensions.semantic_view_db`/`semantic_view_schema`

### Step 2.3: Validate Request JSON

**Before calling FastGen, validate the request JSON**:

✅ **Required Fields Check**:

- Request is wrapped in `json_proto` object
- `name` is present and non-empty
- `database` is present (target database for semantic view)
- `schema` is present (target schema for semantic view)
- `metadata.warehouse` is present
- At least one table in `tables` array
- `sqlSource` object exists (queries array can be empty)

✅ **Warehouse Verification** (MANDATORY):

```sql
SELECT CURRENT_WAREHOUSE();
```

Verify the warehouse is active and use this value for `metadata.warehouse`.

✅ **Table Format Check**:

- Each table has `database`, `schema`, `table` fields
- Each table has `columnNames` array (non-empty, camelCase)
- All table references exist in Snowflake (verified with `DESCRIBE TABLE`)

✅ **SQL Query Check** (if queries provided):

- Each query has `sqlText` field
- `sqlText` is non-empty string
- SQL appears to be valid (starts with SELECT/WITH/etc.)

**If validation fails**: Ask user to provide missing information.

### Step 2.4: Save Request JSON

Save the request JSON to a file for reference:

- Location: `{WORKING_DIR}/creation/<semantic_view_name>_fastgen_request.json`
- Use proper JSON formatting (indent=2)

**⚠️ CRITICAL**: Use the `WORKING_DIR` variable from setup. This is the timestamped session directory created in `setup/SKILL.md`.

**Example path:**
```
{WORKING_DIR}/creation/<semantic_view_name>_fastgen_request.json
# Expands to: /app/semantic_view_20260219_143022/creation/<semantic_view_name>_fastgen_request.json
```

**Present request summary to user** (table count, column count) and proceed directly to Phase 3.

## Phase 3: Call FastGen System Function

### Overview: Single Execution Pattern with Query ID Storage

**⚠️ CRITICAL WORKFLOW**: Execute FastGen **ONCE**, **immediately store the query ID**, then use it for all subsequent data extraction with RESULT_SCAN.

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Execute FastGen (ONLY ONCE)                            │
│ SELECT SYSTEM$CORTEX_ANALYST_FAST_GENERATION(...) AS RESULT;   │
│ ↓ Query ID generated: abc123                                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: IMMEDIATELY Store Query ID (BEFORE ANY OTHER QUERIES!) │
│ SET fastgen_query_id = (SELECT LAST_QUERY_ID());               │
│ ↓ Stored: $fastgen_query_id = abc123                           │
│ ⚠️ CRITICAL: Do this NOW or the ID will be lost!                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Check Length + Get First Chunk                         │
│ SELECT LENGTH(...), SUBSTR(..., 1, 4000)                       │
│ FROM TABLE(RESULT_SCAN($fastgen_query_id));                    │
│ ↑ Uses stored ID, not LAST_QUERY_ID()                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Get Additional Chunks (if needed)                      │
│ SELECT SUBSTR(..., 4001, 4000)                                 │
│ FROM TABLE(RESULT_SCAN($fastgen_query_id));                    │
│ ↑ Uses stored ID, not LAST_QUERY_ID()                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Extract Structured Suggestions                         │
│ SELECT PARSE_JSON($1):json_proto:structuredSuggestions         │
│ FROM TABLE(RESULT_SCAN($fastgen_query_id));                    │
│ ↑ Uses stored ID, not LAST_QUERY_ID()                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Extract Warnings                                       │
│ SELECT PARSE_JSON($1):json_proto:warnings                      │
│ FROM TABLE(RESULT_SCAN($fastgen_query_id));                    │
│ ↑ Uses stored ID, not LAST_QUERY_ID()                          │
└─────────────────────────────────────────────────────────────────┘

Key Benefits:
✅ FastGen executed **ONLY ONCE** (saves compute time)
✅ Query ID stored IMMEDIATELY (prevents loss)
✅ All data accessed via stored ID (reliable and efficient)
✅ No risk of query ID changing (uses variable, not LAST_QUERY_ID())
✅ No need for CTE or multiple executions

⚠️ Common Mistake to Avoid:
❌ Using RESULT_SCAN(LAST_QUERY_ID()) for subsequent queries
✅ Always use RESULT_SCAN($fastgen_query_id) after storing the ID
```

### Step 3.1: Prepare Request JSON String

The system function requires the request JSON as a single-quoted string. Prepare it:

1. **Read the saved request JSON file**:
   ```
   Read file: {WORKING_DIR}/creation/<semantic_view_name>_fastgen_request.json
   ```

2. **Escape single quotes**: Replace any `'` with `''` in the JSON content

3. **Store as SQL-safe string**: Ready for embedding in SQL command

### Step 3.2: Execute FastGen System Function and Store Query ID

**⚠️ CRITICAL TWO-STEP PROCESS**: Execute FastGen once, then IMMEDIATELY store the query ID before any other operations.

#### Part 1: Execute FastGen (ONLY ONCE)

Execute the FastGen system function using `snowflake_sql_execute`:

```sql
SELECT SYSTEM$CORTEX_ANALYST_FAST_GENERATION('{
  "json_proto": {
    "name": "<semantic_view_name>",
    "database": "<target_database>",
    "schema": "<target_schema>",
    "tables": [
      {
        "database": "<table_database>",
        "schema": "<table_schema>",
        "table": "<table_name>",
        "columnNames": ["COLUMN1", "COLUMN2", "COLUMN3"]
      }
    ],
    "sqlSource": {
      "queries": [
        {
          "sqlText": "SELECT col1, SUM(col2) FROM table1 GROUP BY col1",
          "correspondingQuestion": "What is the summary by col1?"
        }
      ]
    },
    "semanticDescription": "Description of the semantic model",
    "metadata": {
      "warehouse": "<current_warehouse>"
    }
  }
}') AS FASTGEN_RESULT;
```

**Note**: 
- Replace the JSON content with the actual escaped request JSON from Step 3.1
- The `sqlSource` and `semanticDescription` fields are optional
- If no SQL queries, you can omit the `sqlSource` section entirely

#### Part 2: IMMEDIATELY Store Query ID (MANDATORY)

**⚠️ DO THIS IMMEDIATELY - BEFORE ANY OTHER QUERIES**

```sql
SET fastgen_query_id = (SELECT LAST_QUERY_ID());
```

**Why this is critical:**
- `LAST_QUERY_ID()` is **volatile** - it changes with EVERY query execution
- If you run any other query before storing it, the FastGen query ID is lost forever
- You will then have to re-execute FastGen (expensive and slow)

**Example of what goes wrong if you don't store it:**
```sql
SELECT SYSTEM$CORTEX_ANALYST_FAST_GENERATION(...);  -- Query ID: abc123
-- Oops, ran another query without storing!
SELECT LENGTH(...);                                  -- Query ID: def456
SELECT LAST_QUERY_ID();                             -- Returns: def456 (FastGen ID is LOST!)
-- Now you have to re-execute FastGen 😢
```

### Step 3.3: Extract YAML Content with Pagination

**Complete Workflow After FastGen Execution:**

Once you've stored the query ID, use `$fastgen_query_id` for ALL subsequent operations:

**1. Check YAML length and get first chunk:**
```sql
SELECT 
  LENGTH(PARSE_JSON($1):json_proto:semanticYaml::VARCHAR) as yaml_length,
  SUBSTR(PARSE_JSON($1):json_proto:semanticYaml::VARCHAR, 1, 4000) as yaml_chunk_1
FROM TABLE(RESULT_SCAN($fastgen_query_id));
```

**2. If yaml_length > 4000, get remaining chunks:**
```sql
-- Get second chunk
SELECT 
  SUBSTR(PARSE_JSON($1):json_proto:semanticYaml::VARCHAR, 4001, 4000) as yaml_chunk_2
FROM TABLE(RESULT_SCAN($fastgen_query_id));

-- Get third chunk (if needed)
SELECT 
  SUBSTR(PARSE_JSON($1):json_proto:semanticYaml::VARCHAR, 8001, 4000) as yaml_chunk_3
FROM TABLE(RESULT_SCAN($fastgen_query_id));

-- Continue for additional chunks based on yaml_length
-- Calculate chunks needed: chunks = CEIL(yaml_length / 4000)
```

**3. Combine all chunks** to form the complete YAML string.

**Key Points:**
- ✅ FastGen is executed **ONLY ONCE**
- ✅ Query ID is stored **IMMEDIATELY** in `$fastgen_query_id` variable
- ✅ All subsequent queries use `RESULT_SCAN($fastgen_query_id)` to access the same result
- ✅ This approach is efficient, reliable, and handles truncation automatically
- ✅ No need for CTE or re-executing the expensive system function
- ⚠️ **NEVER** use `RESULT_SCAN(LAST_QUERY_ID())` after the initial storage - always use the stored variable

### Step 3.4: Extract Structured Suggestions

**Extract relationship suggestions from FastGen:**

```sql
SELECT PARSE_JSON($1):json_proto:structuredSuggestions as suggestions
FROM TABLE(RESULT_SCAN($fastgen_query_id));
```

**Process the suggestions:**

1. Parse the JSON array of suggestions
2. Look for operations with:
   - `operation == "SEMANTIC_MODEL_CHANGE_OPERATION_APPEND"`
   - `path == "relationships"`
3. Extract `value.relationship` from each operation
4. Check `relationshipType` field:
   - ✅ **INCLUDE**: `many_to_one`, `one_to_one`, `one_to_many`
   - ❌ **EXCLUDE**: `many_to_many`

**Example: Filter many-to-many relationships**

Given suggestions like:
```json
{
  "changes": [
    {
      "operation": "SEMANTIC_MODEL_CHANGE_OPERATION_APPEND",
      "path": "relationships",
      "value": {
        "relationship": {
          "name": "ORDERS_TO_CUSTOMERS",
          "relationshipType": "many_to_one",
          ...
        }
      }
    },
    {
      "operation": "SEMANTIC_MODEL_CHANGE_OPERATION_APPEND",
      "path": "relationships",
      "value": {
        "relationship": {
          "name": "ORDERS_TO_PRODUCTS",
          "relationshipType": "many_to_many",
          ...
        }
      }
    }
  ]
}
```

**Filtering Result:**
- ✅ Apply: `ORDERS_TO_CUSTOMERS` (many_to_one)
- ❌ Filter: `ORDERS_TO_PRODUCTS` (many_to_many)

**Convert applied relationships to YAML format** (camelCase → snake_case):
- `leftTable` → `left_table`
- `rightTable` → `right_table`
- `joinType` → `join_type`
- `relationshipType` → `relationship_type`
- `relationshipColumns` → `relationship_columns`
- `leftColumn` → `left_column`
- `rightColumn` → `right_column`

### Step 3.5: Extract Warnings and Errors

**4. Extract warnings (if any):**
```sql
SELECT PARSE_JSON($1):json_proto:warnings as warnings
FROM TABLE(RESULT_SCAN($fastgen_query_id));
```

**5. Check for errors:**
```sql
SELECT 
  PARSE_JSON($1):error_code as error_code,
  PARSE_JSON($1):message as error_message
FROM TABLE(RESULT_SCAN($fastgen_query_id));
```

**If `error_code` is not null**, FastGen failed - proceed to Step 3.7 for error handling.

### Step 3.6: Save FastGen Output (MANDATORY)

**⚠️ CRITICAL**: You MUST save all files to disk. Tests will fail if files don't exist on the filesystem.

**DO NOT** embed YAML inline in SQL - files MUST be saved to disk.

#### 1. Save Semantic Model YAML

**Requirements**:
- **Location**: `{WORKING_DIR}/creation/<semantic_view_name>_semantic_model.yaml`
- **Content**: Complete YAML from all chunks + applied relationship suggestions (if any)
- **Format**: Valid YAML with proper indentation
- **Size**: Must be > 0 bytes (non-empty)

**Steps:**
1. Combine all YAML chunks from Step 3.3
2. Parse suggestions from Step 3.4 and convert applied relationships to YAML
3. Append relationships to the YAML (add to `relationships:` section)
4. Save complete YAML file using `write` tool

#### 2. Save Metadata JSON

- **Location**: `{WORKING_DIR}/creation/<semantic_view_name>_metadata.json`
- **Content**:
  - `semantic_view_name` - Name of the semantic view
  - `target_database` - Target database for deployment
  - `target_schema` - Target schema for deployment
  - `request_id` - Query ID from Step 3.2 (stored in `$fastgen_query_id`)
  - `warnings` - Array of warnings from Step 3.5
  - `errors` - Array of errors (if any) from Step 3.5
  - `suggestions_applied` - Array of applied relationship names
  - `suggestions_filtered` - Array of filtered suggestions with reason
  - `tables_included` - List of table names included in the model

**Metadata JSON Example:**

```json
{
  "semantic_view_name": "SALES_ANALYTICS",
  "target_database": "ANALYTICS_DB",
  "target_schema": "SEMANTIC_MODELS",
  "request_id": "01b2c3d4-e5f6-7890-a1b2-c3d4e5f67890",
  "warnings": [
    {
      "message": "No primary key found for table ORDERS, using heuristics"
    }
  ],
  "errors": [],
  "suggestions_applied": [
    "ORDERS_TO_CUSTOMERS",
    "CUSTOMERS_TO_REGIONS",
    "ORDERS_TO_SHIPMENTS"
  ],
  "suggestions_filtered": [
    {
      "name": "ORDERS_TO_PRODUCTS",
      "reason": "Many-to-many relationships excluded",
      "relationship_type": "many_to_many"
    }
  ],
  "tables_included": [
    "ANALYTICS_DB.PUBLIC.ORDERS",
    "ANALYTICS_DB.PUBLIC.CUSTOMERS",
    "ANALYTICS_DB.PUBLIC.REGIONS",
    "ANALYTICS_DB.PUBLIC.SHIPMENTS"
  ]
}
```

#### 3. Verify Files Saved

**🛑 MANDATORY CHECKPOINT**: Verify all files exist on disk before proceeding to Phase 4.

```bash
ls -la {WORKING_DIR}/creation/<semantic_view_name>_semantic_model.yaml
ls -la {WORKING_DIR}/creation/<semantic_view_name>_metadata.json
ls -la {WORKING_DIR}/creation/<semantic_view_name>_fastgen_request.json
```

All three files must exist and be non-empty.

### Step 3.7: Handle FastGen Failures

If FastGen fails (error_code present or no YAML generated), examine the error response:

**Common Errors:**

- **Table access/permissions** → Grant access or use manual approach
  ```sql
  -- Verify table access
  SELECT * FROM <database>.<schema>.<table> LIMIT 1;
  
  -- Check current role
  SELECT CURRENT_ROLE();
  
  -- Try different role if needed
  USE ROLE <different_role>;
  ```

- **Table not found** → Verify table names are correct and exist
  ```sql
  -- List tables in schema
  SHOW TABLES IN <database>.<schema>;
  
  -- Describe specific table
  DESCRIBE TABLE <database>.<schema>.<table>;
  ```

- **Warehouse not active** → Ensure warehouse is running
  ```sql
  -- Check warehouse status
  SHOW WAREHOUSES;
  
  -- Resume warehouse if suspended
  ALTER WAREHOUSE <warehouse> RESUME;
  
  -- Use warehouse explicitly
  USE WAREHOUSE <warehouse>;
  ```

- **Invalid column names** → Verify columns exist and match case
  ```sql
  -- Get exact column names
  DESCRIBE TABLE <database>.<schema>.<table>;
  ```

- **Insufficient permissions** → Need appropriate role for FastGen system function access
  - Try using ACCOUNTADMIN role (if available)
  - Or request admin to grant FastGen permissions to your role

**⚠️ FALLBACK**: If unrecoverable, load `fallback_creation.md` for manual workflow using `infer_primary_keys.py` and `extract_table_metadata.py`.

## Request JSON Reference

See [fastgen_request_spec.md](fastgen_request_spec.md) for complete system function request schema and examples.
