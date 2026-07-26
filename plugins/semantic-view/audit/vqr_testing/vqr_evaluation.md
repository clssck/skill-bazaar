---
name: VQR Evaluation
description: Evaluate VQR questions against semantic view without VQR hints
parent_skill: vqr-testing-audit
---

# VQR Evaluation

## When to Load

Audit mode Step 3: User selected VQRs to audit.

## Task

Test each VQR to see if Cortex Analyst generates correct SQL without VQR hints.

## Process

**CRITICAL**: Parallelize all tool calls below for multiple VQRs. Do not skip any steps for all VQRs.

### 1. For Each Selected VQR

**CRITICAL**: Each step's tool calls should be done in parallel in a single batch.

#### a. Generate SQL

**Use `snowflake_multi_cortex_analyst` tool** with local file paths (do not prefix with '@') and without the VQR retrieval step. Query Cortex Analyst with the VQR question to test:

**Note:** Use the semantic model with VQRs removed (see setup/SKILL.md for how this is created).

```python
# Call Cortex Analyst for VQR 1
snowflake_multi_cortex_analyst(
    query="{VQR 1 question}",
    semantic_model_file="{WORKING_DIR}/optimization/<semantic_view_name>_semantic_model_no_vqrs.yaml",
    skip_vqr_retrieval=True
)
# Call Cortex Analyst for VQR 2
snowflake_multi_cortex_analyst(
    query="{VQR 2 question}",
    semantic_model_file="{WORKING_DIR}/optimization/<semantic_view_name>_semantic_model_no_vqrs.yaml",
    skip_vqr_retrieval=True
)
...(remaining VQRs for execution)
```

#### b. Retrieve Ground Truth SQLs

Load [semantic_view_get.md](../../reference/semantic_view_get.md).

Retrieve all VQR ground truth SQLs using `semantic_view_get.py`.

```bash
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component verified_queries \
  --extract sqls
```

#### c. Execute and Compare Results

Load [eval_sql_pair.md](../../reference/eval_sql_pair.md).

Execute all generated SQLs and physical ground truth SQLs using `eval_sql_pair.py`.

```bash
cd {WORKING_DIR}/optimization && \
# Execute eval for VQR 1 sql pairs
uv run python {SKILL_BASE_DIR}/scripts/eval_sql_pair.py \
  --sql1 "{VQR 1 ground truth SQL}" \
  --sql2 "{generated SQL}" \
  --output vqr_1_comparison_results.txt

# Execute eval for VQR 2 sql pairs
uv run python {SKILL_BASE_DIR}/scripts/eval_sql_pair.py \
  --sql1 "{VQR 2 ground truth SQL}" \
  --sql2 "{generated SQL}" \
  --output vqr_2_comparison_results.txt
...(remaining VQRs for execution)
```

Compare execution results using [sql_comparison.md](../../reference/sql_comparison.md) format. DO NOT assume pass/fail from SQL structure.

⚠️ MANDATORY CHECKPOINT: Before categorizing any VQR as PASS/FAIL:
- Verify comparison output file exists for EVERY VQR that generated SQL
- Count: generated SQL count MUST equal comparison file count
- DO NOT proceed to results_formatting.md until all comparisons complete

#### d. Categorize

- **PASS**: Results match exactly
- **FAIL**: Results differ, SQL errors, or no SQL generated

### 2. Collect Data

For each VQR: question, ground truth SQL, generated SQL, results comparison, pass/fail status.

Do NOT stop to discuss findings with user yet. Move on to the next instruction.
