---
name: cortex-code-guide
description: "Load this skill when users ask about Cortex Code capabilities, CoCo features, available commands, tools, settings, shortcuts, how to use the CLI, what CoCo can do, CLI reference, keyboard shortcuts, slash commands, configuration options, skill management, agent types, MCP setup, special syntax triggers, hook events, or any question about Cortex Code functionality"
---

# Cortex Code (CoCo) — Complete Reference Guide

## Quick Start

Cortex Code (CoCo) is Snowflake's AI coding assistant CLI. Start a session and type naturally — ask questions, run SQL, edit files, or invoke skills.

**Special input syntax:**

| Trigger | Name | Purpose |
|---------|------|---------|
| `/` | Slash command | Invoke a slash command |
| `!` | Bash terminal | Run a bash command directly |
| `@` | File reference | Reference a file in your prompt |
| `@{` | File injection | Inject file contents inline |
| `#` | Table trigger | Reference a Snowflake table |
| `$` | Skill trigger | Invoke a skill by name |
| `%` | Agent trigger | Mention/invoke a Cortex Agent |

---

## Slash Commands

### Session Management

| Command | Aliases | Description |
|---------|---------|-------------|
| `/new` | | Start a new session (optionally with a name) |
| `/resume` | `/r`, `/sessions` | Resume a previous session |
| `/fork` | | Fork into a new session (optionally `/fork <session-id \| artifact-id \| share-url>`) |
| `/rename` | `/name` | Rename the current session |
| `/clear` | `/cls` | Clear screen (optionally keep last N exchanges) |
| `/compact` | | Clear conversation history but keep a summary in context. Optional: `/compact [instructions]` |
| `/rewind` | | Rewind the conversation by N user messages, or open interactive selector |
| `/unrewind` | | Undo the most recent `/rewind` (lost on next message, `/clear`, or another `/rewind`) |
| `/wipe-session` | | Purge session transcript and exit |
| `/quit` | `/q`, `/exit`, `quit`, `exit` | Exit the CLI with session summary |
| `/recap` | | Generate a session recap now |
| `/goal` | | Set or view the goal for a long-running task |
| `/share` | | Share the current conversation via a link |

### SQL & Data

| Command | Aliases | Description |
|---------|---------|-------------|
| `/sql` | | Execute SQL query directly (use `--limit N` to show more rows) |
| `/sql-readonly` | | Toggle the built-in SQL tool between read-only and write modes |
| `/table` | `/csv` | Open interactive table viewer for SQL results or CSV files |
| `/copy-table` | `/cpt` | Copy a table to clipboard (Enter to copy, ↑↓ to cycle tables) |
| `/connections` | `/conn` | Manage Snowflake connections in fullscreen |
| `/workspace` | | Browse and switch the mounted Snowflake workspace |

### Planning & Execution Modes

| Command | Aliases | Description |
|---------|---------|-------------|
| `/plan` | | Enable plan mode (present plan before execution) |
| `/plan-off` | | Disable plan mode |
| `/auto-accept-plan` | | Enable auto-accept plans (auto-approve plan requests) |
| `/auto-accept-plan-off` | | Disable auto-accept plans |
| `/bypass` | | Enable bypass safeguards mode (auto-approve all tool calls) |
| `/bypass-off` | | Disable bypass safeguards mode |
| `/team` | | Enable teams mode (use parallel teammates) |
| `/team-off` | | Disable teams mode |

### Skills, Agents & Plugins

| Command | Aliases | Description |
|---------|---------|-------------|
| `/skill` | `/skills` | Manage skills — view, add, remove, sync. Subcommand: `new` (opens skill-create wizard) |
| `/agents` | | View and manage sub-agents |
| `/swarm` | `/mission-control` | Open swarm mission control with this session |
| `/background-agent` | `/bg` | Launch a background agent to work on a task while you continue chatting |
| `/plugin` | `/plugins` | Manage plugins. Subcommands: `list`, `info` |
| `/reload-plugins` | | Reload plugins, plugin skills, agents, hooks, and MCP servers |
| `/mcp` | | Manage MCP servers |
| `/automation` | `/automations` | Schedule a Cortex Code automation (recurring agent task run) |

### Configuration & Settings

| Command | Aliases | Description |
|---------|---------|-------------|
| `/settings` | `/preferences`, `/prefs` | Open settings page or modify specific settings |
| `/rules` | | View, edit, or create instruction files |
| `/permissions` | | Manage workspace trust and tool permission rules |
| `/hooks` | | View and test configured hooks |
| `/profile` | | Manage profiles — reusable configurations with custom system prompts and settings |
| `/secrets` | `/secret` | Manage secrets |
| `/model` | | Show and select available models |
| `/theme` | `/themes` | Select color theme (dark/light/pro) |
| `/tts` | `/speak` | Toggle text-to-speech output |
| `/voice-setup` | | Set up voice input (STT) and text-to-speech (TTS) |
| `/guardrails` | | Configure session guardrails (restricted SQL scope, and more) |

### Utilities & Navigation

