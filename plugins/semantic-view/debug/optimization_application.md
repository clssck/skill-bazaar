---
name: Optimization Application
description: Apply optimizations and validate results
parent_skill: semantic-view-debug
---

# Optimization Application

## When to Load

Debug Step 4: User approved optimization plan.

## Task

Apply fixes and validate semantic model. SQL generation with optimized model happens in the validation phase to avoid unnecessary Cortex Analyst calls.

## Apply Optimizations

**⚠️ MANDATORY**: Load [semantic_view_set.md](../reference/semantic_view_set.md) for tool syntax.

For each approved fix from root cause:

1. Load corresponding pattern file for YAML structure (dimension_optimization.md, metric_optimization.md, etc.)
2. Convert to operations array per [semantic_view_set.md](../reference/semantic_view_set.md) and show git-style unified diff of proposed changes with +/- line indicators
3. Prompt user if the diff looks correct
4. Only after explicit approval, execute per [semantic_view_set.md](../reference/semantic_view_set.md)

**Output naming**: Append `_optimized` to input basename.

**Reference**: Only use fields from `example_semantic_view.yaml`. No deprecated fields.

## Validate Semantic Model

Use `reflect_semantic_model` tool.

**If fails**: Analyze error → Fix → Retry. If still fails → Remove entity → Document why.

## Validate Results

### Generate SQL with Optimized Model

Use `snowflake_multi_cortex_analyst` with optimized model (parallel for multiple questions).

### Execute and Compare

Load [sql_comparison.md](../reference/sql_comparison.md) and follow its comparison format.
Load [eval_sql_pair.md](../reference/eval_sql_pair.md) for the SQL comparison tool.
**YOU MUST EXECUTE BOTH SQLs** - This is NOT optional, even if SQL looks correct!

**Compare actual results**: The tool outputs both query results side-by-side. Show first 10-15 rows from BOTH queries in your analysis.

### Validation Checkpoint (DO NOT SKIP - MUST EXECUTE SQLs)

**❌ DO NOT declare optimization successful unless ALL criteria met**:

- ✅ You have **EXECUTED** both generated SQL from optimized model AND ground truth SQL
- ✅ Row counts match EXACTLY
- ✅ Column should match (show comparison table proving this). Ok if generated sql shows up to 3 extra columns if they are reasonable to include.

**If no ground truth SQL**:

- ✅ Generated SQL executes successfully
- ✅ **STOP and ASK**: "Please review these results. Do they match your expectations? Can you provide ground truth SQL to validate?"

### If Validation Fails

**DO NOT** declare success. Instead:

1. Document what differs
2. Repeat root cause analysis workflow in `root_cause_analysis.md`.
3. **⚠️ MANDATORY CHECKPOINT FOR ITERATIVE OPTIMIZATIONS**:
   - After applying the first set of optimizations and validating, if ANY issue remains:
     - STOP immediately
     - Present root cause analysis for remaining issues
     - Wait for explicit user approval before applying additional fixes
   - NEVER chain multiple optimization iterations without user approval between each iteration
   - Each optimization iteration requires separate user approval
4. After explicit approval, apply additional optimizations
5. Re-validate

## Success Criteria

## Output

Optimized semantic view YAML file
