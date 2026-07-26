---
name: semantic-view-debug
description: Debug and fix specific SQL generation issues in semantic views. Diagnoses root causes, applies targeted optimizations, and validates fixes. Use after semantic-view-setup skill when you have a failing question or VQR.
required_skills:
  [
    semantic-view-setup,
    debug/issue_diagnosis,
    debug/root_cause_analysis,
    debug/optimization_application,
    semantic-view-validation,
    semantic-view-patterns,
  ]
---

# Debug Mode

## ⚠️ PREREQUISITES CHECK

**Before starting debug workflow, verify you completed initialization from main SKILL.md:**

**Required:**

- Loaded `setup/SKILL.md`
- Created workspace directory
- Understand semantic view tools

**If ANY requirement is not met:** STOP. Go back to main SKILL.md and complete initialization sequence.

## When to Load

User selects DEBUG MODE or has specific problematic question.

## ⚠️ CRITICAL: Create TODOs

**MANDATORY**: Use `system_todo_write` to create TODOs for all workflow steps.
All steps below are MANDATORY and cannot be skipped.

## ⚠️ TOOL USAGE REQUIREMENT

**For all semantic view YAML operations, use ONLY the approved tools:**

- Reading: `semantic_view_get.py` (see [semantic_view_get.md](../reference/semantic_view_get.md))
- Writing: `semantic_view_set.py` (see [semantic_view_set.md](../reference/semantic_view_set.md))

**DO NOT use grep/cat/jq/sed/awk on semantic view YAMLs.** See tool documentation for rationale and proper usage.

## Workflow

**CRITICAL**: Make sure setup step has completed before proceeding. See [../setup/SKILL.md](../setup/SKILL.md).

### Step 1: Diagnosis

Load `issue_diagnosis.md` and execute ALL steps:

1. Get problematic question(s) from user
2. Generate SQL with Cortex Analyst (parallel for multiple)
3. Present generated SQL

Output: Generated SQL for all questions.

Continue now to Step 2.

### Step 2: Root Cause

Load `root_cause_analysis.md` and execute ALL steps → Analyze SQL issues → Identify semantic view gaps → Get user feedback → **STOP**

Resume condition: If the user explicitly approves (e.g., "Proceed", "Approved", "Looks good", "Apply optimizations"), continue to Step 3 immediately in the same session.

### Step 3: Apply Optimizations

Load `optimization_application.md` → Apply fixes → Validate with [sql_comparison.md](../reference/sql_comparison.md)

## Tools

### Tool 1: snowflake_multi_cortex_analyst

**Description**: Generates SQL from natural language using Cortex Analyst  
**Parameters**: Tool parameters are defined by the `snowflake_multi_cortex_analyst` tool. Use local semantic view file paths without the '@'.

### Tool 2: snowflake_sql_execute

**Description**: Executes SQL queries and returns result sets  
**Parameters**: Tool parameters are defined by the `snowflake_sql_execute` tool

### Tool 3: reflect_semantic_model

**Description**: Validates and reflects on semantic view structure
**Parameters**: Tool parameters are defined by the `reflect_semantic_model` tool

### Tool 4: semantic_view_get.py

**Description**: Retrieves components from semantic view YAML files. Always outputs in YAML format.

**⚠️ MANDATORY**: Load [semantic_view_get.md](../reference/semantic_view_get.md) for complete syntax and examples.

### Tool 5: semantic_view_set.py

**Description**: Modifies semantic view YAML through create, update, delete operations. Always outputs to new file.

**⚠️ MANDATORY**: Load [semantic_view_set.md](../reference/semantic_view_set.md) for complete syntax and examples.

## Stopping Points

- ✋ After diagnosis if ground truth needed
- ✋ After root cause analysis for approval
- ✋ After validation with results

Resume rule: Upon user approval in Step 2, move directly to "Apply Optimizations" (Step 3) without re-asking.

## Success

- ✅ Model validates
- ✅ SQLs execute
- ✅ Results match EXACTLY

## Output

Optimized semantic view YAML file
