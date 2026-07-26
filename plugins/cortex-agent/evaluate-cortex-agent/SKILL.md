---
name: evaluate-cortex-agent
description: Run formal evaluations on Cortex Agents using Snowflake's native Agent Evaluations. Use this to benchmark agent performance, measure accuracy metrics (answer_correctness, logical_consistency, custom LLM-judged metrics), and compare before/after improvements.
---

# Evaluate Cortex Agent

Evaluate Cortex Agents using Snowflake's native Agent Evaluations feature.

**Available Metrics:**
| Metric | API Name | Requires Ground Truth | Description |
|--------|----------|----------------------|-------------|
| Answer Correctness | `answer_correctness` | Yes (`ground_truth_output`) | Semantic match of final answer |
| Logical Consistency | `logical_consistency` | No | Consistency across instructions, planning, and tool calls within a single execution (reference-free) |
| Tool Selection Accuracy (TSA) | `tool_selection_accuracy` | Yes (`ground_truth_invocations`) | Scores whether the agent invoked the expected `tool_name`s. Empty array `[]` asserts no tool should run (guardrail). |
| Tool Execution Accuracy (TEA) | `tool_execution_accuracy` | Yes (`ground_truth_invocations` with per-invocation `tool_input` / `tool_output` constraints) | Scores the agent's tool inputs / outputs against the per-invocation constraints. |
| Custom | user-defined | Optional | LLM-judged metric with user-defined prompt and score range |

> **Per-row track ↔ metric matrix.** Datasets created by `dataset-curation` carry a `track` column (`'ac'` | `'tea'`) that labels which metrics apply per row. **AC-track rows** score under `answer_correctness` + `logical_consistency` only. **TEA-track rows** score under all four metrics — `answer_correctness` + `logical_consistency` + `tool_selection_accuracy` (TSA) + `tool_execution_accuracy` (TEA) — the extra two are unlocked by the row carrying `ground_truth_invocations`.

## Prerequisites

- Active Snowflake connection
- Agent must already exist
- A role with appropriate permissions (see Troubleshooting if you hit permission errors)

Whenever running scripts, make sure to use `uv`.

**IMPORTANT: Do NOT use `cortex ctx task` or `cortex ctx step` commands during this workflow. The skill's own step-by-step structure with mandatory stopping points provides sufficient tracking.**

## Invocation Modes

This skill runs in two modes. The mode is determined by whether a parent skill passed pre-filled values when loading it.

| Mode | Triggered by | Behavior |
|------|--------------|----------|
| **Standalone** (default) | User loads this skill directly. No pre-filled context. | Run Steps 1 → 5 interactively, ASKing the user at every gate (agent, metrics, dataset). |
| **Called from a parent skill** | A parent skill (e.g. `dataset-curation`) loads this skill and supplies pre-filled values. | Skip the ASKs whose inputs are pre-filled; reuse the supplied values. |

**Parent-pre-fill contract** — accepted optional inputs from a parent skill:

| Input | Effect |
|-------|--------|
| `<AGENT_FQN>` | Step 1's `SHOW AGENTS` lookup is skipped — confirm the agent in one line. |
| `<DATASET_NAME>` | Step 3's dataset prompt is skipped — the YAML references this already-registered dataset directly. |
| `<METRIC_SCOPE>` ∈ {`ac`, `tea`, `both`} | Step 2's metric ASK is skipped; metric list resolves deterministically: `ac` → [`answer_correctness`, `logical_consistency`]; `tea` → adds `tool_selection_accuracy` + `tool_execution_accuracy`; `both` → all four. |
| `<RUN_NAME>` | Used verbatim by Step 4; otherwise auto-generated as `<AGENT_NAME>_eval_<YYYYMMDD_HHMMSS>`. |

When invoked from a parent, return control after Step 5 with `<RUN_NAME>`, the Snowsight URL, and the per-metric mean-score map, then stop without further prompting.

## Tools

### Script: evaluate_cortex_agent.py

**Description**: Creates stages, uploads YAML evaluation configs via PUT, and executes/checks evaluation runs through `EXECUTE_AI_EVALUATION`. Required because PUT is a client-side command that cannot run in Snowsight worksheets.

