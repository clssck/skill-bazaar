#!/usr/bin/env python3
"""
Get verified query suggestions for a semantic model from Snowflake Cortex Analyst.

This script calls the /api/v2/cortex/analyst/verified-query-suggestions endpoint
to get query suggestions based on query history analysis. It runs two modes in parallel:
- ca_requests_based: Suggestions based on Cortex Analyst request history
- query_history_based: Suggestions based on query history analysis

Results are merged with query_history_based taking priority.

Usage:
    python get_vqr_suggestions.py --semantic-view <semantic_view> --output <output_file> [--limit N] [--connection NAME] [--speed slow]

Example:
    python get_vqr_suggestions.py --semantic-view DB.SCHEMA.MY_SEMANTIC_VIEW --output response.json --limit 10 --connection snowhouse

    # Slow mode — also queries information_schema (more results, significantly slower):
    python get_vqr_suggestions.py --semantic-view DB.SCHEMA.MY_SEMANTIC_VIEW --output response.json --speed slow
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

import requests
from sf_connection_utils import (
    SnowflakeConnection,
    build_rest_url,
    read_connection_config,
)


def _make_api_request(
    rest_url: str,
    rest_token: str,
    semantic_view: str,
    warehouse: str,
    mode: str,
    limit: int,
    slow: bool = False,
) -> dict[str, Any]:
    """
    Make a single API request to the verified-query-suggestions endpoint.

    Args:
        rest_url: Snowflake REST API URL
        rest_token: Authentication token
        semantic_view: Semantic view name (e.g., DB.SCHEMA.VIEW_NAME)
        warehouse: Warehouse name
        mode: "ca_requests_based" or "query_history_based"
        limit: Number of suggestions to request
        slow: If True, also query information_schema sources (more results, slower)

    Returns:
        API response as dictionary

    Raises:
        Exception: If API request fails
    """
    if mode == "query_history_based":
        experimental = json.dumps(
            {
                "transform_to_logical_enabled": False,
                "transform_ca_requests_suggestions_to_logical": False,
                "use_snowscope_query_history": True,
                "use_information_schema_query_history_by_user": slow,
                "use_account_usage_query_history": False,
                "use_information_schema_query_history": slow,
            }
        )
    else:  # ca_requests_based
        experimental = json.dumps(
            {
                "transform_to_logical_enabled": False,
                "transform_ca_requests_suggestions_to_logical": False,
            }
        )

    # Build request body
    request_body = {
        "semantic_model": {
            "semantic_view": semantic_view,
        },
        "warehouse": warehouse,
        "mode": mode,
        "offset": 0,
        "limit": limit,
        "experimental": experimental,
    }

    # Make API request
    url = f"https://{rest_url}/api/v2/cortex/analyst/verified-query-suggestions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f'Snowflake Token="{rest_token}"',
    }

    print(f"⚡ Requesting suggestions (mode: {mode})...")

    response = requests.post(
        url,
        headers=headers,
        json=request_body,
        timeout=120,
    )

    if response.status_code != 200:
        error_msg = f"API request failed for mode '{mode}' (status {response.status_code}): {response.text}"
        print(f"❌ {error_msg}")
        raise Exception(error_msg)

    result = cast(dict[str, Any], response.json())

    suggestions_count = len(result.get("vq_suggestions", []))
    print(f"✅ Received {suggestions_count} suggestions (mode: {mode})")

    return result


def _merge_suggestions(
    ca_result: dict[str, Any] | BaseException,
    qh_result: dict[str, Any] | BaseException,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Merge suggestions from both API responses, prioritizing query_history_based.

    Handles partial failures by continuing with successful results.

    Args:
        ca_result: Response from ca_requests_based mode or Exception if failed
        qh_result: Response from query_history_based mode or Exception if failed
        limit: Maximum number of suggestions to return

    Returns:
        Tuple of (merged_suggestions, metadata)

    Raises:
        SystemExit: If both API requests failed
    """
    # Handle failures
    if isinstance(ca_result, BaseException) and isinstance(qh_result, BaseException):
        print("❌ Both API requests failed:")
        print(f"   ca_requests_based: {ca_result}")
        print(f"   query_history_based: {qh_result}")
        sys.exit(1)

    if isinstance(ca_result, BaseException):
        print(f"⚠️  ca_requests_based failed: {ca_result}")
        print("   Continuing with query_history_based results only")

    if isinstance(qh_result, BaseException):
        print(f"⚠️  query_history_based failed: {qh_result}")
        print("   Continuing with ca_requests_based results only")

    # Convert to dict, using empty result for failures
    ca_response: dict[str, Any] = (
        ca_result if not isinstance(ca_result, BaseException) else {}
    )
    qh_response: dict[str, Any] = (
        qh_result if not isinstance(qh_result, BaseException) else {}
    )

    ca_raw = ca_response.get("vq_suggestions", [])
    qh_raw = qh_response.get("vq_suggestions", [])

    seen_questions = {}
    merged = []

    # Add query_history_based first (priority)
    for suggestion in qh_raw:
        if suggestion.get("vq_to_add"):
            question = suggestion["vq_to_add"].get("question", "")
            if question:
                seen_questions[question] = "query_history_based"
                merged.append({"source": "query_history_based", **suggestion})

    # Add unique ca_requests_based suggestions
    for suggestion in ca_raw:
        if suggestion.get("vq_to_add"):
            question = suggestion["vq_to_add"].get("question", "")
            if question and question not in seen_questions:
                seen_questions[question] = "ca_requests_based"
                merged.append({"source": "ca_requests_based", **suggestion})

    # Limit to requested size
    merged = merged[:limit]

    # Calculate deduplication stats
    duplicates_removed = len(ca_raw) + len(qh_raw) - len(seen_questions)

    metadata = {
        "ca_requests_count": len(ca_raw),
        "query_history_count": len(qh_raw),
        "total_before_dedup": len(ca_raw) + len(qh_raw),
        "duplicates_removed": duplicates_removed,
        "merged_count": len(merged),
        "limit_applied": limit,
    }

    return merged, metadata


