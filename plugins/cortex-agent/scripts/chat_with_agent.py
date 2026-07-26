#!/usr/bin/env python3
"""
Chat with a Cortex Agent — send a single message and get a response.

Supports two modes:
  1. Agent object   POST /api/v2/databases/{db}/schemas/{schema}/agents/{name}:run
  2. Lite (no obj)  POST /api/v2/cortex/agent:run

For multi-turn conversations, pass --thread-id and --parent-message-id explicitly.
The script prints the assistant's message_id so callers can chain follow-up turns.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import snowflake.connector
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _get_connection(connection_name: str | None = None):
    if connection_name is None:
        connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME", "snowhouse")
    return snowflake.connector.connect(connection_name=connection_name)


def _build_url(host: str, *, database: str | None, schema: str | None, agent_name: str | None):
    if agent_name and database and schema:
        return f"https://{host}/api/v2/databases/{database}/schemas/{schema}/agents/{agent_name}:run"
    return f"https://{host}/api/v2/cortex/agent:run"


def chat(
    question: str,
    *,
    agent_name: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    connection_name: str | None = None,
    thread_id: str | None = None,
    parent_message_id: int = 0,
    output_file: str | None = None,
    lite_config_file: str | None = None,
    enable_research_mode: bool = False,
    current_date_override: str | None = None,
    stream: bool = True,
) -> dict | None:
    conn = _get_connection(connection_name)
    try:
        token = conn.rest.token
        host = conn.host

        url = _build_url(host, database=database, schema=schema, agent_name=agent_name)

        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
        }

        payload: dict = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": question}],
                }
            ],
        }

        if not stream:
            payload["stream"] = False
            headers["Accept"] = "application/json"

        if thread_id:
            payload["thread_id"] = thread_id
            payload["parent_message_id"] = parent_message_id
            print(f"Thread: {thread_id} (parent_message_id={parent_message_id})")

        if lite_config_file:
            with open(lite_config_file) as f:
                lite_cfg = json.load(f)
            for key in ("tools", "tool_resources", "models", "instructions", "orchestration", "tool_choice"):
                if key in lite_cfg:
                    payload[key] = lite_cfg[key]

        experimental_flags: dict = {}
        if enable_research_mode:
            experimental_flags["ReasoningAgentFlowType"] = "staged"
            print("Research mode enabled: staged reasoning agent flow type")
        if current_date_override:
            experimental_flags["CurrentDateOverride"] = current_date_override
            print(f"Current date override: {current_date_override}")
        if experimental_flags:
            payload["experimental"] = experimental_flags

        target = f"{database}.{schema}.{agent_name}" if agent_name else "lite agent (objectless)"
        print(f"Sending to {target}")
        print(f"Question: '{question}'")
        if stream:
            print("Streaming response...\n")

        assistant_message_id = 0

        if not stream:
            resp = requests.post(url, headers=headers, json=payload, verify=False)
            if resp.status_code != 200:
                print(f"Error: {resp.status_code}\n{resp.text}", file=sys.stderr)
                return None
            final_response = resp.json()
        else:
            resp = requests.post(url, headers=headers, json=payload, stream=True, verify=False)
            if resp.status_code != 200:
                print(f"Error: {resp.status_code}\n{resp.text}", file=sys.stderr)
                return None

            final_response = None
            event_type = None

            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded.startswith("event: "):
                    event_type = decoded[7:].strip()
                elif decoded.startswith("data: "):
                    try:
                        data = json.loads(decoded[6:])
                    except json.JSONDecodeError:
                        continue

                    if event_type == "metadata":
                        meta = data.get("metadata", {})
                        if meta.get("role") == "assistant":
                            mid = meta.get("message_id")
                            if mid:
                                assistant_message_id = mid

                    if event_type == "response.text.delta":
                        text_chunk = data.get("text", "")
                        print(text_chunk, end="", flush=True)

                    if event_type == "done":
                        break

                    if event_type == "response":
                        final_response = data
                        if not assistant_message_id:
                            mid = data.get("metadata", {}).get("assistant_message_id")
                            if mid:
                                assistant_message_id = mid

            print()

            if final_response and not assistant_message_id:
                assistant_message_id = (
                    final_response.get("metadata", {}).get("assistant_message_id")
                    or 0
                )

        if final_response is None:
            print("No final response received", file=sys.stderr)
            return None

        print("\n" + "=" * 60)
        print("Request completed successfully!")

        if not stream:
            if "content" in final_response:
                for item in final_response["content"]:
                    if item.get("type") == "text":
                        print(f"\nAgent Response:\n{item['text']}\n")

        if assistant_message_id:
            print(f"assistant_message_id={assistant_message_id}")

        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w") as f:
                json.dump(final_response, f, indent=2)
            print(f"Response saved → {output_file}")

        print("=" * 60)
        return final_response

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Chat with a Cortex Agent (single message, single response)",
        epilog="""
Examples:
  # Single-turn with agent object
  %(prog)s --agent-name MY_AGENT --database DB --schema SCH --question "Hello"

  # Multi-turn first message (pass thread-id from manage_threads.py create)
  %(prog)s --agent-name MY_AGENT --database DB --schema SCH \\
    --question "My name is Alice" --thread-id 12345 --parent-message-id 0

  # Multi-turn follow-up (use assistant_message_id from previous turn)
  %(prog)s --agent-name MY_AGENT --database DB --schema SCH \\
    --question "What is my name?" --thread-id 12345 --parent-message-id 67890

  # Lite / objectless run
  %(prog)s --lite-config agent_config.json --question "What is revenue?"

  # Non-streaming
  %(prog)s --agent-name MY_AGENT --database DB --schema SCH \\
    --question "Hello" --no-stream
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = parser.add_argument_group("agent mode (pick one)")
    mode.add_argument("--agent-name", help="Agent object name (object-based run)")
    mode.add_argument("--database", default="SNOWFLAKE_INTELLIGENCE", help="Database (default: SNOWFLAKE_INTELLIGENCE)")
    mode.add_argument("--schema", default="AGENTS", help="Schema (default: AGENTS)")
    mode.add_argument("--lite-config", help="JSON file with tools/tool_resources/instructions for objectless run")

    parser.add_argument("--question", required=True, help="Question to ask the agent")
    parser.add_argument("--thread-id", help="Thread ID for multi-turn conversations (from manage_threads.py create)")
    parser.add_argument("--parent-message-id", type=int, default=0, help="Parent message ID (0 for first message in thread)")
    parser.add_argument("--output-file", help="Save full response JSON to this file")
    parser.add_argument("--connection", help="Snowflake connection name")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming (get single JSON response)")
    parser.add_argument("--enable-research-mode", action="store_true", help="Enable staged reasoning agent flow type")
    parser.add_argument("--current-date-override", help="Override current date (e.g., '2024-01-15')")

    args = parser.parse_args()

    if not args.agent_name and not args.lite_config:
        parser.error("Either --agent-name (object run) or --lite-config (objectless run) is required")

    chat(
        args.question,
        agent_name=args.agent_name,
        database=args.database,
        schema=args.schema,
        connection_name=args.connection,
        thread_id=args.thread_id,
        parent_message_id=args.parent_message_id,
        output_file=args.output_file,
        lite_config_file=args.lite_config,
        enable_research_mode=args.enable_research_mode,
        current_date_override=args.current_date_override,
        stream=not args.no_stream,
    )


if __name__ == "__main__":
    main()
