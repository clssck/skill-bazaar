---
name: semantic-view-upload
description: Upload a semantic view YAML file to Snowflake database.schema
parent_skill: semantic-view
---

# Upload Semantic View

## When to Load

User wants to upload/deploy a semantic view YAML file to a Snowflake database.schema.

## Prerequisites

- Semantic view YAML file (local file path)
- Snowflake connection configured
- Target database and schema
- Appropriate privileges (CREATE SEMANTIC VIEW on schema, SELECT on tables/views)

## Process

### Step 1: Identify Semantic View YAML File

If the user hasn't specified which semantic view YAML file to upload, ask them to specify the file path.

**Guideline for determining if context is clear:**
- If user says "upload the semantic view" or "upload it" in the context of a recent optimization session, use the most recent optimized YAML file
- If user provides explicit file path, use that
- Otherwise, ask for clarification

### Step 2: Read the YAML File and Determine Target Location

Read the semantic view YAML file to extract:
1. The semantic view name (from `name:` field)
2. Validation check: Ensure the YAML is well-formed

**Determining database.schema:**
- Check if the optimization session has setup information (from setup/SKILL.md step)
- If setup was run, use the original semantic view's fully qualified name (DATABASE.SCHEMA.SEMANTIC_VIEW) as the target location
- Extract database and schema from that fully qualified name
- This ensures the semantic view is uploaded to the same location as the original semantic view being optimized

### Step 3: Prompt User for Upload Options

Present the user with:

```
📤 Ready to upload semantic view: {SEMANTIC_VIEW_NAME}

Target: {DATABASE}.{SCHEMA}.{SEMANTIC_VIEW_NAME}

Upload options:
1. **Overwrite existing**: CREATE OR REPLACE (recommended if view exists)
2. **Create with new name**: Specify a different name

Which option? [1/2]
```

If user chooses option 2, prompt for:
- New semantic view name (keeps same database.schema from YAML)

### Step 4: Upload Semantic View

Upload the semantic view using the upload script:

```bash
python ../scripts/upload_semantic_view_yaml.py \
  {yaml_file_path} \
  {database}.{schema}
```

The script will output a success message with the semantic view location.

### Step 5: Display Post-Upload Information

Show the user:
```
✅ Upload Complete

Semantic View: {database}.{schema}.{semantic_view_name}

**Semantic view already exists:**
- This is handled by CREATE OR REPLACE if user chose option 1 (overwrite)
- If user chose option 2 (new name), this shouldn't happen
```

## Important Notes

1. **DO NOT** modify the YAML content during upload - upload exactly what's in the file
2. **Quoted identifiers**: If database or schema name contains spaces, the upload handles quoting automatically
3. **Connection**: Use the active Snowflake connection unless user specifies otherwise
4. **Python Script**: The upload script (`upload_semantic_view_yaml.py`) handles all SQL escaping and formatting automatically

## Script Usage

The upload script (`../scripts/upload_semantic_view_yaml.py`) provides:

**Arguments:**
- `yaml_file_path`: Path to the semantic view YAML file
- `target_schema`: Target database.schema (e.g., 'ENG_CORTEX_ANALYST.DEV')
- `--connection`: (Optional) Snowflake connection name (default: snowhouse)

**Examples:**
```bash
# Upload
python ../scripts/upload_semantic_view_yaml.py ./semantic_model.yaml ENG_CORTEX_ANALYST.DEV

# Use different connection
SNOWFLAKE_CONNECTION_NAME=myconn python ../scripts/upload_semantic_view_yaml.py ./semantic_model.yaml DB.SCHEMA
```
