---
name: custom-criteria-audit
description: Evaluate semantic view against user-defined validation rules and custom criteria specified in natural language.
required_skills:
  [
    semantic-view-setup,
    audit/custom_criteria/results_formatting,
    reference/semantic_view_get,
  ]
---

# Custom Criteria Audit

## When to Load

User selects "Custom Criteria" from AUDIT MODE menu.

## ⚠️ CRITICAL: Create TODOs

**MANDATORY**: Use `system_todo_write` to create TODOs for all workflow phases.
All steps below are MANDATORY and cannot be skipped.

## Purpose

Allow users to define and evaluate custom validation rules against their semantic view using natural language criteria.

## Workflow

### Phase 1: Gather User Criteria

Prompt user for custom validation criteria:

```
What criteria would you like me to check for in your semantic view?

You can specify rules like:
- "Check that all revenue metrics have 'revenue' in their name"
- "Verify all date columns use DATE or TIMESTAMP data types"
- "Ensure customer-related tables have a customer_id foreign key"
- "Validate that all time dimensions have time granularity defined"
- "Check that measure descriptions mention the aggregation function"

Enter your criteria (one per line, or describe all at once):
```

**MANDATORY STOPPING POINT**: Do NOT proceed until user provides criteria.

### Phase 2: Parse Criteria

Parse user input into actionable validation rules:

1. **Identify Check Type**
   - Naming pattern checks
   - Data type validations
   - Relationship requirements
   - Metadata presence checks
   - Content format validations

2. **Extract Key Components**
   - Target elements (tables, columns, measures, etc.)
   - Conditions to check
   - Expected values or patterns
   - Severity (if mentioned)

3. **Create Validation Plan**
   - List specific checks to perform
   - Define success/failure conditions
   - Determine which components to inspect

### Phase 3: Load Semantic View

**⚠️ MANDATORY - READ FIRST**: Load [semantic_view_get.md](../../reference/semantic_view_get.md)

**Note:** All commands assume you're in `{WORKING_DIR}/optimization/` directory.

Use `semantic_view_get.py` to retrieve relevant components:

```bash
# Load components based on parsed criteria
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component all
```

### Phase 4: Develop Detection Plan

Based on user-provided criteria, create a plan to identify problems in the semantic view:

1. **Determine Search Strategy**
   - Identify which components to examine (tables, columns, measures, relationships)
   - Define what constitutes a violation of each criterion
   - Plan how to detect non-compliant elements
2. **Execute Problem Detection**
   - Scan semantic view components against each criterion
   - Flag violations and non-compliant elements
   - Document specific issues found (missing attributes, incorrect patterns, invalid types)

### Phase 5: Categorize Problems

Organize detected issues by criterion:

- **Violations**: Components that fail to meet the criteria (these are the problems)
- **Compliant**: Components that satisfy the criteria
- **Not Applicable**: Components outside the criterion's scope

### Phase 6: Present Results

Load `results_formatting.md` → Present findings to user

### Phase 7: Next Steps

**STOP** - Prompt user:

- **A**: Add more custom criteria
- **B**: Fix issues with DEBUG MODE
- **C**: Run another audit type
- **D**: Exit

## Tools

### Tool 1: semantic_view_get.py

**Description**: Retrieves components from semantic view YAML files. Always outputs in YAML format.

**⚠️ MANDATORY**: Load [semantic_view_get.md](../../reference/semantic_view_get.md) for complete syntax and examples.

**Usage for this audit**:
```bash
# Get all components for comprehensive validation
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component all

# Get specific components based on criteria
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component measures

cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component time_dimensions
```