async def main_async(args: argparse.Namespace) -> None:
    """Main async execution function."""
    # Read connection configuration
    print("📖 Reading connection configuration...")
    config = read_connection_config(args.connection)

    # Validate required warehouse field
    if "warehouse" not in config:
        print("❌ Connection missing required field: warehouse")
        sys.exit(1)

    print(f"📖 Using semantic view: {args.semantic_view}")

    # Connect to Snowflake to get REST token
    print("🔐 Authenticating to Snowflake...")
    sf_conn = None
    try:
        sf_conn = SnowflakeConnection(args.connection or "snowhouse")
        conn = sf_conn.get_snowflake_session()

        # Get REST token
        rest_token = conn.rest.token
        rest_url = build_rest_url(config)

    except Exception as e:
        print(f"❌ Failed to connect to Snowflake: {e}")
        sys.exit(1)

    try:
        # Execute both API calls in parallel
        print(f"🚀 Launching parallel API requests (limit: {args.limit} per mode)...")

        tasks = [
            asyncio.to_thread(
                _make_api_request,
                rest_url,
                rest_token,
                args.semantic_view,
                config["warehouse"],
                "ca_requests_based",
                args.limit,
            ),
            asyncio.to_thread(
                _make_api_request,
                rest_url,
                rest_token,
                args.semantic_view,
                config["warehouse"],
                "query_history_based",
                args.limit,
                args.speed == "slow",
            ),
        ]

        ca_response, qh_response = await asyncio.gather(*tasks, return_exceptions=True)

        print("✅ Parallel execution completed")

        # Merge suggestions (handles errors internally)
        merged_suggestions, metadata = _merge_suggestions(
            ca_response, qh_response, args.limit
        )

        output_data = {
            "ca_requests_based_response": ca_response,
            "query_history_based_response": qh_response,
            "merged_suggestions": merged_suggestions,
            "metadata": metadata,
        }

        # Save to output file
        try:
            output_path = Path(args.output)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2)
            print(f"💾 Saved API responses to: {output_path}")
        except Exception as e:
            print(f"❌ Failed to save output file: {e}")
            sys.exit(1)

        # Display results to console
        if not merged_suggestions:
            print("\nℹ️  No suggestions returned from either mode")
            print("   This could mean:")
            print("   - No query history available for this semantic model")
            print("   - The semantic model is new or hasn't been used yet")
            return

        print(
            f"\n✅ Successfully merged {len(merged_suggestions)} verified query suggestions:"
        )
        print(
            f"   • query_history_based: {metadata['query_history_count']} suggestions (priority)"
        )
        print(f"   • ca_requests_based: {metadata['ca_requests_count']} suggestions")
        print(f"   • Duplicates removed: {metadata['duplicates_removed']}")
        print(f"   • Final merged count: {metadata['merged_count']}\n")

        for i, suggestion in enumerate(merged_suggestions, 1):
            source = suggestion.get("source", "unknown")
            vq_to_add = suggestion.get("vq_to_add", {})
            question = vq_to_add.get("question", "")
            sql = vq_to_add.get("sql", "")
            verified_at = vq_to_add.get("verified_at")
            score = suggestion.get("score")

            print(f"{i}. [{source}] Question: {question}")
            if score is not None:
                print(f"   Score: {score:.4f}")
            if verified_at:
                print(f"   ✓ Verified at: {verified_at}")
            if sql:
                print(f"   SQL:\n{sql}")
            print()

        print(f"📊 Total suggestions: {len(merged_suggestions)}")

    except requests.exceptions.Timeout:
        print("❌ Request timed out after 120 seconds")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        sys.exit(1)
    finally:
        if sf_conn is not None:
            sf_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Get verified query suggestions from Snowflake Cortex Analyst (dual mode)"
    )
    parser.add_argument(
        "--semantic-view",
        required=True,
        dest="semantic_view",
        help="Semantic view name (e.g., DB.SCHEMA.VIEW_NAME)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path to save raw API response",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of suggestions to return (default: 3)",
    )
    parser.add_argument(
        "--connection",
        default=os.getenv("SNOWFLAKE_CONNECTION_NAME"),
        help="Snowflake connection name (default: from env var or first available)",
    )
    parser.add_argument(
        "--speed",
        choices=["fast", "slow"],
        default="fast",
        help="fast (default): Snowscope only. slow: also queries information_schema (more results, significantly slower)",
    )

    args = parser.parse_args()

    if args.speed == "slow":
        print(
            "⚠️  Slow mode: also querying information_schema sources. "
            "This can be significantly slower than fast mode (Snowscope only)."
        )
    else:
        print("⚡ Fast mode: using Snowscope only for query history.")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