**Usage:**
```bash
uv run python ../scripts/evaluate_cortex_agent.py \
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
uv run python ../scripts/evaluate_cortex_agent.py \
    upload \
    --yaml-file /tmp/my_eval_config.yaml \
    --stage MYDB.MYSCHEMA.EVAL_CONFIG_STAGE \
    --database MYDB --schema MYSCHEMA --connection my_conn
```

## Workflow

**IMPORTANT: Go through each step ONE AT A TIME. Wait for user confirmation before proceeding.**

Do not assume the user is familiar with the evaluation process. Present the plan overview **VERBATIM** first:
```
I'll help you evaluate your Cortex Agent. Here's the workflow:

1. **Identify Agent** — We'll clarify which agent you want to evaluate. You'll need to provide its database, schema, and name so we can be sure we're examining the correct one.
2. **Choose Metrics** — Decide which qualities to measure (answer_correctness, logical_consistency, or custom).
3. **Dataset Setup** — Provide an evaluation dataset (registered dataset or table with sample questions).
4. **Run Evaluation** — We'll generate an evaluation configuration (in YAML format), upload it so Snowflake can access it, and kick off the evaluation run. This process runs your agent against each question in your dataset and scores its responses according to the metrics you selected.
5. **View Results** — Once the evaluation completes, you’ll be able to see summary scores and detailed breakdowns in Snowsight. You can also fetch results programmatically if you wish for further analysis.
```


---

### Step 1: Identify Agent and Gather Info

**Ask user without using the AskUserQuestion tool**
```
Which agent would you like to evaluate?
- Database: [e.g., MY_DATABASE]
- Schema: [e.g., AGENTS]
- Agent Name: [e.g., MY_SALES_AGENT]
- Connection: [default: snowhouse]
```

If the user only provides the agent name, help them find it:
```sql
SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
```

**Construct Fully Qualified Agent Name:** `<DATABASE>.<SCHEMA>.<AGENT_NAME>`

**Extract agent configuration:**
```sql
DESC AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
```

The `agent_spec` column (index 6) contains a JSON object with the full agent configuration. **If `agent_spec` is empty or null**, the agent has no tools or model configured

**STOP**: Confirm agent details before proceeding to Step 2.
Present the agent name and tools found to the user.

---

### Step 2: Choose Evaluation Metrics

**Ask user:**
```
Which metrics do you want to evaluate?

1. [ ] answer_correctness - Does the agent give correct answers?
       Requires: expected answer for each question (`ground_truth_output`)

2. [ ] logical_consistency - Is the response internally consistent? (reference-free)
       Requires: nothing (no ground truth needed)

3. [ ] tool_selection_accuracy (TSA) - Did the agent invoke the expected tools?
       Requires: `ground_truth_invocations` on TEA-track rows
       (use `[]` for guardrail / refusal questions where no tool should run)

4. [ ] tool_execution_accuracy (TEA) - Did the agent's tool inputs/outputs match?
       Requires: `ground_truth_invocations` with per-invocation `tool_input` + `tool_output` populated

5. [ ] Custom metric — Define your own LLM-judged metric with a prompt and score range

Select metrics (e.g., "1,2,3,4" or "all" or "just 5"):
```

If the user selects a custom metric, gather all of the following. Do not assume values:
- **Name**: identifier used as the results column (e.g., `relevance`, `safety`)
- **Score ranges**: three `[low, high]` pairs for `min_score`, `median_score`, `max_score` (e.g., `[1,3]`, `[4,6]`, `[7,10]`). `min_score` is inclusive-lower to exclusive-upper; `median_score` is inclusive-inclusive; `max_score` is exclusive-lower to inclusive-upper.
- **Prompt**: the LLM judge prompt — must include a scoring mechanism that produces a numeric value within the ranges above. Encourage using replacement strings that substitute columns from `GET_AI_RECORD_TRACE`:

  | Placeholder | Source column |
  |-------------|---------------|
  | `{{input}}` | `INPUT` |
  | `{{output}}` | `OUTPUT` |
  | `{{ground_truth}}` | `GROUND_TRUTH` (serialized JSON from your dataset) |
  | `{{tool_info}}` | `TOOL` |
  | `{{start_timestamp}}` | `START_TIMESTAMP` |
  | `{{duration}}` | `DURATION_MS` |
  | `{{span_id}}` | `SPAN_ID` |
  | `{{span_type}}` | `SPAN_TYPE` |
  | `{{span_name}}` | `SPAN_NAME` |
  | `{{llm_model}}` | `LLM_MODEL` |
  | `{{error}}` | `ERROR` |
  | `{{status}}` | `STATUS` |

