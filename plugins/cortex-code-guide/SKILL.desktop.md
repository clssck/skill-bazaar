---
name: cortex-code-guide
description: "what is cortex code desktop, cortex code guide, introduce coco, getting started with cortex code, how do I use cortex code desktop, what can cortex code do, coco features, cortex code ide help, cortex code agent, cortex code shortcuts, cortex code commands, cortex code skills, cortex code settings, cortex code mcp, cortex code views, cortex code panels, cortex code modes, cortex code tools"
---

# Cortex Code Desktop — Reference Guide

## What is Cortex Code Desktop?

**Cortex Code** (application name: `coco`) is Snowflake's AI coding assistant IDE — a graphical desktop application built on VS Code. You interact with it through the GUI: the agent chat panel, editor, side panels, command palette, and toolbar controls. The default color theme is **Cortex Code Dark**.

The core of the experience is the **agent chat panel**, where you converse with the AI, invoke skills, attach context, and review or approve proposed changes.

### Quick Start

1. Sign in via **Sign in to Snowflake** (command palette or welcome screen).
2. Open the agent chat panel and type your request.
3. Use the **mode picker** in the chat toolbar to choose Agent or Plan mode.
4. Use the **approval picker** to control how tool calls are approved.
5. Invoke skills with `/<skill-name>` in the chat input.

---

## Agent Modes

The chat toolbar exposes two pickers that control how the agent operates.

### Agent vs Plan (`planVsAgent`)

| Mode | Description |
|------|-------------|
| **Agent** | The agent executes tasks directly, calling tools as needed. |
| **Plan** | The agent creates a detailed implementation plan for your review before making any changes. |

In Plan mode the agent uses the `create_plan` tool to write a `.snowflake/cortex/plans/<name>.plan.md` file. You can review the plan, then trigger execution with **Build from Plan** (`Ctrl/Cmd+Shift+B`).

### Approval Modes

| Mode | Description |
|------|-------------|
| **Default Approvals** | CoCo uses your configured settings to decide which tool calls require approval. |
| **Bypass Approvals** | All tool calls are auto-approved without prompting. |

