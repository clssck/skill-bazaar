---
name: manage-agent-threads
description: "Manage Cortex Agent conversation threads. Create, list, describe, update, and delete threads. Use when: user wants to create a thread, list threads, view thread messages, rename a thread, delete a thread, manage conversation history."
parent_skill: cortex-agent
---

# Manage Agent Threads

## When to Load

`cortex-agent` SKILL.md → THREADS intent: User wants to create, list, describe, update, or delete conversation threads.

## Prerequisites

- Snowflake connection with Cortex Agent access

## API Reference

| Action   | Method | Endpoint                          |
|----------|--------|-----------------------------------|
| Create   | POST   | `/api/v2/cortex/threads`          |
| List     | GET    | `/api/v2/cortex/threads`          |
| Describe | GET    | `/api/v2/cortex/threads/{id}`     |
| Update   | POST   | `/api/v2/cortex/threads/{id}`     |
| Delete   | DELETE | `/api/v2/cortex/threads/{id}`     |

## Workflow

### Step 1: Determine Action

**Ask user which thread operation they need:**

1. **Create** — create a new empty thread (returns thread UUID)
2. **List** — list existing threads
3. **Describe** — view a thread's messages and metadata
4. **Update** — rename a thread
5. **Delete** — delete a thread

### Step 2: Execute

#### Create a thread

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/manage_threads.py create \
  --connection CONNECTION
```

Returns the new thread UUID. Use this thread_id with `chat-with-agent` for multi-turn conversations.

#### List threads

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/manage_threads.py list \
  --connection CONNECTION --limit 20
```

#### Describe a thread

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/manage_threads.py describe \
  --thread-id THREAD_UUID --connection CONNECTION
```

Optionally save to file:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/manage_threads.py describe \
  --thread-id THREAD_UUID --connection CONNECTION --output-file thread.json
```

#### Update (rename) a thread

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/manage_threads.py update \
  --thread-id THREAD_UUID --name "My conversation" --connection CONNECTION
```

#### Delete a thread

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/manage_threads.py delete \
  --thread-id THREAD_UUID --connection CONNECTION
```

**⚠️ STOP**: Confirm thread ID with user before deleting — this is irreversible.

### Step 3: Next Steps

After thread management, suggest relevant follow-up:

- **After create:** "Use this thread_id with `--thread-state` in chat-with-agent for multi-turn conversations"
- **After describe:** Show message history summary (roles, message count)
- **After delete:** Confirm deletion was successful

## Stopping Points

- ✋ Step 1: After confirming which action to take
- ✋ Step 2 (delete only): Confirm thread ID before deleting

## Output

- Thread UUIDs printed to stdout
- Thread details as JSON (optionally saved to file via `--output-file`)
