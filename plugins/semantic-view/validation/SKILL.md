---
name: semantic-view-validation
description: Validate semantic model changes by comparing SQL execution results with exact match requirements. Used by audit and debug to verify optimizations produce correct results.
applies_to: [semantic-view-audit, semantic-view-debug]
---

# Semantic Model Validation

## When to Load

After generating optimizations, need to validate changes.

**Related (not a substitute for this file):** Snowflake Analyst **`validate_verified_queries`** (compile / EXPLAIN for VQR SQL) is documented in [sva_validate_verified_queries.md](../reference/sva_validate_verified_queries.md). This skill file covers **`reflect_semantic_model`** and **exact SQL result** comparison for optimization/debug loops.

## Validation Levels

### 1. Semantic Model Syntax

```python
reflect_semantic_model(semantic_model_yaml)
```

Checks: YAML syntax, schema compliance, configuration validity.

If fails: Analyze error → Fix → Retry once → If still fails, remove entity.

### 2. SQL Execution & Comparison

**Load**: [sql_comparison.md](../reference/sql_comparison.md) for detailed comparison procedures.

Execute ground truth and generated SQL, compare results.

## Exact Match Requirement

**CRITICAL**: Only EXACT matches acceptable.

✅ **Exact**: 100 = 100, "value" = "value"  
❌ **Not Exact**: 100 ≈ 99, "close" matches

Any "VERY CLOSE", "CLOSE", or approximate = **FAILED**.

## Present Validation Results

Report to user:

- Semantic model status (PASS/FAIL)
- SQL execution status
- Data comparison result (EXACT MATCH / FAILED)
- Use [sql_comparison.md](../reference/sql_comparison.md) format for showing results

## Success Criteria

- ✅ Semantic model validates
- ✅ Both SQLs execute
- ✅ Row counts match
- ✅ Data values match EXACTLY

## If Fails

1. Document failure point
2. Return to root cause analysis
3. Generate additional optimizations
4. Re-run validation
