---
name: Custom Instructions
description: When and how to use custom instructions (LAST RESORT)
parent_skill: semantic-view-patterns
priority: 6
---

# Custom Instructions

## When to Load

Only after trying dimensions, metrics, relationships, and filters.

## Principle

**LAST RESORT**: Only use when semantic view elements cannot express the logic.

Try first: Dimensions → Metrics → Relationships → Filters → Descriptions → Then custom instructions.

## When Appropriate

### Snapshot/Historical Data

```yaml
custom_instructions: |-
  Unless explicitly asked for historical analysis, ALWAYS filter 
  for snapshot_flag = 'Current'.
```

### Aggregation Interpretation

```yaml
custom_instructions: |-
  "Biggest X" where X is categorical means frequency (COUNT), 
  not value (SUM), unless question mentions revenue/ACV.
```

### Domain-Specific Rules

```yaml
custom_instructions: |-
  For fiscal quarters, add 11 months before extracting quarter
  (fiscal year starts in February).
```

## Structure

```yaml
custom_instructions: |-
  1. Data characteristics (snapshot, fiscal calendar)
  2. Interpretation rules ("biggest" = count vs sum)
  3. Business logic (status mappings, filters)
  4. Query patterns (GROUP BY guidance)
```

## Generalized vs Query-Specific

❌ **BAD** (overfitting):

```yaml
custom_instructions: For "Who are biggest partners?", use COUNT(DISTINCT id) GROUP BY partner.
```

✅ **GOOD** (generalized):

```yaml
custom_instructions: |-
  "Biggest [dimension]" means most frequent:
  - GROUP BY dimension
  - COUNT(DISTINCT primary_key)
  - Filter out NULLs

  Examples: "biggest partners" → COUNT GROUP BY partner
```

## Module-Specific

```yaml
module_custom_instructions:
  sql_generation: Use table aliases for readability.
  question_categorization: Treat trend questions as UNAMBIGUOUS_SQL.
```

**⚠️ Important**:

- If the semantic view has NEITHER `custom_instructions` NOR `module_custom_instructions`, **prefer creating `module_custom_instructions`** (more targeted).
- If the semantic view already has `module_custom_instructions`, preserve and extend them with append mode.
- If the semantic view only has `custom_instructions`, preserve the existing pattern and continue to use that.

## Validation

1. Validate model with instructions
2. Test with original question
3. Test with related questions (ensure generalization)
4. Check no negative impact on working queries

## Avoid

❌ SQL hints ("Use exact query: SELECT...")
❌ Query-specific instructions  
❌ Replacing semantic view (should enhance)

## Applying This Optimization

Use `semantic_view_set.py` to apply. See [semantic_view_set.md](../reference/semantic_view_set.md) for complete JSON syntax.

**Example operation for creating custom instructions**:

```json
{
  "operation": "create",
  "component": "custom_instructions",
  "value": "Unless explicitly asked for historical analysis, ALWAYS filter for snapshot_flag = 'Current'."
}
```

**Example operation for appending to existing custom instructions**:

```json
{
  "operation": "update",
  "component": "custom_instructions",
  "value": "When filtering by customers and partners, use: snowflake_account_type IN ('Customer', 'Partner')",
  "mode": "append"
}
```
