---
name: SQL Comparison and Validation
description: Compare generated SQL against ground truth or analyze independently
applies_to: [audit, debug, validation]
---

# SQL Comparison and Validation

## When to Load

- Compare generated vs ground truth SQL
- Validate SQL execution and results
- Part of audit evaluation or debug validation

## Two Modes

**Mode 1 - With Ground Truth**: Execute both, compare results  
**Mode 2 - Without Ground Truth**: Analyze generated SQL, identify issues, get user feedback

## ⚠️ MANDATORY EXECUTION STEP

**YOU MUST ALWAYS EXECUTE BOTH SQLs** - This is NOT optional!

Even if the SQL looks correct by inspection, you MUST execute and compare actual results.

**⚠️ CRITICAL**: Load [eval_sql_pair.md](eval_sql_pair.md) for the comparison tool.

**Use the `eval_sql_pair.py` tool**:

```bash
uv run python scripts/eval_sql_pair.py \
  --sql1 "{ground_truth_sql}" \
  --sql2 "{generated_sql}" \
  --output comparison_results.txt \
  --connection snowhouse
```

**Why this is mandatory:**
- SQL may look correct but produce different results
- Edge cases and data issues only visible through execution
- "Looks good" ≠ "Works correctly"
- User explicitly requires execution-based validation

## Comparison Criteria

- **Row counts**: Must match exactly
- **Column names**: Must be equivalent
- **Data values**: Must match EXACTLY (no approximations)

## Present Results

### With Ground Truth

Show:

- Ground truth results (first 10-15 rows)
- Generated results (first 10-15 rows)
- Row count comparison
- Match status: ✅ EXACT MATCH / ❌ FAILED
- Specific differences if any

### Without Ground Truth

Show:

- Generated SQL
- Execution status
- Row count
- Potential issues identified

## ⚠️ Exact Match Requirement

**CRITICAL**: Only accept ✅ EXACT MATCH when values identical.

- "VERY CLOSE" = ❌ FAILED
- "CLOSE" = ❌ FAILED
- Approximate = ❌ FAILED
- "Looks correct by inspection" = ❌ FAILED (must execute!)

**Must execute BOTH SQLs and show first 10-15 rows from BOTH for concrete comparison.**
