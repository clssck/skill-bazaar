---
name: evaluate-cortex-analyst
description: Run formal evaluations on Cortex Analyst semantic views using Snowflake's native Analyst Evaluations. Use this to measure SQL generation accuracy against a semantic view's own verified queries (the `sql_correctness` metric), track regressions, and validate before/after improvements.
---

# Evaluate Cortex Analyst

Evaluate a Cortex Analyst semantic view using Snowflake's native Analyst Evaluations feature.

Evaluations test a semantic view against its **own verified queries** as ground truth: Cortex Analyst generates SQL for each verified query's question, executes it, and compares the results against the verified SQL. This produces an accuracy score and surfaces regressions (queries that were previously answered correctly but now fail).

**Available Metric:**
| Metric | API Name | Ground Truth Source | Description |
|--------|----------|---------------------|-------------|
| SQL Correctness | `sql_correctness` | Verified queries on the semantic view | Executes the generated SQL and compares its result set against the verified query's result set. This is the **only** supported metric for Cortex Analyst evaluations. |

> **No dataset, no metric selection.** Unlike Cortex Agent evaluations, Analyst evaluations do not use a separate dataset table or registered dataset, and there is exactly one metric. The evaluation set comes entirely from verified queries (VQs) already attached to the semantic view.

> **How verified queries are used.** When you select VQs for an evaluation run, Cortex Analyst creates a temporary copy of the semantic view with the selected queries removed, then generates SQL using that copy. This prevents the evaluation queries from influencing SQL generation, so the score reflects genuine generation ability. VQs you do *not* select remain in the temporary view and continue to guide generation. A VQ can either guide generation at runtime or be used as ground truth in a run, but not both at once.

## Prerequisites

- Active Snowflake connection
- The semantic view must already exist and have at least one verified query
- A role with appropriate permissions (see Troubleshooting if you hit permission errors)

Whenever running scripts, make sure to use `uv`.

**IMPORTANT: Do NOT use `cortex ctx task` or `cortex ctx step` commands during this workflow. The skill's own step-by-step structure with mandatory stopping points provides sufficient tracking.**

## Tools

### Script: evaluate_cortex_analyst.py

**Description**: Creates stages, uploads YAML evaluation configs via PUT, and executes/checks evaluation runs through `EXECUTE_AI_EVALUATION`. Required because PUT is a client-side command that cannot run in Snowsight worksheets.

**Usage:**
```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/evaluate_cortex_analyst.py \
    <subcommand> [args]
```

**Subcommands:**
| Subcommand | Description | Key Args |
|------------|-------------|----------|
| `upload` | Create stage + upload YAML config | `--yaml-file`, `--stage` |
| `start` | Start an evaluation run | `--run-name`, `--stage`, `--config-filename` |
| `status` | Check evaluation run status | `--run-name`, `--stage`, `--config-filename`, `--wait` |

**Common args** (all subcommands): `--connection`, `--database`, `--schema`

**Status-specific args:** `--wait` (poll until done), `--poll-interval` (default 30s), `--timeout` (default 600s)

**Example:**
```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/evaluate_cortex_analyst.py \
    upload \
    --yaml-file <DATABASE>_<SCHEMA>_<SEMANTIC_VIEW_NAME>/<SEMANTIC_VIEW_NAME>_eval_config.yaml \
    --stage MYDB.MYSCHEMA.METRICS \
    --database MYDB --schema MYSCHEMA --connection my_conn
```

## Workflow

**IMPORTANT: Go through each step ONE AT A TIME. Wait for user confirmation before proceeding.**

Do not assume the user is familiar with the evaluation process. Present the plan overview **VERBATIM** first:
```
I'll help you evaluate your Cortex Analyst semantic view. Here's the workflow:

1. **Identify Semantic View** — We'll clarify which semantic view you want to evaluate. You'll need to provide its database, schema, and name so we can be sure we're examining the correct one.
2. **Review Verified Queries** — Evaluations use the semantic view's own verified queries as ground truth. We'll list the available verified queries and decide whether to evaluate all of them or a specific subset.
3. **Run Evaluation** — We'll generate an evaluation configuration (in YAML format), upload it so Snowflake can access it, and kick off the evaluation run. This runs Cortex Analyst against each verified query's question and scores the generated SQL with the `sql_correctness` metric.
4. **View Results** — Once the evaluation completes, you'll be able to see accuracy, regressions, and per-query results in Snowsight. You can also fetch results programmatically if you wish for further analysis.
```

---

### Step 1: Identify Semantic View and Gather Info

