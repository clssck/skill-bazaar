---
name: semantic-view-patterns
description: Library of optimization patterns for dimensions, metrics, filters, relationships, and custom instructions. Use when root cause analysis identifies gaps needing targeted fixes.
sub_skills:
  [
    dimension_optimization.md,
    metric_optimization.md,
    filter_optimization.md,
    relationship_optimization.md,
    custom_instructions.md,
  ]
---

# Optimization Pattern Library

## When to Load

- Root cause analysis (debug) identified semantic view gaps
- Audit identified structural issues to fix (e.g., missing relationships)

## LLM Approach

**These are patterns, not rigid rules**:

- Understand the underlying principles
- Adapt to the specific semantic view and issue
- Use judgment for unusual cases
- Ask user when uncertain

**Don't just copy examples** - analyze the issue and apply the right fix creatively.

## Load Strategy

| Issue Type                | Load Skill                     |
| ------------------------- | ------------------------------ |
| Column not used correctly | `dimension_optimization.md`    |
| Wrong aggregations        | `metric_optimization.md`       |
| Missing filter patterns   | `filter_optimization.md`       |
| Missing joins             | `relationship_optimization.md` |
| Complex business logic    | `custom_instructions.md`       |
| Issue calls for an advanced modeling pattern: comparing a metric to the same period last year/month (YoY, MoM, SPLY); rolling / YTD / lag-N metrics; SCD2 / ASOF temporal joins; snapshot facts that must not sum across time; accumulating funnels with multiple milestone dates; routing a metric through a specific FK when one fact has two FKs to the same dim; cross-entity derived metrics; `PRIVATE` facts; computed-FK joins; AI metadata steering Cortex Analyst; or diagnosing a structural error like a fan trap or "multi-path relationship not supported" | `../patterns/SKILL.md` |

## Optimization Priority

1. **Enhance Dimensions/Facts** (descriptions, synonyms) → `dimension_optimization.md`
2. **Add Metrics** (aggregations) → `metric_optimization.md`
3. **Add Filters** (WHERE conditions) → `filter_optimization.md`
4. **Add/Fix Relationships** (joins) → `relationship_optimization.md`
5. **Custom Instructions** (last resort) → `custom_instructions.md`

## Key Constraints

**Cannot Add**:

- Dimensions (physical columns - only enhance metadata)
- Facts (physical columns - only enhance metadata)

**Can Add**:

- Metrics (calculated aggregations)
- Filters (named WHERE clauses)
- Relationships (joins)
- Custom instructions

**Prefer**: Explicit model elements over custom instructions

## References

- Example: `example_semantic_view.yaml` (valid field structures)
- Proto: `semantic_model.proto` (Dimension 105-134, Fact 174-199, Metric 307-325)

## Guidelines

- **DO NOT** modify `verified_queries` **while applying these dimension/metric/filter/relationship patterns**. Dedicated VQR editing uses **`semantic_view_set.py`** — see [semantic_view_set.md](../reference/semantic_view_set.md). Optional compile-check / expand / truncate: [sva_validate_verified_queries.md](../reference/sva_validate_verified_queries.md), [sva_expand_truncate_verified_query.md](../reference/sva_expand_truncate_verified_query.md).
- **ASK** user for clarifications when ambiguous
- **VALIDATE** after each optimization
- **ITERATE** if first attempt doesn't work