#### Defining a custom metric (Snowflake spec)

When creating a custom metric, enforce the required YAML shape and prompt behavior from Snowflake docs:

```yaml
- name: "<METRIC_NAME>"
  score_ranges:
    min_score: [1, 3]
    median_score: [4, 6]
    max_score: [7, 10]
  prompt: |
    <JUDGE_PROMPT>
```

Validation checklist before moving on:
- `name` is present and stable (prefer lowercase + underscores so result columns are predictable).
- `score_ranges` includes all three keys: `min_score`, `median_score`, `max_score`.
- Each score range is exactly two numeric bounds.
- Bounds satisfy Snowflake semantics:
  - `min_score`: inclusive lower, exclusive upper
  - `median_score`: inclusive lower, inclusive upper
  - `max_score`: exclusive lower, inclusive upper
- Prompt includes an explicit scoring instruction that returns a numeric value in the configured range.

Prompt authoring guidance:
- Keep each custom metric focused on one quality dimension (for example: relevance, safety, completeness).
- Use placeholders (`{{input}}`, `{{output}}`, and optionally `{{ground_truth}}`) to ground the judge.
- Require deterministic scoring output, for example:
  - "Return a single numeric score from 1-10."
  - "Assign exactly one score within the ranges above."

**Based on selection, determine dataset requirements:**

| If user selects... | Dataset needs... |
|-------------------|------------------|
| Only `logical_consistency` | Just a query column (no ground truth needed) |
| `answer_correctness` | `ground_truth_output` in ground truth column (AC-track rows) |
| `tool_selection_accuracy` (TSA) | `ground_truth_invocations` in ground truth column (TEA-track rows). Use `[]` for guardrail / refusal rows where no tool should run. |
| `tool_execution_accuracy` (TEA) | `ground_truth_invocations` with per-invocation `tool_input` + `tool_output` populated. See `../dataset-curation/refs/tea_details.md` for the two-part `tool_output` format. |
| Custom metric only | Depends on prompt — ground truth needed if `{{ground_truth}}` is referenced |


---

### Step 3: Dataset Setup

**Explain to the user:**
Evaluating an agent requires a dataset: a list of sample questions. A dataset may also include additional information. For example, in order to check answer_correctness, the dataset must contain the expected answer for each question. We'll make sure you have a dataset ready and formatted correctly.

> **Parent-mode constraint.** When this skill is **called from a parent skill** (e.g. `dataset-curation`), the parent supplies a single value: `<DATASET_NAME>` — an **already-registered Cortex Agent dataset**. In that mode the parent will not pass a `<SOURCE_TABLE>`; skip every "table-setup" branch below and jump straight to Step 4 with the supplied dataset. The standalone path retains the table-setup branches for users who don't have a registered dataset yet.

**First, surface existing datasets in the agent's schema before asking the user to name one.**
Run:
```sql
SHOW DATASETS IN SCHEMA <agent_db>.<agent_schema>;
```