**Ask user without using the AskUserQuestion tool**
```
Which semantic view would you like to evaluate?
- Database: [e.g., MY_DATABASE]
- Schema: [e.g., ANALYTICS]
- Semantic View Name: [e.g., SALES_SEMANTIC_VIEW]
- Connection: [default: snowhouse]
```

If the user only provides the view name, help them find it:
```sql
SHOW SEMANTIC VIEWS LIKE '%<SEMANTIC_VIEW_NAME>%' IN ACCOUNT;
```

**Construct Fully Qualified Semantic View Name:** `<DATABASE>.<SCHEMA>.<SEMANTIC_VIEW_NAME>`

**STOP**: Confirm the semantic view details before proceeding to Step 2.

---

### Step 2: Review Verified Queries

**Explain to the user:**
Cortex Analyst evaluations use the semantic view's verified queries (VQs) as the evaluation set — each VQ pairs a natural-language question with its expected SQL answer. You need at least one VQ before you can run an evaluation.

**List the verified queries attached to the semantic view:**
```sql
DESC SEMANTIC VIEW <DATABASE>.<SCHEMA>.<SEMANTIC_VIEW_NAME>;
```

In the output, verified queries are the rows where `object_kind = 'AI_VERIFIED_QUERY'`. The question text is in the rows where `property = 'QUESTION'`. To pull just the questions:
```sql
SELECT "property_value" AS question
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'AI_VERIFIED_QUERY'
  AND "property" = 'QUESTION';
```

- **If no verified queries are returned**, stop the evaluation workflow. Explain that the semantic view needs at least one verified query first. Verified queries are added through the semantic view editor in Snowsight (AI & ML » Cortex Analyst), or via the `AI_VERIFIED_QUERIES` clause of `CREATE OR ALTER SEMANTIC VIEW`. Do not continue until at least one VQ exists.

- **If one or more verified queries are returned**, present the questions to the user and ask:
  > I found these verified queries on `<DATABASE>.<SCHEMA>.<SEMANTIC_VIEW_NAME>`:
  > - `<question_1>`
  > - `<question_2>`
  > - ...
  >
  > Would you like to evaluate **all** of them, or a **specific subset**? (Selecting all is the default.)

Record the user's choice:
- **All VQs** → omit the `verified_queries` list in the YAML (Step 3); all VQs are used automatically.
- **Subset** → record the exact question text of each selected VQ; these go into the `verified_queries` list in the YAML.

**⚠️ MANDATORY STOPPING POINT**: Confirm the verified-query selection before proceeding to Step 3.

---

### Step 3: Build YAML Config, Upload to Stage, and Run Evaluation

#### Step 3.1: Generate YAML Config

Based on Steps 1 and 2, generate a YAML config file.

```yaml
# --- REQUIRED ---
evaluation:
  analyst_params:
    analyst_name: "<DATABASE>.<SCHEMA>.<SEMANTIC_VIEW_NAME>"   # MUST be fully qualified (DB.SCHEMA.VIEW)
    analyst_type: "SEMANTIC VIEW"
  source_metadata:
    type: "verified_queries"
    # OPTIONAL: list specific verified queries by their question text.
    # Omit this list entirely to evaluate ALL verified queries on the view.
    verified_queries:
      - "<QUESTION_1>"
      - "<QUESTION_2>"

# --- REQUIRED: sql_correctness is the only supported metric ---
metrics:
  - "sql_correctness"
```

Field reference:
- `analyst_params.analyst_name`: the **fully qualified** name of the semantic view to run the evaluation against, in `DATABASE.SCHEMA.SEMANTIC_VIEW_NAME` form. `EXECUTE_AI_EVALUATION` fails if this is not fully qualified.
- `analyst_params.analyst_type`: the string constant `SEMANTIC VIEW`.
- `source_metadata.type`: for Cortex Analyst, the only supported source type is `verified_queries`.
- `source_metadata.verified_queries` (optional): a list of question texts matching the `QUESTION` of each verified query to use as ground truth. **Omit** to use all verified queries.
- `metrics`: must be exactly `sql_correctness` — the only supported metric.

**Save the YAML config to a workspace directory:**

Create the workspace directory `<DATABASE>_<SCHEMA>_<SEMANTIC_VIEW_NAME>/` (FQN with underscores) if it doesn't exist. This keeps files organized when evaluating multiple semantic views. Use the **Write** tool to save the YAML config to `<DATABASE>_<SCHEMA>_<SEMANTIC_VIEW_NAME>/<SEMANTIC_VIEW_NAME>_eval_config.yaml`.

#### Step 3.2: Upload YAML to Stage

