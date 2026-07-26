---
name: Metric Optimization
description: Add and optimize metrics for aggregations and calculations
parent_skill: semantic-view-patterns
priority: 2
---

# Metric Optimization

## When to Load

- Wrong aggregation logic in generated SQL
- Missing KPIs or calculations
- Complex calculations needed repeatedly

## Core Principles

**Facts vs Metrics**:

- **Facts**: Physical numeric columns (cannot add, only enhance)
- **Metrics**: Calculated aggregations (CAN add new)

## Metric Patterns

### When to Add Metrics

- LLM uses wrong aggregation function (SUM vs COUNT vs AVG)
- Missing common KPIs referenced in questions
- Complex calculations needed repeatedly

### Metric Structure

```yaml
metrics:
  - name: { DESCRIPTIVE_NAME }
    description: "{What it calculates and when to use}"
    expr: { AGGREGATE_EXPRESSION }
    access_modifier: public_access
```

**Common aggregations**: SUM, COUNT, COUNT DISTINCT, AVG, conditional aggregations

**Proto** (lines 307-325): name, synonyms, description, expr, access_modifier

### Table-Level vs Model-Level

- **Table-level**: Single table aggregations
- **Model-level**: Cross-table or complex calculations

## Examples

**Distinct customer count**:

```yaml
- name: UNIQUE_CUSTOMERS
  description: "Count of distinct customers in the data"
  expr: COUNT(DISTINCT customer_id)
  access_modifier: public_access
```

**Total revenue**:

```yaml
- name: TOTAL_REVENUE
  description: "Sum of all order amounts"
  expr: SUM(order_amount)
  access_modifier: public_access
```

**Average order value**:

```yaml
- name: AVERAGE_ORDER_VALUE
  description: "Average value across all orders"
  expr: AVG(order_amount)
  access_modifier: public_access
```

## Common Mistakes

❌ Using `default_aggregation` (deprecated field)
❌ Non-aggregate expressions in metrics
❌ Missing access_modifier
❌ Unclear or missing descriptions
❌ Overly complex expressions that should be broken down

## Validation

Test that new metrics:

- Use correct aggregation functions
- Work correctly in generated SQL
- Don't break existing queries
- Have clear, understandable descriptions for the LLM

## Applying This Optimization

Use `semantic_view_set.py` to apply. See [semantic_view_set.md](../reference/semantic_view_set.md) for complete JSON syntax.

**Example operation for creating a metric**:

```json
{
  "operation": "create",
  "component": "column",
  "table_name": "ORDERS",
  "data": {
    "name": "UNIQUE_CUSTOMERS",
    "kind": "metric",
    "description": "Count of distinct customers in the data",
    "expr": "COUNT(DISTINCT customer_id)",
    "access_modifier": "public_access"
  }
}
```
