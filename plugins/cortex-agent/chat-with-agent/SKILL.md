---
name: chat-with-agent
description: "Interactive chat with a Cortex Agent. Supports object-based and lite (objectless) agent runs, single-turn and multi-turn conversations via threads. Use when: user wants to talk to an agent, have a conversation, send messages, chat, ask follow-up questions."
parent_skill: cortex-agent
---

# Chat with Agent

## When to Load

`cortex-agent` SKILL.md → CHAT intent: User wants to have a conversation with an existing agent or run a lite agent interactively.

## Prerequisites

- Snowflake connection with Cortex Agent access
- For object-based runs: agent already created
- For lite runs: a JSON config file with tools/tool_resources/instructions

## Workflow

### Step 1: Determine Run Mode

**Ask user:**

```
How would you like to chat?

1. Agent object — talk to a deployed agent (DATABASE.SCHEMA.AGENT_NAME)
2. Lite (objectless) — provide tools/instructions inline via JSON config
```

**If object-based:** Collect agent coordinates (database, schema, agent_name, connection).
**If lite:** Collect path to a JSON config file containing `tools`, `tool_resources`, `instructions`, etc.

**⚠️ STOP**: Confirm agent coordinates or config file before proceeding.

### Step 2: Single-Turn or Multi-Turn

**Ask user:**

```
Do you want:
1. Single question (one-shot)
2. Multi-turn conversation (follow-ups keep context)
```

For manual thread management (list, describe, rename, delete threads), use the **manage-agent-threads** skill.

#### How Multi-Turn Threading Works

Multi-turn conversations use the Cortex Threads API to maintain context between turns. The protocol is:

1. **Create a thread** — Use `manage_threads.py create` to create a new thread. This calls `POST /api/v2/cortex/threads` and returns a `thread_id`.
2. **Turn 1** — Send the first message with `--thread-id <thread_id> --parent-message-id 0` (zero means first message in the thread).
3. **Extract assistant message_id** — The script prints `assistant_message_id=<id>` after each response. This is the ID to use as `parent_message_id` for the next turn.
4. **Turn 2+** — Send the next message with `--thread-id <thread_id> --parent-message-id <assistant_message_id from previous turn>`.
5. **Repeat** — Each turn's `assistant_message_id` becomes the next turn's `--parent-message-id`.

The `assistant_message_id` comes from the streaming `metadata` event emitted by the API:
```json
event: metadata
data: {"metadata": {"role": "assistant", "message_id": 156100587885066, "run_id": "..."}}
```

### Step 3: Send Messages

#### Object-based run (single-turn)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/chat_with_agent.py \
  --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION \
  --question "Your question here" \
  --output-file response.json
```

#### Object-based run (multi-turn)

First, create a thread:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/manage_threads.py create \
  --connection CONNECTION
```
This prints `Thread created: <thread_id>`. Use this thread_id below.

Turn 1 (first message, parent_message_id is 0):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/chat_with_agent.py \
  --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION \
  --question "Your first question" \
  --thread-id <THREAD_ID> --parent-message-id 0 \
  --output-file response_01.json
```
Note the `assistant_message_id=<ID>` printed in the output.

Turn 2+ (follow-ups, use the assistant_message_id from the previous turn):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/chat_with_agent.py \
  --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION \
  --question "Follow-up question" \
  --thread-id <THREAD_ID> --parent-message-id <ASSISTANT_MESSAGE_ID> \
  --output-file response_02.json
```

#### Lite / objectless run

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/chat_with_agent.py \
  --lite-config agent_config.json \
  --connection CONNECTION \
  --question "Your question here" \
  --output-file response.json
```

Multi-turn works the same way — create a thread first, then pass `--thread-id` and `--parent-message-id`.

#### Additional flags

- `--no-stream` — disable streaming, get single JSON response
- `--enable-research-mode` — enable staged reasoning agent flow
- `--current-date-override 2024-01-15` — override current date for time-sensitive queries

### Step 4: Review Response

After each message:

1. Read the agent's text response printed to stdout
2. If `--output-file` was used, inspect the full response JSON for tool calls, tables, charts
3. Ask user: "Would you like to send a follow-up message?"

**If yes:** Go back to Step 3 with the next question (using the `assistant_message_id` from the last turn).
**If no:** Chat session is complete.

### Step 5: Analyze Conversation (Optional)

If the user wants to debug or inspect:

```bash
cat response_01.json | jq '.content[] | select(.type == "tool_use") | .tool_use.name'
cat response_01.json | jq -r '.content[] | select(.type == "tool_result") | .tool_result.content[0].json.sql'
```

**For deeper debugging:** LOAD `debug-single-query-for-cortex-agent` skill.

## Lite Config File Format

For objectless runs, the JSON config should contain any combination of:

```json
{
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "my_analyst_tool"
      }
    }
  ],
  "tool_resources": {
    "my_analyst_tool": {
      "type": "cortex_analyst_text_to_sql",
      "semantic_view": "DB.SCHEMA.MY_SEMANTIC_VIEW"
    }
  },
  "models": {
    "orchestration": "claude-4-sonnet"
  },
  "instructions": {
    "response": "Be concise.",
    "system": "You are a helpful assistant."
  }
}
```

## Stopping Points

- ✋ Step 1: After confirming agent coordinates / config file
- ✋ Step 4: After each response, ask if user wants to continue

## Output

- Agent responses printed to stdout (streamed token-by-token by default)
- `assistant_message_id=<id>` printed after each response (for multi-turn chaining)
- Optional full response JSON files via `--output-file`