| Command | Aliases | Description |
|---------|---------|-------------|
| `/status` | | Show current configuration |
| `/context` | | View current context window breakdown |
| `/diff` | `/changes`, `/review` | Review git changes in fullscreen (`--staged` or `--cached` for staged changes) |
| `/worktree` | | Manage git worktrees (create, list, switch, delete) |
| `/add-dir` | | Add an additional working directory |
| `/copy` | `/cp` | Copy last response to clipboard as rich text (`--md` for markdown, `--text` for plain text) |
| `/qq` | `/quick`, `/btw` | Quick question — side conversation |
| `/sh` | | Execute shell command directly or enter terminal mode |
| `/ssh` | `/remote` | SSH into a remote server and continue this session there |
| `/port-forward` | `/pf` | Forward a host port to the sandbox VM (requires running sandbox) |
| `/help` | `/h`, `/?` | Open help menu |
| `/docs` | | Open Cortex Code CLI documentation in browser |
| `/shop` | `/store` | Open the Snowflake store in browser |
| `/update` | | Update Cortex Code to the latest version |
| `/feedback` | | Create a feedback bundle for debugging and support |
| `/doctor` | `/diag` | Diagnose Snowflake connection issues |
| `/clear-cache` | | Clear application caches (debug logging, table cache, etc.) |
| `/commands` | `/cmds` | Manage custom commands — view, copy, move between locations |
| `/monitors` | `/monitor` | View and manage running monitors |
| `/index` | | Build or refresh search indexes (tgrep semantic search and/or instant-grep regex search). Use `--rebuild` to force a refresh |
| `/tgrep` | | Enable, disable, or show status of tgrep semantic code search. Subcommands: `on \| off \| status` |
| `/airflow` | | Configure Airflow instances |
| `/self-improve` | | Inspect and run the skill self-improvement loop |
| `/context` | | View current context window breakdown |

### dbt

| Command | Description |
|---------|-------------|
| `/fdbt` | Execute fdbt command for fast DBT project analysis |
| `/lineage` | Show dbt model lineage in fullscreen DAG view |

### Jupyter

| Command | Description |
|---------|-------------|
| `/setup-jupyter` | Set up Jupyter notebook environment with required packages |

### Scheduling

| Command | Aliases | Description |
|---------|---------|-------------|
| `/loop` | `/cron` | Schedule recurring tasks (cron-style scheduling) |

---

## Tools

### File & Code Operations

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `read` | Reads file content with line numbers. Supports text, images (PNG/JPG/GIF/WebP), PDFs, and Jupyter notebooks. Use `offset`/`limit` to paginate. For PDFs, offset/limit are page numbers (0-based). | `file_path` (string, required), `offset` (number), `limit` (number) |
| `write` | Writes content to a file, creating it (and parent dirs) if needed, or overwriting if it exists. | `file_path` (string, required), `content` (string, required) |
| `edit` | Search-and-replace in a file. `old_string` must appear exactly once (or once within `after` scope). | `file_path` (string, required), `old_string` (string, required), `new_string` (string, required), `after` (string) |
| `apply_patch` | Edit files using a structured diff/patch format. Supports add, delete, and update file operations, including renames. | `input` (string, required) |
| `glob` | Find files matching a glob pattern. Returns matching file paths. | `pattern` (string, required), `path` (string) |
| `grep` | Search for a regex pattern in files. Returns matching lines with file paths and line numbers. | `pattern` (string, required), `path` (string), `include` (string), `head_limit` (number) |

### Shell & Process

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `bash` | Execute a bash command and return output. | `command` (string, required), `description` (string), `timeout_ms` (number), `run_in_background` (boolean) |
| `bash_output` | Retrieve output from a running or completed background bash shell started with `run_in_background=true`. | `bash_id` (string, required), `filter` (string), `wait` (boolean), `timeout_ms` (number) |
| `kill_shell` | Kill a running background bash shell by ID. | `shell_id` (string, required) |
| `monitor` | Start a background monitor that streams events from a long-running script. Each stdout line is an event. Use `grep --line-buffered` in pipes. Monitors are host-only; unavailable when cocobox VM sandbox is enabled. | `command` (string, required), `description` (string, required), `timeout_ms` (integer), `persistent` (boolean) |
| `find_custom_python_environment` | Find custom Python environments (UV/Poetry/venv) in a directory. Returns the appropriate command to run Python for each environment. | `working_dir` (string, required) |

### Agents & Tasks

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `task` | Launch a new agent (subprocess) to handle complex tasks autonomously. See **Bundled Agent Types** below. | `subagent_type` (string, required), `description` (string, required), `prompt` (string, required), `name` (string), `run_in_background` (boolean), `resume` (string), `model` (string), `worktree_isolation` (boolean), `team_name` (string) |
| `kill_agent` | Terminate a running background agent by ID. | `agent_id` (string, required) |
| `send_message` | Send a message to another agent or the main conversation. Used in multi-agent workflows. | `recipient` (string, required), `content` (string, required), `summary` (string) |
| `enter_plan_mode` | Request to enter plan mode for complex, risky, or multi-file tasks. Research and plan without making changes, then present via `exit_plan_mode`. | `reason` (string, required) |
| `exit_plan_mode` | Present a plan to the user and exit plan mode, requesting confirmation before execution. | `plan` (string, required), `question_to_clarify_with_user` (string), `team_mode` (boolean) |

