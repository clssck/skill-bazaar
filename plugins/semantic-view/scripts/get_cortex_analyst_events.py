#!/usr/bin/env python3
"""
Get Cortex Analyst events from CORTEX_ANALYST_REQUESTS table.

Fetches and groups Cortex Analyst requests by source with automatic deduplication
and feedback analysis. See reference/get_cortex_analyst_events.md for usage details.
"""

import argparse
import json
from typing import Any, Dict, List, Optional, Tuple

import snowflake.connector


def parse_agent_full_name(agent_full_name: str) -> Tuple[str, str, str]:
    """Parse 'DATABASE.SCHEMA.AGENT_NAME' into components."""
    parts = agent_full_name.split(".")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid agent full name format: {agent_full_name}. "
            f"Expected 'DATABASE.SCHEMA.AGENT_NAME'"
        )
    return parts[0], parts[1], parts[2]


def parse_feedback_from_row(row_dict: Dict[str, Any]) -> str:
    """Parse feedback from row, prioritizing agent feedback over analyst request feedback."""
    # Try agent feedback first
    agent_value = row_dict.get("agent_feedback_value")
    if agent_value:
        try:
            parsed = (
                json.loads(agent_value) if isinstance(agent_value, str) else agent_value
            )
            if isinstance(parsed, dict):
                positive = parsed.get("positive")
                if positive is not None:
                    return "positive" if positive else "negative"
        except (json.JSONDecodeError, TypeError):
            pass

    # Then try CORTEX_ANALYST_REQUESTS feedback
    analyst_value = row_dict.get("feedback")
    if analyst_value:
        try:
            parsed = (
                json.loads(analyst_value)
                if isinstance(analyst_value, str)
                else analyst_value
            )
            if isinstance(parsed, list) and len(parsed) > 0:
                last = parsed[-1]
                if isinstance(last, dict):
                    positive = last.get("positive")
                    if positive is not None:
                        return "positive" if positive else "negative"
        except (json.JSONDecodeError, TypeError):
            pass

    return ""


def build_sql_query(
    semantic_view_type: str,
    semantic_view_name: str,
    where_clause: str,
    order_by_clause: str,
    limit: int,
    agent_full_name: Optional[str] = None,
    request_ids: Optional[List[str]] = None,
) -> str:
    """Build SQL query with optional agent feedback JOIN and request ID filtering."""
    # Build WHERE clause with optional request ID filtering
    where_conditions = [where_clause] if where_clause else []
    if request_ids:
        ids_list = "', '".join(request_ids)
        request_id_filter = (
            f"(request_id IN ('{ids_list}') OR "
            f"PARSE_JSON(source):\"agent_request_id\"::STRING IN ('{ids_list}'))"
        )
        where_conditions.append(request_id_filter)

    final_where = " AND ".join(where_conditions) if where_conditions else "1=1"
    final_query_filter = f"{final_where} {order_by_clause}".strip()

    # Base CTE (always included)
    base_cte = f"""
    WITH analyst_requests AS (
      SELECT *
      FROM TABLE(SNOWFLAKE.LOCAL.CORTEX_ANALYST_REQUESTS(
        '{semantic_view_type}',
        '{semantic_view_name}'
      ))
      WHERE {final_query_filter}
      LIMIT {limit}
    )
    """

    # Conditionally add agent feedback CTE and JOIN
    if agent_full_name:
        agent_db, agent_schema, agent_name = parse_agent_full_name(agent_full_name)
        agent_feedback_cte = f"""
        , agent_feedback AS (
          SELECT
            PARSE_JSON(ar.source):"agent_request_id"::STRING as record_id,
            MAX_BY(obs.value, obs.timestamp) as value
          FROM analyst_requests ar
          INNER JOIN TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
            '{agent_db}',
            '{agent_schema}',
            '{agent_name}',
            'CORTEX AGENT'
          )) obs
            ON PARSE_JSON(ar.source):"agent_request_id"::STRING = obs.record_attributes:"ai.observability.record_id"::STRING
          WHERE obs.record:"name" = 'CORTEX_AGENT_FEEDBACK'
            AND PARSE_JSON(ar.source):"agent_request_id" IS NOT NULL
          GROUP BY PARSE_JSON(ar.source):"agent_request_id"::STRING
        )
        """
        final_select = """
        SELECT ar.*, af.value as agent_feedback_value
        FROM analyst_requests ar
        LEFT JOIN agent_feedback af
          ON PARSE_JSON(ar.source):"agent_request_id"::STRING = af.record_id
        """
    else:
        agent_feedback_cte = ""
        final_select = "SELECT * FROM analyst_requests"

    return base_cte + agent_feedback_cte + final_select


