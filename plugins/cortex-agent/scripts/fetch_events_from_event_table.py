#!/usr/bin/env python3
"""
Fetch evaluation questions from AI Observability Event Table.

This script provides functions to query the event table and extract evaluation questions
from the record_attributes JSON field. Questions can be deduplicated, filtered, and
optionally include full trace data. Feedback data is automatically fetched for each question.

COMMAND-LINE USAGE:
    python fetch_events_from_event_table.py <agent_name> <database> <schema> [OPTIONS]

    # Fast path — only a request/record ID (same SQL as debug-single-query skill):
    python fetch_events_from_event_table.py --request-id <UUID> [--connection NAME] [--limit N] [--output PATH]

COMMAND-LINE OPTIONS:
    --connection CONNECTION        Snowflake connection name (default: snowhouse)
    --output OUTPUT               Path to save questions as JSON (default: print to console)
    --where WHERE_CLAUSE          Additional WHERE clause conditions
    --limit N                     Maximum number of records to return
    --unique                      Deduplicate questions by question text
    --raw-trace                   Return raw trace instead of summary (default: summarize traces)
    --dangerously-fetch-events    WARNING: Directly query table, bypassing authorization checks

COMMAND-LINE EXAMPLES:
    # Fetch all events for an agent:
    python fetch_events_from_event_table.py RAVEN_SALES_ASSISTANT SNOWFLAKE_INTELLIGENCE AGENTS
    
    # Fetch last 10 unique questions with summarized traces (default):
    python fetch_events_from_event_table.py MY_AGENT MY_DB MY_SCHEMA \\
        --where "ORDER BY timestamp DESC" --limit 10 --unique
    
    # Fetch with raw (unsummarized) traces:
    python fetch_events_from_event_table.py MY_AGENT MY_DB MY_SCHEMA \\
        --raw-trace --output ./questions.json
    
    # Get 20 questions from last 30 days:
    python fetch_events_from_event_table.py MY_AGENT MY_DB MY_SCHEMA \\
        --where "timestamp > dateadd(day, -30, current_timestamp())" --limit 20

LIBRARY USAGE:
    from fetch_events_from_event_table import (
        fetch_events_by_request_id_only,
        fetch_events_from_event_table,
    )

    # Fast path by request/record ID only (AI_OBSERVABILITY_EVENTS, no agent FQN):
    rows = fetch_events_by_request_id_only("550e8400-e29b-41d4-a716-446655440000", connection_name="default")

    # Get all questions with summarized traces (default):
    questions = fetch_events_from_event_table('MY_AGENT', 'MY_DB', 'MY_SCHEMA')
    
    # Get last 10 unique questions with summarized traces:
    questions = fetch_events_from_event_table(
        'MY_AGENT', 'MY_DB', 'MY_SCHEMA',
        where_clause="ORDER BY timestamp DESC",
        limit=10,
        unique=True
    )
    
    # Get raw (unsummarized) traces:
    questions = fetch_events_from_event_table(
        'MY_AGENT', 'MY_DB', 'MY_SCHEMA',
        raw_trace=True
    )
"""

import json
import argparse
import logging
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import snowflake.connector
from typing import List, Dict, Any, Optional

import pandas as pd
from trulens.core.feedback.selector import Trace
from trulens.otel.semconv.trace import SpanAttributes as TruLensSpanAttributes

# Configure logging
logger = logging.getLogger(__name__)

# Add parent directory to path for imports (required before local imports below)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Local imports (must come after sys.path modification)
from scripts.summarize_traces import summarize_trace as create_trace_summary  # noqa: E402

# Event table constants
EVENT_TABLE_DB = "SNOWFLAKE"
EVENT_TABLE_SCHEMA = "LOCAL"
EVENT_TABLE_FUNCTION = "GET_AI_OBSERVABILITY_EVENTS"
EVENT_TABLE_NAME = "AI_OBSERVABILITY_EVENTS"

# Agent and Record Type Constants
AGENT_TYPE = "CORTEX AGENT"
FEEDBACK_RECORD_NAME = "CORTEX_AGENT_FEEDBACK"

# Record field names
RECORD_FIELD_NAME = 'name'

# Output dictionary keys
OUTPUT_KEY_QUESTION = 'question'
OUTPUT_KEY_ANSWER = 'answer'
OUTPUT_KEY_GROUND_TRUTH = 'ground_truth'
OUTPUT_KEY_RECORD_ID = 'record_id'
OUTPUT_KEY_TRACE = 'trace'
OUTPUT_KEY_FEEDBACK = 'feedback'
OUTPUT_KEY_TRACE_EVENTS = 'trace_events'
EVENT_TABLE_COLUMN_TIMESTAMP = 'timestamp'
EVENT_TABLE_COLUMN_START_TIMESTAMP = 'start_timestamp'
OUTPUT_KEY_VALUE = 'value'