### Task Tracking

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `system_todo_write` | Updates the local todo store for UI rendering. | `todos` (array, required) |
| `task_create` | Create a new task to track work. | `subject` (string, required), `description` (string, required), `active_form` (string) |
| `task_get` | Get full details of a specific task by ID. Use `task_list` first to find IDs. | `task_id` (string, required) |
| `task_list` | List all tasks with status, owner, and dependencies. | (none) |
| `task_update` | Update a task's fields: status, subject, description, owner, dependencies. Use status `deleted` to remove. | `task_id` (string, required), `status` (string), `subject` (string), `description` (string), `active_form` (string), `owner` (string), `add_blocks` (array), `add_blocked_by` (array) |
| `task_stats` | Summarize queue status including counts by status/class, stale in-progress leases, and hedge-eligible stragglers. | `team_name` (string), `all_sessions` (boolean), `stale_after_minutes` (integer) |
| `task_next` | Claim the next ready task (scheduler-facing). Returns full task details. | `owner` (string), `task_id` (string), `team_name` (string), `allow_unsafe_claim` (boolean) |
| `task_claim` | Atomically claim the next ready unowned task, or a specific ready task, for a named worker. | `task_id` (string), `owner` (string), `team_name` (string), `allow_unsafe_claim` (boolean) |
| `task_complete` | Mark a leased task as completed through the scheduler. Preferred completion path for shared-pool workers. | `task_id` (string, required), `result` (string) |
| `task_fail` | Report task failure. By default requeues the task; set `requeue=false` to pause instead. | `task_id` (string, required), `error` (string, required), `requeue` (boolean) |
| `task_heartbeat` | Renew the current lease on an in-progress task to prevent requeue during long execution. | `task_id` (string, required), `owner` (string) |

### Team / Multi-Agent

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `team_create` | Create a new team for multi-agent coordination. Returns next_steps, phase_order, roles_by_phase, role_agent_types. | `team_name` (string, required), `description` (string) |
| `team_delete` | Remove the current team and its task directories when team work is complete. | (none) |
| `list_teammates` | List available teammate roles and the phase contract. Filter by phase or list all. | `phase` (string), `include_excluded` (boolean) |
| `spawn_teammate` | Spawn N role-typed pool workers for a team-workflow task. Workers self-schedule by claiming steps. | `role` (string, required), `task_id` (string, required), `count` (integer), `skill_dir` (string) |

### Snowflake — Connections & SQL

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `snowflake_connections_list` | Returns metadata about all available Snowflake connections including the active connection. | (none) |
| `snowflake_connections_set_active` | Switch the active Snowflake connection. Tool handles the persistence prompt automatically — do not ask the user first. | `name` (string, required), `persist_to_config` (boolean) |
| `sql_execute` | Execute SQL against the active connection (Snowflake or Postgres). Supports SELECT, INSERT, UPDATE, DELETE, DDL, and more. Check `semantic_view_search` first for complex analytical queries. | `sql` (string, required), `description` (string, required), `connection` (string), `timeout_seconds` (number), `only_compile` (boolean) |

### Snowflake — Discovery & Search

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `snowflake_object_search` | Semantic search for Snowflake database objects: tables, views, schemas, databases, functions, agents, streamlit apps, external tables, external databases/schemas, BI objects. | `search_query` (string, required), `object_types` (array), `connection` (string), `max_results` (number) |
| `snowflake_table_lookup` | Look up detailed metadata for specific tables: full column lists, join relationships with frequency data, column usage patterns. Use after `snowflake_object_search`. | `schema` (string, required), `table` (string, required), `tables` (array), `connection` (string) |
| `snowflake_product_docs` | Semantic search of Snowflake product documentation. Use `web_fetch` on result URLs for full content. | `search_query` (string, required), `connection` (string), `max_results` (number) |
| `cortex_agent_search` | Search and discover Cortex Agents. Use before complex queries to find agents with domain-specific instructions. Modes: `search_query`, `discover`, `describe_agent`. | `search_query` (string), `discover` (boolean), `describe_agent` (string), `database` (string), `schema` (string), `account` (boolean), `max_results` (number), `shallow` (boolean), `connection` (string) |
| `semantic_view_search` | Search and discover Snowflake Semantic Views. Use before generating complex SQL — semantic views provide curated, verified business definitions. Modes: `search_query`, `discover`, `describe_view`. | `search_query` (string), `discover` (boolean), `describe_view` (string), `database` (string), `schema` (string), `account` (boolean), `max_results` (number), `connection` (string) |
| `snowscope_search` | Search Snowflake data assets using Snowscope. | (none) |

### Snowflake — Cortex Analyst & Artifacts

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `snowflake_multi_cortex_analyst` | Execute Cortex Analyst queries over a semantic model to generate SQL from natural language. Returns generated SQL, explanations, and suggested follow-up questions. | `query` (string, required), `original_query` (string, required), `previous_related_tool_result_id` (string, required), `check_metric_distribution` (string, required), `check_missing_data` (string, required), `has_time_column` (boolean, required), `queried_time_period` (string, required), `semantic_model_file` (string), `semantic_view` (string), `connection` (string), `skip_vqr_retrieval` (boolean) |
| `reflect_semantic_model` | Validate a semantic model YAML file: file existence, YAML syntax, schema validation against Cortex Analyst spec, and Snowflake server-side validation. | `semantic_model_file` (string, required), `target_schema` (string) |
| `snowflake_create_artifact` | Upload files to a Snowflake Workspace. Supports notebooks (`.ipynb`) and generic files. | `artifact_type` (string, required), `artifact_name` (string, required), `local_file_path` (string, required), `remote_location` (string), `overwrite` (boolean), `connection` (string) |

