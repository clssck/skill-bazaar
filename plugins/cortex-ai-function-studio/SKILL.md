---
name: cortex-ai-function-studio
description: "Create, evaluate, and optimize custom AI functions using Snowflake Cortex AI Complete. Also helps users apply built-in Cortex AI functions (AI_CLASSIFY, AI_EXTRACT, AI_FILTER, AI_COMPLETE, AI_SENTIMENT, AI_SUMMARIZE_AGG, AI_AGG, AI_TRANSLATE, AI_EMBED, AI_PARSE_DOCUMENT, AI_REDACT, AI_TRANSCRIBE, AI_SIMILARITY) and onboard research-preview bring-your-own-model SPCS services. Use when: building LLM-powered functions, evaluating AI function performance, tuning prompts, selecting models, checking async job status, onboarding BYOM/SPCS model inference, classifying content, extracting from text, filtering rows by condition, summarizing, sentiment analysis, analyzing unstructured data with AI, exploring AI function options, using cortex AI functions. Triggers: ai function builder, custom ai function, user defined ai function, build my own llm function, evaluate ai function, tune ai function, optimize ai function, BYOM, bring your own model, model service, SPCS inference, Hugging Face model, demo ai function, resume ai function job, image classification, document analysis, multimodal ai function, AI_CLASSIFY, AI_EXTRACT, AI_FILTER, AI_COMPLETE, AI_SENTIMENT, AI_SUMMARIZE_AGG, AI_TRANSLATE, AI_EMBED, AI_PARSE_DOCUMENT, AI_REDACT, AI_SIMILARITY, classify text, extract from text, filter rows, summarize text, analyze data with AI, explore AI functions, unstructured data, what AI functions, analyze my data, cortex function, which AI function, built-in AI function."
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Cortex AI Function Studio

**Skill Version:** 1.0.0

Build, evaluate, and optimize AI functions powered by Snowflake Cortex AI Complete.

## When to Load

Load when user wants to work with AI functions — either built-in Cortex AI functions or custom AI function workflows: "custom ai function", "build llm function", "evaluate ai function", "optimize prompt", "tune ai function", "AI_CLASSIFY", "AI_EXTRACT", "classify", "extract from text", "which AI function", "analyze data with AI", "explore AI functions", "unstructured data analysis".

**If the user's message already contains a clear intent** (e.g., "create a custom function", "evaluate my function", "check status", names a specific function like AI_CLASSIFY, or asks which built-in/AI functions they can use), skip this welcome and go directly to Step 1.

**If the user enters with no specific request** (bare `/cortex-ai-function-studio`, or generic prompt without a clear workflow), render the following message **VERBATIM** — do NOT paraphrase, shorten, or omit sections. Then WAIT for the user to choose. Do NOT skip ahead to prerequisites or assume CREATE:
```
Welcome to the Cortex AI Function Studio — your one-stop shop for AI-powered analytics on unstructured data in Snowflake.

I can help you work with Snowflake's AI functions — whether you want to use a **built-in** function (AI_CLASSIFY, AI_EXTRACT, AI_FILTER, AI_TRANSLATE, etc.) for immediate results, build a **custom** AI function tailored to your domain, or onboard a research-preview Bring your own Model/SPCS model service.

For custom functions, the intended workflow is create → evaluate → optimize. During creation, you choose how to build: Direct (simple AI_COMPLETE call) or [research preview] Agent Research (I research and propose approaches with SQL pre/post-processing — you can also specify your own strategy). After building, evaluate against labeled data, then optimize with automated function body optimization and model selection.
If you're new to custom functions, start with a demo to see a worked example end-to-end.

What would you like to do?

1. Create — Build a new Custom AI Function (start here if you haven’t created one before)
2. Evaluate — Evaluate an existing Custom AI Function's performance
3. Optimize — Tune prompts and compare models for an existing Custom AI Function for better cost-quality tradeoff
4. Demo — Interactive walkthrough with example use cases of custom AI Function
5. Check Status — Check on an async evaluation or optimization job on a Custom AI Function
6. Built-in AI Functions — Use a native Snowflake built-in AI Function (no setup, immediate SQL)
**Note:** Evaluate and Optimize only work with Custom AI Functions today. They do not apply to built-in AI Functions yet.

Pick a number or describe what you're working on.
```