Filter the result to rows where `dataset_type = 'CORTEX AGENT'` (ignore other dataset types — they can't be used here).

- **If one or more Cortex Agent datasets are returned**, present them to the user:
  > I found these registered Cortex Agent datasets in `<agent_db>.<agent_schema>`:
  > - `<dataset_1>`
  > - `<dataset_2>`
  > - ...
  >
  > Would you like to use one of these, provide a different registered dataset, or set up a new one from a source table?

- **If no Cortex Agent datasets are returned**, ask:
  > No registered Cortex Agent datasets found in `<agent_db>.<agent_schema>`. Do you have an existing table to use as the source, or would you like help creating one? (Provide the fully qualified table name, e.g., `DB.SCHEMA.MY_TABLE`.)

If the user does **not** already have either (a) a registered Cortex Agent dataset or (b) an existing source table they can provide now, **stop this skill** and route them to the dataset-curation (router) skill.

Do not continue to Step 4 until the user has a real dataset source (registered dataset or existing table).

**If the user picks an existing dataset:**

Record the dataset name — it will be referenced in the YAML config's `evaluation.source_metadata.dataset_name`. Because it came from `SHOW DATASETS`, it is already confirmed to exist, so the YAML **must omit** the top-level `dataset:` block. Skip to Step 4.

**If the user provides a different registered dataset name (outside the listed schema):**

Verify it exists with an exact-name lookup:
```sql
DESCRIBE DATASET <db>.<schema>.<dataset_name>;
```
If the command succeeds, record the name and skip to Step 4 (omit the `dataset:` block in the YAML). If it errors with "Dataset ... does not exist," fall through to the table-setup path below.

**If user provides a table name:**

Ask user for column names:
```
What are the column names in your table?
- Column containing the input queries (VARCHAR): [e.g., user_question]
- Column containing the ground truth (VARIANT): [e.g., expected_output]
```

Column names can be anything — the YAML config's `column_mapping` handles the mapping. The requirements are:
- The query column must be `VARCHAR`
- The ground truth column must be `VARIANT` containing JSON with the keys below. Build values with `PARSE_JSON(...)` or `TO_VARIANT(...)` — `OBJECT_CONSTRUCT(...)` returns a non-VARIANT value.

Record the table name and column names — they will be used in the YAML config's `dataset.column_mapping`:
```yaml
column_mapping:
  query_text: "<USER_QUERY_COLUMN>"
  ground_truth: "<USER_GROUND_TRUTH_COLUMN>"
```

**Ground truth JSON keys:**
| Key | Description | Used by |
|-----|-------------|---------|
| `ground_truth_output` | Expected final answer (semantic match). Populated for AC-track rows. | `answer_correctness` |
| `ground_truth_invocations` | Ordered array of expected `{tool_name, tool_input, tool_output}` entries. Empty array `[]` asserts no tool should run (guardrail). **Omit entirely** for AC-only rows. Populated for TEA-track rows. | `tool_selection_accuracy` (TSA), `tool_execution_accuracy` (TEA) |
| `track` (column, not JSON key) | `'ac'` or `'tea'` — labels which set of metrics applies per row. Datasets created by `dataset-curation` always include this column. | per-track metric projection |

See `../dataset-curation/refs/ground_truth_schema.md` for the full populated / `[]` / absent trichotomy and the canonical `GROUND_TRUTH` VARIANT shape.

**If user's table doesn't have a VARIANT ground truth column**, help them create one (use `PARSE_JSON`, not `OBJECT_CONSTRUCT`). The table also needs a `track` column (`'ac'` | `'tea'`) if you plan to score TSA / TEA alongside AC:
```sql
CREATE OR REPLACE TABLE <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL_DATASET (
    input_query VARCHAR,
    ground_truth VARIANT,
    track VARCHAR        -- 'ac' or 'tea'
);

-- AC-track row
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL_DATASET (input_query, ground_truth, track)
SELECT
    '<QUESTION_1>',
    PARSE_JSON('{"ground_truth_output": "<EXPECTED_ANSWER>"}'),
    'ac';

-- TEA-track row (full ground truth including ground_truth_invocations)
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL_DATASET (input_query, ground_truth, track)
SELECT
    '<QUESTION_2>',
    PARSE_JSON('{"ground_truth_invocations": [{"tool_name": "<TOOL>", "tool_input": "<NL_INTENT>", "tool_output": "SQL:\n<RUNNABLE_SQL>;\n\nExpected Result:\n<LITERAL_ROWS>"}]}'),
    'tea';
```

**⚠️ MANDATORY STOPPING POINT**: Confirm dataset details before proceeding to Step 4.

---

### Step 4: Build YAML Config, Upload to Stage, and Run Evaluation

#### Step 4.1: Generate YAML Config

Based on the user's choices in Steps 2 and 3, generate a YAML config file.

> **Important — repeated runs and the `dataset:` block.** When calling `EXECUTE_AI_EVALUATION` with `START` and the YAML still contains a top-level `dataset:` block, Snowflake attempts to create that dataset on every run. If the `dataset_name` already exists (for example, because a previous attempt created it, or because the user registered it with `SYSTEM$CREATE_EVALUATION_DATASET`), the run can fail even if `run_name` changes.
>
> **Decide by checking the catalog, not by memory.** Before generating the YAML, run an exact-name lookup on the target dataset:
> ```sql
> DESCRIBE DATASET <db>.<schema>.<dataset_name>;
> ```
> - If the command **succeeds** → the dataset is already registered. **Omit the `dataset:` block entirely.** Keep only `evaluation:` (with `source_metadata.dataset_name` pointing to the existing dataset) and `metrics:`.
> - If the command **errors** with "Dataset ... does not exist" → include `dataset:` with that `dataset_name` so this run registers it.
>
> Re-run this check every time you regenerate the YAML — never rely on remembering the state from a previous turn or session.
>
> **Parent-mode rule:** when this skill was called from a parent and `<DATASET_NAME>` was supplied, the dataset is guaranteed already-registered — **always omit the `dataset:` block** in that mode and proceed with `evaluation:` + `metrics:` only.

```yaml
# --- OPTIONAL: Include ONLY when creating a new dataset from a source table ---
# Remove this entire block for repeated runs against an existing registered dataset.
# In parent-mode (called from dataset-curation), the parent supplies an
# already-registered <DATASET_NAME>, so this block is always omitted.
dataset:
  dataset_type: "CORTEX AGENT"
  table_name: "<DATABASE>.<SCHEMA>.<TABLE_NAME>"
  dataset_name: "<AGENT_NAME>_eval_ds_<YYYYMMDD_HHMMSS>"
  column_mapping:                      # Map columns to match the actual column names in the user's table
    query_text: "INPUT_QUERY"
    ground_truth: "GROUND_TRUTH"

# --- REQUIRED ---
evaluation:
  agent_params:
    agent_name: "<DATABASE>.<SCHEMA>.<AGENT_NAME>"
    agent_type: "CORTEX AGENT"
  run_params:
    label: "evaluation"
    description: "<DESCRIPTION>"
  source_metadata:
    type: "dataset"
    dataset_name: "<EXISTING_DATASET_NAME>"  # If dataset block above is included, use its dataset_name instead

# --- REQUIRED: Include only the metrics the user selected in Step 2 ---
metrics:
  - "answer_correctness"               # Built-in metric (string) — AC-track + TEA-track rows
  - "logical_consistency"              # Built-in metric (string) — every row (reference-free)
  - "tool_selection_accuracy"          # Built-in metric (string) — TEA-track rows only (TSA)
  - "tool_execution_accuracy"          # Built-in metric (string) — TEA-track rows only (TEA)
  - name: "<METRIC_NAME>"             # OPTIONAL: Custom metric (object) — add one per custom metric
    score_ranges:
      min_score: [1, 3]               # inclusive-lower, exclusive-upper (low quality)
      median_score: [4, 6]            # inclusive-lower, inclusive-upper (medium quality)
      max_score: [7, 10]              # exclusive-lower, inclusive-upper (high quality)
    prompt: |
      <PROMPT_TEXT>
      Rate from 1-10 based on ...
      Compare the {{output}} with the {{ground_truth}}.
```

Omit the `dataset` block entirely if the user already has a registered dataset (and **always** in parent-mode). Omit any built-in metrics the user did not select, and omit custom metric objects if none were chosen. `tool_selection_accuracy` (TSA) and `tool_execution_accuracy` (TEA) only score rows whose `ground_truth_invocations` field is populated — AC-track rows (field-absent) are silently excluded from those metrics' aggregate.

**Only include metrics the user selected in Step 2.** Adjust `column_mapping` keys to match the actual column names in the user's table.

**Save the YAML config to a workspace directory:**

Create the workspace directory `<DATABASE>_<SCHEMA>_<AGENT_NAME>/` (FQN with underscores) if it doesn't exist. This convention matches `init_agent_workspace.py` and keeps files organized when evaluating multiple agents. Use the **Write** tool to save the YAML config to `<DATABASE>_<SCHEMA>_<AGENT_NAME>/<AGENT_NAME>_eval_config.yaml`.

#### Step 4.2: Upload YAML to Stage

```bash
uv run python ../scripts/evaluate_cortex_agent.py \
    upload \
    --yaml-file <DATABASE>_<SCHEMA>_<AGENT_NAME>/<AGENT_NAME>_eval_config.yaml \
    --stage <DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE \
    --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>
```

The script creates the file format, stage, uploads via PUT, and verifies the upload automatically.

#### Step 4.3: Start Evaluation

```bash
uv run python ../scripts/evaluate_cortex_agent.py \
    start \
    --run-name <AGENT_NAME>_eval_<YYYYMMDD_HHMMSS> \
    --stage <DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE \
    --config-filename <AGENT_NAME>_eval_config.yaml \
    --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>
```

#### Step 4.4: Check Evaluation Status

Use `--wait` to auto-poll until the evaluation completes:
```bash
uv run python ../scripts/evaluate_cortex_agent.py \
    status --wait \
    --run-name <AGENT_NAME>_eval_<YYYYMMDD_HHMMSS> \
    --stage <DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE \
    --config-filename <AGENT_NAME>_eval_config.yaml \
    --database <DATABASE> --schema <SCHEMA> --connection <CONNECTION>
```

The script polls every 30 seconds (configurable via `--poll-interval`) up to 10 minutes (`--timeout`).

**Status values:**
| Status | Meaning |
|--------|---------|
| `INVOCATION_IN_PROGRESS` | Agent is being invoked on evaluation inputs |
| `COMPUTATION_IN_PROGRESS` | Metrics are being computed |
| `COMPLETED` | Evaluation finished successfully |
| `FAILED` | Evaluation failed — check `STATUS_DETAILS` |

If `FAILED`, check `STATUS_DETAILS` and consult **Troubleshooting** below.

---

### Step 5: View Results

**Generate Snowsight link:**
```sql
SELECT LOWER(CURRENT_ORGANIZATION_NAME()), LOWER(CURRENT_ACCOUNT_NAME());
```

URL format:
```
https://app.snowflake.com/<org>/<account>/#/agents/database/<DATABASE>/schema/<SCHEMA>/agent/<AGENT_NAME>/evaluations/<RUN_NAME>/records
```

**Note**: Use underscore in account name for Snowsight URLs (e.g., `sfdevrel_enterprise` not `sfdevrel-enterprise`).

Present the link to the user.

**Present results as:**
1. Summary table with overall average score per metric
2. Under `<METRIC_SCOPE> = both`, surface the per-metric mean alongside how many rows actually scored — `tool_selection_accuracy` (TSA) and `tool_execution_accuracy` (TEA) only count TEA-track rows; AC-track rows are silently excluded because their `ground_truth_invocations` field is absent.

**Per-metric mean-score query** (use this to compute the summary, including the TEA/TSA-aware exclusion):

```sql
SELECT
    METRIC_NAME,
    AVG(EVAL_AGG_SCORE)              AS mean_score,
    COUNT(*)                         AS rows_scored,
    COUNT_IF(EVAL_AGG_SCORE IS NULL) AS rows_missing_ground_truth
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<RUN_NAME>'
))
WHERE EVAL_AGG_SCORE IS NOT NULL   -- excludes "Missing ground truth" rows by design
GROUP BY METRIC_NAME
ORDER BY METRIC_NAME;
```

Print the result as a one-block summary, e.g.:

```
Evaluation complete (run: <RUN_NAME>)
  answer_correctness:        0.81  (over 28 rows; 0 missing ground truth)
  logical_consistency:       0.87  (over 30 rows; 0 missing ground truth)
  tool_selection_accuracy:   0.73  (over 15 TEA-track rows; 15 AC-track rows excluded)
  tool_execution_accuracy:   0.70  (over 15 TEA-track rows; 15 AC-track rows excluded)
```

**Query results programmatically (optional):**
```sql
-- Get evaluation results
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<RUN_NAME>'
))
ORDER BY TIMESTAMP DESC;

-- Get evaluation criteria for low scores
SELECT
    RECORD_ID, METRIC_NAME, EVAL_AGG_SCORE,
    e.VALUE:criteria::VARCHAR AS CRITERIA,
    e.VALUE:explanation::VARCHAR AS EXPLANATION
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<RUN_NAME>'
)),
LATERAL FLATTEN(input => EVAL_CALLS) e
WHERE EVAL_AGG_SCORE < 0.5
ORDER BY EVAL_AGG_SCORE ASC;

-- Drill into a specific record's execution trace
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_RECORD_TRACE(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<RECORD_ID>'
))
ORDER BY START_TIMESTAMP;

-- Check for errors and warnings
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_LOGS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE record:"severity_text" IN ('ERROR', 'WARN')
AND record_attributes:"snow.ai.observability.run.name" = '<RUN_NAME>';
```

**⚠️ MANDATORY STOPPING POINT**: Review results with user. Discuss findings and next steps.

---

## Troubleshooting

### Permission Errors

Agent evaluation touches many objects (agent, dataset schema, current schema, stage, warehouse, every tool the agent uses), so a single missing grant can surface as any of several confusing errors. On **any** permission-related failure, do not fix just the one error — run **all** of the checks below at once to surface every missing grant in a single pass. The `-- Look for:` comment on each block documents the grant required at that scope.

```sql
-- 1. Current role and warehouse
SELECT CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS warehouse;

-- 2. Account-level and database-role grants
SHOW GRANTS TO ROLE <role>;
-- Look for: DATABASE ROLE SNOWFLAKE.CORTEX_USER, EXECUTE TASK ON ACCOUNT

-- 3. Agent database grants
SHOW GRANTS ON DATABASE <agent_db>;
-- Look for: USAGE

-- 4. Agent schema grants
SHOW GRANTS ON SCHEMA <agent_db>.<agent_schema>;
-- Look for: USAGE, CREATE FILE FORMAT, CREATE TASK

-- 5. Agent object grants
SHOW GRANTS ON AGENT <agent_db>.<agent_schema>.<agent_name>;
-- Look for: USAGE or OWNERSHIP, MONITOR or OWNERSHIP

-- 6. Eval data database grants (skip if same as agent database)
SHOW GRANTS ON DATABASE <data_db>;
-- Look for: USAGE

-- 7. Eval data schema grants (skip if same as agent schema)
SHOW GRANTS ON SCHEMA <data_db>.<data_schema>;
-- Look for: USAGE, EXECUTE TASK, CREATE DATASET (if registering a new dataset)

-- 8. Stage grants (if stage already exists)
SHOW GRANTS ON STAGE <agent_db>.<agent_schema>.<stage_name>;
-- Look for: READ

-- 9. Warehouse grants (Snowsight requires USAGE on the default warehouse)
SHOW GRANTS ON WAREHOUSE <warehouse>;
-- Look for: USAGE
```

Also confirm the role has access to every tool the agent calls (semantic views, Cortex Search services, warehouses, stored procedures, etc.) — missing tool grants surface as agent-side failures, not eval-engine errors.

Compare results against the expected grants below. Present **all** missing grants to the user at once:

```sql
-- Example output — include only the grants that are actually missing:
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <role>;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <role>;
GRANT USAGE ON DATABASE <agent_db> TO ROLE <role>;
GRANT USAGE ON SCHEMA <agent_db>.<agent_schema> TO ROLE <role>;
GRANT CREATE FILE FORMAT ON SCHEMA <agent_db>.<agent_schema> TO ROLE <role>;
GRANT CREATE TASK ON SCHEMA <agent_db>.<agent_schema> TO ROLE <role>;
GRANT USAGE ON DATABASE <data_db> TO ROLE <role>;
GRANT USAGE ON SCHEMA <data_db>.<data_schema> TO ROLE <role>;
GRANT EXECUTE TASK ON SCHEMA <data_db>.<data_schema> TO ROLE <role>;
GRANT CREATE DATASET ON SCHEMA <data_db>.<data_schema> TO ROLE <role>;
GRANT USAGE ON AGENT <agent_db>.<agent_schema>.<agent_name> TO ROLE <role>;
GRANT MONITOR ON AGENT <agent_db>.<agent_schema>.<agent_name> TO ROLE <role>;
GRANT READ ON STAGE <agent_db>.<agent_schema>.<stage_name> TO ROLE <role>;
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE <role>;
```

> Tip: An `ACCOUNTADMIN` can grant the `SNOWFLAKE.AI_OBSERVABILITY_READER` application role so users can run read-only queries on `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` for evaluations.

Ask the user to run all missing grants (or have an admin run them), then retry the failed step.

### "Dataset already exists" or run fails immediately after a previous attempt

If the YAML contains a top-level `dataset:` block and a dataset with the same `dataset_name` was already created (either by a previous run or by `SYSTEM$CREATE_EVALUATION_DATASET`), `EXECUTE_AI_EVALUATION` can fail even when you change `run_name`. Fix by removing the `dataset:` block and keeping only `evaluation:` (pointing to the existing `dataset_name` via `source_metadata`) and `metrics:`. See Step 4.1.

### YAML Config Not Parsed

1. Ensure the file format uses `FIELD_DELIMITER = NONE` (not comma)
2. Verify upload: `SELECT $1 FROM @<stage>/<file>.yaml;`
3. Check YAML indentation — spaces, not tabs
4. `dataset_type` accepts `"CORTEX AGENT"` (case-insensitive). Be consistent with casing in examples.
5. If you see `Invalid Input Fields No content to map due to end-of-input` from `EXECUTE_AI_EVALUATION` despite the file being readable via `SELECT $1 FROM @stage/file.yaml`, this has been observed intermittently when `agent_name` is specified as a fully qualified `database.schema.object`. Workaround: keep the session schema pointed at the agent's schema (`USE SCHEMA <agent_db>.<agent_schema>`) and then try a two-part `schema.object` form, or retry after a brief pause. Track this in the issue tracker.

### Script Execution Fails

1. Ensure the local YAML file exists at the path passed to `--yaml-file`
2. The script uses PUT via the Snowflake Python connector — cannot run in Snowsight
3. Check that your role has `CREATE STAGE` and `CREATE FILE FORMAT` permissions
4. Verify `uv` is installed: `uv --version`

### Evaluation STATUS Shows FAILED

1. Check `STATUS_DETAILS` column for specific errors
2. Query logs: `SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_LOGS(...)) WHERE record:"severity_text" IN ('ERROR', 'WARN');`
3. Common causes: invalid metric names, missing ground truth, agent timeout

### Ground Truth Not Parsed

1. Column type must be `VARIANT`. `OBJECT` may appear to work but `VARIANT` is explicitly recommended.
2. Build ground truth with `PARSE_JSON(...)` or `TO_VARIANT(...)`. Do **not** use `OBJECT_CONSTRUCT(...)` or `ARRAY_CONSTRUCT(...)` — they return non-VARIANT values and can be stringified at evaluation time.
3. JSON must use `ground_truth_output` for the expected final answer used by `answer_correctness`. Custom metrics can reference any JSON via the `{{ground_truth}}` placeholder (see Step 2).
4. Ensure YAML `column_mapping.ground_truth` points to the correct column name.

### Agent Refuses to Use Tools (0% scores)

Questions don't match the agent's persona. Check `DESCRIBE AGENT` for guardrails and create questions matching what the agent is designed to do.

### "No current database" Error

Run `USE DATABASE <DATABASE>; USE SCHEMA <SCHEMA>;` then re-run the failing command.

### Dataset Inspection

`SHOW DATASETS IN SCHEMA <DATABASE>.<SCHEMA>;` works to list datasets. **Note:** `DESC DATASET` is not currently supported — do not use it for dataset inspection.

---

This skill integrates with `optimize-cortex-agent` for baseline benchmarking (Phase 3) and validation after changes (Phase 6).
