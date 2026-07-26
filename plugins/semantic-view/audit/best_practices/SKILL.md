---
name: best-practices-audit
description: Verify semantic view compliance with established best practices including naming conventions, descriptions, metadata completeness, data quality standards, inconsistencies detection, and duplicates detection.
required_skills:
  [
    semantic-view-setup,
    audit/best_practices/results_formatting,
    audit/best_practices/inconsistencies,
    audit/best_practices/duplicates,
    audit/best_practices/missing_relationships,
    reference/semantic_view_get,
  ]
---

# Best Practices Audit

## When to Load

User selects "Best Practices" from AUDIT MODE menu.

## ⚠️ CRITICAL: Create TODOs

**MANDATORY**: Use `system_todo_write` to create TODOs for all workflow phases.
All steps below are MANDATORY and cannot be skipped.

## Purpose

Verify that the semantic view follows established best practices for naming, documentation, metadata completeness, and data quality. Additionally, detect structural inconsistencies and duplicate instructions to ensure model integrity and maintainability.

## Workflow

### Phase 1: Load Semantic View

**⚠️ MANDATORY - READ FIRST**: Load [semantic_view_get.md](../../reference/semantic_view_get.md)

**Note:** All commands assume you're in `{WORKING_DIR}/optimization/` directory.

Use `semantic_view_get.py` to retrieve the complete semantic view:

```bash
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component all
```

### Phase 2: Execute Checks

Run all checks against the semantic view in three categories:

#### Phase 2a: Best Practices Checks

1. **Documentation Checks**

   - Verify all tables have descriptions
   - Verify all columns have descriptions
   - Check description quality clarity

2. **Naming Convention Checks**

   - Check for special characters
   - Verify naming consistency

3. **Metadata Completeness Checks**

   - Verify data types are defined
   - Synonyms are not necessary
   - Relationships should have no descriptions

4. **Type Safety Checks**
   - Validate dimension vs measure classification
   - Check time dimension types for date columns

#### Phase 2b: Inconsistencies Checks

**⚠️ MANDATORY**: Load [inconsistencies.md](inconsistencies.md) for detection methodology

#### Phase 2c: Duplicates Checks

**⚠️ MANDATORY**: Load [duplicates.md](duplicates.md) for detection methodology

#### Phase 2d: Missing Relationships Checks

**⚠️ MANDATORY**: Load [missing_relationships.md](missing_relationships.md) for detection methodology

Only flag if relationship count is suspiciously low for table count.

### Phase 3: Categorize Issues

Group findings by category and severity:

**Best Practices:**

- **ERROR**: Critical issues that will cause failures
- **WARNING**: Issues that should be addressed but won't break functionality
- **INFO**: Recommendations for improvement

**Inconsistencies:**

- **CRITICAL**: Will cause query failures or wrong results
- **HIGH**: Likely to cause confusion or unexpected behavior
- **MEDIUM**: May cause issues in specific scenarios
- **LOW**: Stylistic inconsistencies

**Duplicates:**

- **Exact duplicates**: Instruction repeats model element verbatim
- **High similarity**: Instruction conveys same information (>85%)
- **Partial overlap**: Instruction partially repeats model information

**Missing Relationships:**

- Only flagged when count is below threshold for table count

### Phase 4: Present Results

Load `results_formatting.md` → Present findings to user

### Phase 5: Next Steps

**STOP** - Prompt user:

- **A**: Run another audit type
- **B**: DEBUG MODE (query-based problem investigation)
- **C**: OPTIMIZATION MODE (apply fixes for identified issues)
- **D**: Exit

## Tools

### Tool 1: semantic_view_get.py

**Description**: Retrieves components from semantic view YAML files. Always outputs in YAML format.

**⚠️ MANDATORY**: Load [semantic_view_get.md](../../reference/semantic_view_get.md) for complete syntax and examples.

**Usage for this audit**:

```bash
# Get all components
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component all

# Get specific components
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component tables

cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component dimensions

cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --component measures
```

## Output

- **Best Practices**: Categorized list of violations with severity levels
- **Inconsistencies**: Conflicts and logical errors with severity and impact assessment
- **Duplicates**: Duplicate instructions with similarity scores
- **Missing Relationships**: Potential relationships with confidence levels and prerequisites
- Specific locations in semantic view for all issues
- Recommendations for fixes