## Agent Execution Rules

**After a `⚠️ STOP` point is cleared by the user, execute all subsequent tool calls (stored procedure calls, SQL, uv scripts) WITHOUT re-asking for confirmation until the next `⚠️ STOP` point.** The skill-level confirmation IS the authorization to proceed.

Do NOT:
- Ask "shall I proceed?" immediately before running a command the user just approved
- Ask "OK to run this SQL?" after the user confirmed the evaluation/optimization settings
- Re-confirm tool calls that are direct consequences of an already-approved action
- Ask the user to choose between sync and async execution — default to sync
- Use the `SNOWFLAKE.CORTEX.*` namespace for built-in AI functions — it is **deprecated**. Always use `AI_CLASSIFY`, `AI_EXTRACT`, `AI_SENTIMENT`, `AI_TRANSLATE`, `AI_COMPLETE`, etc. directly (no prefix). If a user references `SNOWFLAKE.CORTEX.CLASSIFY(...)` or similar, correct them to the `AI_*` equivalent.

These rules apply to all sub-skills (create, evaluate, optimize, Bring your own Model, demos).

### Snowsight Environment Rules

**If `environment == snowsight`** (detected in Step 0 prerequisites), these rules apply to ALL sub-skills:

1. **Use stored procedures or documented SQL, not Python scripts.** Execute `CALL SNOWFLAKE.CORTEX.<procedure>(...)` or Bring your own Model SQL DDL/session statements via the `execute_sql` tool. Do NOT run `uv run`, `!python`, or any Python scripts, except for the Bring your own Model notebook-based Model Registry import fallback explicitly documented in `byom/SKILL.md` Step 4 after `SYSTEM$IMPORT_MODEL` fails. Each sub-skill's `**If environment == snowsight:**` branch provides the exact CALL syntax.

2. **Execute stored procedure CALLs via `execute_sql`, not in notebook cells.** The `execute_sql` tool runs SQL in the agent's own execution context. Notebooks are for display only (results, charts, Try It examples), except for the Bring your own Model notebook-based Model Registry import fallback explicitly documented in `byom/SKILL.md` Step 4 after `SYSTEM$IMPORT_MODEL` fails.

3. **Always set database/schema context before CALL statements.** The `execute_sql` session may not have a current database/schema. Prepend `USE {database}.{schema};` before every `CALL SNOWFLAKE.CORTEX.<procedure>(...)` to avoid `Cannot perform CREATE ... This session does not have a current database` errors.

4. **Create and use a notebook for visual output.** Load `references/snowsight/core.md` when entering any sub-skill workflow (loaded once at prerequisites time). Per-workflow notebook recipes are in `references/snowsight/{create,evaluate,optimize,synthetic_data,custom_metrics}.md`. The notebook is required for example calls (Create), evaluation results (Evaluate), optimization charts (Optimize), and data previews (Synthetic Data). Do NOT complete workflows with chat-only output.

5. **Do NOT write to existing `.sql` files or Snowsight SQL worksheets.** Always create a `.ipynb` notebook file for the function.

6. **Do NOT query internal experiment stage files.** Never access `candidates.json.gz`, `gepa_state.bin.gz`, `run_dir/`, or other internal artifacts via `snow://experiment/...` paths for retrieving function bodies or optimization state. Use ONLY `SHOW RUN METRICS` and `SHOW RUN PARAMETERS` to retrieve optimization/evaluation results. SnowURL paths are only valid for per-row eval detail files (`seed_eval_detail.json`, `best_eval_detail.json`).

