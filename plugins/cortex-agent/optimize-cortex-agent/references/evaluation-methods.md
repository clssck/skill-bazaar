# Evaluation Methods Reference

**Purpose:** Detailed guide for running evaluations during agent optimization using Native Snowflake Agent Evaluations.
**Used by:** Phases 2, 3, 4, and 6 of the optimization workflow.

---

## Evaluation Approach

**Always use Native Snowflake Agent Evaluations** via the `evaluate-cortex-agent` skill. This provides:
- Built-in metrics: `answer_correctness`, `tool_selection_accuracy`, `logical_consistency`
- Results visible in Snowsight Evaluations UI
- Formal benchmarking and tracking over time

**Dataset format:** `INPUT_QUERY`, `GROUND_TRUTH` (OBJECT) columns.

**⚠️ IMPORTANT:** Use the same evaluation method throughout the entire optimization workflow (baseline, re-evaluation, final validation) for consistent comparison.

**LOAD:** `evaluate-cortex-agent` skill for detailed workflow.

---

## Running Evaluations

### 1. Convert Dataset to Native Format

If your dataset uses `question`/`expected_answer` columns, convert:
```sql
CREATE OR REPLACE TABLE EVAL_NATIVE_FORMAT AS
SELECT 
    question AS INPUT_QUERY,
    OBJECT_CONSTRUCT('ground_truth_output', expected_answer) AS GROUND_TRUTH
FROM existing_eval_table;
```

### 2. Register Evaluation Dataset
```sql
CALL SYSTEM$CREATE_EVALUATION_DATASET(
    'Cortex Agent',
    '<DATABASE>.<SCHEMA>.EVAL_NATIVE_FORMAT',
    '<AGENT_NAME>_baseline_dataset',
    OBJECT_CONSTRUCT('query_text', 'INPUT_QUERY', 'expected_tools', 'GROUND_TRUTH')
);
```

### 3. Run Evaluation
```sql
CALL SYSTEM$EXECUTE_AI_OBSERVABILITY_RUN(
    OBJECT_CONSTRUCT('object_name', '<DB>.<SCHEMA>.<AGENT>', 'object_type', 'CORTEX AGENT', 'object_version', ''),
    OBJECT_CONSTRUCT('run_name', '<RUN_NAME>', 'label', '<LABEL>', 'description', '<DESCRIPTION>'),
    OBJECT_CONSTRUCT('type', 'dataset', 'dataset_name', '<AGENT_NAME>_baseline_dataset', 'dataset_version', 'SYSTEM_AI_OBS_CORTEX_AGENT_DATASET_VERSION_DO_NOT_DELETE'),
    ARRAY_CONSTRUCT('answer_correctness', 'tool_selection_accuracy', 'logical_consistency'),
    ARRAY_CONSTRUCT('INGESTION', 'COMPUTE_METRICS')
);
```

### 4. Poll for Results

Evaluations run asynchronously. Poll until results appear:
```sql
SELECT COUNT(*) as record_count
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'))
WHERE RECORD_ATTRIBUTES:"snow.ai.observability.run.name" = '<RUN_NAME>'
AND RECORD_ATTRIBUTES:"ai.observability.span_type" = 'eval_root';
```

If `record_count` is 0, wait 30-60 seconds and try again.

### 5. Query Results
```sql
WITH eval_results AS (
    SELECT * FROM TABLE(
        GET_AI_OBSERVABILITY_EVENTS(
            OBJECT_CONSTRUCT('object_name', '<DB>.<SCHEMA>.<AGENT>', 'object_type', 'CORTEX AGENT'),
            '<RUN_NAME>'
        )
    )
),
scores AS (
    SELECT 
        r.value:ATTRIBUTES:input_query::STRING AS question,
        r.value:ATTRIBUTES:answer_correctness::FLOAT AS correctness,
        r.value:ATTRIBUTES:tool_selection_accuracy::FLOAT AS tool_selection,
        r.value:ATTRIBUTES:logical_consistency::FLOAT AS consistency,
        r.value:ATTRIBUTES:answer_correctness_explanation::STRING AS explanation
    FROM eval_results,
    LATERAL FLATTEN(input => PARSE_JSON(SPANS)) r
    WHERE r.value:NAME::STRING = 'eval_root'
)
SELECT * FROM scores;
```

---

## Evaluation Run Naming Conventions

Use descriptive run names to track your optimization journey:
- `baseline_v1` — initial evaluation before any changes
- `after_improvements_v1` — after instruction improvements (Phase 4)
- `generalized_v1` — after generalization (Phase 6)

---

## Filtering & Progressive Testing Strategies

For targeted re-evaluation after improvements, create filtered datasets:
```sql
-- Re-test only failed questions
CREATE OR REPLACE TABLE EVAL_RETRY AS
SELECT * FROM EVAL_NATIVE_FORMAT WHERE INPUT_QUERY IN ('question 1', 'question 2');

-- Test by category
CREATE OR REPLACE TABLE EVAL_ROUTING AS
SELECT * FROM EVAL_NATIVE_FORMAT WHERE /* routing questions */;
```

**Progressive approach:**
1. Start with small subset (5-10 questions) to validate agent works
2. Run full evaluation once agent shows promise
3. Re-test only failed questions after improvements
4. Run final comprehensive evaluation before deployment
