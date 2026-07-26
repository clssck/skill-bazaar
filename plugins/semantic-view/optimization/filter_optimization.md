---
name: Filter Optimization
description: Add and optimize filters for common WHERE conditions
parent_skill: semantic-view-patterns
priority: 3
---

# Filter Optimization

## When to Load

- Common WHERE conditions repeated across queries
- Business logic rules needed (active customers, recent data, valid transactions)
- Time-based filters required (fiscal year, last quarter)
- Missing domain-specific filter patterns

## Core Principles

**Filters**: Named WHERE conditions that can be added to semantic views

- **Purpose**: Encapsulate common business logic and filtering patterns
- **Reusability**: Define once, reference in multiple queries
- **Clarity**: Make filter intent explicit to the LLM
- **Scope**: Filters are table-scoped and must be nested under the table they apply to

## Filter Patterns

### When to Add Filters

- Common WHERE conditions repeated across queries
- Business logic rules (active customers, recent data, valid transactions)
- Time-based filters (fiscal year, last quarter)
- Domain-specific filtering requirements

### Filter Structure

**Important**: Filters must be nested under the table they apply to.

```yaml
tables:
  - name: { TABLE_NAME }
    filters:
      - name: { DESCRIPTIVE_NAME }
        description: "{When and how to use this filter}"
        expr: { WHERE_CLAUSE_EXPRESSION }
```

**Proto** (lines 204-214): name, synonyms, description, expr

### Examples

**Time-based filter**:

```yaml
tables:
  - name: SALES
    filters:
      - name: LAST_30_DAYS
        description: "Filter for records in the last 30 days"
        expr: date >= DATEADD(day, -30, CURRENT_DATE())
```

**Business logic filter**:

```yaml
tables:
  - name: CUSTOMERS
    filters:
      - name: ACTIVE_CUSTOMERS
        description: "Filter for customers with active status"
        expr: status = 'ACTIVE' AND last_purchase_date >= DATEADD(month, -6, CURRENT_DATE())
```

**Categorical filter**:

```yaml
tables:
  - name: TRANSACTIONS
    filters:
      - name: VALID_TRANSACTIONS
        description: "Filter for completed and verified transactions only"
        expr: transaction_status = 'COMPLETED' AND is_verified = TRUE
```

## Common Mistakes

❌ Placing filters at the top level instead of nested under tables
❌ Using HAVING clauses (should be WHERE style expressions)
❌ Overly complex expressions that should be broken down
❌ Filters that depend on aggregations (use metrics instead)
❌ Missing clear descriptions of when to use the filter

## Validation

Test that new filters:

- Work correctly in generated SQL
- Don't break existing queries
- Improve SQL generation for relevant questions
- Have clear, understandable descriptions for the LLM

## Applying This Optimization

Use `semantic_view_set.py` to apply. See [semantic_view_set.md](../reference/semantic_view_set.md) for complete JSON syntax.

**Example operation for creating a filter**:

```json
{
  "operation": "create",
  "component": "column",
  "table_name": "SALES",
  "data": {
    "name": "LAST_30_DAYS",
    "kind": "filter",
    "description": "Filter for records in the last 30 days",
    "expr": "date >= DATEADD(day, -30, CURRENT_DATE())"
  }
}
```
