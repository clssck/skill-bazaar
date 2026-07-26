---
name: semantic-view-creation
description: Create new semantic views using FastGen system function for automated generation from SQL queries and table metadata. Falls back to manual approach if FastGen fails.
---

# Creation Mode

## When to Load

User wants to CREATE a new semantic view (not optimize an existing one).

## ⚠️ CRITICAL: Create TODOs

**MANDATORY**: Use `system_todo_write` to create TODOs for all workflow phases.
All steps below are MANDATORY and cannot be skipped.

## Purpose

Generate a complete, validated semantic view using FastGen system function, which automatically:

- Extracts table metadata from Snowflake
- Infers primary keys and relationships
- Generates dimensions, measures, and metrics
- Creates VQRs from SQL queries

Falls back to manual approach if FastGen fails.

## Workflow

### Phase 0: Create Subdirectory

**⚠️ IMPORTANT**: The `WORKING_DIR` variable has already been set by `setup/SKILL.md` and points to the timestamped session directory: `{BASE_WORKING_DIR}/semantic_view_{TIMESTAMP}`.

**Create the creation subdirectory:**
```bash
mkdir -p {WORKING_DIR}/creation
```

**Example:**
```
WORKING_DIR = /app/semantic_view_20260219_143022
Creation directory: /app/semantic_view_20260219_143022/creation/
```

**All files for this creation workflow will be saved to `{WORKING_DIR}/creation/`**.

### Phase 1: Context Gathering

#### Step 1.1: Get Semantic View Name

Ask user for semantic view name (will be used as model name).

**Format**: Valid identifier (no spaces, lowercase with underscores recommended)

**Example**: `cortex_analyst_usage_analytics`

#### Step 1.2: Get Snowflake Context

Ask user for Snowflake configuration:

1. **Target Database** (required): Database for semantic view
2. **Target Schema** (required): Schema for semantic view

**Note**: Warehouse will be automatically retrieved from the active Snowflake connection settings. No need to ask the user for it.

**Example**:

- Database: `ANALYTICS_DB`
- Schema: `SEMANTIC_MODELS`

#### Step 1.3: Get SQL Context and Business Information

Ask user to provide context in ONE request. They can provide:

- SQL queries
- Table references
- Business context
- Any combination of the above

**⚠️ CRITICAL**: Never generate SQL queries on your own - always wait for user to provide them.

**What to Accept:**

**SQL Queries:**

- Supported: SQL strings, .sql files, .py files with SQL, VQR YAML files
- Extract: Table references, column names, complete SQL statements
- FastGen will use these to generate VQRs

```sql
SELECT account_id, DATE_TRUNC('day', logged_at) as ds,
  COUNT(DISTINCT user_id) as active_users
FROM analytics.logs.usage_logs
WHERE logged_at >= '2024-01-01' GROUP BY account_id, ds;
```

**Table References:**

- Accept fully qualified names: `database.schema.table`
- Query Snowflake to get all columns via `DESCRIBE TABLE`
- Set `sql_source.queries` to empty array in config

**Business Context:**

- Purpose of semantic view
- Key metrics to track
- Important filters or dimensions
- Time granularity (daily, hourly, etc.)

**⚠️ MANDATORY STOPPING POINT**: Wait for user to provide all context before proceeding.

### Phases 2-3: FastGen Workflow

**⚠️ LOAD FASTGEN WORKFLOW**: For detailed FastGen steps, load [fastgen_workflow.md](fastgen_workflow.md).

**Summary**: FastGen automates semantic model generation by:
1. Building and validating a request JSON from extracted SQL tables/queries
2. Executing FastGen system function directly via SQL: `SELECT SYSTEM$CORTEX_ANALYST_FAST_GENERATION(...)`
3. Storing query ID immediately: `SET fastgen_query_id = (SELECT LAST_QUERY_ID());`
4. Extracting YAML with pagination using `RESULT_SCAN($fastgen_query_id)`
5. Extracting and filtering structured suggestions (excluding many-to-many relationships)
6. Saving YAML and metadata files to disk
7. Handling common errors (permissions, syntax, warehouse issues)

**If FastGen fails**: Fall back to manual workflow in [fallback_creation.md](fallback_creation.md).

### Phase 4: Validation and Results

#### Step 4.1: Review FastGen Output

Check generated files:

- **YAML**: `<semantic_view_name>_semantic_model.yaml` (complete semantic model with tables, dimensions, measures, metrics, relationships, VQRs)
- **Metadata JSON**: `<semantic_view_name>_metadata.json` containing:
  - `warnings` - Any warnings from FastGen
  - `errors` - Any errors encountered
  - `request_id` - Unique identifier for debugging FastGen requests
  - `suggestions` - Relationship and primary key suggestions from FastGen (if any)

**Inspect the semantic model using `semantic_view_get.py`**:

```bash
# Get overview of all tables
cd {WORKING_DIR}/creation && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component tables

# Get all relationships
cd {WORKING_DIR}/creation && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component relationships

# Get all verified queries
cd {WORKING_DIR}/creation && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component verified_queries
```

**Note**: Files are in `{WORKING_DIR}/creation/` and scripts are in `{SKILL_BASE_DIR}/scripts/`.

**Reference**: See `reference/semantic_view_get.md` for complete tool documentation.