7. **Procedure names are EXACT — do NOT hallucinate alternatives.** The only valid CAIFS stored procedures are:
   - `SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION` (9 positional params) — do NOT use `CREATE FUNCTION ... LANGUAGE CORTEX_AI` DDL
   - `SNOWFLAKE.CORTEX.EVALUATE_AI_FUNCTION` (12 positional params) — do NOT use `AI_FUNC_EVALUATE` or named `=>` params
   - `SNOWFLAKE.CORTEX.OPTIMIZE_AI_FUNCTION` (18 positional params; inside a Task for async, direct CALL for sync/demo) — do NOT use `OBJECT_CONSTRUCT(...)` single-param syntax

	   All parameters are **positional**. Never use named parameters (`param_name => value`). You MUST read the sub-skill file to get the exact parameter order — do NOT guess from training data. Bring your own Model uses documented SQL object/service operations and `AI_COMPLETE('<service_name>', ...)`; do not invent Bring your own Model-specific `SNOWFLAKE.CORTEX.*` procedures.

**Handling "Object already exists" errors:** All `CREATE` statements (FUNCTION, TABLE, VIEW, STAGE) use plain `CREATE` (not `CREATE OR REPLACE`). If any `CREATE` fails with `SQL compilation error: Object '{name}' already exists`, prompt the user:
```
That object name already exists. Would you like to:
1. **Choose a different name** — e.g., {OBJECT_NAME}_{YYYYMMDD_HHMMSS} to avoid clashes
2. **Drop and recreate** — Drop the existing object first, then create the new one
```
If option 1, suggest a timestamped variant and re-run. If option 2, run the appropriate `DROP ... IF EXISTS` then retry.

## Workflow

### Step 0: Check Prerequisites

**⚠️ STOP**: Before proceeding, verify all prerequisites by loading `references/prerequisites.md`. This checks the Snowflake connection, tool installation, collects the target database/schema, and verifies the user's role has the necessary privileges.

**Snowsight environments**: `prerequisites.md` will mandate loading `references/snowsight/core.md` next — read it before any `write`/`notebook_action` call to avoid silent kernel timeouts and invalid cell payloads.

If any prerequisites or privileges are missing, follow the instructions in the prerequisites file. Do not proceed until all checks pass.

### Step 1: Detect Intent

| Intent | Triggers | Route |
|--------|----------|-------|
| CREATE | "create", "build", "new" + custom/ai/llm function | `create/SKILL.md` |
| EVALUATE | "evaluate", "test", "measure", "score" | `evaluate/SKILL.md` |
| OPTIMIZE | "optimize", "tune", "improve" | `optimize/SKILL.md` |
| BYOM | "BYOM", "bring your own model", "model service", "SPCS inference", "Hugging Face model" | `byom/SKILL.md` |
| DEMO | "demo", "example", "walkthrough", "show me", "how does this work" | `demos/SKILL.md` |
| CHECK_STATUS | "check status", "run_id", "ai_func_eval_", "ai_func_opt_", "is my job done", "resume", "pick up" | `references/async_status.md` |
| BUILTIN_FUNCTION | explicit function name (AI_CLASSIFY, AI_EXTRACT, etc.), "use built-in", "which AI function" | `built-in-ai-functions/SKILL.md` |
| EXPLORE | task-oriented request (classify, extract, filter, summarize, sentiment), "analyze data with AI", "explore AI functions", "unstructured data", generic data analysis — without explicit function name or studio keyword | See Explore below |

**Routing priority (highest to lowest):**
1. **CREATE / EVALUATE / OPTIMIZE / DEMO / CHECK_STATUS** — If the user explicitly mentions these workflows (e.g., "create a custom function", "evaluate my function", "optimize", "demo"), route there. These always win.
2. **BUILTIN_FUNCTION** — If the user names a specific built-in function (AI_CLASSIFY, AI_EXTRACT, etc.) or says "use built-in" / "which AI function", route there. Only override with CREATE if the user also explicitly says "custom function", "my own", or expresses accuracy dissatisfaction.
3. **EXPLORE** — Fallback for task-oriented requests ("classify my tickets", "summarize feedback") or generic discovery ("analyze data with AI") that don't match the above.

