---
name: semantic-view-setup
description: Initial setup for all semantic view workflows. Creates session directory structure and routes to appropriate workflow (creation or optimization).
required_for: All workflows
---

# Setup

## ⚠️ STOP - Prerequisites Check (BLOCKING)

**Before reading ANY of this skill, you MUST have loaded:**

1. ✋ **[reference/semantic_view_get.md](../reference/semantic_view_get.md)**
   - **Verify**: What are the required parameters for semantic_view_get.py? (If you don't know, load it now)
   - **Verify**: What does the `--component` parameter accept? (If you don't know, load it now)

**❌ If you have NOT loaded the file above, STOP and load it NOW.**

**✅ If you HAVE loaded it, state: "Prerequisites verified - proceeding with setup" and continue below.**

---

## ⚠️ Environment Prerequisites Check (BLOCKING)

**Before proceeding to any workflow, verify the execution environment can run skill scripts.**

### Check 1: Verify `uv` is installed

```bash
uv --version
```

`uv --version` works identically on macOS, Linux, and Windows. If the command is not found, treat `uv` as missing.

**If `uv` is not found**: STOP. Tell the user (show the snippet that matches their OS):

> `uv` (Python package manager) is required but not installed. Install it, then restart your shell and retry.
>
> **macOS / Linux:**
> ```bash
> curl -LsSf https://astral.sh/uv/install.sh | sh
> ```
>
> **Windows (PowerShell):**
> ```powershell
> powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
> ```

**DO NOT proceed. DO NOT attempt workarounds with pip or python directly.**

### Check 2: Verify Python packages are available

```bash
uv run --project {SKILL_BASE_DIR} python -c "import snowflake.connector; import yaml; import requests; print('OK')"
```

**If packages are missing**: STOP. Tell the user:

> Required Python packages are missing. Run from the skill directory:
> `uv sync --project {SKILL_BASE_DIR}`

**DO NOT manually pip install packages. `uv` manages dependencies via pyproject.toml.**

### Check 3: Verify Snowflake config exists

Run the cross-platform prereq check (resolves `~` via `Path.home()` so it works on Windows too):

```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/init_session.py check --json
```

The script reports `uv_installed`, `snowflake_config_present`, and `all_passed` as a JSON object. At least one of `~/.snowflake/config.toml` or `~/.snowflake/connections.toml` must exist (the script looks for both).

**If `snowflake_config_present` is `false`**: STOP. Tell the user to configure Snowflake CLI credentials.

**⚠️ ALL THREE CHECKS MUST PASS before continuing to Part 1.**

---

## When to Load

**ALWAYS** load this file as Step 2 from main SKILL.md, regardless of workflow type (creation or optimization).

This setup is the common initialization for ALL semantic view workflows.

## Purpose

This setup will:

1. Capture skill base directory (where scripts are located)
2. Get working directory from user (where to create files)
3. Create session directory with timestamp
4. Route to appropriate workflow (creation or optimization)

## Process

### Part 1: Directory Initialization

#### 1.1: Determine Skill Base Directory

**When the skill loads**, Cortex Code provides the skill base directory. Capture this information:

- Look for: "Base directory for this skill: /path/to/skill" in the skill launch message
- Store as: `SKILL_BASE_DIR` variable

**If base directory is not explicitly provided:**

- Use current working directory when skill was invoked

**Example:**

```
Skill launched with base: /custom-skills/semantic-view-optimization
SKILL_BASE_DIR = /custom-skills/semantic-view-optimization
Scripts located at: {SKILL_BASE_DIR}/scripts/
```

#### 1.2: Get Working Directory

Ask user for working directory where files will be created, or infer from their message:

**Question**: "Where would you like to create the semantic view files? (Press Enter to use the default: $SKILL_BASE_DIR)"

**Inference**: If user's message contains path references like "in /app", "at /workspace", extract and use that path.

**Default**: If user doesn't specify or presses Enter, use `SKILL_BASE_DIR`

**User can provide:**

- Absolute path: `/app`, `/workspace`, `/tmp/semantic_views`, `/home/user/projects`
- Relative path: Will be resolved relative to current directory
- Empty/Enter: Use `SKILL_BASE_DIR`

**Store as**: `BASE_WORKING_DIR` variable

**Example:**

```
User input: /app
BASE_WORKING_DIR = /app
```

#### 1.3: Create Session Directory

Create a timestamped directory for this session via the cross-platform helper. **Do not** hand-roll this with `$(date ...)` and `mkdir -p` — those don't work in native Windows `cmd.exe` / PowerShell.

```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/init_session.py init \
  --base-dir {BASE_WORKING_DIR} --json
```

The script prints a JSON object containing:

- `timestamp` — e.g. `20260218_143022`
- `working_dir` — e.g. `/app/semantic_view_20260218_143022`
- `base_working_dir` — the resolved absolute path of `--base-dir`

**Store as**: `WORKING_DIR = <working_dir from JSON>`

**Why this is important:**

- Each session gets its own isolated directory
- Easy to identify files from specific sessions
- Prevents conflicts between multiple runs
- Consistent structure for both creation and optimization workflows

**Example output:**

```json
{
  "timestamp": "20260218_143022",
  "base_working_dir": "/app",
  "working_dir": "/app/semantic_view_20260218_143022",
  "sub_dir": null
}
```

**Verify directory:**

```bash
uv run --project {SKILL_BASE_DIR} python -c "from pathlib import Path; p=Path('{WORKING_DIR}'); print(p, '->', 'exists' if p.is_dir() else 'MISSING')"
```

**⚠️ IMPORTANT**: All workflows will create subdirectories within `WORKING_DIR`:

- Creation: `{WORKING_DIR}/creation/`
- Optimization: `{WORKING_DIR}/optimization/`

### Part 2: Workflow Routing

#### 2.1: Determine Workflow Type

**Ask user or infer from context: Is this for a NEW semantic view or an EXISTING one?**

**Path A: CREATION (New Semantic View)**

If user wants to CREATE a new semantic view:

- **Action**: Load [creation/SKILL.md](../creation/SKILL.md)
- **Stop here** - do NOT proceed to Part 3

**Path B: OPTIMIZATION (Existing Semantic View)**

If user wants to OPTIMIZE an existing semantic view:

- **Continue to Part 3** below

#### 2.2: Entry paths that skip Part 3

The root [SKILL.md](../SKILL.md) **Core Capabilities** also include **VQR Suggestions**, **Filters & Metrics Suggestions**, and **Tableau Import**. If the user’s goal matches one of those, **load that sub-skill directly** after Part 1 (session dir) — **do not** run Part 3 optimization download unless the workflow needs a local YAML copy (e.g. inline SVA validation — see [sva_validate_verified_queries.md](../reference/sva_validate_verified_queries.md)).

### Part 3: Optimization Setup (ONLY for Path B)

**⚠️ ONLY execute this part if workflow type is OPTIMIZATION.**

**If you are on CREATION path, you should have already loaded creation/SKILL.md and stopped.**

#### 3.1: Semantic View Name

If the user already provided the semantic view name in the conversation (in any format: `DATABASE.SCHEMA.VIEW_NAME`, `database.schema.view_name`, or just `VIEW_NAME` with separate database/schema mentions), then move to step 3.2.

Otherwise, ask.

## Prerequisites

- Fully qualified semantic view name (DATABASE.SCHEMA.VIEW_NAME)
- Snowflake access configured
- Python environment (managed automatically via `uv`)

#### 3.2: Create Optimization Subdirectory

Create the `optimization/` subdirectory for the optimization workflow. Use Python so this works identically on macOS, Linux, and Windows:

```bash
uv run --project {SKILL_BASE_DIR} python -c "from pathlib import Path; Path('{WORKING_DIR}/optimization').mkdir(parents=True, exist_ok=True)"
```

> Tip: if you're creating the session dir and the optimization sub-dir together, you can do both in one call by passing `--sub-dir optimization` to `init_session.py init` in step 1.3.

**Why this is important:**

- All optimization files will be saved to `{WORKING_DIR}/optimization/`
- `WORKING_DIR` is the timestamped session directory from Part 1,
- `optimization/` subdirectory keeps optimization files organized
- Use `{WORKING_DIR}/optimization/` consistently when referencing the directory and do not use global patterns like `*`.
- Consistent structure across all workflows

#### 3.3: Download Semantic Model

Use [download_semantic_view_yaml.py](../scripts/download_semantic_view_yaml.py) to download semantic model YAML to optimization directory.

```bash
cd {WORKING_DIR}/optimization && \
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python {SKILL_BASE_DIR}/scripts/download_semantic_view_yaml.py <SEMANTIC_VIEW_NAME> .
```

**Note**:

- Use `{SKILL_BASE_DIR}/scripts/` for script location (absolute path)
- Run from `{WORKING_DIR}/optimization/` so files are downloaded there

**Use semantic_view_get.py** (from prerequisites) to extract components as needed:

- Tables: `--component tables`
- Verified queries: `--component verified_queries`
- Custom instructions: `--component custom_instructions`
- Module custom instructions: `--component module_custom_instructions`
- Relationships: `--component relationships`

All commands require both `--file` and `--component` arguments.

Handle Python environment issues if they arise (clean environment approach available).

#### 3.4: Present Summary

Present ONLY this summary:

```
✅ Setup Complete
Directory: semantic_view_TIMESTAMP/
Semantic Model: X KB
VQRs: Y queries
Ready to proceed.
```

**🛑 MANDATORY STOP - DO NOT PROCEED FURTHER**

Present mode selection.

## Next Skills

- AUDIT MODE → [audit/SKILL.md](../audit/SKILL.md)
- DEBUG MODE → [debug/SKILL.md](../debug/SKILL.md)