```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/evaluate_cortex_analyst.py \
    upload \
    --yaml-file <DATABASE>_<SCHEMA>_<SEMANTIC_VIEW_NAME>/<SEMANTIC_VIEW_NAME>_eval_config.yaml \
    --stage <DATABASE>.<SCHEMA>.METRICS \
    --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>
```

The script creates the file format, stage, uploads via PUT, and verifies the upload automatically.

#### Step 3.3: Start Evaluation

```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/evaluate_cortex_analyst.py \
    start \
    --run-name <SEMANTIC_VIEW_NAME>_eval_<YYYYMMDD_HHMMSS> \
    --stage <DATABASE>.<SCHEMA>.METRICS \
    --config-filename <SEMANTIC_VIEW_NAME>_eval_config.yaml \
    --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>
```

The run name should be unique for the semantic view being evaluated.

#### Step 3.4: Check Evaluation Status

First do a **single** status check (returns immediately with the current state):
```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/evaluate_cortex_analyst.py \
    status \
    --run-name <SEMANTIC_VIEW_NAME>_eval_<YYYYMMDD_HHMMSS> \
    --stage <DATABASE>.<SCHEMA>.METRICS \
    --config-filename <SEMANTIC_VIEW_NAME>_eval_config.yaml \
    --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>
```

If it is not yet terminal, re-run with `--wait` to auto-poll until the evaluation completes:
```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/evaluate_cortex_analyst.py \
    status --wait \
    --run-name <SEMANTIC_VIEW_NAME>_eval_<YYYYMMDD_HHMMSS> \
    --stage <DATABASE>.<SCHEMA>.METRICS \
    --config-filename <SEMANTIC_VIEW_NAME>_eval_config.yaml \
    --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>
```

Always run the single (non-`--wait`) check first so you confirm the run is progressing before committing to a long poll. The `--wait` poll runs every 30 seconds (configurable via `--poll-interval`) up to 10 minutes (`--timeout`).

**Status values:**
| Status | Meaning |
|--------|---------|
| `INVOCATION_IN_PROGRESS` | Cortex Analyst is generating/executing SQL for the evaluation inputs |
| `COMPUTATION_IN_PROGRESS` | The `sql_correctness` metric is being computed |
| `COMPLETED` | Evaluation finished successfully |
| `FAILED` | Evaluation failed — check `STATUS_DETAILS` |

If `FAILED`, check `STATUS_DETAILS` and consult **Troubleshooting** below.

---

### Step 4: View Results

**Generate Snowsight link:**
```sql
SELECT LOWER(CURRENT_ORGANIZATION_NAME()), LOWER(CURRENT_ACCOUNT_NAME());
```

You can also reach results in Snowsight via **AI & ML » Cortex Analyst** → select the semantic view → **Evaluations** tab → select the run.

Present the link to the user.

**Query results programmatically:**

Use `GET_ANALYST_AI_EVALUATION_DATA` (note: `object_type` is `'SEMANTIC VIEW'`):
```sql
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<SEMANTIC_VIEW_NAME>', 'SEMANTIC VIEW', '<RUN_NAME>'
))
ORDER BY TIMESTAMP DESC;
```

**Compute an accuracy summary:**
```sql
SELECT
    METRIC_NAME,
    AVG(EVAL_AGG_SCORE)              AS mean_score,
    COUNT(*)                         AS rows_scored,
    COUNT_IF(ERROR IS NOT NULL)      AS rows_with_errors
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<SEMANTIC_VIEW_NAME>', 'SEMANTIC VIEW', '<RUN_NAME>'
))
GROUP BY METRIC_NAME
ORDER BY METRIC_NAME;
```

**Inspect per-query correctness criteria (e.g., for incorrect rows):**
```sql
SELECT
    RECORD_ID,
    INPUT                                AS question,
    OUTPUT                               AS generated_sql,
    GROUND_TRUTH                         AS verified_sql,
    EVAL_AGG_SCORE,
    e.VALUE:criteria::VARCHAR            AS criteria,
    e.VALUE:explanation::VARCHAR         AS explanation
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<SEMANTIC_VIEW_NAME>', 'SEMANTIC VIEW', '<RUN_NAME>'
)),
LATERAL FLATTEN(input => METRIC_CALLS) e
ORDER BY EVAL_AGG_SCORE ASC;
```

**Present results as:**
1. Overall accuracy (mean `sql_correctness` score, percentage of verified queries answered correctly).
2. Regressions — verified queries that were previously correct but now fail (visible in the Snowsight Evaluations tab).
3. Per-query breakdown for any incorrect rows: question, expected SQL, generated SQL, and the explanation.

