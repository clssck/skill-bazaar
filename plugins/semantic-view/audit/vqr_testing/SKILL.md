---
name: vqr-testing-audit
description: Systematically test semantic views by evaluating all verified queries without VQR hints. Identifies which queries fail to measure semantic view completeness.
required_skills:
  [
    semantic-view-setup,
    audit/vqr_testing/vqr_extraction,
    audit/vqr_testing/vqr_evaluation,
    audit/vqr_testing/results_formatting,
    reference/sql_comparison,
  ]
---

# VQR Testing Audit

## When to Load

User selects "VQR Testing" from AUDIT MODE menu.

## ⚠️ CRITICAL: Create TODOs

**MANDATORY**: Use `system_todo_write` to create TODOs for all workflow phases.
All steps below are MANDATORY and cannot be skipped.

## Purpose

Identify which VQRs fail when semantic view has no VQR hints.

## Workflow

### Phase 1: VQR Selection

Load `vqr_extraction.md` → Present VQRs → Get user selection → **STOP**

### Phase 2: Evaluate VQRs

Load `vqr_evaluation.md` → Test each VQR → Use [sql_comparison.md](../../reference/sql_comparison.md) for comparisons

### Phase 3: Present Results

Load `results_formatting.md` → Present findings to user

### Phase 4: Next Steps

**STOP** - Prompt user:

- **A**: DEBUG MODE (fix failing VQRs)
- **B**: Continue audit (more VQRs)
- **C**: Exit

## Tools

### Tool 1: snowflake_multi_cortex_analyst

**Description**: Generates SQL from natural language using Cortex Analyst  
**Parameters**: Tool parameters are defined by the `snowflake_multi_cortex_analyst` tool

### Tool 2: eval_sql_pair.py

**Description**: Executes pair of SQL queries and returns corresponding pair of result sets for comparison.
**Parameters**: Load [eval_sql_pair.md](../../reference/eval_sql_pair.md)

### Tool 3: semantic_view_get.py

**Description**: Retrieves components from semantic view YAML files. Always outputs in YAML format.

**⚠️ MANDATORY**: Load [semantic_view_get.md](../../reference/semantic_view_get.md) for complete syntax and examples.
