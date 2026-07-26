# Failure Analysis Patterns

**Purpose:** Guide for analyzing evaluation failures, discovering patterns, and categorizing fixes.
**Used by:** Phase 3 (baseline evaluation) and Phase 4 (instruction improvements).

---

## Analyzing Each Failure

For each failed question, determine:
- What did the agent return?
- What should it have returned?
- Which tool did it call (if any)?
- What tool type was used? (Check response JSON for `tool_use.type`)
- Why did it fail?

**⚠️ CRITICAL DECISION POINT:**
If the failure involves a `cortex_analyst_text_to_sql` tool AND has SQL issues:
- Check the generated SQL in the tool_result
- If SQL is incorrect (wrong filters, missing columns, incorrect date logic):
  - STOP analyzing this failure at agent level
  - Mark for semantic view optimization
  - Continue analyzing other failures

---

## Discovering Failure Patterns

**❌ Don't:** Use predefined failure categories — forcing issues into predetermined buckets misses the actual root cause.

**✅ Do:** Discover actual patterns from the data.

**Example analysis:**
```
I've analyzed the 9 failures and found 4 distinct patterns:

1. **Percentage vs. Absolute Values (3 failures: Q4, Q9, Q11)**
   - Questions asked for "percentage" or "proportion"
   - Agent returned absolute numbers instead of percentages
   - Root cause: Instructions don't specify to compute percentage

2. **Wrong Tool Selection (2 failures: Q7, Q12)**
   - Agent routed to incorrect semantic model
   - Example: Q7 asked about "Streamlit Open Source" but used "Streamlit in Snowflake" tool
   - Root cause: No guidance on tool disambiguation

3. **Time Period Interpretation (2 failures: Q1, Q10)**
   - Agent misinterpreted relative time periods
   - Root cause: No explicit date range definitions

4. **Missing Data Validation (2 failures: Q5, Q13)**
   - Agent didn't check if date range covered full period
   - Root cause: No mandatory validation checks

Would you like me to generate improvement suggestions for each pattern?
```

### Common Tool Routing Patterns to Look For
- Agent using wrong semantic model/tool for the question
- Agent not asking for clarification when multiple tools could apply
- Agent not coordinating across multiple tools when needed
- Agent confusing similar product names (e.g., "Streamlit in Snowflake" vs "Streamlit Open Source")

---

## Categorizing by Fix Location

After discovering failure patterns, separate into two categories:

### Category A: Agent-Level Fixes (Orchestration Instructions)
- Tool routing issues (wrong tool selected)
- Response formatting issues
- Missing clarification questions
- Incorrect interpretation of user intent
- Multi-tool coordination issues

### Category B: Semantic View Fixes (YAML Model)
- Incorrect SQL generation from Cortex Analyst
- Missing columns or tables in semantic view
- Wrong join relationships
- Incorrect filters or date logic in generated SQL
- VQR (Verified Query Repository) misleading the SQL generation

### Presenting to User

```
Failure Analysis:
- Total Failures: 9
- Agent-level fixes needed: 5 failures (Q2, Q5, Q8, Q11, Q13)
- Semantic view fixes needed: 4 failures (Q1, Q4, Q7, Q10)

For the 4 semantic view issues:
- Q1: Date interpretation ("last week" = calendar week vs rolling 7 days)
- Q4: Missing column for percentage calculation
- Q7: Wrong table joined in semantic view
- Q10: VQR pattern misleading SQL generation

Would you like to:
A) Fix agent-level issues first, then semantic views
B) Fix semantic views first, then agent-level issues  
C) Fix both in parallel (recommended if different people own them)
```

---

## Handling Semantic View Fixes

### If Same Team Owns Both

For each semantic view with failures:

1. Extract semantic view name from agent tool configuration:
   ```bash
   jq '.tools[] | select(.tool_spec.type=="cortex_analyst_text_to_sql")' agent_config.json
   ```

2. **LOAD:** `semantic-view` skill in DEBUG mode

3. Provide: semantic view name, failing questions, expected vs actual SQL

4. Follow semantic-view DEBUG workflow → apply fixes → validate

5. Re-run evaluation on just the semantic view questions:
   ```bash
   uv run python ../scripts/run_evaluation.py \
       --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
       --eval-source "SELECT * FROM eval_table WHERE question_id IN (1, 4, 7, 10)" \
       --output-dir "$VER_DIR/evals/eval_semantic_view_retry" \
       --connection CONNECTION_NAME \
       --judge answeronly
   ```

### If Different Team Owns Semantic Views

Create a handoff document with:
- Semantic view name
- Failing question and expected vs actual SQL
- Root cause analysis
- Suggested fix

Pause optimization until semantic view fixes are deployed, then resume.