# Default row cap for --request-id mode (matches skill fast-path SQL LIMIT)
REQUEST_ID_ONLY_DEFAULT_LIMIT = 50

# Snowflake event table column names that contain JSON
JSON_FIELDS = ['record', 'record_attributes', 'trace', 'resource_attributes', 'value']

# Snowflake event table column names that contain timestamps
TIMESTAMP_FIELDS = [EVENT_TABLE_COLUMN_START_TIMESTAMP, EVENT_TABLE_COLUMN_TIMESTAMP]

def escape_sql_string(value: str) -> str:
    """Escape single quotes in SQL string literals to prevent SQL injection."""
    return value.replace("'", "''")


def validate_filter_prompt(prompt: str) -> tuple[bool, str]:
    """
    Validate a filter prompt for potentially problematic characters.
    
    Args:
        prompt: The filter prompt to validate
        
    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    if not prompt or not prompt.strip():
        return True, ""
    
    # Check for null bytes which can cause issues
    if '\x00' in prompt:
        return False, "Filter contains null bytes which are not allowed"
    
    # Check for extremely long prompts (>1000 chars is probably a mistake)
    if len(prompt) > 1000:
        return False, f"Filter is too long ({len(prompt)} characters). Maximum is 1000 characters"
    
    # Warn about multiple consecutive quotes (might be a mistake)
    if "''" in prompt or '""' in prompt:
        # This is actually OK after escaping, but log a warning
        logger.warning(f"Filter contains consecutive quotes: {prompt[:50]}...")
    
    return True, ""


def build_ai_filter_clause(prompt: str, field_attr: str, field_name: str) -> str:
    """
    Build an AI_FILTER clause for natural language filtering on event table fields.
    
    Args:
        prompt: Natural language filter prompt
        field: Field name to filter on (e.g., "ai.observability.record_root.input")
        
    Returns:
        AI_FILTER SQL clause string
    """
    # Escape single quotes to prevent SQL injection
    escaped_prompt = escape_sql_string(prompt)
    return f"AI_FILTER(PROMPT('Check if the <{field_name}> matches the user''s search criteria. <CRITERIA>: {escaped_prompt}. <{field_name}>: {{0}}', RECORD_ATTRIBUTES:\"{field_attr}\"))"


def build_where_clause_with_ai_filters(
    where_clause: Optional[str],
    question_filter: Optional[str],
    answer_filter: Optional[str],
    strict_validation: bool = False
) -> Optional[str]:
    """
    Combine a base WHERE clause with AI filters for questions and answers.
    
    Args:
        where_clause: Base WHERE clause (or None)
        question_filter: Natural language filter for questions (or None)
        answer_filter: Natural language filter for answers (or None)
        strict_validation: If True, validate filter prompts for problematic characters (default: False)
        
    Returns:
        Combined WHERE clause with AI filters, or None if no filters
        
    Raises:
        ValueError: If strict_validation=True and any filter prompt contains invalid characters
    """
    ai_filters = []
    
    if question_filter:
        # Validate question filter if validation is enabled
        if strict_validation:
            is_valid, error_msg = validate_filter_prompt(question_filter)
            if not is_valid:
                raise ValueError(f"Invalid question filter: {error_msg}")
        ai_filters.append(build_ai_filter_clause(question_filter, field_attr="ai.observability.record_root.input", field_name="question"))
    
    if answer_filter:
        # Validate answer filter if validation is enabled
        if strict_validation:
            is_valid, error_msg = validate_filter_prompt(answer_filter)
            if not is_valid:
                raise ValueError(f"Invalid answer filter: {error_msg}")
        ai_filters.append(build_ai_filter_clause(answer_filter, field_attr="ai.observability.record_root.output", field_name="answer"))
    
    if not ai_filters:
        return where_clause
    
    combined_ai_filters = " AND ".join(ai_filters)
    
    if not where_clause:
        return combined_ai_filters
    
    if where_clause.strip().upper().startswith('ORDER BY'):
        return f"{combined_ai_filters} {where_clause}"
    
    return f"{combined_ai_filters} AND {where_clause}"


def filter_traces_client_side(events: List[Dict], trace_filter: str, connection) -> List[Dict]:
    """
    Filter events using natural language queries on trace data.
    
    This performs client-side filtering by calling CORTEX.COMPLETE for each event's trace.
    Use this for trace filtering since traces are constructed post-query.
    
    Args:
        events: List of event dictionaries with 'trace' field
        trace_filter: Natural language filter query (e.g., "used chart generation tool")
        connection: Active Snowflake connection
        
    Returns:
        Filtered list of events matching the trace filter
    """
    if not trace_filter:
        return events
    
    filtered_events = []
    
    try:
        cursor = connection.cursor()
        
        for event in events:
            trace = event.get('trace', {})
            trace_str = json.dumps(trace)
            
            prompt = f"Does this trace show that the agent {trace_filter}? Answer only yes or no.\n\nTrace: {trace_str}"
            
            cursor.execute(
                "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS result",
                ('claude-sonnet-4-5', prompt)
            )
            result = cursor.fetchone()
            response = str(result[0]).lower() if result else ""
            
            if 'yes' in response:
                filtered_events.append(event)
        
        cursor.close()
        
        return filtered_events
    
    except Exception as e:
        logger.error(f"Trace filtering failed: {str(e)}")
        return events


def _parse_json_if_string(value: Any) -> Any:
    """
    Parse JSON field that may be a string or already parsed.
    
    Args:
        value: Value that may be JSON string or already parsed object
        
    Returns:
        Parsed JSON object if value was a string, otherwise returns value as-is
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Keep as string if not valid JSON
            return value
    return value


