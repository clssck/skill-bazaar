---
name: semantic-view-audit
description: Comprehensive audit system for semantic views with multiple audit types including VQR testing (behavioral), SVA VQR compile validation (validate_verified_queries), best practices verification (with inconsistencies and duplicates detection), and custom criteria evaluation.
required_skills:
  [
    semantic-view-setup,
    audit/vqr_testing/SKILL,
    audit/best_practices/SKILL,
    audit/custom_criteria/SKILL,
  ]
---

# Audit Mode

## ⚠️ PREREQUISITES CHECK

**Before starting audit workflow, verify you completed initialization from main SKILL.md:**

**Required:**

- Loaded `setup/SKILL.md`
- Created workspace directory
- Understand semantic view tools

**If ANY requirement is not met:** STOP. Go back to main SKILL.md and complete initialization sequence.

## When to Load

User selects AUDIT MODE after setup.

## ⚠️ TOOL USAGE REQUIREMENT

**For all semantic view YAML operations, use ONLY the approved tools**: `semantic_view_get.py` and `semantic_view_set.py`. See [semantic_view_get.md](../reference/semantic_view_get.md) and [semantic_view_set.md](../reference/semantic_view_set.md) for documentation.

## ⚠️ CRITICAL: Create TODOs

**MANDATORY**: Use `system_todo_write` to create TODOs for all workflow phases.
All steps below are MANDATORY and cannot be skipped.

## Purpose

Provide comprehensive semantic view auditing through multiple specialized audit types.

## Workflow

**CRITICAL**: Make sure setup step has completed before proceeding. See [../setup/SKILL.md](../setup/SKILL.md).

### Phase 1: Audit Type Selection

Present audit menu to user:

```
Select audit type:

1. VQR Testing - Test queries against semantic view without VQR hints (behavioral; CA vs ground truth)
2. Best Practices - Verify naming, documentation, metadata, inconsistencies, and duplicates
3. Custom Criteria - Evaluate user-defined validation rules
4. SVA VQR compile check - validate stored or candidate SQL via validate_verified_queries (Snowflake EXPLAIN path)

Enter your selection (1-4):
```

**MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

### Phase 2: Route to Selected Audit

Based on user selection, load the appropriate audit skill:

**Option 1: VQR Testing**

- Load `vqr_testing/SKILL.md`
- Execute VQR testing workflow
- Identify which VQRs fail without hints

**Option 2: Best Practices**

- Load `best_practices/SKILL.md`
- Check naming conventions, descriptions, metadata completeness
- Detect inconsistencies (conflicting definitions, logical errors)
- Identify duplicates (redundant information across the model)
- Report all findings with severity levels

**Option 3: Custom Criteria**

- Load `custom_criteria/SKILL.md`
- Prompt user for criteria
- Evaluate and report findings

**Option 4: SVA VQR compile check**

- Load [../reference/sva_validate_verified_queries.md](../reference/sva_validate_verified_queries.md)
- Collect semantic view FQN and warehouse (bulk mode), **or** local model YAML path + SQL strings (inline mode after stripping `verified_queries` from the YAML payload)
- Run the SQL from that reference via the user’s Snowflake execution path; present per-query `valid` / `error_detail` results
- **Do not confuse** with Option 1 — Option 1 tests NL→SQL behavior without VQR hints; Option 4 tests SQL compilation against the model

### Phase 3: Execute Audit

Follow the loaded audit skill's workflow.

### Phase 4: Next Steps

After audit completion, prompt user:

- **A**: Run another audit type
- **B**: DEBUG MODE (query-based problem investigation)
- **C**: OPTIMIZATION MODE (apply fixes for identified issues)
- **D**: Exit

## Tools

All tools are defined in the individual audit skill files.

## Output

Output format depends on selected audit type. See individual audit skills for details.
