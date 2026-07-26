---
name: VQR Extraction and Selection
description: Extract VQRs from semantic view and prompt user to select which to audit
parent_skill: vqr-testing-audit
---

# VQR Extraction and Selection

## When to Load

- Audit mode Step 1: User has selected AUDIT MODE
- Need to present VQRs to user for selection

## Prerequisites

- Semantic model YAML available for extraction

## Task

Read VQRs and get user selection for which VQRs to audit.

## Steps

### 1. Read VQRs

**⚠️ MANDATORY - READ FIRST**: Load [semantic_view_get.md](../../reference/semantic_view_get.md)

**Note:** All commands assume you're in `{WORKING_DIR}/optimization/` directory.

Use tool:

```bash
# To extract only questions:
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component verified_queries \
  --extract questions

# To extract only SQL queries:
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component verified_queries \
  --extract sqls
```

### 2. Present VQRs to User

Identify VQR natural language question and present them to the user.

**MANDATORY FORMAT**:

```
Found X VQRs:

1. Question: {natural language question}
2. Question: {natural language question}
3. Question: {natural language question}
...

Which questions do you want to audit against the semantic view?
Enter numbered questions (e.g., "1,3,5") or "ALL"
```

### 3. STOP and WAIT

**MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

### 4. Parse User Response

- "ALL" → Select all VQRs
- "1,3,5" → Select VQRs at indices 1, 3, 5
- Store selected VQR indices for evaluation phase

## Output

- List of selected VQR questions and their ground truth SQL
- Ready to proceed to VQR evaluation phase

## Next Skill to Load

After user selection confirmed:
→ Load `vqr_evaluation.md` to begin testing