def parse_question_from_row(row: tuple, column_names: List[str]) -> Optional[Dict[str, Any]]:
    """
    Parse question data from a single event table row.
    
    Args:
        row: Raw row tuple from cursor
        column_names: Column names from cursor description
        
    Returns:
        Dictionary with question, answer, ground_truth, record_id, timestamp, start_timestamp or None if parsing fails
    """
    try:
        # Convert row to dict using column names
        row_dict = dict(zip(column_names, row))
        
        # Parse record_attributes JSON
        record_attributes = _parse_json_if_string(row_dict.get('record_attributes'))
        
        # Extract fields from record_attributes
        question = record_attributes.get(TruLensSpanAttributes.RECORD_ROOT.INPUT)
        answer = record_attributes.get(TruLensSpanAttributes.RECORD_ROOT.OUTPUT)
        ground_truth = record_attributes.get(TruLensSpanAttributes.RECORD_ROOT.GROUND_TRUTH_OUTPUT)
        record_id = record_attributes.get(TruLensSpanAttributes.RECORD_ID)
        
        # Skip if no question
        if not question:
            return None
        
        # Extract timestamp (convert to string if datetime object)
        timestamp = row_dict.get(EVENT_TABLE_COLUMN_TIMESTAMP)
        start_timestamp = row_dict.get(EVENT_TABLE_COLUMN_START_TIMESTAMP)
        
        # Build and return question data
        return {
            OUTPUT_KEY_QUESTION: question,
            OUTPUT_KEY_ANSWER: answer,
            OUTPUT_KEY_GROUND_TRUTH: ground_truth,
            OUTPUT_KEY_RECORD_ID: record_id,
            EVENT_TABLE_COLUMN_TIMESTAMP: str(timestamp) if timestamp else None,
            EVENT_TABLE_COLUMN_START_TIMESTAMP: str(start_timestamp) if start_timestamp else None,
        }
        
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse event record: {e}")
        return None