Present warnings/errors to user and check for applied/filtered suggestions in metadata JSON.

#### Step 4.2: Validate Semantic Model

**⚠️ CRITICAL PREREQUISITES**:
- ✅ FastGen execution completed (Phase 3)
- ✅ YAML file saved to disk at: `{WORKING_DIR}/creation/<semantic_view_name>_semantic_model.yaml`
- ✅ This is a VALIDATION-ONLY step (not for initial creation)

**⚠️ IF YOU HAVEN'T COMPLETED PHASE 3 FASTGEN WORKFLOW, GO BACK TO PHASE 2.**

**⚠️ MANDATORY STEP - Verify the semantic view yaml from FastGen System function**

**Validation Method**: Use `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML` with verify-only mode to validate the FastGen-generated YAML.

**Process**:

1. **Read the YAML file** (generated by FastGen in Phase 3):
   ```
   Read file: {WORKING_DIR}/creation/<semantic_view_name>_semantic_model.yaml
   ```

2. **Execute validation SQL**:
   ```sql
   CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
     '<target_database>.<target_schema>',
     $$
     <insert full YAML content from step 1 here>
     $$,
     TRUE
   );
   ```
   
**Note**: The `$$...$$` delimiter safely handles the YAML content without escaping issues. The `TRUE` flag means verify-only (no actual creation).

**Expected output**: 
- ✅ Success: "Semantic model is valid" or similar confirmation message
- ❌ Error: Specific validation errors with line numbers and issue descriptions

**If validation fails**:

- **Schema issues**: Check table/column names match Snowflake exactly - regenerate FastGen request with correct names and rerun Phase 3
- **Relationship issues**: Verify foreign key columns exist in both tables - check FastGen suggestions in metadata JSON
- **Syntax issues**: This indicates a FastGen generation issue - review FastGen output warnings/errors
- **Major issues**: Regenerate with modified FastGen request (return to Phase 2) OR fall back to manual approach ([fallback_creation.md](fallback_creation.md))

**⚠️ NEVER create or edit YAML manually - always regenerate via FastGen with corrected request, or use the fallback workflow.**

Apply fixes and re-validate until successful.

#### Step 4.3: Present Final Results

Present summary: name, location, counts (tables, columns, relationships, metrics, VQRs), warnings/errors, and file paths (YAML, metadata JSON, config JSON).

**⚠️ MANDATORY STOPPING POINT**: Ask user what they want to do next:

**User Options:**

1. **Enhance relationships and primary keys** → Proceed to Phase 5
2. **Skip to testing/deployment** → Proceed to Phase 6

### Phase 5: Optional Enhancement - Primary Keys and Relationships

**⚠️ OPTIONAL**: Only proceed if user selected option 1 from Step 4.3.

**⚠️ LOAD ENHANCEMENT WORKFLOW**: For detailed enhancement steps, load [primary_keys_and_relationships.md](primary_keys_and_relationships.md).

**Summary**: This optional phase automatically:
1. Identifies potential relationships by analyzing column naming patterns
2. Verifies primary keys using `infer_primary_keys.py` (95% uniqueness threshold)
3. Generates relationships using `relationship_creation.py`
4. Adds verified primary keys and relationships to the semantic model
5. Validates the enhanced model

### Phase 6: Next Steps

**Present user with options for next steps:**

**Option 1: Test with AUDIT MODE** (Recommended)

- Run AUDIT MODE to test VQRs and identify optimization opportunities
- Load `../audit/SKILL.md`

**Option 2: Debug SQL Generation**

- Run DEBUG MODE to troubleshoot specific SQL generation issues
- Load `../debug/SKILL.md`

**Option 3: Deploy to Snowflake**

- Upload semantic view to Snowflake
- Load `../upload/SKILL.md`

**Option 4: Manual Refinement**

- Use `semantic_view_set.py` for targeted edits
- Use `semantic_view_get.py` to inspect specific elements

**Option 5: Apply an advanced modeling pattern**

- Load `../patterns/SKILL.md` if the user wants to: compare a metric to the same period last year/month (YoY, MoM, SPLY); build a rolling average, YTD/QTD/MTD running total, or lag-N period comparison; model an SCD2 lookup with `valid_from`/`valid_to` or attribute an event to the dim row active at event time (ASOF); track a snapshot fact that must not sum across time (balance, inventory, headcount); model an accumulating funnel across multiple milestone dates; route a metric down a specific FK when one fact has two FKs to the same dim (multi-path `USING`); reuse the same physical dim under multiple roles; add a cross-entity derived metric (`% of total`, `net = gross − returns`); split shared dims across multiple fact tables; expose a `PRIVATE` fact used only inside the SV to derive a tier or other dimension; join on a key that doesn't exist as a physical column (computed FK); steer Cortex Analyst with verified queries / `AI_SQL_GENERATION` / `AI_QUESTION_CATEGORIZATION` metadata; or diagnose a fan trap, "multi-path relationship not supported" error, or numbers that look inflated against a deployed semantic view.

**⚠️ MANDATORY STOPPING POINT**: Wait for user to select next action.

## Request JSON Reference

See [fastgen_request_spec.md](fastgen_request_spec.md) for complete FastGen system function request schema and examples.
