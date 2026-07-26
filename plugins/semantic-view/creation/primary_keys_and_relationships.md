---
name: primary-keys-and-relationships
description: Optional enhancement workflow to automatically discover and add missing primary keys and relationships to semantic models
---

# Primary Keys and Relationships Enhancement

## Overview

**⚠️ OPTIONAL**: This workflow is only used when explicitly requested by the user after FastGen completes.

**Purpose**: Automatically discover and add missing primary keys and relationships to improve the semantic model's completeness.

## Prerequisites

- Completed semantic model from FastGen (Phase 4)
- User explicitly chose to enhance relationships and primary keys

## Workflow

### Step 5.1: Identify All Tables and Potential Primary Keys

Analyze the semantic model to identify ALL tables and their potential primary key columns. Look for columns with naming patterns like `*_ID`, `*_KEY`, `*_CODE` that may be primary keys or unique identifiers.

**Create a list of all tables and their potential primary key columns:**

```
Tables and Potential Primary Keys:
1. CUSTOMERS - Potential PK: CUSTOMER_ID
2. ORDERS - Potential PK: ORDER_ID
3. PRODUCTS - Potential PK: PRODUCT_ID
4. ORDER_DETAILS - Potential PK: ORDER_DETAIL_ID or (ORDER_ID, PRODUCT_ID)
5. CUSTOMER_FEEDBACK - Potential PK: FEEDBACK_ID
```

### Step 5.2: Verify Primary Keys for ALL Tables

For EACH table in the semantic model, verify its primary key using the `infer_primary_keys.py` script:

```bash
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python ../scripts/infer_primary_keys.py \
  --table <database>.<schema>.<table> \
  --output /tmp/<table>_pk.yaml \
  --hint-columns <column1>,<column2>,<column3>
```

**Note**: 
- `--hint-columns` accepts **comma-separated** column names (e.g., `CUSTOMER_ID` or `ACCOUNT_ID,DEPLOYMENT`)

**Example:**
```bash
uv run python ../scripts/infer_primary_keys.py \
  --table TEMP.SRIDHAR_ECOMMERCE_AGENT.CUSTOMERS \
  --output /tmp/customers_pk.yaml \
  --hint-columns CUSTOMER_ID
```

**Verification Logic:**

- Read the output YAML file
- Check `candidates` array for the column
- Verify `uniqueness_percentage >= 95.0` (default threshold)
- If valid → Primary key confirmed ✅
- If invalid → Mark as no valid primary key ❌

**⚠️ CRITICAL**: Run this for ALL tables in the semantic model, not just dimension tables. This ensures we have complete primary key information before attempting relationship generation.

**Collect all verified primary keys** with their uniqueness percentages for the summary.

### Step 5.3: Identify Potential Relationships

After verifying primary keys for all tables, analyze potential foreign key relationships. Look for columns with naming patterns like `*_ID`, `*_KEY`, `*_CODE` that may reference other tables. Common patterns include fact tables → dimension tables (e.g., ORDERS → CUSTOMERS), line item → header tables (e.g., ORDER_DETAILS → ORDERS), and event tables → multiple dimensions.

**Create a list of potential relationships:**

```
Potential Relationships:
1. ORDERS.CUSTOMER_ID → CUSTOMERS.CUSTOMER_ID
2. ORDER_DETAILS.ORDER_ID → ORDERS.ORDER_ID
3. ORDER_DETAILS.PRODUCT_ID → PRODUCTS.PRODUCT_ID
4. CUSTOMER_FEEDBACK.CUSTOMER_ID → CUSTOMERS.CUSTOMER_ID
5. CUSTOMER_FEEDBACK.ORDER_ID → ORDERS.ORDER_ID
6. CUSTOMER_FEEDBACK.PRODUCT_ID → PRODUCTS.PRODUCT_ID
```

**⚠️ CRITICAL RULE - Check Primary Key Compatibility:**
For each potential relationship, verify that source tables have matching columns for the COMPLETE primary key of the target table. **NEVER modify existing primary keys** - flag incompatibilities and ask the user whether to proceed without those relationships.


### Step 5.4: Generate Relationships Using relationship_creation.py

For each potential relationship where the target table has a verified primary key, use the `relationship_creation.py` script:

```bash
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python ../scripts/relationship_creation.py \
  --semantic-model <path_to_semantic_model.yaml> \
  --left-table <LEFT_TABLE> \
  --right-table <RIGHT_TABLE> \
  --left-columns <FK_COLUMN> \
  --right-columns <PK_COLUMN> \
  --output /tmp/<left_table>_to_<right_table>_rel.yaml

```bash
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python ../scripts/relationship_creation.py \
  --semantic-model <path_to_semantic_model.yaml> \
  --left-table <LEFT_TABLE> \
  --right-table <RIGHT_TABLE> \
  --left-columns <FK_COLUMN> \
  --right-columns <PK_COLUMN> \
  --output /tmp/<left_table>_to_<right_table>_rel.yaml
