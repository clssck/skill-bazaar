---
name: openflow-core-guidelines
description: Core context and guidelines for Openflow operations. Always load this reference at the start of any Openflow session.
---

# Openflow Core Guidelines

Foundational context for all Openflow operations. The main skill handles routing; this reference provides the knowledge needed to execute any workflow correctly.

## Mandatory Behavior Pattern

These rules apply to ALL operations. Violating them indicates context drift - reload skills immediately.

1. **Never guess.** If unsure of a function signature, argument, or required value - stop.
2. **Skills first.** Check the intent table in `SKILL.md` to find the correct reference for the operation.
3. **Load references when directed.** When a workflow step says to load a reference, STOP and load it. Do not substitute general knowledge for reference content. References exist because they contain domain-specific configuration that differs from standard approaches (e.g., required package extras, specific install methods, non-obvious flags). Skipping a reference and improvising from general knowledge is a common cause of cascading failures.
4. **Help second.** If skills do not cover it, run `--help` on the command to discover arguments.
5. **Ask third.** If still unsure, ask the user: "I need to do X - is this the correct approach?"
6. **No fabrication.** Do not invent commands, parameters, or API calls. Use documented examples only.
7. **No secrets in output.** Never echo passwords, tokens, or sensitive values back to the user.
8. **Verify results.** After operations, check the result matches expectations before proceeding.

**Context drift indicators** (if you notice these, reload `SKILL.md`):
- Writing custom code for operations that should have CLI commands
- Trying multiple argument variations to see what works
- Proceeding without knowing what a command will do
- Skipping a reference load because you think you already know how to do it

---

## What is Openflow?

Openflow is a Snowflake product built on Apache NiFi. It provides data integration capabilities through:

- **Connectors** - Pre-built flows for common sources (PostgreSQL, MySQL, Google Drive, etc.)
- **Custom Flows** - User-built NiFi flows for specific integration needs

## Tool Hierarchy

Three layers of tooling, each with different scope:

### 1. Snowflake SQL / CLI (Account Level)

Operations on Snowflake account resources:

| Operation | Tool | Example |
|-----------|------|---------|
| Create Network Rule | SQL | `CREATE NETWORK RULE ...` |
| Create External Access Integration | SQL | `CREATE EXTERNAL ACCESS INTEGRATION ...` |
| Query Runtime Logs | SQL | `SELECT * FROM <events_table> ...` |
| Show Deployments | SQL / `snow` | `SHOW OPENFLOW DEPLOYMENTS` |

### 2. Openflow Control Plane UI or SQL (Infrastructure Level)

Infrastructure operations. On accounts using the SOM (Snowflake Object Model), these can also be done via SQL; on legacy accounts the UI is required. This skill supports both models — commands are SOM-first with legacy fallbacks noted where applicable.

| Operation | SQL (SOM) | UI |
|-----------|-----------|----|
| Create Deployment | `CREATE OPENFLOW DEPLOYMENT` | Supported |
| Terminate/Drop Deployment | `ALTER ... TERMINATE` + `DROP` | Supported |
| Terminate/Drop Deployment (with runtimes) | `ALTER ... TERMINATE CASCADE` + `DROP CASCADE` | Supported |
| Create Runtime | `CREATE OPENFLOW RUNTIME` | Supported |
| Suspend/Resume/Restart Runtime | `ALTER OPENFLOW RUNTIME ... SUSPEND/RESUME/RESTART` | Supported |
| Terminate/Drop Runtime | `ALTER ... TERMINATE` + `DROP` | Supported |
| Terminate/Drop Runtime (with connectors) | `ALTER ... TERMINATE CASCADE` + `DROP CASCADE` | Supported |
| Attach EAI to Runtime | `ALTER OPENFLOW RUNTIME ... SET EXTERNAL_ACCESS_INTEGRATIONS` | Supported |
| Configure Runtime Resources | `ALTER OPENFLOW RUNTIME ... SET` | Supported |

### 3. NiFi API via nipyapi (Runtime Level)

**Everything within a Runtime** is accessible via nipyapi. Use the simplest level that works:

**Preference order:**

1. **CLI commands** - For operations with simple inputs/outputs. Returns structured JSON.
2. **CI functions** - Common workflows with error handling (`nipyapi ci ...` or `nipyapi.ci.*`)
3. **Module functions** - Granular control (`nipyapi canvas ...` or `nipyapi.canvas.*`)

**Common operations (CLI preferred):**