### Notebooks

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `notebook_actions` | Primary tool for all Jupyter notebook operations: setup, execute_cell, insert_cell, edit_cell, delete_cell, read_cell, read_notebook, execute_all, restart_kernel. Maintains kernel state across operations. Always call `setup` first; always `read_notebook` before modifying an existing notebook. Do NOT call multiple `insert_cell` or `delete_cell` in the same response (indices shift). | `action` (string, required), `notebook_path` (string, required), `cell_index` (number), `cell_content` (string), `cell_type` (string), `timeout_seconds` (number), `kernel_name` (string) |
| `notebook_execute` | Execute a Jupyter notebook as a batch run (papermill-style). | `notebook_path` (string, required), `output_path` (string), `timeout_seconds` (number), `allow_errors` (boolean), `kernel_name` (string), `parameters` (object), `working_directory` (string), `additional_packages` (array), `python_version` (string) |

### dbt

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `fdbt` | Fast dbt project explorer — 10–50x faster than Python for models, sources, lineage, and tests. **Always use this first** for any dbt project questions. Supports: `info`, `list`, `lineage`, `impact`, `tests`, `sources`, `columns`, `schema`, `compile`, `macros`. | `command` (string, required), `project_path` (string) |

### Skills

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `skills_list` | List available skills with compact metadata. | `query` (string), `state` (string), `includeArchived` (boolean), `limit` (integer) |
| `skill_view` | View full SKILL.md instructions or a support file for a single skill. | `name` (string, required), `filePath` (string) |
| `skill_manage` | Create, patch, edit, archive, restore, or add support files for agent-created skills. | `action` (string, required), `name` (string, required), `content` (string), `category` (string), `filePath` (string), `fileContent` (string), `oldString` (string), `newString` (string), `replaceAll` (boolean), `absorbedInto` (string) |
| `curator` | Run and inspect the skill Curator lifecycle manager. | `action` (string, required), `skill` (string), `dryRun` (boolean), `mutate` (boolean), `llmReview` (boolean), `sync` (boolean) |
| `tool_search` | Search deferred tools by keyword. Pass space-separated keywords. Supports lexical (default) and regex modes. | `query` (string, required), `max_results` (number), `search_type` (string) |

### Scheduling (Cron)

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `cron_create` | Schedule a prompt at a future time using standard 5-field cron (local timezone). One-shot (`recurring: false`) or recurring (default). Jobs live only in the current session. Tasks auto-expire after 3 days. Max 50 tasks per session. Scheduler adds jitter (up to 10% of period, max 15 min). | `cron` (string, required), `prompt` (string, required), `recurring` (boolean) |
| `cron_delete` | Cancel a scheduled task by its 8-character ID. Use `cron_list` to find IDs. | `task_id` (string, required) |
| `cron_list` | List all active scheduled tasks in the current session: ID, schedule, prompt, next fire time, fire count, expiry. | (none) |

### Data Diff

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `data_diff` | Compare two Snowflake tables and identify row-level differences (added/removed rows). Supports same-database and cross-account diffs. Connection name from `snowflake_connections_list` must be wrapped in angle brackets in the URI: `snowflake://<connection_name>/DB/SCHEMA`. | `command` (string, required) |

### Web

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `web_fetch` | Fetch content from a URL and optionally extract text. | `url` (string, required), `extract_text` (boolean) |
| `web_search` | Search the web using Brave Search. Requires `ENABLE_CORTEX_WEBSEARCH` enabled for your account. | `query` (string, required), `num_results` (number) |

### Secrets & UI

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `request_secret` | Request credentials for a third-party service. Checks secret store and keychain; configures sandbox proxy to inject credentials. Real secrets never enter the sandbox. If not found, guide user to `/secret`. | `service` (string, required), `reason` (string, required) |
| `render_ui` | Render a rich interactive UI in the browser (web UI mode only). Supports: Card, MetricCard, BarChart, LineChart, PieChart, DataTable, SqlBlock, Grid, Stack, Heading, Text, Badge. | `spec` (object, required) |

### Semantic Code Search

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `tgrep` | Semantic and keyword code search over the project. Modes: `semantic` (default), `keyword`, `hybrid`. Index built on first use. Use `reindex=true` after editing files. Results are approximate — verify with grep/read. | `query` (string, required), `mode` (string), `max_results` (integer), `compact` (boolean), `reindex` (boolean), `directory` (string) |

### Programmatic Tool Calling

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `programmatic_tool_calling` | Execute Python that calls tools internally via `call_tool(name, input)` for serial work, or `call_tools([...])` to run N independent tool calls concurrently. Returns results in input order. | `script` (string, required), `timeout_ms` (number) |

---

## Bundled Agent Types

Use with the `task` tool via the `subagent_type` parameter. Users can also define custom agents in `.cortex/agents/` or the cortex agents directory.

| Agent Type | Description |
|------------|-------------|
| `general-purpose` | General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks. Use when searching for a keyword or file and not confident you'll match on the first few tries. |
| `Explore` | Fast codebase exploration agent. Finds files by pattern, searches code for keywords, and answers questions about the codebase. Specify thoroughness: `quick`, `medium`, or `very thorough`. |
| `Plan` | Read-only codebase exploration and implementation planning agent. Explores, identifies critical files, traces code paths, and returns a structured step-by-step plan. Cannot modify files. |
| `search` | Comprehensive codebase, web, and documentation search specialist. |
| `feedback` | Collects structured feedback about the coding session. |
| `dbt-verify` | dbt project verification agent. Use after implementing or fixing a dbt project to validate correctness. |
| `sql-verify` | SQL correctness verification agent. Reviews SQL for cartesian joins, NULL comparison errors, division by zero, fanout from one-to-many joins, and other Snowflake SQL traps. Does not run the query — static analysis only. |
| `curator` | Reviews agent-created skills and recommends or applies safe lifecycle maintenance. |
| `skill-improver` | Saves or updates agent-created skills from what the agent learned across recent sessions. |
| `golang-code-reviewer` | Expert-level code review for Go (Golang) implementations. |
| `data-discovery` | No description. |
| `semantic-view-transform` | Transforms semantic view YAML into SQL-ready markdown documentation with physical table names. Use when working with semantic views to prevent "Object does not exist" errors. |

