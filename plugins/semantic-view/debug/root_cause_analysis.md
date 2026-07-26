---
name: Root Cause Analysis
description: Analyze generated SQL and identify semantic view gaps
parent_skill: semantic-view-debug
---

# Root Cause Analysis

## When to Load

Debug mode Step 2: After getting generated SQL, need to identify issues.

## Prerequisites

- Generated SQL from Cortex Analyst
- Original user question

## Analysis Process

### Step 1: Execute SQL (if not already executed)

**CRITICAL**: Only execute step a or b. DO NOT do both.

#### a. Execute Generated SQL (without ground truth)

If this SQL isn't already executed in the conversation, execute it now:

```python
snowflake_sql_execute(sql="{generated_sql}", connection="snowhouse")
```

Show first 10-15 rows to understand what the query returns.

#### b. Execute Generated + Ground Truth SQL (with ground truth)

If user provided ground truth SQL, load [eval_sql_pair.md](../reference/eval_sql_pair.md).

Use the `eval_sql_pair.py` script.

### Step 2: Analyze Generated SQL

Compare generated SQL against the semantic view structure (tables, relationships, columns) you learned in setup.

Check for missing tables/joins (especially intermediate tables like hierarchy tables), incorrect columns, wrong aggregations, or missing filters.

### Step 2.5: Load Optimization Framework

**MANDATORY**: Load `../optimization/SKILL.md`

This provides:

- Types of fixes possible (dimension, metric, filter, relationship, custom_instructions)
- Priority order (try simpler first)
- Constraints (cannot add dimensions/facts, only enhance)

Use this to categorize your findings in the next step.

### Step 3: Identify Semantic Model Gaps

**⚠️ MANDATORY - READ FIRST**: Load [semantic_view_get.md](../reference/semantic_view_get.md)

Link SQL issues to missing semantic view elements by using the `semantic_view_get.py` tool to read the semantic view:

| SQL Issue                       | Likely Semantic Model Gap                                 |
| ------------------------------- | --------------------------------------------------------- |
| Missing column                  | Dimension/fact not properly described or missing synonyms |
| Wrong aggregation               | Missing metric definition or unclear fact descriptions    |
| Missing JOIN                    | Missing relationship between tables                       |
| Uses table not in semantic view | Table needs to be added to semantic view                  |
| Incorrect filter                | Missing named filter or unclear dimension values          |

### Step 4: Present Analysis

Present to user:

**Generated SQL**: {show SQL}

**Issues Found**:

- {issue 1} → {semantic view gap type}
- {issue 2} → {semantic view gap type}

**Recommended Fixes** (categorized by optimization priority):

1. **[dimension]** {what to enhance} → {why}
2. **[metric]** {what to add} → {why}
3. **[filter]** {what pattern} → {why}
4. **[relationship]** {what join} → {why}
5. **[custom_instructions]** {what rule} → {why}

(Present concepts only - no YAML or JSON syntax yet)

### Step 5: Get User Feedback

**MANDATORY STOP. DO NOT continue to next step until user explicitly approves**:

```

I've identified these issues. You can:

1. Proceed with these fixes
2. Provide ground truth SQL to compare
3. Tell me what's actually wrong with the SQL

```

### Step 6: Refine Analysis

Based on user response:

- **User approves** → Proceed to optimization
- **User provides ground truth** → Load [sql_comparison.md](../reference/sql_comparison.md) → Compare → Refine analysis
- **User explains issue** → Update analysis → Confirm with user

## Output

User-validated recommended fixes ready for application

## Next Skill

If user approves → Load `optimization_application.md`