| Operation | CLI Command |
|-----------|-------------|
| Deploy flow | `nipyapi ci deploy_flow --bucket X --flow Y` |
| Start/Stop flow | `nipyapi ci start_flow --pg_id <id>` |
| Get status | `nipyapi ci get_status --pg_id <id>` |
| Configure params | `nipyapi ci configure_inherited_params --pg_id <id> --parameters '{...}'` |
| Get bulletins | `nipyapi bulletins get_bulletin_board` |
| List processors | `nipyapi canvas list_all_processors --pg_id <id>` |
| Cleanup | `nipyapi ci cleanup --pg_id <id>` |

**When to use Python instead of CLI:**
- Complex logic across multiple API calls
- Need to inspect/manipulate response objects
- Looping or conditional operations
- Operations not exposed in CLI (e.g., `nipyapi.canvas.create_processor()`)

For unfamiliar commands, check `--help` first. See "Command Types" section below for discovery guidance.

**CLI Error Output:** nipyapi CLI returns structured JSON even on failure. No need to fall back to curl for HTTP status codes:

```json
{
  "success": false,
  "error": "(503)\nReason: Service Unavailable\nHTTP response headers: ...",
  "error_type": "ApiException",
  "logs": ["HTTP response body..."]
}
```

Use `success` to check outcome, `error` for HTTP status/reason, `error_type` to categorize (ApiException, ConnectionError, etc.).

### 4. Curl (Alternative for Runtime Level)

If the user prefers curl or Python/nipyapi is unavailable, basic operations can be performed via curl against the NiFi REST API.

**Setup:** Extract URL and PAT from the nipyapi profile. If no profile exists, run `references/setup-main.md` first to create one.

Run this once per session:

```bash
PROFILE="<profile-name>"
BASE_URL=$(awk -v profile="$PROFILE:" '$0 ~ profile {found=1} found && /nifi_url:/ {gsub(/.*nifi_url: *"?|"?$/, ""); print; exit}' ~/.nipyapi/profiles.yml)
PAT=$(awk -v profile="$PROFILE:" '$0 ~ profile {found=1} found && /nifi_bearer_token:/ {gsub(/.*nifi_bearer_token: *"?|"?$/, ""); print; exit}' ~/.nipyapi/profiles.yml)
AUTH_HEADER="Authorization: Bearer $PAT"
```

**Usage:** All curl commands use `$BASE_URL` and `$AUTH_HEADER`. Always use the profile that matches the runtime you're working with, just as you use `--profile <name>` with nipyapi and `-c <connection>` with snow. Add `-k` to curl commands if you encounter certificate verification errors.

**Coverage:** Curl provides basic operations only. The following references include curl alternatives:

| Reference | Curl Operations Available |
|-----------|---------------------------|
| `ops-flow-deploy.md` | List registries, list flows, deploy |
| `ops-flow-lifecycle.md` | Start, stop, bulletins, terminate |
| `ops-parameters-main.md` | List contexts, get context details, update parameters, find ownership |
| `ops-parameters-assets.md` | Asset upload |
| `ops-config-verification.md` | Full verification workflow |
| `connector-cdc.md` | Table state queries |

**Not available via curl (require nipyapi):**
- Layout management (`ops-layout.md`)
- Version control helpers (`ops-version-control.md`)
- Tracked modifications (`ops-tracked-modifications.md`)
- Extension management (`ops-extensions.md`)
- Automatic parameter ownership resolution (curl requires manual context identification)

Check the cache for tooling preference: `jq '.tooling.preferred' ~/.snowflake/cortex/memory/openflow_infrastructure_*.json`

## Deployment Types

| Type | Description | Authentication | Network Access |
|------|-------------|----------------|----------------|
| **SPCS** | Snowflake-managed (Snowpark Container Services) | Session token (automatic) | Requires EAI for external sources |
| **BYOC** | Bring Your Own Cloud (customer-managed) | Managed token (default); Key-pair (alternative) | Direct network access |

### Detecting from URL

| Type | URL Pattern |
|------|-------------|
| SPCS | Starts with `of--` (e.g., `https://of--account.snowflakecomputing.app/...`) |
| BYOC | Contains `snowflake-customer.app` (e.g., `https://xxx.openflow.region.snowflake-customer.app/...`) |

```python
def is_spcs_deployment(url: str) -> bool:
    from urllib.parse import urlparse
    return urlparse(url).netloc.startswith("of--")
```

### Key Differences