---

## Settings

### Connections

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `cortexAgentConnectionName` | Inference Connection | connection | | Snowflake connection used for AI/LLM inference calls |
| `sqlConnectionName` | SQL Connection | connection | | Default SQL connection for database queries (falls back to active Snowflake connection if not set) |
| `connections` | Manage Connections | link | | View and manage Snowflake connections |

### Agent Behavior

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `agentMode` | Agent Mode | enum | `standard` | Behavior profile for the CLI. Options: `standard`, `code` |
| `agentMentionMode` | Agent Mention Mode (%) | enum | `cortex_code` | `cortex_code`: inject agent spec into prompt. `snowflake_intelligence`: call Agent API directly (supports MCP servers) |
| `autoAcceptPlans` | Auto Accept Plans | boolean | `false` | Automatically accept plan mode requests without confirmation |
| `cortexAgentEagerMode` | Agent Eager Mode | boolean | `false` | Encourage agent to search for relevant Cortex Agents before analytical queries. Requires `cortexAgentIndexService`. |
| `cortexAgentIndexService` | Agent Index Service | string | | Fully qualified name of the Cortex Search service for the agent index |

### Display

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `diffDisplayMode` | Diff Display Mode | enum | `unified` | How file edits are displayed. Options: `unified` (git-style), `side_by_side` |
| `defaultViewMode` | Default View Mode | enum | `compact` | View mode on start (cycle with Ctrl+O). Options: `compact`, `expanded`, `transcript` |
| `transcriptTruncationLimit` | Exchanges to Display | number | `50` | Max exchanges shown on resume or view mode change (1 exchange = user message + response) |
| `toolGroupingEnabled` | Tool Grouping | boolean | `false` | Collapse consecutive tool calls into compact grouped summaries |
| `alwaysShowContextUsage` | Show Context Usage | boolean | `false` | Always show context usage indicator (by default only appears when ≤30% remains) |
| `contextUsageFormat` | Context Usage Format | enum | `absolute` | Format for context usage indicator. Options: `absolute` (160k/1m), `relative` (84%) |
| `showModelInFooter` | Show Model in Footer | boolean | `false` | Display the active model name in the status footer |
| `showInferenceConnectionWhileAgentWorking` | Show Inference Connection While Agent Working | boolean | `false` | Show the Cortex agent (inference) connection and account in the loading bar while working |
| `titleLocation` | Title Location | enum | `inputBar` | Where to display the session title. Options: `hidden`, `footer`, `inputBar` |
| `theme` | Theme | link | | Select color theme (dark/light/pro) |
| `penguinColors` | CoCo Color | link | | Customize CoCo the penguin |
| `funThinkingWords` | Thinking Word Theme | enum | `penguins` | Themed word pack for the animated thinking indicator. Options: penguins, cooking, fitness, music, science, gardening, space, coffee, woodworking, cats, pirate, mountaineering, dogs, off |

### Session

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `sessionRecap` | Session Recap | boolean | `true` | Automatically generate a brief recap after periods of inactivity. Use `/recap` to trigger manually. |
| `enableMemory` | Memory | boolean | `true` | Remember preferences, rules, and context across sessions |
| `sessionCleanup.enabled` | Enabled | boolean | | Enable automatic cleanup of old session files |
| `sessionCleanup.maxAgeDays` | Max Age | number | | Delete conversation and debug files older than this many days |

### Task Viewer

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `confirmTaskDelete` | Confirm Task Delete | boolean | `true` | Ask for confirmation before deleting a single task (d) in the task viewer |
| `confirmTaskDeleteAll` | Confirm Delete All Tasks | boolean | `true` | Ask for confirmation before deleting all tasks (D) in the task viewer |

### Search

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `tgrepEnabled` | Semantic Search (tgrep) | boolean | `true` | Semantic code search via Snowflake Cortex embeddings. Requires account access to snowflake arctic embeddings model. |

### Timeouts

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `bashDefaultTimeoutMs` | Bash Default Timeout | number | `180000` | Default timeout for bash commands |
| `bashMaxTimeoutMs` | Bash Max Timeout | number | | Maximum timeout for bash commands (caps both default and agent-specified) |
| `jupyterExecuteTimeoutMs` | Jupyter Execution Timeout | number | `600000` | Timeout for Jupyter notebook cell execution |
| `pythonReplMaxTimeoutMs` | Python REPL Max Timeout | number | | Maximum timeout for python_repl execution. Overridden by `COCO_PYTHON_REPL_TIMEOUT_MS` env var. |
| `sqlDefaultTimeoutSeconds` | SQL Max Timeout | number | `180` | Default timeout for Snowflake SQL execution when `timeout_seconds` is not specified |

### Table Cache

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `tableCache.maxCacheSizeBytes` | Max Cache Size | number | `1073741824` | Maximum total cache size in bytes |
| `tableCache.ttlDays` | TTL Days | number | `7` | Time-to-live for cached results in days |
| `tableCache.inlineMaxBytes` | Inline Max Bytes | number | `50000` | Maximum bytes to send inline to agent |