Approval behavior can also be tuned per tool category via settings (see [Settings](#settings)).

---

## Agent Tools

These are the tools the in-IDE agent can call on your behalf. Tools with no additional description are listed by name.

| Tool | Description |
|------|-------------|
| `agent_output` | — |
| `apply_patch` | Apply a unified patch to the workspace (add, update, delete, or move files). |
| `ask_user_question` | Ask the user one or more questions and await their responses. Supports multiple choice (`options`) and free-form text (`text`) question types. |
| `bash` | — |
| `bash_output` | — |
| `browser_back` | — |
| `browser_click` | — |
| `browser_close` | — |
| `browser_console_messages` | — |
| `browser_drag` | — |
| `browser_evaluate` | — |
| `browser_file_upload` | — |
| `browser_fill_form` | — |
| `browser_forward` | — |
| `browser_hover` | — |
| `browser_navigate` | — |
| `browser_network_requests` | — |
| `browser_press_key` | — |
| `browser_read_clipboard` | — |
| `browser_refresh` | — |
| `browser_resize` | — |
| `browser_run_code` | — |
| `browser_select_option` | — |
| `browser_snapshot` | — |
| `browser_tabs` | — |
| `browser_take_screenshot` | — |
| `browser_type` | — |
| `browser_wait_for` | — |
| `call_cortex_analyst` | Call Cortex Analyst to convert natural language questions into SQL queries using a semantic model. |
| `create_plan` | Create a detailed implementation plan as a markdown file before executing code changes. Used when Plan mode is enabled. |
| `edit` | Performs exact string replacements in files. |
| `evaluate_semantic_view` | Evaluate a semantic view by running verified queries against it and comparing results using LLM-as-judge. |
| `glob` | Fast file pattern matching tool that works with any codebase size. |
| `grep` | A powerful search tool built on ripgrep for searching file contents. |
| `kill_agent` | — |
| `memory` | Store and retrieve information across conversations through a memory file directory. |
| `multi_edit` | Performs multiple exact string replacements in a single file. |
| `notebook_add_cell` | Add a new cell to a Jupyter notebook. |
| `notebook_delete_cell` | Delete a cell from a Jupyter notebook. |
| `notebook_edit_cell` | Edit a Jupyter notebook cell using string replacement. |
| `notebook_eval_expr` | Execute a Python expression in the notebook kernel and return the result. |
| `notebook_get_df_sample` | Get sample rows from a DataFrame. Supports pandas, polars, PySpark, and Snowpark DataFrames. |
| `notebook_get_df_schema` | Get DataFrame schema information including columns, data types, row count, and column count. |
| `notebook_get_kernel_status` | Get the current status of the Jupyter notebook kernel. |
| `notebook_inspect_var` | Inspect a variable in the notebook kernel namespace. |
| `notebook_interrupt_kernel` | Interrupt running cell execution in a Jupyter notebook kernel. |
| `notebook_list_vars` | List all variables in the notebook kernel namespace. |
| `notebook_output` | Read execution outputs from a Jupyter notebook cell. |
| `notebook_read` | Read Jupyter notebook cell source code. |
| `notebook_restart_kernel` | Restart the Jupyter notebook kernel, clearing all variables and state. |
| `notebook_run_cell` | Execute cells in a Jupyter notebook. Supports a single cell, a range of cells, or all cells. |
| `notebook_select_kernel` | Select a kernel for a Jupyter notebook by label. |
| `open_browser` | — |
| `read` | Reads a file from the local filesystem. |
| `reflect_semantic_model` | Validates a semantic model YAML file using Snowflake. |
| `skill` | Invoke a skill by name. Skills contain specialized knowledge and workflows for specific domains. |
| `snowflake_object_search` | Search Snowflake objects in the catalog (databases, schemas, tables, views, etc.). |
| `snowflake_product_docs` | Search and read Snowflake product documentation. |
| `snowflake_semantic_view_search` | Search Snowflake semantic views for business entities, metrics, dimensions, and relationships. |
| `snowflake_sql_execute` | Execute or compile SQL queries and DDLs against Snowflake. |
| `task` | — |
| `terminal_last_command` | — |
| `terminal_selection` | — |
| `tgrep` | Semantic and keyword code search over the workspace, backed by Snowflake Cortex embeddings. |
| `visualize_data` | — |
| `web_fetch` | Fetches content from a web page URL. |
| `web_search` | Search the web using Brave Search. Use this for current information beyond the model knowledge cutoff. |
| `write` | Writes a file to the local filesystem. |

---

## Commands

Access these through the **command palette** or application menus. Keyboard shortcuts are shown where available.

### Agent Manager

| Title | Shortcut |
|-------|----------|
| Accept All Changes | `Ctrl/Cmd+Shift+A` |
| Focus Changes | `Ctrl/Cmd+2` |
| Focus Conversation | `Ctrl/Cmd+1` |
| Quick Open in Agent Manager | `Ctrl/Cmd+P` |
| Reject All Changes | `Ctrl/Cmd+Shift+R` |
| Show Inbox | `Ctrl/Cmd+I` |
| Start Conversation | `Ctrl/Cmd+N` |
| Toggle Sidebar | `Ctrl/Cmd+B` |
| Toggle Terminal | `Ctrl/Cmd+J` |
| Discard Changes | — |
| Group by Folder | — |
| Show in Files | — |
| Source Control | — |
| SQL Playground | — |
| Stage File | — |
| Terminal | — |
| Unstage File | — |
| View as List | — |

### Apps

| Title | Shortcut |
|-------|----------|
| Build a Snowflake App Runtime app | — |
| Build a Streamlit App | — |
| Build an app | — |
| Open Apps | — |
| Refresh | — |

### Browser

| Title | Shortcut |
|-------|----------|
| Open Agentic Browser | `Ctrl/Cmd+Shift+B` |
| Close Browser Session | — |
| Get Browser Accessibility Snapshot | — |
| Take Browser Screenshot | — |

### Chat

| Title | Shortcut |
|-------|----------|
| Toggle Agent or Editor View | `Ctrl/Cmd+E` |
| Add Context... | `Ctrl/Cmd+Slash` |
| Add Selection to Chat | `Ctrl/Cmd+L` |
| Build from Plan | `Ctrl/Cmd+Shift+B` |
| Add File to Chat | — |
| Add Files From References | — |
| Add Folder to Chat | — |
| Add Search Results to Chat | — |
| Agentic browser | — |
| Attach file | — |
| Build from Plan... | — |
| Copy | — |
| Copy All | — |
| Copy link | — |
| Copy Math Source | — |
| Copy response | — |
| Copy selected text | — |
| Edit Request | `Enter` |
| Helpful | — |
| Insert into Notebook | — |
| Keep | — |
| New session | — |
| Open Agent Settings | — |
| Open Automations | — |
| Open Changes in Diff Editor | — |
| Open Chat Storage Folder | — |
| Open File | — |
| Open File Snapshot | — |
| Read Aloud | — |
| Redo | — |
| Redo Last Request | — |
| Report Issue | — |
| Retry | — |
| Reveal Current Session File in File Manager | — |
| Revert changes | `Delete` |
| Save As... | — |
| Select Model | — |
| Undo | — |
| Undo changes | — |
| Undo Last Request | — |
| Undo Requests | `Delete` |
| Unhelpful | — |
| View All Changes | — |

### SQL

| Title | Shortcut |
|-------|----------|
| Execute SQL | `Ctrl/Cmd+Enter` |
| Run All | `Ctrl/Cmd+Shift+Enter` |
| Stop Query | `Esc` |
| Clear SQL Results | — |
| Focus on SQL Results View | — |

### Snowflake Connection

| Title |
|-------|
| Add Snowflake Connection |
| Change Role |
| Default Warehouse |
| Manage Snowflake Connections |
| Private Mode |
| Refresh Snowflake Connections |
| Sign in to Snowflake |
| View Snowflake Connections |

### Snowflake Catalog

| Title |
|-------|
| Add to Chat |
| Clear Cache |
| Refresh |

### Voice

| Title | Shortcut |
|-------|----------|
| Inline Voice Chat | `Ctrl/Cmd+I` |
| Stop Listening | `Esc` |
| Stop Listening and Submit | `Ctrl/Cmd+I` |
| Stop Reading Aloud | `Esc` |
| Voice Chat in Chat View | `Ctrl/Cmd+I` |

### SSH

| Title |
|-------|
| Add New SSH Host... |
| Add SSH Host |
| Connect Current Window to Host... |
| Connect to Host... |
| Disconnect from Host |
| Kill Remote Server on Host |
| Open SSH Configuration File... |
| Refresh SSH Targets |
| Show SSH Connection Status |

### dbt

| Title |
|-------|
| Toggle dbt Execution Mode (Snowflake-Managed/Local) |

---

## Keyboard Shortcuts — Quick Reference

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd+1` | Focus Conversation (Agent Manager) |
| `Ctrl/Cmd+2` | Focus Changes (Agent Manager) |
| `Ctrl/Cmd+B` | Toggle Sidebar |
| `Ctrl/Cmd+E` | Toggle Agent or Editor View |
| `Ctrl/Cmd+I` | Inline Voice Chat / Show Inbox / Voice Chat in Chat View / Stop Listening and Submit |
| `Ctrl/Cmd+J` | Toggle Terminal |
| `Ctrl/Cmd+L` | Add Selection to Chat |
| `Ctrl/Cmd+N` | New Session / Start Conversation |
| `Ctrl/Cmd+P` | Quick Open in Agent Manager |
| `Ctrl/Cmd+Slash` | Add Context... |
| `Ctrl/Cmd+Backspace` | Undo |
| `Ctrl/Cmd+Enter` | Execute SQL / Keep |
| `Ctrl/Cmd+Shift+A` | Accept All Changes |
| `Ctrl/Cmd+Shift+B` | Build from Plan / Open Agentic Browser |
| `Ctrl/Cmd+Shift+Enter` | Run All (SQL) |
| `Ctrl/Cmd+Shift+R` | Reject All Changes |
| `Delete` | Revert changes / Undo Requests |
| `Enter` | Edit Request |
| `Esc` | Stop Query / Stop Listening / Stop Reading Aloud |

---

## Views & Panels

Open these panels from the sidebar or via the command palette:

| Panel | Description |
|-------|-------------|
| **Snowflake Catalog** | Browse Snowflake databases, schemas, tables, and other objects. Objects can be added to chat as context. |
| **SQL Results** | View results from SQL queries executed in the editor. |
| **dbt** | dbt integration view. Toggle between Snowflake-managed and local execution modes. |
| **Apps** | Build and manage Snowflake App Runtime and Streamlit apps. |
| **Automations** | Manage scheduled tasks and automations. |

---

## MCP (Model Context Protocol)

Cortex Code discovers MCP servers from two configuration locations:

| Source | Configuration File |
|--------|--------------------|
| **Snowflake Global** | `~/.snowflake/cortex/mcp.json` — applies across all workspaces. |
| **Snowflake Workspace** | `.cortex/mcp.json` in the current workspace root — applies to the open project only. |

To add an MCP server, edit the appropriate JSON file directly. Workspace-level config overrides or supplements global config for that project.

---

## Skills

Skills are specialized knowledge packages and workflows that the agent can invoke.

- **Invoke in chat**: type `/<skill-name>` in the chat input to run a skill.
- **Manage skills**: use the skills marketplace (accessible via the command palette) to install, uninstall, publish, refresh, or create skills.

### Marketplace Commands

| Command |
|---------|
| Install Skill |
| Uninstall Skill |
| Publish Skill |
| Refresh Skills |
| Create User Skill |
| Initialize Marketplace |
| Open Skill |

### Skill Source Locations

Skills can originate from the following locations:

- `bundled` — shipped with the IDE
- `user` — installed by the user
- `project` — local to the current workspace/project
- `remote` — fetched from a remote source
- `stage` — loaded from a Snowflake stage
- `profile` — associated with an agent profile
- `plugin` — provided by an IDE plugin/extension

Disabled skills and recent stage paths can be managed via the `snowflake.skills.disabledSkills` and `snowflake.skills.recentStagePaths` settings.

---

## Settings

Notable settings you can configure in the IDE's Settings UI or `settings.json`.

### Chat settings (`chat.*`)

| Setting Key | Purpose |
|-------------|---------|
| `chat.agent.enabled` | Enable or disable the agent. |
| `chat.agent.thinkingStyle` | Controls the agent's thinking style. |
| `chat.agent.thinking.generateTitles` | Whether the agent generates titles during thinking. |
| `chat.agent.enable1MContext` | Enables extended context window. |
| `chat.agent.codeBlockProgress` | Show code block progress animation. |
| `chat.agent.toolSearch.enabled` | Enable tool search for the agent. |
| `chat.edits2.enabled` | Enable the updated edits experience. |
| `chat.editRequests` | Configure edit request behavior. |
| `chat.extensionTools.enabled` | Allow extension-provided tools in the agent. |
| `chat.tools.global.autoApprove` | Globally auto-approve all tool calls. |
| `chat.tools.edits.autoApprove` | Auto-approve file edit tool calls. |
| `chat.tools.urls.autoApprove` | Auto-approve tool calls to specific URLs. |
| `chat.tools.eligibleForAutoApproval` | Which tools are eligible for auto-approval. |
| `chat.checkpoints.enabled` | Enable conversation checkpoints. |
| `chat.math.enabled` | Enable math rendering in chat. |
| `chat.stickyPromptHeader.enabled` | Keep a sticky prompt header visible in chat. |
| `chat.threads.enabled` | Enable threaded conversations. |
| `chat.restoreLastPanelSession` | Restore the last panel session on startup. |
| `chat.notifyWindowOnResponseReceived` | Notify the window when a response is received. |
| `chat.agentSessionsViewLocation` | Where to display the agent sessions view. |
| `chat.showAgentSessionsViewDescription` | Show description text in the agent sessions view. |
| `chat.customAgentInSubagent.enabled` | Allow custom agents in subagent tool calls. |
| `chat.exitAfterDelegation` | Exit the agent after delegating to a subagent. |
| `chat.suspendThrottling` | Suspend response throttling. |
| `chat.agentManager.showDiffStats` | Show diff statistics in Agent Manager. |
| `chat.agentManager.inbox.enabled` | Enable the Agent Manager inbox. |
| `chat.agentManager.flatView` | Use flat view in Agent Manager. |
| `chat.snowboard.enabled` | Enable the Snowboard feature. |
| `chat.skillsCatalog.enabled` | Enable the skills catalog. |
| `chat.agentProfiles.enabled` | Enable agent profiles. |

### Snowflake settings (`snowflake.*`)

| Setting Key | Purpose |
|-------------|---------|
| `snowflake.skills.disabledSkills` | List of skills that are disabled. |
| `snowflake.skills.recentStagePaths` | Recently used Snowflake stage paths for skills. |
| `snowflake.sql.maxResultRows` | Maximum number of rows returned in SQL results. |
| `snowflakeCatalog.addToChat` | Configure "Add to Chat" behavior from the catalog. |
| `snowflakeCatalog.addToChatHover` | Configure hover behavior for "Add to Chat" in the catalog. |
| `snowflakeCatalog.clearCache` | Clear the Snowflake catalog cache. |
| `snowflakeCatalog.refresh` | Refresh the Snowflake catalog. |

---

## Tips

- **Add context quickly**: select code in the editor and press `Ctrl/Cmd+L` to send it directly to the chat as context. Use `Ctrl/Cmd+Slash` to open the full context picker.
- **Plan before you build**: switch to **Plan** mode before asking the agent to implement a complex feature. Review the generated plan file, then press `Ctrl/Cmd+Shift+B` to execute it.
- **Review changes before accepting**: in Agent Manager, use `Ctrl/Cmd+2` to focus the diff view and inspect all proposed edits. Accept with `Ctrl/Cmd+Shift+A` or reject with `Ctrl/Cmd+Shift+R`.
- **Use Bypass Approvals carefully**: setting the approval mode to Bypass Approvals auto-approves all tool calls, including file writes and SQL execution. Switch back to Default Approvals for sensitive operations.
- **Browse Snowflake objects visually**: open the **Snowflake Catalog** panel to explore your databases and schemas, then use "Add to Chat" to include objects as context for the agent.
- **SQL workflow**: open a `.sql` file, run the statement under the cursor with `Ctrl/Cmd+Enter`, or run all statements with `Ctrl/Cmd+Shift+Enter`. Stop a running query with `Esc`. View results in the **SQL Results** panel.
- **Voice input**: press `Ctrl/Cmd+I` to start voice input in the chat panel. Press `Esc` to cancel or `Ctrl/Cmd+I` again to stop and submit.
- **Skills marketplace**: type `/` in the chat input to see available skills, or open the command palette and search for skill marketplace commands to install new skills from remote sources or Snowflake stages.
- **MCP servers**: add workspace-specific MCP servers by creating `.cortex/mcp.json` in your project root — no global config changes needed.
- **Notebook support**: the agent can read, edit, run, and inspect cells and variables in Jupyter notebooks open in the IDE, including sampling DataFrames and checking kernel status.
- **Memory across sessions**: the agent's `memory` tool can persist information across conversations. If you want the agent to remember project conventions or preferences, ask it to store that information in memory.