| Aspect | SPCS | BYOC |
|--------|------|------|
| Snowflake Auth Strategy | `SNOWFLAKE_SESSION_TOKEN` | `SNOWFLAKE_MANAGED` (default) or `KEY_PAIR` (alternative) |
| Private Key Service bulletins | Ignore (not used) | Ignore when using managed token; required for key-pair |
| Account Identifier parameter | Not required | Not required (managed token); Required (key-pair) |
| Snowflake Username parameter | Not required | Not required (managed token); Required (key-pair) |
| Runtime role | Managed by SPCS automatically | Set via `EXECUTE_AS_ROLE` on runtime (must configure) |
| External Access Integration | Required for external sources | Not required |

## Safety Principles

1. **NiFi has no undo.** Before bulk modifications (layout changes, parameter updates, flow restructuring), suggest the user commit to version control first.

2. **Dry-run before modifying.** When making changes, run with `--dry_run` first unless the user has explicitly instructed the change. Present the dry-run output to the user for confirmation before executing.

3. **Permission boundaries.** The agent typically operates under a limited Snowflake role (not ACCOUNTADMIN). When operations fail with privilege errors:
   - Explain the permission boundary encountered
   - Provide the user with exact SQL/commands to run with elevated privileges
   - Wait for user confirmation before continuing
   - Do NOT assume the user cannot do something - they may have access via a different role

## Context Refresh Procedures

### On Resuming from Summary

When starting from a system-provided summary (indicating context was compressed):

1. Re-read `SKILL.md` to refresh the intent routing table
2. Identify which skills are relevant to the current task
3. Load those skill references into active context before proceeding

### Before Command Execution

Before running any nipyapi or snow command:

1. Identify the operation category from the intent table in `SKILL.md`
2. Check if the relevant skill reference is in active memory
3. If uncertain of command syntax, re-read the reference first

**Red flags requiring skill reload:**
- Writing custom Python for operations that should have CLI commands
- Guessing command arguments
- Previous command failed with unexpected syntax

---

## Command Types in References

References contain two types of commands:

### Exact Commands

Marked with **"Run exactly"** or listed in command reference tables. These have known, fixed values - only substitute session variables.

**Session variables** (always available from session context):
- `<profile>` - nipyapi profile name from cache
- `<pg-id>` - process group ID from previous step

When a reference shows a command with fixed values (registry names, bucket names, specific flags), use those exact values. The reference has already determined the correct syntax.

### Template Commands

Require discovery or user input before execution. The reference will indicate this with phrases like "Discover first" or show `--help` usage.

**Example:**

```bash
# Discover arguments first
nipyapi canvas create_processor --help

# Then construct with discovered arguments and user-provided values
```

### When to Discover

| Situation | Action |
|-----------|--------|
| Command marked "Run exactly" | Run as-is, substitute session variables only |
| Command in a reference table | Run as-is, these are exact |
| Command with user-specific values | Gather from user, then run |
| Command for Advanced operations | Check `--help` to understand arguments |
| Unfamiliar function | Check `--help` before first use |

For common Primary tier operations (list flows, get status, start, stop), commands are exact and don't need discovery.

## Interrupt Handling

Two types of interruptions require pausing the current workflow: system errors and user corrections.

### System Errors

When any CLI command, Python script, or API call returns an unexpected error:

1. **Save Context** - Create a todo item capturing current workflow state:
   ```
   [paused] <workflow name> - <current step>
   Error: <brief error description>
   ```

2. **Load Handler** - Load `references/core-troubleshooting.md`

3. **Resolve Error** - Follow the troubleshooting workflow to match and remediate

4. **Restore Context** - Check todos for paused items and resume where you left off

**Key Principle:** Do not attempt workarounds (writing Python scripts, trying alternative commands) until after consulting the troubleshooting reference. The error may have a known pattern with a documented fix.

**What counts as unexpected:** Any error that prevents the current operation from completing - timeouts, HTTP errors, exceptions, validation failures, permission denials.

### User Corrections

When user redirects focus, provides corrections, or requests a sidequest:

1. **Save Context** - Create a todo item capturing current workflow state:
   ```
   [paused] <workflow name> - <current step>
   Reason: User requested <brief description>
   ```

2. **Complete the Sidequest** - Give the user's new request full attention. Do not rush through it to return to the main task. Apply the same rigor (skill loading, verification, testing) as the main workflow.

3. **Confirm Completion** - Explicitly confirm the sidequest is complete before returning:
   ```
   "The [sidequest description] is complete. Returning to [main task name]."
   ```

4. **Restore Context** - Check todos for paused items and resume where you left off

**Key Principle:** Sidequests deserve full attention. Rushing through a correction to return to the main task often results in incomplete work that requires another interruption. Complete the sidequest properly, confirm it is done, then resume.

---

## Handling User Corrections

Quickly classify user corrections before responding:

**Simple corrections** (value fixes, typos, yes/no answers):
Acknowledge, apply, continue. No flow break needed.

**Significant redirections** (questions about what you did/didn't do, concepts you haven't loaded docs for, implied missed steps):
Pause. Note your position in the current workflow. Load relevant documentation BEFORE responding. Reassess task list. Resume with corrected understanding.

When uncertain, treat as significant. A brief pause to verify documentation costs less than extended troubleshooting from a missed step.

---

## Operational Pattern: Check-Act-Check

For operations that modify service state, always verify before and after:

1. **Check** - Read current state using the appropriate function
2. **Act** - Execute the operation
3. **Check** - Read state again to confirm the expected result

Many NiFi operations are **asynchronous** - the command returns before the action completes, and the object returned may be an intermediate state. The post-Act check confirms the operation achieved the expected result.

### Example

```bash
# Check: Confirm flow is stopped
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
# Expect: stopped_processors > 0

# Act: Start the flow
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"

# Check: Confirm flow is running
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
# Expect: running_processors > 0, bulletin_errors = 0
```

### Guidance

- Default to `get_status` for the Check step when unsure
- Use more specific read functions when `get_status` doesn't contain the required information
- If pre-Check shows unexpected state, investigate before proceeding
- If post-Check shows unexpected state, investigate and discuss corrective action with the user

Operations references (e.g., `ops-flow-lifecycle.md`) provide specific Check-Act-Check examples for each operation.

## Workflow Modes

Recognize the user's workflow mode from their intent patterns. Mode influences agent behavior and guidance.

### Mode Detection

| Mode | Intent Patterns | Examples |
|------|-----------------|----------|
| **Investigation** | "show", "list", "check", "what is", "status", "describe", "find", "get" | "Show me the flows", "What connectors are running?" |
| **Deployment** | "deploy", "start", "stop", "configure", "upgrade", "install" | "Deploy the CDC connector", "Configure the parameters" |
| **Authorship** | "create", "add", "modify", "change", "edit", "build", "customize" | "Add a processor", "Create a new flow", "Customize this connector" |

### Investigation Mode

Read-only operations focused on understanding and reporting:
- List flows, connectors, processors
- Check status and health
- Describe configuration and parameters
- Query event tables for diagnostics

No prompts about version control. Focus on reporting state and explaining what exists.

**Complex Investigations:** If the investigation exceeds 5-10 exchanges or involves customer issues, consider using the investigation diary methodology. See `references/core-investigation-diary.md` for maintaining context across extended sessions.

### Deployment Mode

Operational changes to pre-built connectors supplied by Snowflake:
- **Deploy** connectors from the Snowflake connector registry
- **Configure** parameter values on deployed flows
- **Control** process groups (start/stop) and controller services
- **Upgrade** connectors to newer versions

These are "service editing" changes - modifying operational state and configuration without altering flow structure.

**Key context:** The Snowflake connector registry (`Snowflake Openflow Connector Registry`) is pre-provisioned and read-only. No registry client setup is required for connector activities.

**Agent behavior:**
- Proceed with deployment and configuration without version control prompts
- After deploying, expect to configure parameters (this is part of the deployment workflow)
- Prompt about EAI if SPCS deployment needs external network access

### Authorship Mode

Structural changes to flow design - adding/removing/modifying processors, connections, or process groups.

**Critical distinction:** The Snowflake connector registry (`Snowflake Openflow Connector Registry`) is **read-only**. It provides pre-built connectors but cannot save custom edits. For Authorship work, the user needs their own Git registry client or to author flows without using version control.

**Agent behavior:**
- **Prompt about version control** if the target flow is not already versioned to a user-owned registry:
  > "You're about to make structural changes to this flow. Would you like to set up version control first? This requires connecting your own Git repository (the Snowflake connector registry is read-only). This provides undo capability and change management. (Skip if you're just experimenting.)"
- If flow is versioned to `main` branch, suggest a feature branch:
  > "This flow is connected to the main branch. Consider creating a feature branch on your VCS for your changes."
- See `references/ops-version-control.md` for Git registry client setup

### Mode Transitions

| From | To | Trigger | Agent Action |
|------|----|---------|--------------|
| Investigation | Deployment | "Deploy the connector", "Start the flow" | Proceed with deployment workflow |
| Investigation | Authorship | "Add a processor", "Modify this flow" | Prompt about version control |
| Deployment | Authorship | "Customize this connector", "Add handling for X" | Prompt about version control (Snowflake registry won't save these changes) |

When transitioning **into Authorship** from Deployment, make clear that customizations cannot be saved back to Snowflake's registry - the user needs their own Git registry client.
