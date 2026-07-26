---
name: optimize-cortex-agent
description: |
   This goes through a workflow to guide AI assistants through optimizing Snowflake Cortex Agents for production readiness through systematic evaluation, improvement, and generalization. The process uses AI reasoning combined with human domain expertise to achieve significant accuracy improvements.
   Use this workflow when:
   - Preparing an agent for production deployment
   - Agent has known accuracy or performance issues
   - Need to validate agent behavior systematically
   - Want to ensure agent generalizes beyond test cases
---

# Optimize Cortex Agent

## Required Access & Tools

- Snowflake connection with Cortex Agents access and permissions to query agent schemas
- Scripts in `../scripts/`: `get_agent_config.py`, `create_or_alter_agent.py`, `test_agent.py`, `agent_events_explorer.py`, `fetch_events_from_event_table.py`, `load_eval_data_from_json.py`, `extract_agent_config.py`
- Always run scripts with `uv`
- Domain expert availability (2-3 sessions, 2-3 hours each)

**Tracking changes:** Use the `agent-system-of-record` skill to track changes.

---

## State Gate (Required)

At each phase transition, read/write `<WORKSPACE_DIR>/state.json` to track progress. This file survives context overflow — if context is lost, the coordinator reads the gate file to resume from the last completed phase.

```json
{
  "agent_fqn": "DATABASE.SCHEMA.AGENT",
  "clone_fqn": null,
  "workspace_dir": "/path/to/workspace",
  "eval_method": null,
  "eval_source": null,
  "current_phase": 1,
  "phases_completed": {
    "1_discovery": { "status": "pending" },
    "2_dataset": { "status": "pending" },
    "3_baseline": { "status": "pending" },
    "4_improvements": { "status": "pending" },
    "5_overfitting": { "status": "pending" },
    "6_generalization": { "status": "pending" }
  }
}
```

**Rules:** Update `current_phase` and `phases_completed` after each phase. Write the file immediately — do not batch updates. On resume, read `state.json` first and skip to the current phase.

---

## The Optimization Process

### Phase 1: Agent Discovery & Workspace Setup

**Goal:** Identify agent, establish workspace, extract configuration.

1. **Discover agent:** Ask user if they have an agent in mind. If not, query `INFORMATION_SCHEMA.CORTEX_AGENTS` to list available agents.
2. **Confirm workspace:** Get fully qualified agent name (`DATABASE.SCHEMA.AGENT`), workspace directory, and production status.
3. **Create workspace:** `mkdir -p "$WORKSPACE_DIR/versions"`
4. **If production agent:** ⚠️ Ask user for clone FQN. Extract config, then create clone via `create_or_alter_agent.py create`. Use clone for all subsequent work.
5. **Create version folder:** `VERSION="v$(date +%Y%m%d-%H%M)"` → `mkdir -p "$VER_DIR/evals"`
6. **Extract config:** Run `get_agent_config.py` → `extract_agent_config.py` to produce `agent_config.json`, `instructions_orchestration.txt`, `tools_summary.json`.
7. **Review with user:** Present instruction size, tool count, agent purpose, known issues.
8. **Initialize:** Create `optimization_log.md` per `agent-system-of-record` skill. Write `state.json`.

**Deliverables:** Workspace created, config extracted, clone created (if prod), optimization log initialized.

⚠️ **Gate:** User confirms agent identity and workspace before proceeding.
**State update:** `1_discovery → passed`

---

### Phase 2: Evaluation Dataset Creation

**Goal:** Ensure 15-20 diverse evaluation questions with expected answers.

**Load:** `references/evaluation-methods.md` — native evaluation workflow via `evaluate-cortex-agent` skill.
**Load:** `references/dataset-creation-guide.md` — full dataset creation workflows.

1. **Prepare evaluation:** Record `eval_method` as `native` in `state.json`.
2. **Check existing dataset:** Ask user if they already have one.
3. **If no dataset:** Use Option A (from production data via Agent Events Explorer) or Option B (from scratch). Follow `dataset-creation-guide.md`.
4. **Validate coverage:** Check tool routing coverage, question diversity, expected answer specificity.
5. **Log dataset location** to `optimization_log.md`.

**Deliverables:** 15-20 evaluation questions, 25% testing tool routing, dataset location logged.

⚠️ **Gate:** User confirms dataset coverage before proceeding.
**State update:** `2_dataset → passed`, record `eval_source` in `state.json`.

---

### Phase 3: Baseline Evaluation

**Goal:** Measure current accuracy and identify failure patterns.

