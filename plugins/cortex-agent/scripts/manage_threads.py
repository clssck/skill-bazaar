#!/usr/bin/env python3
"""
Manage Cortex Agent Threads — create, list, describe, update, delete.

Threads API:
  POST   /api/v2/cortex/threads          → create
  GET    /api/v2/cortex/threads           → list
  GET    /api/v2/cortex/threads/{id}      → describe (includes messages)
  POST   /api/v2/cortex/threads/{id}      → update (rename)
  DELETE /api/v2/cortex/threads/{id}      → delete
"""

import argparse
import json
import os
import sys

import requests
import snowflake.connector
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _get_connection(connection_name: str | None = None):
    if connection_name is None:
        connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME", "snowhouse")
    return snowflake.connector.connect(connection_name=connection_name)


def _build_headers(token: str) -> dict:
    return {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
    }


def create_thread(connection_name: str | None = None) -> str:
    conn = _get_connection(connection_name)
    try:
        url = f"https://{conn.host}/api/v2/cortex/threads"
        resp = requests.post(url, headers=_build_headers(conn.rest.token), json={}, verify=False)
        if resp.status_code not in (200, 201):
            print(f"Error creating thread: {resp.status_code}\n{resp.text}", file=sys.stderr)
            sys.exit(1)
        body = resp.json()
        if isinstance(body, dict):
            thread_id = body.get("thread_id", "")
            print(f"Thread created: {thread_id}")
            print(json.dumps(body, indent=2))
        else:
            thread_id = str(body)
            print(f"Thread created: {thread_id}")
        return str(thread_id)
    finally:
        conn.close()


def list_threads(connection_name: str | None = None, limit: int = 20):
    conn = _get_connection(connection_name)
    try:
        url = f"https://{conn.host}/api/v2/cortex/threads"
        params = {"limit": limit}
        resp = requests.get(url, headers=_build_headers(conn.rest.token), params=params, verify=False)
        if resp.status_code != 200:
            print(f"Error listing threads: {resp.status_code}\n{resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        if isinstance(data, list):
            threads = data
        else:
            threads = data.get("threads", data.get("items", [data]))
        print(f"Found {len(threads)} thread(s):\n")
        for t in threads:
            if isinstance(t, dict):
                tid = t.get("thread_id", t.get("id", "?"))
                name = t.get("thread_name", t.get("name", ""))
                print(f"  {tid}  {name}")
            else:
                print(f"  {t}")
        return threads
    finally:
        conn.close()


def describe_thread(thread_id: str, connection_name: str | None = None, output_file: str | None = None):
    conn = _get_connection(connection_name)
    try:
        url = f"https://{conn.host}/api/v2/cortex/threads/{thread_id}"
        resp = requests.get(url, headers=_build_headers(conn.rest.token), verify=False)
        if resp.status_code != 200:
            print(f"Error describing thread: {resp.status_code}\n{resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        print(json.dumps(data, indent=2))
        if output_file:
            with open(output_file, "w") as f:
                json.dump(data, f, indent=2)
            print(f"\nSaved to {output_file}")
        return data
    finally:
        conn.close()


def update_thread(thread_id: str, name: str, connection_name: str | None = None):
    conn = _get_connection(connection_name)
    try:
        url = f"https://{conn.host}/api/v2/cortex/threads/{thread_id}"
        resp = requests.post(url, headers=_build_headers(conn.rest.token), json={"thread_name": name}, verify=False)
        if resp.status_code not in (200, 204):
            print(f"Error updating thread: {resp.status_code}\n{resp.text}", file=sys.stderr)
            sys.exit(1)
        print(f"Thread {thread_id} renamed to '{name}'")
    finally:
        conn.close()


def delete_thread(thread_id: str, connection_name: str | None = None):
    conn = _get_connection(connection_name)
    try:
        url = f"https://{conn.host}/api/v2/cortex/threads/{thread_id}"
        resp = requests.delete(url, headers=_build_headers(conn.rest.token), verify=False)
        if resp.status_code not in (200, 204):
            print(f"Error deleting thread: {resp.status_code}\n{resp.text}", file=sys.stderr)
            sys.exit(1)
        print(f"Thread {thread_id} deleted")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Manage Cortex Agent Threads (create, list, describe, update, delete)",
        epilog="""
Examples:
  %(prog)s create
  %(prog)s list --limit 10
  %(prog)s describe --thread-id <UUID>
  %(prog)s describe --thread-id <UUID> --output-file thread.json
  %(prog)s update  --thread-id <UUID> --name "My conversation"
  %(prog)s delete  --thread-id <UUID>
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="action", required=True)

    create_p = sub.add_parser("create", help="Create a new thread")
    create_p.add_argument("--connection", help="Snowflake connection name")

    list_p = sub.add_parser("list", help="List threads")
    list_p.add_argument("--limit", type=int, default=20, help="Max threads to return (default 20)")
    list_p.add_argument("--connection", help="Snowflake connection name")

    desc_p = sub.add_parser("describe", help="Describe a thread (show messages)")
    desc_p.add_argument("--thread-id", required=True, help="Thread UUID")
    desc_p.add_argument("--output-file", help="Save thread JSON to file")
    desc_p.add_argument("--connection", help="Snowflake connection name")

    upd_p = sub.add_parser("update", help="Update thread name")
    upd_p.add_argument("--thread-id", required=True, help="Thread UUID")
    upd_p.add_argument("--name", required=True, help="New thread name")
    upd_p.add_argument("--connection", help="Snowflake connection name")

    del_p = sub.add_parser("delete", help="Delete a thread")
    del_p.add_argument("--thread-id", required=True, help="Thread UUID")
    del_p.add_argument("--connection", help="Snowflake connection name")

    args = parser.parse_args()

    if args.action == "create":
        create_thread(args.connection)
    elif args.action == "list":
        list_threads(args.connection, args.limit)
    elif args.action == "describe":
        describe_thread(args.thread_id, args.connection, getattr(args, "output_file", None))
    elif args.action == "update":
        update_thread(args.thread_id, args.name, args.connection)
    elif args.action == "delete":
        delete_thread(args.thread_id, args.connection)


if __name__ == "__main__":
    main()