### Updates & System

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `autoUpdate` | Auto Update | boolean | `true` | Automatically update on launch (if disabled, shows notification only) |
| `enableFips` | Enable FIPS Mode | boolean | `false` | Enable FIPS 140 cryptography at startup. Requires a FIPS-capable build. Override per-run with `--enable-fips` / `--no-enable-fips`. |
| `enableDesktopNotifications` | Desktop Notifications | boolean | `false` | Send OS notifications when agent needs your attention |
| `monitorEnabled` | Monitor Tool | boolean | `true` | Stream stdout from long-running background scripts as task notifications. Host-only; unavailable when cocobox VM sandbox is enabled. |
| `mcpWait` | Wait for MCP Servers | boolean | `false` | Wait for all MCP servers to connect before starting task execution |
| `disableCron` | Disable Scheduled Tasks | boolean | `false` | Disable `/loop` command and cron scheduling tools. Also configurable via `COCO_DISABLE_CRON=1`. |

### Plugins & Skills

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `disableBundledSkills` | Disabled Bundled Skills | array | | List of bundled skills to disable |
| `plugins` | Plugin Directories | array | | Paths to plugin directories to load |
| `disabledPlugins` | Disabled Plugins | array | | Plugin names that have been disabled |
| `enabledInstructionPatterns` | Instruction Files | array | | Glob patterns for instruction files to load (case-insensitive) |
| `experimental` | Experimental Features | link | | Toggle experimental features |
| `shellCompletion` | Shell Completion | link | | Automatic shell tab-completion for cortex commands |

### Browser

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `browserHeadless` | Browser Headless Mode | boolean | `false` | Run browser automation without a visible window. Also toggleable via `CORTEX_BROWSER_HEADLESS=1`. |
| `browserProfilePath` | Browser Profile Path | string | | Custom browser profile directory for Playwright. Leave empty for default. |

### Windows

| Key | Label | Type | Default | Description |
|-----|-------|------|---------|-------------|
| `windowsShell` | Windows Shell Executor | enum | `powershell` | Shell used to execute commands on Windows. Options: `powershell`, `cmd`, `bash` (Git Bash/WSL). Ignored on macOS/Linux. |

---

## Keyboard Shortcuts

### Global

| Key | Action |
|-----|--------|
| `Ctrl+P` | Toggle Plan Mode |
| `Ctrl+G` | Toggle Team Mode |
| `Ctrl+O` | Cycle view mode |
| `Shift+Tab` | Cycle Permission Level |
| `Ctrl+C` | Interrupt / cancel |
| `Ctrl+Z` | Suspend |
| `Ctrl+B` | No description |
| `Ctrl+S` | Open subagent picker |
| `Escape` | Set Show Help / close overlays |

### Text Input / Editor

| Key | Action |
|-----|--------|
| `Ctrl+J` | Insert newline |
| `Ctrl+A` | Move to line start |
| `Ctrl+E` | Move to line end |
| `Ctrl+B` | Move left (character) |
| `Ctrl+F` | Move right (character) |
| `Alt+B` | Move left (word) |
| `Alt+F` | Move right (word) |
| `Ctrl+W` | Delete word left |
| `Ctrl+K` | Delete to end of line |
| `Ctrl+U` | No description |
| `Alt+D` / `Ctrl+Delete` | Delete word right |
| `Ctrl+Y` | Yank (paste deleted text) |
| `Alt+U` | Undo |
| `Shift+Alt+U` | Redo |
| `Alt+A` | No description |
| `Alt+R` | No description |
| `Shift+Left/Right/Up/Down` | Extend selection |
| `Shift+Home` / `Shift+End` | Extend selection to line start/end |
| `Home` / `End` | Move to line start/end |
| `Ctrl+Q` | No description |
| `Ctrl+R` | History search |

### Navigation & Viewers

| Key | Action |
|-----|--------|
| `Up` / `Down` | Navigate up/down |
| `Left` / `Right` | Navigate left/right |
| `Tab` / `Shift+Tab` | Cycle tabs/focus |
| `Pageup` / `Pagedown` | Page up/down |
| `Ctrl+Pageup` / `Ctrl+Pagedown` | Page up/down (list navigation) |
| `Alt+T` | Exit fullscreen todo viewer |
| `Ctrl+Alt+Return` | No description (lineage viewer) |
| `Escape` | Exit search / close view / cancel |
| `Return` | Confirm / submit |
| `Backspace` | Go back (session manager) |

### Quick Question

| Key | Action |
|-----|--------|
| `Up` | Open fork (QQ inline view) |
| `Escape` | Set input mode |

---

## MCP (Model Context Protocol)

| Item | Value |
|------|-------|
| Supported transports | `http`, `sse`, `stdio` |
| Tool naming pattern | `mcp__<server>__<tool>` |
| Config file | `~/.snowflake/cortex/mcp.json` |
| CLI command | `cortex mcp` |

**`cortex mcp` subcommands:** `add`, `get`, `list`, `reconnect`, `remove`, `start`

---

## Hook Events

Hooks are shell commands configured to execute in response to lifecycle events.