**⚠️ MANDATORY STOPPING POINT**: Review results with the user. Discuss findings and next steps (e.g., refining the semantic view, then re-running to measure impact and check for regressions).

---

## Troubleshooting

### Permission Errors

Analyst evaluation runs are executed using Snowflake tasks and touch several objects (the semantic view, its referenced tables, the current schema, the stage). A single missing grant can surface as a confusing error. On **any** permission-related failure, run **all** of the checks below at once to surface every missing grant in a single pass. The `-- Look for:` comment documents the grant required at that scope.

> All required privileges must be granted under a **single primary role** — evaluation runs execute via tasks, which do not consider secondary-role privileges.

```sql
-- 1. Current role and warehouse
SELECT CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS warehouse;

-- 2. Account-level and database-role grants
SHOW GRANTS TO ROLE <role>;
-- Look for: DATABASE ROLE SNOWFLAKE.CORTEX_USER, EXECUTE TASK ON ACCOUNT

-- 3. Database grants
SHOW GRANTS ON DATABASE <database>;
-- Look for: USAGE

-- 4. Schema grants (schema containing the semantic view)
SHOW GRANTS ON SCHEMA <database>.<schema>;
-- Look for: USAGE, CREATE TASK, CREATE DATASET

-- 5. Semantic view grants
SHOW GRANTS ON SEMANTIC VIEW <database>.<schema>.<semantic_view_name>;
-- Look for: SELECT, MONITOR

-- 6. Stage grants (if stage already exists)
SHOW GRANTS ON STAGE <database>.<schema>.<stage_name>;
-- Look for: READ

-- 7. Warehouse grants (Snowsight requires USAGE on the default warehouse)
SHOW GRANTS ON WAREHOUSE <warehouse>;
-- Look for: USAGE
```

Also confirm the role has `SELECT` on every base table referenced by the semantic view — missing table grants surface as SQL-execution failures during the run, not as eval-engine errors.

Compare results against the expected grants below. Present **all** missing grants to the user at once:

```sql
-- Example output — include only the grants that are actually missing:
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <role>;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <role>;
GRANT USAGE ON DATABASE <database> TO ROLE <role>;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT CREATE TASK ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT CREATE DATASET ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT SELECT ON SEMANTIC VIEW <database>.<schema>.<semantic_view_name> TO ROLE <role>;
GRANT MONITOR ON SEMANTIC VIEW <database>.<schema>.<semantic_view_name> TO ROLE <role>;
GRANT READ ON STAGE <database>.<schema>.<stage_name> TO ROLE <role>;
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE <role>;
```

Ask the user to run all missing grants (or have an admin run them), then retry the failed step.

### No Verified Queries Found

Evaluations require at least one verified query on the semantic view. Add VQs through the semantic view editor in Snowsight (AI & ML » Cortex Analyst » Verified Queries), or via the `AI_VERIFIED_QUERIES` clause of `CREATE OR ALTER SEMANTIC VIEW`. Re-run `DESC SEMANTIC VIEW` to confirm they exist before retrying.

### YAML Config Not Parsed

1. Ensure the file format uses `FIELD_DELIMITER = NONE` (not comma).
2. Verify upload: `SELECT $1 FROM @<stage>/<file>.yaml;`
3. Check YAML indentation — spaces, not tabs.
4. `analyst_type` must be the string constant `SEMANTIC VIEW`.
5. `metrics` must contain exactly `sql_correctness` — no other metric is supported for Analyst evaluations.

### Script Execution Fails

1. Ensure the local YAML file exists at the path passed to `--yaml-file`.
2. The script uses PUT via the Snowflake Python connector — cannot run in Snowsight.
3. Check that your role has `CREATE STAGE` and `CREATE FILE FORMAT` permissions.
4. Verify `uv` is installed: `uv --version`.

### Evaluation STATUS Shows FAILED

1. Check `STATUS_DETAILS` for specific errors.
2. Common causes: the role lacks `SELECT` on a table referenced by the semantic view, the verified-query SQL no longer runs, or `EXECUTE TASK ON ACCOUNT` is missing.

### Ground Truth Staleness

If verified queries reference time-relative concepts (e.g., `last quarter` rather than `Q1 2025`), evaluation results may drift over time because the verified SQL and generated SQL return different rows on different days. Scope verified queries to specific, absolute dates and time ranges for consistent results.

### "No current database" Error

Run `USE DATABASE <DATABASE>; USE SCHEMA <SCHEMA>;` then re-run the failing command.

---

This skill measures SQL generation accuracy for a semantic view and is the recommended way to establish a baseline, improve the semantic view, and re-run to validate improvements while watching for regressions.
