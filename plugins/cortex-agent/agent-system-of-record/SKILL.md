---
name: agent-system-of-record
description: Establish a consistent protocol for tracking agent optimization work by organizing per-agent workspaces, versioned configuration snapshots, evaluation outputs, and a running optimization log.
---

# System of Record for Agent Optimization

Create and maintain a clear, auditable record of all optimization work across agents. This skill standardizes folder structure, versioning, and logging so changes are traceable and reproducible.

**When to use:** Before optimizing, evaluating, or modifying any Cortex Agent (e.g., during `optimize-cortex-agent` or `debug-single-query-for-cortex-agent` workflows).

> ⚠️ **Critical:** Never modify production agents directly. Always create and use a safe clone for experimentation.

## Directory Structure

Workspace can be any directory. Default: `<current_dir>/<AGENT_FQN_WITH_UNDERSCORES>` (e.g., `SNOWFLAKE_INTELLIGENCE.AGENTS.AGENT_NAME` → `SNOWFLAKE_INTELLIGENCE_AGENTS_AGENT_NAME`).

```
<WORKSPACE_DIR>/
├── optimization_log.md                     # Running log (update continuously)
├── versions/
│   ├── vYYYYMMDD-HHMM/                     # One folder per version
│   │   ├── agent_config.json               # Full config snapshot
│   │   ├── instructions_orchestration.txt  # Instructions at this version
│   │   ├── tools_summary.txt               # Tool inventory (optional)
│   │   ├── change_manifest.md              # What changed in this version
│   │   └── evals/                          # Evaluation runs
│   │       ├── eval_<name>/
│   │       │   ├── evaluation_summary.json
│   │       │   ├── q01_response.json ...
│   │       │   └── notes.md                # Optional
│   │       └── ...
│   └── ...
└── README.md                               # Optional overview
```

## Setup Steps

**1. Confirm agent details:**
- Fully qualified agent name (`DATABASE.SCHEMA.AGENT`)
- Workspace directory (default: current dir + FQN with underscores)
- Is this production? If yes, ask user for the **fully qualified clone name** (`DATABASE.SCHEMA.CLONE_AGENT_NAME`) where they want the clone created.

**2. Create workspace and version directory:**

Use [`init_agent_workspace.py`](../scripts/init_agent_workspace.py) — it builds the FQN-with-underscores directory name, creates `versions/<vYYYYMMDD-HHMM>/evals/`, seeds `metadata.yaml` and `optimization_log.md`, and emits all paths as JSON. **Do not** hand-roll this with shell — the script is the cross-platform (macOS / Linux / Windows) source of truth.

```bash
uv run --project <SKILL_BASE_DIR> python <SKILL_BASE_DIR>/scripts/init_agent_workspace.py \
  --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --base-dir <WORKSPACE_PARENT_DIR> --json
```

Capture the JSON output. The keys you'll reuse below: `workspace_dir`, `version_dir`, `evals_dir`, `agent_config_file`, `optimization_log_file`. **Re-use the same `version_dir` from this single invocation for steps 3, 4, and 6 — do not re-run init for each step.**

**3. For production agents, create clone:**

⚠️ **Ask the user:** "What fully qualified name would you like for the clone? (e.g., `DATABASE.SCHEMA.CLONE_NAME`)"

Using `version_dir` and `evals_dir` from step 2's JSON output:

```bash
uv run --project <SKILL_BASE_DIR> python <SKILL_BASE_DIR>/scripts/get_agent_config.py \
  --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION_NAME --output <version_dir>/full_agent_spec.json

uv run --project <SKILL_BASE_DIR> python <SKILL_BASE_DIR>/scripts/create_or_alter_agent.py create \
  --agent-name CLONE_AGENT_NAME --config-file <version_dir>/full_agent_spec.json \
  --database CLONE_DATABASE --schema CLONE_SCHEMA --role ROLE_NAME --connection CONNECTION_NAME
```

Use the clone's FQN (`CLONE_DATABASE.CLONE_SCHEMA.CLONE_AGENT_NAME`) for all subsequent operations.

**4. Snapshot the agent config into the version folder:**

```bash
uv run --project <SKILL_BASE_DIR> python <SKILL_BASE_DIR>/scripts/get_agent_config.py \
  --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION_NAME --output <agent_config_file>
```

`<agent_config_file>` is the value from step 2's JSON (e.g. `<version_dir>/agent_config.json`).

**5. Initialize optimization log:**
Step 2 already creates `<workspace_dir>/optimization_log.md` from the template below if it doesn't exist. If you need to append a new entry, edit it directly with the template format shown below.

**6. Run evaluations:**
```bash
uv run --project <SKILL_BASE_DIR> python <SKILL_BASE_DIR>/scripts/run_evaluation.py \
  --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --eval-source database.schema.eval_table --output-dir <evals_dir>/eval_baseline \
  --connection CONNECTION_NAME --judge answeronly
```
> **Important:** Update `optimization_log.md` after every evaluation run with the results, metrics, and observations.

**7. When modifying agent:**
- **For instruction-only changes:**
  - Edit `<version_dir>/instructions_orchestration.txt`
  - Deploy: `uv run --project <SKILL_BASE_DIR> python <SKILL_BASE_DIR>/scripts/create_or_alter_agent.py alter --agent-name AGENT_NAME --instructions <version_dir>/instructions_orchestration.txt --database DATABASE --schema SCHEMA --connection CONNECTION_NAME`
- **For all other changes (models, tools, orchestration, etc.):**
  - Edit `<version_dir>/agent_config.json` or create `<version_dir>/full_agent_spec.json`
  - Deploy: `uv run --project <SKILL_BASE_DIR> python <SKILL_BASE_DIR>/scripts/create_or_alter_agent.py alter --agent-name AGENT_NAME --config-file <version_dir>/full_agent_spec.json --database DATABASE --schema SCHEMA --connection CONNECTION_NAME`
- Update `optimization_log.md`

## optimization_log.md Template

```markdown
# Optimization Log

## Agent details
- Fully qualified agent name: <DATABASE.SCHEMA.AGENT>
- Clone FQN (if production): <CLONE_DATABASE.CLONE_SCHEMA.CLONE_AGENT_NAME>
- Owner / stakeholders: <names>
- Purpose / domain: <short description>
- Current status: <draft | staging | production>

## Evaluation dataset
- Location: <local path or DATABASE.SCHEMA.TABLE/VIEW>
- Coverage: <question count, categories>

## Agent versions
- <vYYYYMMDD-HHMM>: <short title> — <summary>

## Optimization details
### Entry: <YYYY-MM-DD HH:MM>
- Version: <vYYYYMMDD-HHMM>
- Goal: <what we intended to improve>
- Changes made: <list>
- Rationale: <why>
- Eval: <path, metrics>
- Result: <observations>
- Next steps: <follow-ups>
```

## Guidelines

- **Production agents:** NEVER modify directly. Always create and work with a clone.
- Create new `versions/<ver>/` before each instruction change.
- Store all evaluation outputs in `versions/<ver>/evals/`.
- Update `optimization_log.md` after every evaluation run and for each change.