def get_cortex_analyst_events(
    semantic_view_type: str,
    semantic_view_name: str,
    connection_name: str = "snowhouse",
    where_clause: str = "timestamp >= dateadd(day, -7, current_timestamp())",
    order_by_clause: str = "ORDER BY timestamp DESC",
    limit: int = 25,
    agent_full_name: Optional[str] = None,
    request_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Get Cortex Analyst events from CORTEX_ANALYST_REQUESTS table, grouped by source.

    Returns results grouped by source (agent_request_id or request_id) with automatic
    deduplication and feedback aggregation. See reference/get_cortex_analyst_events.md
    for detailed usage information.
    """
    conn = snowflake.connector.connect(connection_name=connection_name)
    cursor = None
    try:
        cursor = conn.cursor()

        # Execute query
        sql = build_sql_query(
            semantic_view_type=semantic_view_type,
            semantic_view_name=semantic_view_name,
            where_clause=where_clause,
            order_by_clause=order_by_clause,
            limit=limit,
            agent_full_name=agent_full_name,
            request_ids=request_ids,
        )

        print("Querying CORTEX_ANALYST_REQUESTS table")
        print(f"  Type: {semantic_view_type}")
        print(f"  Name: {semantic_view_name}")
        print(f"  Filter: {where_clause}")
        print(f"  Order: {order_by_clause}")
        print(f"  Limit: {limit}")
        if agent_full_name:
            print(f"  Agent: {agent_full_name} (with feedback lookup)")
        if request_ids:
            print(f"  Request IDs: {', '.join(request_ids)}")

        print(f"\nGenerated SQL:\n{sql}\n")

        cursor.execute(sql)

        column_names = [desc[0].lower() for desc in cursor.description]
        rows = cursor.fetchall()
        print(f"\nRetrieved {len(rows)} records")

        # Process and group records by source
        source_groups: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            try:
                row_dict = dict(zip(column_names, row))

                # Extract fields from row
                request_id = row_dict.get("request_id")
                source_field = row_dict.get("source")
                latest_question = row_dict.get("latest_question")
                generated_sql = row_dict.get("generated_sql")

                # Determine source: use agent_request_id if present, otherwise request_id
                source_id = request_id
                if source_field:
                    try:
                        if isinstance(source_field, str):
                            source_json = json.loads(source_field)
                        else:
                            source_json = source_field

                        if (
                            isinstance(source_json, dict)
                            and "agent_request_id" in source_json
                        ):
                            source_id = source_json["agent_request_id"]
                    except (json.JSONDecodeError, TypeError):
                        pass
                if not source_id:
                    continue

                # Initialize source group
                if source_id not in source_groups:
                    source_groups[source_id] = {
                        "requests": [],
                        "questions_seen": set(),
                        "feedback": "",
                    }

                # Add request with deduplication by question (skip if no SQL generated)
                if (
                    generated_sql
                    and latest_question
                    and latest_question
                    not in source_groups[source_id]["questions_seen"]
                ):
                    source_groups[source_id]["questions_seen"].add(latest_question)
                    source_groups[source_id]["requests"].append(
                        {
                            "request_id": request_id,
                            "latest_question": latest_question,
                            "generated_sql": generated_sql,
                        }
                    )

                # Parse and set feedback (priority: agent feedback > CORTEX_ANALYST_REQUESTS feedback)
                if not source_groups[source_id]["feedback"]:
                    source_groups[source_id]["feedback"] = parse_feedback_from_row(
                        row_dict
                    )

            except Exception as e:
                print(f"Warning: Failed to parse record: {e}")
                continue

        # Build final output
        results = []
        for source_id, group_data in source_groups.items():
            results.append(
                {
                    "source": source_id,
                    "requests": group_data["requests"],
                    "feedback": group_data["feedback"],
                }
            )

        print(f"Grouped into {len(results)} sources")

        return results

    finally:
        if cursor:
            cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get Cortex Analyst events from CORTEX_ANALYST_REQUESTS table. See reference/get_cortex_analyst_events.md for usage details."
    )

    parser.add_argument(
        "semantic_view_type", help="Semantic view type (e.g., SEMANTIC_VIEW)"
    )
    parser.add_argument(
        "semantic_view_name",
        help="Semantic view name (e.g., DATABASE.SCHEMA.SEMANTIC_VIEW_NAME)",
    )
    parser.add_argument(
        "--agent-full-name",
        help="Agent full name in format DATABASE.SCHEMA.AGENT_NAME (enables agent feedback lookup)",
    )
    parser.add_argument(
        "--request-ids",
        help="Comma-separated list of request IDs to filter. Can be either analyst request IDs or agent request IDs (e.g., 'id1,id2,id3')",
    )
    parser.add_argument(
        "--connection",
        default="snowhouse",
        help="Snowflake connection name (default: snowhouse)",
    )
    parser.add_argument(
        "--where",
        default="timestamp >= dateadd(day, -7, current_timestamp())",
        help="WHERE clause for filtering (default: last 7 days)",
    )
    parser.add_argument(
        "--order-by",
        default="ORDER BY timestamp DESC",
        help="ORDER BY clause (default: ORDER BY timestamp DESC)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of records before grouping (default: 25)",
    )
    parser.add_argument(
        "--output", help="Path to save results as JSON (default: print to console)"
    )

    args = parser.parse_args()

    # Parse request IDs with trimming
    request_ids = (
        [rid.strip() for rid in args.request_ids.split(",")]
        if args.request_ids
        else None
    )

    events = get_cortex_analyst_events(
        semantic_view_type=args.semantic_view_type,
        semantic_view_name=args.semantic_view_name,
        connection_name=args.connection,
        where_clause=args.where,
        order_by_clause=args.order_by,
        limit=args.limit,
        agent_full_name=args.agent_full_name,
        request_ids=request_ids,
    )

    # Output results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(events, f, indent=2)
        print(f"\n✓ Saved {len(events)} source groups to: {args.output}")
    else:
        print(f"\n{'='*80}")
        print("RESULTS")
        print("=" * 80 + "\n")
        print(json.dumps(events, indent=2))
