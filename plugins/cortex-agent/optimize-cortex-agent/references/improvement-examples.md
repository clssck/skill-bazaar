# Instruction Improvement Examples

**Purpose:** Concrete examples of how to draft, iterate, and apply instruction improvements for common failure patterns.
**Used by:** Phase 4 (instruction improvements).

---

## Example: Percentage Calculation Pattern

**Failure pattern:** Questions asking for percentages/proportions get absolute numbers instead.

**Suggested instruction section:**
```
## Proportion/Percentage Calculations

When calculating "proportion of X spent on Y" or "percentage":

**For "what percent" questions:**
- Return the percentage value as primary answer
- Include context: "67.4% (1.2M out of 1.8M total credits)"

**For "highest proportion" questions:**
- Query both numerator and denominator separately
- Calculate: (numerator / NULLIF(denominator, 0)) * 100
- Sort by percentage DESC, not absolute values
- Return top results: "1. Acme: 89.3% (500K/560K), 2. Beta: 76.2%"

**Validation:**
- Verify denominator is non-zero
- If percentage >100%, re-examine query (numerator shouldn't exceed denominator)
```

---

## Example: Tool Routing Pattern

**Failure pattern:** Agent routes to incorrect semantic model/tool.

**Suggested instruction section:**
```
## Tool Selection and Routing

Before answering a question, identify which semantic model/tool has the required data.

**Product disambiguation:**
- "Streamlit in Snowflake" vs "Streamlit Open Source" are DIFFERENT products
- "ML Platform" or "Snowflake ML" refers to specific product, NOT all AI/ML
- "AI/ML" includes: Cortex ML, Cortex LLM, Snowflake ML, ML Packages, Copilot
- "Notebooks" is separate from AI/ML categories

**Tool selection rules:**
- For product-specific questions → use product_categories or product-specific tool
- For geographic breakdowns → use product_geo tool
- For feature usage (SIS, Notebooks execution) → use feature_usage tool
- For organizational metadata → use product_owners tool

**When multiple tools could apply:**
- Ask for clarification: "To answer accurately, I need to know: [specific question]"
- Example: "For 'ML usage', do you mean Snowflake ML specifically or all AI/ML products?"

**Tool coordination:**
- Some questions require querying multiple tools
- Query each tool separately, then combine results in your answer
```

---

## Iteration Pattern with User

The key principle: **never accept first draft → iterate on wording → show how it handles the failed question → then update.**

**Example interaction flow:**
```
You: Let me analyze the failures from baseline evaluation.

I found 3 distinct patterns:
1. Percentage Calculation Issues (Q4, Q9, Q11)
2. Account Name Ambiguity (Q7, Q12)  
3. Time Period Misinterpretation (Q1, Q10)

Let's start with #1. All three questions asked for percentages or proportions,
but the agent returned absolute numbers instead.

Looking at Q4: "what percent of snowflake credits were used by accounts with 
Databricks usage?"

Expected: "67.42%" 
Actual: "1.2M credits"

I suggest adding this section to orchestration instructions:
[shows draft]

Does this make sense? Any adjustments needed?

User: Yes, but what if denominator is zero?

You: Good catch! The NULLIF handles division by zero, but we should explain 
what to do. Let me add:
- If denominator is zero, return "Cannot calculate percentage (no baseline data)"

Should I also add a sanity check for very small denominators?

User: Yes, warn if denominator seems unusually low.

You: I'll add:
- If denominator <1000 credits, note: "Warning: Small baseline (only X credits)"

Here's the updated version: [shows complete section]

Does this fully address the percentage calculation failures?

User: Perfect. What about pattern #2?

You: For the account name ambiguity pattern...
[continues through all patterns]
```

---

## Applying Improvements

1. **Draft** instruction section for each failure pattern
2. **Iterate** with user — explain reasoning, show how it handles failed questions
3. **Combine** all improvements with original instructions
4. **Organize** logically (critical rules first)
5. **Create new version folder:**
   ```bash
   VERSION="v$(date +%Y%m%d-%H%M)"
   VER_DIR="$WORKSPACE_DIR/versions/$VERSION"
   mkdir -p "$VER_DIR/evals"
   cp "$PREVIOUS_VER_DIR/instructions_orchestration.txt" "$VER_DIR/instructions_orchestration.txt"
   ```