**Load:** `references/best-practices.md` — behavioral guidelines (applies through Phase 6).
**Load:** `references/evaluation-methods.md` — run evaluation using chosen method.
**Load:** `references/failure-analysis-patterns.md` — analyze and categorize failures.

1. **Run baseline evaluation** using Native Snowflake Agent Evaluations (see `evaluation-methods.md`).
2. **Calculate and present accuracy** (correct/partial/incorrect counts).
3. **Analyze each failure:** Determine what went wrong, which tool was called, why it failed.
4. **Discover failure patterns:** Group by actual root cause — do NOT use predefined categories.
5. **Categorize by fix location:** Agent-level (Category A) vs Semantic view (Category B).
6. **Present findings** to user with prioritization recommendation.

**Deliverables:** Baseline accuracy, categorized failure analysis, agent-level vs semantic-view separation.

⚠️ **Gate:** User confirms failure categorization and fix priorities.
**State update:** `3_baseline → passed`

---

### Phase 4: Instruction Improvements

**Goal:** Systematically improve instructions based on failure patterns.

**Load:** `references/failure-analysis-patterns.md` — for semantic view fix workflow.
**Load:** `references/improvement-examples.md` — example improvements and iteration pattern.

1. **If semantic view fixes needed:** Follow Category B workflow in `failure-analysis-patterns.md` — either fix directly (LOAD `semantic-view` skill) or create handoff doc.
2. **For each agent-level failure pattern:** Draft instruction improvements with specific examples.
3. **Iterate with user** on each improvement — explain reasoning, show how it handles failed questions.
4. **Create new version folder** and save updated instructions.
5. **Update agent** via `create_or_alter_agent.py alter`.
6. **Re-evaluate** using Native Snowflake Agent Evaluations (same as Phase 3).
7. **Compare results** — show improvements, regressions, remaining failures.
8. **If accuracy <70%:** Iterate — analyze remaining failures, draft more improvements.

**Deliverables:** Updated instructions, improved accuracy (target >70%), comparison showing improvements.

⚠️ **Gate:** User approves instruction changes before agent update.
**State update:** `4_improvements → passed`

---

### Phase 5: Overfitting Detection

**Goal:** Identify instruction patterns too specific to evaluation questions.

**Load:** `references/overfitting-detection-guide.md` — detection patterns and examples.

1. **Analyze instructions** for evaluation-specific patterns (hardcoded dates, company names, thresholds, result counts, absolute ranges).
2. **For each issue:** Explain the problem, production risk, and needed generalization.
3. **Prioritize:** Critical (will cause prod failures), Medium (might cause issues), Low (minor).
4. **Present analysis** to user for validation.

**Deliverables:** Prioritized overfitting analysis, user confirmation on issues to address.

⚠️ **Gate:** User confirms which overfitting issues to fix.
**State update:** `5_overfitting → passed`

---

### Phase 6: Generalization & Validation

**Goal:** Create production-ready instructions that work beyond evaluation cases.

**Load:** `references/overfitting-detection-guide.md` — generalization patterns and templates.
**Load:** `references/output-files-reference.md` — deployment summary template.

1. **For each overfitting issue:** Create generalized version. Show before/after with rationale.
2. **Present complete generalized instructions** to user for approval.
3. **Create new version folder** and save generalized instructions.
4. **Update agent** with generalized instructions.
5. **Run final evaluation** using Native Snowflake Agent Evaluations.
6. **Three-way comparison:** Baseline → Updated → Generalized. Verify zero regressions.
7. **Create deployment summary** using template in `output-files-reference.md`.

**Deliverables:** Production-ready agent, ≥80% accuracy, zero critical overfitting, deployment summary.

⚠️ **Gate:** User approves for production deployment.
**State update:** `6_generalization → passed`

---

## Reference Documents

| Document | Purpose | Used In |
|----------|---------|---------|
| `references/evaluation-methods.md` | Native Snowflake Agent Evaluation workflow | Phase 2, 3, 4, 6 |
| `references/dataset-creation-guide.md` | Creating eval datasets from prod data or scratch | Phase 2 |
| `references/failure-analysis-patterns.md` | Analyzing failures, categorizing fixes | Phase 3, 4 |
| `references/improvement-examples.md` | Example instruction improvements, iteration | Phase 4 |
| `references/overfitting-detection-guide.md` | Detecting overfitting, generalization patterns | Phase 5, 6 |
| `references/best-practices.md` | AI assistant guidelines for this workflow | All phases |
| `references/output-files-reference.md` | Workspace structure, success metrics | Phase 1, 6 |