EXPLORE never takes priority over an explicit workflow or function request. When no clear intent at all, show the options menu from "When to Load" and WAIT.

### Step 2: Route

**⚠️ MANDATORY**: You MUST read the sub-skill file before responding. The sub-skill contains the actual command syntax, parameter formats, and execution details. Do NOT generate commands, SQL, or CLI invocations from memory — always read the sub-skill first. **If you skip this read, you WILL produce hallucinated procedure names and incorrect parameter signatures that do not exist in Snowflake.**

**If CREATE:** Read `create/SKILL.md`. (In Snowsight, deployment uses `CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(...)` with **9 positional params**. Do NOT use raw `CREATE FUNCTION` DDL or `LANGUAGE CORTEX_AI` — these are wrong. `create/SKILL.md` Step 9 will direct you to read `references/snowsight/create.md` for the exact template.)

**If EVALUATE:** Read `evaluate/SKILL.md` before responding. (In Snowsight, runs via `CALL SNOWFLAKE.CORTEX.EVALUATE_AI_FUNCTION(...)` with **12 positional params**. Do NOT use `AI_FUNC_EVALUATE`, `AI_FUNCTION_EVALUATE`, or named `=>` parameters — these do not exist.)

**If OPTIMIZE:** Read `optimize/SKILL.md` before responding. (In Snowsight, runs via `CALL SNOWFLAKE.CORTEX.OPTIMIZE_AI_FUNCTION(...)` with **18 positional params**. For `budget == demo`, call directly (sync); otherwise wrap in a `CREATE TASK` (async). Do NOT use `OBJECT_CONSTRUCT(...)` single-param syntax or named parameters — these do not exist.)

**If BYOM:** Read `byom/SKILL.md` before responding. Bring your own Model is a research-preview onboarding path layered into model selection and optimization: inspect GPU compute pools, shortlist verified Hugging Face models, import/deploy the selected model to Snowflake Model Registry/SPCS if needed, then expose it through `AI_COMPLETE('<db>.<schema>.<service>', ...)`. Do NOT fabricate unavailable system functions, model registries, image names, or service specs; use verified references and ask for missing account-specific values.

**If DEMO:** Read `demos/SKILL.md` before responding.

**If CHECK_STATUS:** Read `references/async_status.md` with the run_id from the user's message (if provided).

**If BUILTIN_FUNCTION:** Read `built-in-ai-functions/SKILL.md` before responding. The user wants to use a specific built-in function — help them directly.

**If EXPLORE:** Follow the explore logic below to present options.

**If unclear**, display the options menu from "When to Load" and wait for user choice.

### Explore Logic

When the user describes a task (e.g., "classify support tickets"), wants to explore AI function options (e.g., "analyze my data with AI"), or arrives from the UI landing page:

0. **Run a quick Cortex-access check first — this is your FIRST action, before writing any recommendation.** Do not skip it and do not answer from the welcome/recommendation text until it has returned. A single representative `EXPLAIN_PRIVILEGES` call is enough here (no need for the full per-function sweep): `SELECT EXPLAIN_PRIVILEGES(statement => $$SELECT AI_CLASSIFY('x',['a','b'])$$, missing_only => true);`. This is the **only** query permitted in Explore. It is best-effort: if it errors (`EXPLAIN_PRIVILEGES` unavailable, the query fails), skip it silently and assume access. If it returns `{"authorized": true}` proceed; if it comes back denied, say the role lacks Cortex AI access and give the remediation grant from `references/access_control.md` before recommending a path.
1. **Understand the use case.** If unclear, ask what data they have and what they want to accomplish.
2. **Check if custom is even applicable.** Custom AI functions are built on AI_COMPLETE and do NOT support embeddings (AI_EMBED), vector similarity (AI_SIMILARITY), aggregation (AI_SUMMARIZE_AGG, AI_AGG), transcription (AI_TRANSCRIBE), or document parsing (AI_PARSE_DOCUMENT). If the task maps to one of these, tell the user a built-in function handles it and route to BUILTIN_FUNCTION — custom is not an alternative.
3. **Recommend a path and stop.** This is a single, immediate **text-only reply** — apart from the access check in step 0, do NOT call any tools, run searches, query the database, inspect the schema/data, load sub-skills, or spawn research/agents on this turn. Base the recommendation only on what the user already said. Your response MUST be short (3-5 sentences max). Do NOT exhaustively list function names, produce tables of functions, or generate SQL. First present the two options as a list:
   - Built-in AI functions: no setup, immediate SQL, handles common patterns
   - Custom AI functions: higher accuracy on domain-specific tasks, control over cost/quality (model selection, prompt optimization)

   Then, as a **separate block below the list** (not a list item), add a line that literally begins with `Recommendation:` and, in 1–2 sentences, states which path you recommend and why — the signal is complexity, not task type, judged purely from the user's wording (do not investigate to assess it). If the user mentions rules, policies, multi-step logic, domain-specific criteria, or accuracy requirements, say "Recommendation: I'd start with a custom AI function" and note built-in as a simpler fallback; otherwise say "Recommendation: I'd start with [built-in function]" and note custom as a next step for higher accuracy. The recommendation is always a **soft suggestion, never a decision** — phrase it as a suggestion ("I'd suggest", "you might start with"), never as a directive or an assumption that they'll take it. The user stays in charge: close by asking which path they'd like to proceed with, making clear they can pick either regardless of the recommendation.
4. **Wait for the user to choose.** Do NOT continue until they respond. Do NOT load sub-skills, generate SQL, or elaborate further.

After the user picks, route to BUILTIN_FUNCTION or CREATE as appropriate.

## Capabilities

- **Create**: Two modes — Direct (simple AI_COMPLETE) or [research preview] Agent Research (research + propose SQL UDF structures, with option to specify your own)
- **Evaluate**: Measure with pre-built or custom metrics via SQL
- **Optimize**: Improve functions using function body optimization (modifies prompts, model references, and SQL pre/post-processing) and perform cost/quality model comparison. Pass ALL models in a single call — the optimizer runs them concurrently. Do NOT make separate calls per model.
- **Bring your own Model**: Research-preview onboarding for task-specific open-source/Hugging Face models served through Snowpark Container Services and compared on the CAIFS cost/quality Pareto frontier.
- **Demo**: Interactive walkthroughs with example use cases
- **Data Preparation**: Prepare train/test data (`references/data_preparation.md`)
- **Synthetic Data**: Generate data for evaluation and optimization (`synthetic-data/SKILL.md`)
- **Pseudo Labels**: Label input-only tables using strong-model inference and reuse for evaluate/optimize (`synthetic-data/SKILL.md`)

## Data Suggestions

| Workflow | Recommended Rows |
|----------|------------------|
| Evaluate | 20–50 rows       |
| Optimize | 20–50 rows       |

> These sizes are enough for fast iteration. Larger datasets (200+ rows) improve statistical signal but are not required to get started.

## Stopping Points

- ✋ Step 0: After prerequisite check fails
- ✋ Step 1-2: If intent unclear, ask user to select workflow

Each sub-skill has its own stopping points documented within.

## Output

Depends on workflow selected:
- **Create**: AI function created in Snowflake via stored procedure
- **Evaluate**: Performance score and detailed results table
- **Optimize**: Optimized function with improved performance
- **Demo**: Completed walkthrough with demo objects (cleanable)
