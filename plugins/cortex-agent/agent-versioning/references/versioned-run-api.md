# Cortex Agent Versioned Run API

---

> **Note**
>
> Requests to the Cortex Agent REST API time out after 15 minutes.

The versioned run API allows you to run a **specific version** of a Cortex Agent. This is in addition to the existing [`agent:run`](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-run) endpoint (see [Behavior change for `agent:run`](#behavior-change-for-agentrun-after-versioning) for how `agent:run` resolves versions).

The `version:run` endpoint supports streaming responses by default. To disable streaming and receive a single JSON response, set `stream` to `false`.

---

## Agent versioned run request

`POST` `/api/v2/databases/{database}/schemas/{schema}/agents/{name}/versions/{version}:run`

Sends a user query to a specific version of the agent object and returns its response.

By default, the API streams responses as server-sent events (SSE). To receive a
single JSON response, set `stream` to `false` in the request body.

The `{version}` path parameter accepts:

- A **version name** (e.g., `VERSION$2`)
- A **user-defined alias** (e.g., `production`)
- A **shortcut**: `FIRST`, `LAST`, `DEFAULT`, `LIVE`

### Path parameters

| Parameter | Required | Type | Description |
| :--- | :--- | :--- | :--- |
| `database` | Yes | string | The database containing the agent. You can use the `/api/v2/databases` GET request to get a list of available databases. |
| `schema` | Yes | string | The schema containing the agent. You can use the `/api/v2/databases/{database}/schemas` GET request to get a list of available schemas. |
| `name` | Yes | string | The name of the agent. |
| `version` | Yes | string | The version to run. Accepts a version name (e.g., `VERSION$2`), a user-defined alias (e.g., `production`), or a shortcut (`FIRST`, `LAST`, `DEFAULT`, `LIVE`). |

### Request headers

| Header | Required | Description |
| :--- | :--- | :--- |
| `Authorization` | Yes | Authorization token. See [Authentication](https://docs.snowflake.com/en/developer-guide/sql-api/authenticating). Supported schemes: KeyPair, ExternalOAuth, SnowflakeOAuth, ProgrammaticAccessToken. |
| `Content-Type` | Yes | `application/json` |
| `Accept` | No | Response content type. Use `text/event-stream` for streaming responses or `application/json` for a single non-streaming response. |

### Request body

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `messages` | array of [Message](#message) | Yes | Conversation payload. If `thread_id` and `parent_message_id` are passed, `messages` includes only the current user message. Otherwise, `messages` includes the full conversation history and the current message. Minimum 1 message. |
| `thread_id` | integer | No | The thread ID for the conversation. If used, `parent_message_id` must also be passed. |
| `parent_message_id` | integer | No | The ID of the parent message in the thread. If this is the first message, `parent_message_id` should be `0`. |
| `stream` | boolean | No | Whether to return a streaming response (`text/event-stream`) or a non-streaming JSON response (`application/json`). Default: `true`. |
| `background` | boolean | No | Whether to execute asynchronously. Default: `false`. When `true`, `thread_id` is required. |
| `tool_choice` | [ToolChoice](#toolchoice) | No | Configures how the agent should select and use tools during the interaction. |
| `tool_bindings` | object | No | Auto-injection bindings for tool parameters. |
| `query_tags` | array of string | No | Tags applied to session queries executed by the agent. |
| `execution_trace` | object | No | Contains `enabled` (boolean, required within this object) to enable tracing metadata in the response. |
| `variables` | object | No | Variable dictionary with metadata. |
| `origin_application` | string | No | Caller identity. Allowed values: `inline_copilot`, `data_science_agent`, `microsoft_teams`, `coding_agent`, `external`. Default: `external`. |

Example

```json
{
  "thread_id": 0,
  "parent_message_id": 0,
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "What is the total revenue for 2023?"
        }
      ]
    }
  ],
  "stream": false,
  "tool_choice": {
    "type": "auto",
    "name": [
      "analyst_tool",
      "search_tool"
    ]
  }
}
```

The request body supports an optional `stream` boolean field:

- If `stream` is omitted, it defaults to `true` and the response is streamed as SSE events.
- If `stream` is `false`, the API returns a single JSON object (see [Non-streaming response](#non-streaming-response-stream-false)).

---

## Version resolution

The `{version}` path parameter is resolved against the agent's versioned stage. The following resolution rules apply:

| Value | Resolves To |
| :--- | :--- |
| `VERSION$N` | The committed version with system ID `N` (e.g., `VERSION$1`, `VERSION$2`). |
| User-defined alias | The version with the matching alias (e.g., `production`, `staging`). Unquoted aliases are case-insensitive. |
| `FIRST` | The first committed version. |
| `LAST` | The last (most recent) committed version. |
| `DEFAULT` | The version set as default via `ALTER AGENT SET DEFAULT_VERSION`. |
| `LIVE` | The current live (mutable) version. |

> **Note**
>
> - Unresolved version identifiers return a version-not-found error (HTTP 404).
> - Runtime may block `VERSION$1` when that placeholder version has no spec and the guard parameter is enabled.

---

## Usage notes

- The versioned run endpoint shares the same request body schema as the standard `agent:run` endpoint. The only difference is the additional `{version}` path parameter.
- You cannot set, update, or overwrite the `models`, `instructions`, and `orchestration` fields via the versioned run request. These fields are defined in the agent specification of the target version. To update them, use [`ALTER AGENT MODIFY LIVE VERSION SET SPECIFICATION`](./sql-reference.md#alter-agent-modify-live-version) or [`ALTER AGENT ADD VERSION`](./sql-reference.md#alter-agent-add-version).
- **Shortcut handling:** Shortcuts like `LIVE`, `DEFAULT`, `FIRST`, `LAST` are resolved server-side.

---

## Behavior change for `agent:run` after versioning

The standard `agent:run` endpoint (without `{version}` in the path) has a **behavior change** once an agent has committed versions:

| Agent State | `agent:run` Talks To | `DESCRIBE AGENT` (SQL & REST) Shows |
| :--- | :--- | :--- |
| **Before versioning** (only LIVE version exists) | LIVE | LIVE spec |
| **After versioning** (customer has committed versions) | DEFAULT | DEFAULT version spec |

> **Important**
>
> This applies to both the SQL `DESCRIBE AGENT` command and the REST `agent:run` API. Once any committed version exists, both resolve to the **DEFAULT** version rather than LIVE.
>
> If you always need to interact with the LIVE version regardless of whether committed versions exist, use the versioned run endpoint with `LIVE` explicitly:
>
> ```
> POST /api/v2/databases/{database}/schemas/{schema}/agents/{name}/versions/LIVE:run
> ```
>
> Similarly, to always read the LIVE spec (e.g., in tooling like `get_agent_config.py`), use the stage query instead of `DESCRIBE AGENT`:
>
> ```sql
> SELECT LISTAGG(RTRIM($1), '\n') WITHIN GROUP (ORDER BY METADATA$FILE_ROW_NUMBER)
>   AS agent_specification
> FROM snow://agent/DB.SCHEMA.AGENT/versions/LIVE/agent_spec.yaml
> WHERE TRIM($1) <> '';
> ```

---

## Examples

Use the `agent_version_run.py` script (in the parent skill at `cortex-agent/scripts/agent_version_run.py`) to run a specific version of an agent:

```bash
uv run --project /path/to/cortex-agent python /path/to/cortex-agent/scripts/agent_version_run.py \
  --agent-name MY_AGENT \
  --version LIVE \
  --question "What were total sales last quarter?" \
  --output-file ./response.json
```

### Run the LIVE version

```bash
uv run --project /path/to/cortex-agent python /path/to/cortex-agent/scripts/agent_version_run.py \
  --agent-name MY_AGENT --version LIVE \
  --question "What were total sales last quarter?" \
  --output-file ./response.json
```

### Run a committed version (VERSION$2)

```bash
uv run --project /path/to/cortex-agent python /path/to/cortex-agent/scripts/agent_version_run.py \
  --agent-name MY_AGENT --version "VERSION\$2" \
  --question "Summarize pipeline incidents from yesterday" \
  --output-file ./response.json
```

> **Note:** The `$` character in `VERSION$N` is automatically URL-encoded by the script.

### Run the DEFAULT version

```bash
uv run --project /path/to/cortex-agent python /path/to/cortex-agent/scripts/agent_version_run.py \
  --agent-name MY_AGENT --version DEFAULT \
  --question "Show me the top 10 customers by revenue" \
  --output-file ./response.json
```

### Run by user-defined alias

```bash
uv run --project /path/to/cortex-agent python /path/to/cortex-agent/scripts/agent_version_run.py \
  --agent-name MY_AGENT --version production \
  --question "What is our current inventory level?" \
  --output-file ./response.json
```

### Run with workspace auto-resolution

```bash
uv run --project /path/to/cortex-agent python /path/to/cortex-agent/scripts/agent_version_run.py \
  --agent-name MY_AGENT --version LIVE \
  --question "What can you do?" \
  --database MY_DB --schema AGENTS \
  --workspace MY_DB_AGENTS_MY_AGENT --output-name test_verification.json
```

### Run with a custom connection and database

```bash
uv run --project /path/to/cortex-agent python /path/to/cortex-agent/scripts/agent_version_run.py \
  --agent-name MY_AGENT --version DEFAULT \
  --question "What was our revenue last month?" \
  --database MY_DB --schema MY_SCHEMA \
  --connection my_connection \
  --output-file ./response.json
```