```

**Example:**

```bash
cd {WORKING_DIR}/creation && \
uv run python {SKILL_BASE_DIR}/scripts/relationship_creation.py \
  --semantic-model <semantic_view_name>_semantic_model.yaml \
  --left-table ORDERS \
  --right-table CUSTOMERS \
  --left-columns CUSTOMER_ID \
  --right-columns CUSTOMER_ID \
  --output /tmp/orders_to_customers_rel.yaml
```

**The script will:**

- ✅ Validate both tables exist
- ✅ Validate join columns exist
- ✅ Check primary keys on both sides
- ✅ Infer relationship type (many_to_one or one_to_one)
- ✅ Auto-swap tables if needed (left has PK but right doesn't)
- ❌ Reject many_to_many relationships

**Exit Codes:**
- **0**: Relationship successfully created (YAML file written)
- **2**: Relationship rejected as many-to-many (this is NOT an error - the script correctly identified an invalid relationship)
- **1**: Actual error (table not found, validation failed, etc.)

**Important**: When the Bash tool shows "failed" for this script, check the output message. If it says "Relationship REJECTED", this is a **successful rejection**, not a script failure. The script correctly determined the relationship is invalid.

**Collect all valid relationships** from the output YAML files (only those with exit code 0).

### Step 5.6: Apply Enhancements to Semantic Model

Apply all verified primary keys and relationships in a single atomic operation using `semantic_view_set.py`:

```bash
cd {WORKING_DIR}/creation && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_set.py \
  --input-file <semantic_view_name>_semantic_model.yaml \
  --output-file <semantic_view_name>_semantic_model.yaml \
  --operations-json '[
    {"operation": "update", "component": "table", "table_name": "CUSTOMERS", "property": "primary_key", "value": {"columns": ["CUSTOMER_ID"]}},
    {"operation": "update", "component": "table", "table_name": "ORDERS", "property": "primary_key", "value": {"columns": ["ORDER_ID"]}},
    {"operation": "update", "component": "table", "table_name": "PRODUCTS", "property": "primary_key", "value": {"columns": ["PRODUCT_ID"]}},
    {"operation": "create", "component": "relationship", "data": {"name": "ORDERS_TO_CUSTOMERS", "left_table": "ORDERS", "right_table": "CUSTOMERS", "join_type": "inner", "relationship_type": "many_to_one", "relationship_columns": [{"left_column": "CUSTOMER_ID", "right_column": "CUSTOMER_ID"}]}},
    {"operation": "create", "component": "relationship", "data": {"name": "ORDER_DETAILS_TO_ORDERS", "left_table": "ORDER_DETAILS", "right_table": "ORDERS", "join_type": "inner", "relationship_type": "many_to_one", "relationship_columns": [{"left_column": "ORDER_ID", "right_column": "ORDER_ID"}]}},
    {"operation": "create", "component": "relationship", "data": {"name": "CUSTOMER_FEEDBACK_TO_CUSTOMERS", "left_table": "CUSTOMER_FEEDBACK", "right_table": "CUSTOMERS", "join_type": "inner", "relationship_type": "many_to_one", "relationship_columns": [{"left_column": "CUSTOMER_ID", "right_column": "CUSTOMER_ID"}]}}
  ]'
```

**Benefits:** Atomic operation (all succeed or none apply), safe (validates before modifying), sequential execution respects dependencies.

**Reference**: See `reference/semantic_view_set.md` for complete operation syntax.

### Step 5.7: Show Enhancement Summary

Show user a summary:
- Primary keys added: CUSTOMERS.CUSTOMER_ID (100.6% uniqueness), ORDERS.ORDER_ID (100.5% uniqueness), CUSTOMER_FEEDBACK.FEEDBACK_ID (100.87% uniqueness)
- Primary keys skipped: ORDER_DETAILS.ORDER_DETAIL_ID (failed uniqueness test)
- Relationships added: 5 new (e.g., ORDERS → CUSTOMERS, ORDER_DETAILS → ORDERS, CUSTOMER_FEEDBACK → CUSTOMERS)
- Validation: Passed

### Step 5.8: Validate Enhanced Semantic Model

Run validation to confirm all enhancements were applied correctly:

```bash
cd {WORKING_DIR}/creation && \
cortex reflect <semantic_view_name>_semantic_model.yaml --target-schema <DATABASE>.<SCHEMA>
```

Expected: "Semantic model validated successfully"

Confirm success and show updated file location.