def fetch_all_events_for_records(
    cursor,
    database: str,
    schema: str,
    agent_name: str,
    record_ids: List[str],
    dangerously_fetch_events: bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch all events (traces + feedback) for multiple record_ids in a single query.
    
    This is a major performance optimization that reduces N queries to 1 query.
    
    Args:
        cursor: Snowflake cursor
        database (str): Database where the agent is located
        schema (str): Schema where the agent is located
        agent_name (str): Name of the agent
        record_ids (list[str]): List of record IDs to fetch events for
        
    Returns:
        dict[str, dict]: Dictionary mapping record_id to event data:
                        {
                            'record_id_1': {
                                'trace_events': [...],  # All non-feedback events
                                'feedback': [...]       # All feedback events
                            },
                            ...
                        }
    """
    if not record_ids:
        return {}
    
    # Build IN clause for all record_ids
    record_ids_str = "', '".join([escape_sql_string(rid) for rid in record_ids])
    
    # Build SQL query - either use safe UDTF or dangerous direct table access
    if dangerously_fetch_events:
        # WARNING: Directly query the table, bypassing authorization checks
        batch_sql = f"""
    SELECT *
    FROM {EVENT_TABLE_DB}.{EVENT_TABLE_SCHEMA}.{EVENT_TABLE_NAME}
    WHERE RECORD_ATTRIBUTES:"snow.ai.observability.database.name" = '{escape_sql_string(database)}'
    AND RECORD_ATTRIBUTES:"snow.ai.observability.schema.name" = '{escape_sql_string(schema)}'
    AND RECORD_ATTRIBUTES:"snow.ai.observability.object.name" = '{escape_sql_string(agent_name)}'
    AND RECORD_ATTRIBUTES:"{TruLensSpanAttributes.RECORD_ID}" IN ('{record_ids_str}')
    ORDER BY RECORD_ATTRIBUTES:"{TruLensSpanAttributes.RECORD_ID}", START_TIMESTAMP ASC
    """
    else:
        batch_sql = f"""
    SELECT *
    FROM TABLE({EVENT_TABLE_DB}.{EVENT_TABLE_SCHEMA}.{EVENT_TABLE_FUNCTION}(
        '{escape_sql_string(database)}',
        '{escape_sql_string(schema)}',
        '{escape_sql_string(agent_name)}',
        '{AGENT_TYPE}'
    ))
    WHERE RECORD_ATTRIBUTES:"{TruLensSpanAttributes.RECORD_ID}" IN ('{record_ids_str}')
    ORDER BY RECORD_ATTRIBUTES:"{TruLensSpanAttributes.RECORD_ID}", START_TIMESTAMP ASC
    """
    
    cursor.execute(batch_sql)
    
    # Get column names
    column_names = [desc[0].lower() for desc in cursor.description]
    
    # Fetch all events
    all_rows = cursor.fetchall()
    
    # Group events by record_id
    events_by_record = {}
    
    for row in all_rows:
        row_dict = dict(zip(column_names, row))
        
        # Parse JSON fields
        for json_field in JSON_FIELDS:
            if json_field in row_dict and row_dict[json_field]:
                row_dict[json_field] = _parse_json_if_string(row_dict[json_field])
        
        # Convert timestamps to ISO format strings
        for ts_field in TIMESTAMP_FIELDS:
            if ts_field in row_dict and row_dict[ts_field]:
                row_dict[ts_field] = str(row_dict[ts_field])
        
        # Get record_id
        record_attributes = row_dict.get('record_attributes', {})
        record_id = record_attributes.get(TruLensSpanAttributes.RECORD_ID)
        
        if not record_id:
            continue
        
        # Initialize record entry if needed
        if record_id not in events_by_record:
            events_by_record[record_id] = {
                OUTPUT_KEY_TRACE_EVENTS: [],
                OUTPUT_KEY_FEEDBACK: []
            }
        
        # Check if this is a feedback event
        record = row_dict.get('record', {})
        if record.get(RECORD_FIELD_NAME) == FEEDBACK_RECORD_NAME:
            # This is feedback
            timestamp = row_dict.get(EVENT_TABLE_COLUMN_TIMESTAMP)
            value = row_dict.get(OUTPUT_KEY_VALUE)
            events_by_record[record_id][OUTPUT_KEY_FEEDBACK].append({
                EVENT_TABLE_COLUMN_TIMESTAMP: timestamp,
                OUTPUT_KEY_VALUE: value
            })
        else:
            # This is a trace event
            events_by_record[record_id][OUTPUT_KEY_TRACE_EVENTS].append(row_dict)
    
    return events_by_record


# TODO: parallelize
def _add_trace_and_feedback_data(
    cursor,
    questions: List[Dict[str, Any]],
    database: str,
    schema: str,
    agent_name: str,
    raw_trace: bool,
    dangerously_fetch_events: bool = False
) -> None:
    """
    Add trace and feedback data to questions by batch fetching events.
    
    Modifies the questions list in-place by adding 'trace' and 'feedback' keys.
    
    Args:
        cursor: Snowflake cursor for database queries
        questions: List of question dictionaries to enrich
        database: Database where the agent is located
        schema: Schema where the agent is located
        agent_name: Name of the agent
        raw_trace: If True, use raw trace data; if False, summarize traces
    """
    # Batch fetch all events (traces + feedback) for all questions in a single query
    # This is a major performance optimization: 2N queries → 1 query
    record_ids = [q.get('record_id') for q in questions if q.get('record_id')]
    
    if not record_ids:
        logger.info("No valid record_ids to fetch events for")
        for question in questions:
            question[OUTPUT_KEY_FEEDBACK] = []
            question[OUTPUT_KEY_TRACE] = None
        return
    
    logger.info(f"Batch fetching traces and feedback for {len(record_ids)} records...")
    
    try:
        events_by_record = fetch_all_events_for_records(
            cursor=cursor,
            database=database,
            schema=schema,
            agent_name=agent_name,
            record_ids=record_ids,
            dangerously_fetch_events=dangerously_fetch_events
        )
        logger.info(f"Retrieved events for {len(events_by_record)} records")
        
        # Now process each question with its events
        logger.info("Processing traces and feedback...")
        for i, question in enumerate(questions):
            record_id = question.get(OUTPUT_KEY_RECORD_ID)
            
            # Add feedback (always present, even if empty list)
            if record_id and record_id in events_by_record:
                question[OUTPUT_KEY_FEEDBACK] = events_by_record[record_id][OUTPUT_KEY_FEEDBACK]
            else:
                question[OUTPUT_KEY_FEEDBACK] = []
            
            # Add trace (always included)
            if record_id and record_id in events_by_record:
                trace_events = events_by_record[record_id][OUTPUT_KEY_TRACE_EVENTS]
                
                if trace_events:
                    try:
                        # Convert to DataFrame for TruLens processing
                        # TODO: Consider removing pandas and Trace dependencies here and directly using trace_events
                        events_df = pd.DataFrame(trace_events)
                        
                        trace = Trace()
                        trace.events = events_df
                        
                        # Get uncompressed trace data
                        trace_json_str = (
                            trace.events.to_json(default_handler=str)
                            if trace.events is not None
                            else "{}"
                        )
                        
                        trace_data = json.loads(trace_json_str)
                        
                        # Summarize if not raw_trace, otherwise use raw trace data
                        if not raw_trace:
                            question[OUTPUT_KEY_TRACE] = create_trace_summary(trace_data)
                        else:
                            question[OUTPUT_KEY_TRACE] = trace_data
                    except Exception as e:
                        logger.warning(f"Failed to process trace for record_id {record_id}: {e}")
                        question[OUTPUT_KEY_TRACE] = None
                else:
                    question[OUTPUT_KEY_TRACE] = {}
            else:
                question[OUTPUT_KEY_TRACE] = None
            
            if (i + 1) % 10 == 0:
                logger.debug(f"Processed {i + 1}/{len(questions)} records...")
        
        logger.info("Completed processing all traces and feedback")
        
    except Exception as e:
        logger.error(f"Error fetching trace and feedback data: {e}")
        logger.warning("Setting empty trace and feedback for all questions")
        
        # Set empty data on failure
        for question in questions:
            question[OUTPUT_KEY_FEEDBACK] = []
            question[OUTPUT_KEY_TRACE] = None


def _coerce_row_for_json(row_dict: Dict[str, Any]) -> None:
    """Normalize Snowflake driver types so json.dump accepts every top-level column."""
    for key, val in list(row_dict.items()):
        if isinstance(val, (datetime, date)):
            row_dict[key] = str(val)
        elif isinstance(val, Decimal):
            row_dict[key] = str(val)


def fetch_events_by_request_id_only(
    request_id: str,
    connection_name: str = "snowhouse",
    limit: int = REQUEST_ID_ONLY_DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """
    Load AI observability rows for a single request/record ID using the skill fast-path SQL.

    Queries SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS (no agent FQN). Does not call
    GET_AI_OBSERVABILITY_EVENTS or attach summarized traces.

    Args:
        request_id: Value of RECORD_ATTRIBUTES:\"ai.observability.record_id\" for the run.
        connection_name: Snowflake connection name (default: snowhouse).
        limit: Max rows (default REQUEST_ID_ONLY_DEFAULT_LIMIT, capped at 10000).

    Returns:
        List of row dicts (column names lowercased, JSON/timestamp fields normalized).
    """
    rid = str(request_id).strip()
    if not rid:
        raise ValueError("request_id must be non-empty")

    lim = max(1, min(int(limit), 10_000))
    escaped = escape_sql_string(rid)
    record_key = TruLensSpanAttributes.RECORD_ID
    sql = f"""
SELECT *
FROM {EVENT_TABLE_DB}.{EVENT_TABLE_SCHEMA}.{EVENT_TABLE_NAME}
WHERE RECORD_ATTRIBUTES:"{record_key}"::STRING = '{escaped}'
LIMIT {lim}
"""

    conn = snowflake.connector.connect(connection_name=connection_name)
    cursor = None
    try:
        cursor = conn.cursor()
        logger.info("Querying AI_OBSERVABILITY_EVENTS by request_id (fast path, no agent FQN)")
        logger.info(f"Query SQL: {sql}")
        cursor.execute(sql)
        column_names = [desc[0].lower() for desc in cursor.description]
        rows = cursor.fetchall()
        logger.info(f"Retrieved {len(rows)} event rows")

        out: List[Dict[str, Any]] = []
        for row in rows:
            row_dict = dict(zip(column_names, row))
            for json_field in JSON_FIELDS:
                if json_field in row_dict and row_dict[json_field]:
                    row_dict[json_field] = _parse_json_if_string(row_dict[json_field])
            for ts_field in TIMESTAMP_FIELDS:
                if ts_field in row_dict and row_dict[ts_field] is not None:
                    row_dict[ts_field] = str(row_dict[ts_field])
            _coerce_row_for_json(row_dict)
            out.append(row_dict)
        return out
    finally:
        if cursor:
            cursor.close()
        conn.close()


def fetch_events_from_event_table(
    agent_name: str,
    database: str,
    schema: str,
    connection_name: str = "snowhouse",
    where_clause: Optional[str] = None,
    limit: Optional[int] = None,
    unique: bool = False,
    raw_trace: bool = False,
    dangerously_fetch_events: bool = False
) -> List[Dict[str, Any]]:
    """
    Fetch evaluation questions from the AI Observability Event Table.
    
    This function queries the event table using GET_AI_OBSERVABILITY_EVENTS UDTF and extracts
    questions and ground truth answers from the record_attributes JSON field using
    TruLens SpanAttributes constants (RECORD_ROOT.INPUT and RECORD_ROOT.GROUND_TRUTH_OUTPUT).
    
    By default, returns all events with summarized traces. Set raw_trace=True to get raw 
    (unsummarized) trace data. Set unique=True to deduplicate by question text.
    
    Args:
        agent_name (str): Name of the agent to fetch events for
        database (str): Database where the agent is located
        schema (str): Schema where the agent is located
        connection_name (str): Snowflake connection name (default: "snowhouse")
        where_clause (Optional[str]): Additional conditions to filter results (joined with AND).
                                      Can include ORDER BY clauses.
                                      Examples: 
                                        - "timestamp > '2025-01-01'"
                                        - "ORDER BY timestamp DESC"
                                      Note: Don't include "WHERE" or "AND" at the beginning of the string - they're added automatically
        limit (Optional[int]): Maximum number of records to return.
                              When unique=False, limits SQL results.
                              When unique=True, limits after deduplication to ensure exact count.
                              Example: limit=10 with unique=True returns exactly 10 unique questions
        unique (bool): If True, deduplicate questions by question text (default: False).
                      When True, keeps first occurrence of each unique question.
        raw_trace (bool): If True, return raw (unsummarized) trace JSON. If False (default), 
                         summarize trace into readable format with execution trace.
        dangerously_fetch_events (bool): If True, directly query AI_OBSERVABILITY_EVENTS table 
                                        instead of using GET_AI_OBSERVABILITY_EVENTS UDTF.
                                        WARNING: This bypasses authorization checks. (default: False)
        
    Returns:
        list[dict]: List of question dictionaries, each containing:
                   - question (str): The question text
                   - answer (str): The actual answer from the agent
                   - ground_truth (str): The expected answer (ground truth)
                   - record_id (str): The record ID for this question/answer
                   - timestamp (str): When the question was asked/answered
                   - start_timestamp (str): When the trace started
                   - trace (dict): Trace data (always included).
                                  Summarized format by default (raw_trace=False),
                                  or raw trace JSON if raw_trace=True.
                   - feedback (list[dict]): List of feedback entries. Each entry contains:
                                           - timestamp (str): When feedback was provided
                                           - value (dict): Feedback data (categories, entity_type, feedback_message, positive)
                                           Empty list if no feedback exists for this record.
        
    Example:
        # Basic usage (includes summarized traces by default):
        questions = fetch_events_from_event_table(
            agent_name="RAVEN_SALES_ASSISTANT",
            database="SNOWFLAKE_INTELLIGENCE",
            schema="AGENTS"
        )
        
        # Get last 10 unique questions with summarized traces:
        questions = fetch_events_from_event_table(
            agent_name="MY_AGENT",
            database="MY_DB",
            schema="MY_SCHEMA",
            where_clause="ORDER BY timestamp DESC",
            limit=10,
            unique=True
        )
        
        # Get raw (unsummarized) traces:
        questions = fetch_events_from_event_table(
            agent_name="MY_AGENT",
            database="MY_DB",
            schema="MY_SCHEMA",
            raw_trace=True
        )
        
        # Get 20 questions from last 30 days (may include duplicates):
        questions = fetch_events_from_event_table(
            agent_name="MY_AGENT",
            database="MY_DB",
            schema="MY_SCHEMA",
            where_clause="timestamp > dateadd(day, -30, current_timestamp())",
            limit=20
        )
    """
    conn = snowflake.connector.connect(connection_name=connection_name)
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Build SQL query - either use safe UDTF or dangerous direct table access
        if dangerously_fetch_events:
            # WARNING: Directly query the table, bypassing authorization checks
            base_sql = f"""
        SELECT *
        FROM {EVENT_TABLE_DB}.{EVENT_TABLE_SCHEMA}.{EVENT_TABLE_NAME}
        WHERE RECORD_ATTRIBUTES:"snow.ai.observability.database.name" = '{escape_sql_string(database)}'
        AND RECORD_ATTRIBUTES:"snow.ai.observability.schema.name" = '{escape_sql_string(schema)}'
        AND RECORD_ATTRIBUTES:"snow.ai.observability.object.name" = '{escape_sql_string(agent_name)}'
        AND RECORD_ATTRIBUTES:"{TruLensSpanAttributes.SPAN_TYPE}" = '{TruLensSpanAttributes.SpanType.RECORD_ROOT.value}'
        """
        else:
            # Build SQL query using GET_AI_OBSERVABILITY_EVENTS
            # NOTE: This function validates agent existence and authorization at query time.
            base_sql = f"""
        SELECT *
        FROM TABLE({EVENT_TABLE_DB}.{EVENT_TABLE_SCHEMA}.{EVENT_TABLE_FUNCTION}(
            '{escape_sql_string(database)}',
            '{escape_sql_string(schema)}',
            '{escape_sql_string(agent_name)}',
            '{AGENT_TYPE}'
        ))
        WHERE RECORD_ATTRIBUTES:"{TruLensSpanAttributes.SPAN_TYPE}" = '{TruLensSpanAttributes.SpanType.RECORD_ROOT.value}'
        """
        
        # Add additional conditions if provided
        if where_clause:
            # Check if where_clause starts with ORDER BY (no AND needed)
            if where_clause.strip().upper().startswith('ORDER BY'):
                sql = f"{base_sql} {where_clause}"
            else:
                sql = f"{base_sql} AND {where_clause}"
        else:
            sql = base_sql
        
        # Add LIMIT if specified (only when not deduplicating, otherwise apply after dedup)
        if limit is not None and limit > 0 and not unique:
            sql = f"{sql} LIMIT {limit}"
        
        logger.info(f"Querying event table for agent: {database}.{schema}.{agent_name}")
        logger.info(f"Query SQL: {sql}")

        cursor.execute(sql)
        
        # Get column names from cursor description
        column_names = [desc[0].lower() for desc in cursor.description]
        
        # Process rows and extract questions
        rows = cursor.fetchall()
        
        logger.info(f"Retrieved {len(rows)} event records")
        logger.debug(f"Columns: {', '.join(column_names)}")
        
        if unique:
            # Deduplicate by question text
            questions_dict = {}
            for row in rows:
                question_data = parse_question_from_row(row, column_names)
                if question_data is None:
                    continue
                
                question = question_data[OUTPUT_KEY_QUESTION]
                
                # Skip duplicates (keep first occurrence)
                if question in questions_dict:
                    continue
                
                questions_dict[question] = question_data
            
            # Convert dict to list
            questions = list(questions_dict.values())
            
            # Apply limit after deduplication
            if limit is not None and limit > 0:
                questions = questions[:limit]
            
            logger.info(f"Extracted {len(questions)} unique questions from event table")
        else:
            # No deduplication
            questions = []
            for row in rows:
                question_data = parse_question_from_row(row, column_names)
                if question_data is None:
                    continue
                
                questions.append(question_data)
            
            logger.info(f"Extracted {len(questions)} questions from event table")
        
        # Add trace and feedback data to questions
        _add_trace_and_feedback_data(
            cursor=cursor,
            questions=questions,
            database=database,
            schema=schema,
            agent_name=agent_name,
            raw_trace=raw_trace,
            dangerously_fetch_events=dangerously_fetch_events
        )
        
        return questions
        
    finally:
        if cursor:
            cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch evaluation questions from AI Observability Event Table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fast path — only request/record ID (same filter as skill SQL on AI_OBSERVABILITY_EVENTS):
  %(prog)s --request-id 550e8400-e29b-41d4-a716-446655440000 --connection default --limit 50

  # Fetch all events (agent-scoped UDTF):
  %(prog)s --agent-name RAVEN_SALES_ASSISTANT --database SNOWFLAKE_INTELLIGENCE --schema AGENTS

  # Fetch last 10 unique questions with traces (summarized by default):
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --where "ORDER BY timestamp DESC" --limit 10 --unique

  # Fetch with raw (unsummarized) traces:
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA --raw-trace

  # Save to file:
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --connection snowhouse --output ./questions.json

  # Get 20 questions from last 30 days:
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --where "timestamp > dateadd(day, -30, current_timestamp())" --limit 20

  # Filter by question content:
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --filter-question "about sales data" --limit 10

  # Filter by both question and answer:
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --filter-question "revenue queries" --filter-answer "contains SQL" --unique

  # Use direct table access (dangerous mode):
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --dangerously-fetch-events --limit 10
        """
    )
    
    parser.add_argument(
        "--request-id",
        metavar="UUID",
        help=(
            "Observability record/request ID only: query AI_OBSERVABILITY_EVENTS with the skill fast-path SQL. "
            "Do not pass --agent-name/--database/--schema in this mode."
        ),
    )
    parser.add_argument("--agent-name", help="Name of the agent to fetch events for (agent-scoped mode)")
    parser.add_argument("--database", help="Database where agent is located (agent-scoped mode)")
    parser.add_argument("--schema", help="Schema where agent is located (agent-scoped mode)")
    
    # Optional arguments
    parser.add_argument(
        "--connection",
        default="snowhouse",
        help="Snowflake connection name (default: snowhouse)"
    )
    parser.add_argument(
        "--output",
        help="Path to save questions as JSON (default: print to console)"
    )
    parser.add_argument(
        "--where",
        help="Additional WHERE clause conditions (don't include 'WHERE' or 'AND')"
    )
    parser.add_argument(
        "--filter-question",
        help="Natural language filter for questions (e.g., 'about sales data')"
    )
    parser.add_argument(
        "--filter-answer",
        help="Natural language filter for answers (e.g., 'contains SQL queries')"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of records to return"
    )
    parser.add_argument(
        "--unique",
        action="store_true",
        help="Deduplicate questions by question text"
    )
    parser.add_argument(
        "--raw-trace",
        action="store_true",
        help="Return raw trace instead of summary (default: summarize traces)"
    )
    parser.add_argument(
        "--dangerously-fetch-events",
        action="store_true",
        help="WARNING: Directly query AI_OBSERVABILITY_EVENTS table, bypassing authorization checks"
    )

    
    args = parser.parse_args()

    def _has_full_agent() -> bool:
        return bool(args.agent_name and args.database and args.schema)

    def _has_partial_agent() -> bool:
        return bool(args.agent_name or args.database or args.schema) and not _has_full_agent()

    if args.request_id and _has_full_agent():
        parser.error("Use either --request-id alone (fast path) or --agent-name/--database/--schema, not both.")
    if _has_partial_agent():
        parser.error("Agent-scoped mode requires all of: --agent-name, --database, --schema.")
    if not args.request_id and not _has_full_agent():
        parser.error("Provide --request-id (fast path) or all of --agent-name, --database, --schema.")
    if args.request_id and (
        args.filter_question
        or args.filter_answer
        or args.where
        or args.unique
        or args.raw_trace
        or args.dangerously_fetch_events
    ):
        parser.error(
            "--request-id mode does not support --where, --filter-question, --filter-answer, "
            "--unique, --raw-trace, or --dangerously-fetch-events."
        )

    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    
    logger.info("\nFetching Events from AI Observability Event Table")
    logger.info("="*80)
    if args.request_id:
        logger.info(f"Mode: request-id fast path (record id: {args.request_id})")
    else:
        logger.info(f"Agent: {args.database}.{args.schema}.{args.agent_name}")
    logger.info(f"Connection: {args.connection}")
    if args.where:
        logger.info(f"Filter: {args.where}")
    if args.filter_question:
        logger.info(f"Question filter: {args.filter_question}")
    if args.filter_answer:
        logger.info(f"Answer filter: {args.filter_answer}")
    if args.limit:
        logger.info(f"Limit: {args.limit}")
    if args.unique:
        logger.info("Mode: Unique questions only")
    
    # Determine trace settings
    raw_trace = args.raw_trace
    dangerously_fetch_events = args.dangerously_fetch_events
    
    if args.request_id:
        logger.info("Traces: N/A (raw event rows only in request-id mode)")
    elif raw_trace:
        logger.info("Traces: Enabled (raw)")
    else:
        logger.info("Traces: Enabled (summarized)")
    
    if dangerously_fetch_events and not args.request_id:
        logger.info("⚠️  WARNING: Using direct table access (bypassing authorization checks)")
    
    logger.info("="*80 + "\n")

    if args.request_id:
        rid_limit = args.limit if args.limit is not None and args.limit > 0 else REQUEST_ID_ONLY_DEFAULT_LIMIT
        questions = fetch_events_by_request_id_only(
            request_id=args.request_id,
            connection_name=args.connection,
            limit=rid_limit,
        )
    else:
        where_clause = build_where_clause_with_ai_filters(
            args.where,
            args.filter_question,
            args.filter_answer
        )

        questions = fetch_events_from_event_table(
            agent_name=args.agent_name,
            database=args.database,
            schema=args.schema,
            connection_name=args.connection,
            where_clause=where_clause,
            limit=args.limit,
            unique=args.unique,
            raw_trace=raw_trace,
            dangerously_fetch_events=dangerously_fetch_events
        )
    
    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(questions, f, indent=2)
        label = "rows" if args.request_id else "questions"
        logger.info(f"\n✓ Saved {len(questions)} {label} to: {args.output}")
    else:
        logger.info(f"\n{'='*80}")
        logger.info("ROWS" if args.request_id else "QUESTIONS")
        logger.info("="*80 + "\n")
        print(json.dumps(questions, indent=2))