| Event | Description |
|-------|-------------|
| `PreToolUse` | Fires before a tool is used |
| `PostToolUse` | Fires after a tool is used |
| `PermissionRequest` | Fires when a permission is requested |
| `UserPromptSubmit` | Fires when the user submits a prompt |
| `Stop` | Fires when the agent stops |
| `SubagentStop` | Fires when a subagent stops |
| `Notification` | Fires on notification |
| `SessionStart` | Fires at session start |
| `SessionEnd` | Fires at session end |
| `PreCompact` | Fires before context compaction |
| `Setup` | Fires during setup |

View and test configured hooks with `/hooks`.

---

## Permission Modes

| Mode | Description |
|------|-------------|
| `default` | Standard permission behavior |
| `plan` | Present plan before execution |
| `confirmActions` | Confirm individual tool calls |
| `dontAsk` | No description |
| `bypassPermissions` | Auto-approve all tool calls (Bypass mode) |

**Permission levels:** `Confirm Actions` (default), `Bypass` (auto-approve all)

Cycle permission level with `Shift+Tab`. Toggle bypass with `/bypass` / `/bypass-off`.

---

## Environment Variables & Feature Flags

| Feature | Env Var / Config Key |
|---------|---------------------|
| Code streaming | `CORTEX_CODE_STREAMING` |
| Disable todo tool | `CORTEX_DISABLE_TODO_TOOL` |
| Developer mode (local orchestrator) | `CORTEX_AGENT_USE_LOCAL_ORCHESTRATOR` |
| Enable Cortex Sense | `CORTEX_AGENT_ENABLE_CORTEX_SENSE` |
| Step enforcement | `CTX_STEP_ENFORCEMENT` |
| Enable memory | `CORTEX_ENABLE_MEMORY` |
| Disable cron | `COCO_DISABLE_CRON` |
| Disable routines | `COCO_DISABLE_ROUTINES` |
| Disable browser reminder | `COCO_DISABLE_BROWSER_REMINDER` |
| Enable Snowflake-managed MCP servers | `CORTEX_CODE_ENABLE_SNOWFLAKE_MANAGED_MCP_SERVERS` |
| Subagent model escalation | `CORTEX_SUBAGENT_ENABLE_MODEL_ESCALATION` |
| Subagent escalation without history | `CORTEX_SUBAGENT_ESCALATE_WITHOUT_HISTORY` |
| Browser headless mode | `CORTEX_BROWSER_HEADLESS` |
| Python REPL max timeout | `COCO_PYTHON_REPL_TIMEOUT_MS` |
| SSH (config-based) | `config: ssh` |
| Tool search (config-based) | `config: toolSearch` |
| Apply patch (config-based) | `config: applyPatch` |
| Programmatic tool calling (config-based) | `config: programmaticToolCalling` |
| Tgrep semantic search (config-based) | `config: tgrep` |
| Skill catalog (config-based) | `config: enableSkillCatalog` |
| Cocobox sandbox (config-based) | `config: cocoboxSandbox` |
| Use threads (config-based) | `config: useThreads` |

---

## CLI Subcommands Reference

| Command | Subcommands |
|---------|-------------|
| `cortex acp` | `serve` |
| `cortex agentStudio` | `metrics` |
| `cortex conversations` | `delete`, `list`, `search`, `transcript` |
| `cortex ctx` | `ctxRunner`, `init`, `push`, `remember`, `repo`, `search`, `show`, `step`, `task` |
| `cortex logs` | `errors`, `path`, `query`, `reader`, `shared`, `show`, `tail` |
| `cortex mcp` | `add`, `get`, `list`, `reconnect`, `remove`, `start` |
| `cortex memory` | `drop`, `edit`, `extract`, `init`, `list`, `recall`, `remember`, `runners`, `show` |
| `cortex plugin` | `activate`, `add`, `check`, `deactivate`, `find`, `list`, `publish`, `remove`, `unpublish`, `update`, `validate` |
| `cortex postgres` | `add`, `list`, `remove` |
| `cortex profile` | `add`, `delete`, `list-remote`, `list`, `publish`, `set-default`, `show`, `sync` |
| `cortex skill-catalog` | `install`, `publish`, `remove`, `search` |
| `cortex update` | `download`, `releaseChannel` |
| `cortex workspace` | `cp`, `ls`, `metrics`, `parseSpec`, `rm`, `shared` |
| `cortex worktree` | `cleanup`, `create`, `delete`, `list`, `switch` |
| `cortex developer` | `system-prompt` |

**Top-level CLI commands:** `acp`, `analyst`, `artifact`, `automation`, `automations`, `completion`, `connections`, `conversations`, `ctx`, `curator`, `env`, `logs`, `mcp`, `memory`, `plugin`, `postgres`, `profile`, `reflect`, `search`, `semantic-views`, `skill`, `update`, `versions`, `worktree`

---

## Bundled Skills

CoCo ships with bundled skills that are automatically invoked based on context. Key skills include:

| Skill | Trigger Summary |
|-------|----------------|
| `access-troubleshooter` | Access denied, insufficient privileges, permission errors, role issues, missing grants |
| `ai-data-share` | Creating semantic views for listings, cortex agents for data shares, AI-ready listings |
| `ai-functions-pipeline-builder` | Building document/file pipelines with Cortex AI functions, incremental ingestion pipelines |
| `ai-readiness-score` | AI readiness scoring, semantic view coverage, consumption-ready tables, readiness reports |
| `alert` | Create, alter, suspend, resume, and troubleshoot Snowflake alerts |
| `billing` | Org-level Snowflake billing in dollars/currency, spend trends, contract details |
| `certified-data-product-discovery` | Find certified data products that can answer a user's question and guide their use |
| `certify-object` | Apply, verify, and manage the SNOWFLAKE.CORE.CERTIFICATION_STATUS tag on Snowflake objects |
| `cortex-agent` | **Required for all agent requests**: list, create, edit, delete, debug, chat with Cortex Agents |
| `cortex-ai-function-studio` | Build, evaluate, and optimize custom AI functions; built-in Cortex AI functions |
| `cortex-code-guide` | This guide — CoCo capabilities, commands, tools, settings, shortcuts |
| `cortex-secrets` | Credentials, API keys, tokens, passwords, secret management |
| `cost-intelligence` | Account-level credit usage, budgets, quotas, resource monitors, anomaly detection |
| `data-cleanrooms` | Snowflake Data Clean Rooms: collaborations, templates, activations, RBAC |
| `data-governance` | Masking/row-access/aggregation policies, PII classification, data stewardship |
| `data-quality` | Monitor and enforce data quality using Snowflake DMFs |
| `data-sharing` | Create direct shares, external marketplace listings, debug share failures |
| `declarative-sharing` | Share data products across accounts with versioning; application packages with TYPE=DATA |
| `deploy-to-spcs` | Deploy containerized apps to Snowpark Container Services |
| `developing-with-streamlit-in-snowflake` | Streamlit development with Snowflake, SiS deployment, troubleshooting |
| `document-intelligence` | Extract fields, parse/OCR, classify documents, analyze charts — single file or one-time batch |
| `dynamic-tables` | **Required for all Dynamic Table operations**: create, optimize, monitor, troubleshoot |
| `find-skill-and-plugin` | Discover, install, and update catalog skills and plugins |
| `iceberg` | Use for **ALL** Iceberg table requests in Snowflake. **REQUIRED** entry point for create, catalog integrations, external volumes |
| `lineage` | Table/column lineage, impact analysis, root cause, data provenance |
| `machine-learning` | **Required for all ML/data science tasks**: models, pipelines, feature store, forecasting |
| `marketplace-search` | Search the Snowflake Marketplace for datasets, apps, data shares |
| `migration-guide` | Migrate databases, SQL, stored procedures from non-Snowflake systems |
| `native-app-consumer` | Installing and configuring Native Apps as a consumer |
| `native-app-provider` | **Required for all Native App Framework tasks**: packages, manifests, SPCS containers |
| `recommend-object` | Score and rank candidate Snowflake objects on trust signals to identify the most reliable |
| `semantic-view` | **Required for all semantic view requests**: create, debug, optimize, VQR, Analyst evaluations |
| `skill-development` | Create, audit, refactor, and compile skills for Cortex Code |
| `snowflake-apps` | Build and deploy web applications on Snowflake. Use for ALL app requests: create, scaffold, build, deploy |
| `snowflake-notebooks` | Create and edit Workspace notebooks (`.ipynb`) for Snowflake |
| `snowflake-tasks` | **Required for all Snowflake Task operations**: create, schedule, monitor, troubleshoot |
| `snowpark-python` | **Required for all Snowpark Python requests**: pipelines, UDFs, stored procedures |
| `sql-author` | Write, fix, run, or debug Snowflake SQL |
| `team-workflow` | Multi-phase team orchestration. Load first when user requests teammates or parallel agents. |
| `warehouse` | Warehouse configuration, DDL, performance tuning, sizing |

Use `/skill` or `$<skill-name>` to invoke skills directly.

---

## Tips

- **Run shell commands inline** by prefixing with `!` (e.g., `! git status`) — output lands directly in the conversation.
- **Reference files** in your prompt with `@filename` or inject their contents with `@{filename}`.
- **Reference Snowflake tables** directly in your prompt using `#tablename`.
- **Invoke skills** explicitly with `$skill-name` (e.g., `$sql-author fix this query`).
- **Mention Cortex Agents** using `%` to chat with or invoke them directly.
- **Use `/plan` mode** for complex or risky tasks — CoCo will present a plan for approval before making changes. Toggle with `Ctrl+P`.
- **Use `/team` mode** (or `Ctrl+G`) to enable parallel teammates for large, multi-phase work.
- **Check `semantic_view_search`** before writing complex analytical SQL — semantic views provide curated, verified business definitions.
- **Use `cortex_agent_search`** before complex queries to find domain-specific agents with routing instructions.
- **Search past conversations** with `cortex conversations search "<query>"` and retrieve full transcripts with `cortex conversations transcript <session-id>`.
- **Quick side questions** without disrupting your main session: use `/qq` (or `/btw`).
- **Compact long sessions** with `/compact` to free up context while preserving a summary.
- **Rewind mistakes** with `/rewind` and undo with `/unrewind` (before your next message).
- **Manage profiles** with `/profile` to switch between named configurations with different system prompts and settings.
- **Monitor long-running scripts** with the `monitor` tool — each stdout line becomes a chat notification.
- **Background agents** continue working while you keep chatting; launch with `/bg` and check with the agent output tool.
- **Schedule recurring prompts** with `/loop` (cron-style); manage with `cron_list` and `cron_delete`.
- **Use `fdbt`** (or `/fdbt`) for any dbt project question — it is 10–50x faster than shell-based exploration.
- **Toggle SQL read-only mode** with `/sql-readonly` to prevent accidental writes.
- **Cycle view modes** (compact/expanded/transcript) with `Ctrl+O`.
- **Configure MCP servers** with `cortex mcp add` — tools appear automatically as `mcp__<server>__<tool>`.