6. **Update the agent:**

   > ⚠️ **CRITICAL: Never use `--config-file` without `--merge-with` in this workflow.**
   > A bare `--config-file` call replaces the *entire* agent specification with the file's contents.
   > If the file contains only instructions, the agent's `tools` and `tool_resources` will be **silently stripped**, leaving an agent that can no longer execute tools (it will only emit `<tool_call ...>` text).
   > Always use one of the two forms below.

   **6a. Orchestration-only update (preferred when only orchestration changes):**

   `--instructions` is safe by default — it auto-fetches the current spec and merges in the new orchestration text, so `tools`, `tool_resources`, `response`, and other fields are preserved.

   ```bash
   uv run python ../scripts/create_or_alter_agent.py alter \
       --agent-name AGENT_NAME \
       --instructions "$VER_DIR/instructions_orchestration.txt" \
       --database DATABASE --schema SCHEMA --connection CONNECTION_NAME
   ```

   **6b. Multi-field instruction update (orchestration + response, etc.):**

   `--instructions` only updates `orchestration`. To update `response` (or both at once), build a partial `edit_spec.json` containing only the keys you want to change, and **always pass `--merge-with`** so the existing `tools`/`tool_resources` are preserved.

   ```bash
   # Runs in CoCo bash sandbox (Linux) — not executed on the host.
   # Step 1: write a partial spec containing ONLY the instruction fields you are changing.
   cat > "$VER_DIR/edit_spec.json" <<'JSON'
   {
     "instructions": {
       "orchestration": "...new orchestration text...",
       "response": "...new response text..."
     }
   }
   JSON

   # Step 2: snapshot the current full spec to disk (used as the merge base).
   uv run python <SKILL_DIR>/scripts/get_agent_config.py \
       --agent-name AGENT_NAME \
       --database DATABASE --schema SCHEMA --connection CONNECTION_NAME \
       --output "$VER_DIR/current_agent_spec.json"

   # Step 3: alter with --merge-with (REQUIRED). The script deep-merges
   # edit_spec.json into current_agent_spec.json, so existing tools and
   # tool_resources are preserved.
   uv run python <SKILL_DIR>/scripts/create_or_alter_agent.py alter \
       --agent-name AGENT_NAME \
       --config-file "$VER_DIR/edit_spec.json" \
       --merge-with "$VER_DIR/current_agent_spec.json" \
       --database DATABASE --schema SCHEMA --connection CONNECTION_NAME
   ```

   **6c. Verify tools survived (mandatory check after every alter):**

   Always confirm the agent's tools were not stripped before re-evaluating.

   ```bash
   # Re-fetch the live spec and assert the tools array still contains the expected names.
   uv run python <SKILL_DIR>/scripts/get_agent_config.py \
       --agent-name AGENT_NAME \
       --database DATABASE --schema SCHEMA --connection CONNECTION_NAME \
       --output "$VER_DIR/post_alter_spec.json"
   python3 -c "
   import json, sys
   spec = json.load(open('$VER_DIR/post_alter_spec.json'))
   raw = spec.get('agent_spec', spec)
   spec = json.loads(raw) if isinstance(raw, str) else raw
   tools = spec.get('tools') or []
   print(f'Tools after alter: {len(tools)}')
   for t in tools:
       print(f'  - {t.get(\"tool_spec\", {}).get(\"name\")}')
   assert tools, 'ERROR: tools array is empty or missing — alter stripped tools!'
   "
   ```

   If the assertion fails, **stop the workflow**, report to the user, and do not proceed to re-evaluation.
7. **Re-evaluate** using the SAME method as baseline
8. **Compare results** — show before/after, identify improvements and regressions

### Comparison Format
```
Evaluation Comparison:

Baseline:      4/13 (31%)
After Update: 10/13 (77%)

Improvements: Q1, Q4, Q5, Q7, Q9, Q10 (6 fixes)
- Agent instruction fixes: Q5, Q9 (2 fixes)
- Semantic view fixes: Q1, Q4, Q7, Q10 (4 fixes)

Regressions: None
Still Failing: Q2, Q8, Q13
```

If accuracy < 70%, iterate: analyze remaining failures → draft additional improvements → update and re-evaluate.
