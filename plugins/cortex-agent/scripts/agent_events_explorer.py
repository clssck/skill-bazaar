#!/usr/bin/env python3
"""
Agent Events Explorer & Annotation Tool

USAGE:
    streamlit run agent_events_explorer.py
    
    # With command line arguments:
    streamlit run agent_events_explorer.py -- --connection myconn --database MYDB --schema MYSCHEMA --agent MYAGENT
    
OPTIONS:
    --connection              Snowflake connection name (default: from env SNOWFLAKE_CONNECTION_NAME or "snowhouse")
    --database                Database name (default: from env SNOWFLAKE_DATABASE or "SNOWFLAKE_INTELLIGENCE")
    --schema                  Schema name (default: from env SNOWFLAKE_SCHEMA or "AGENTS")
    --agent                   Agent name (default: from env AGENT_NAME or "PDS_AGENT")
    --storage-table           Storage table FQN for annotations (default: {database}.{schema}.AGENT_ANNOTATIONS_{agent})
    --model                   LLM model for trace chat (default: claude-sonnet-4-5)
    --dangerously-fetch-events  WARNING: Enable direct table access mode (bypassing authorization checks)
"""
import os
import sys
import json
import argparse
from datetime import datetime
import pandas as pd
import streamlit as st
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from fetch_events_from_event_table import (
    fetch_events_from_event_table,
    build_where_clause_with_ai_filters,
    filter_traces_client_side,
)
from agent_feedback import submit_agent_feedback

# Available models for chat (defined early for CLI choices)
AVAILABLE_CHAT_MODELS = [
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-4-sonnet",
    "openai-gpt-5",
    "openai-gpt-5-mini",
    "openai-gpt-4.1",
    "llama3.1-70b",
    "llama3.1-8b",
]
DEFAULT_CHAT_MODEL = "claude-sonnet-4-5"

# Prompt for auto-generating trace summaries
TRACE_SUMMARY_PROMPT = "Given the agent response, show me the most important tool calls and generated SQL that led to the response and would help understand this trace."

# Predefined feedback categories
FEEDBACK_CATEGORIES = [
    "Ambiguous question",
    "Correct response",
    "Date/timestamp mismatch",
    "Hallucination",
    "Incomplete answer",
    "Incorrect SQL",
    "Wrong data queried",
    "Wrong tool used",
]

# Parse command line arguments before Streamlit starts
parser = argparse.ArgumentParser(description="Agent Events Explorer & Annotation Tool")
parser.add_argument("--connection", type=str, help="Snowflake connection name")
parser.add_argument("--database", type=str, help="Database name of the agent")
parser.add_argument("--schema", type=str, help="Schema name of the agent")
parser.add_argument("--agent", type=str, help="Agent name")
parser.add_argument("--storage-table", type=str, help="Storage table FQN for eval dataset/annotations")
parser.add_argument("--model", type=str, choices=AVAILABLE_CHAT_MODELS, help="LLM model for trace chat")
parser.add_argument("--dangerously-fetch-events", action="store_true", help="WARNING: Enable direct table access mode")

# Parse only our custom args, ignore Streamlit's args
args, unknown = parser.parse_known_args()

st.set_page_config(layout="wide", page_title="Agent Events Explorer")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_available_connections() -> List[str]:
    """Get list of available Snowflake connections from config files.
    
    Follows Snowflake connector's behavior:
    - If connections.toml exists, it takes precedence over config.toml
    - This matches how Snowflake's CONFIG_MANAGER uses config slices
    """
    try:
        import toml
        connections = []
        
        # Note: This traversal logic mirrors the connection discovery behavior used in snowflake.connector.connect 
        # Check connections.toml first - if it exists, it completely replaces config.toml's [connections]
        connections_path = Path.home() / '.snowflake' / 'connections.toml'
        if connections_path.exists():
            config = toml.load(connections_path)
            # connections.toml has top-level connection keys (Snowflake's slice mechanism moves these to [connections])
            connections = list(config.keys())
        else:
            # Fall back to config.toml only if connections.toml doesn't exist
            config_path = Path.home() / '.snowflake' / 'config.toml'
            if config_path.exists():
                config = toml.load(config_path)
                # config.toml has connections under the [connections] section
                connections = list(config.get('connections', {}).keys())
        
        return connections
    except Exception:
        return []


def get_snowflake_connection(conn_name: str):
    import snowflake.connector
    return snowflake.connector.connect(connection_name=conn_name)


def create_events_dataframe(events: List[Dict], annotations: Dict) -> pd.DataFrame:
    df_data = []
    for event in events:
        df_data.append({
            'timestamp': event.get('timestamp', ''),
            'request_id': event.get('record_id', ''),
            'question': event.get('question', ''),
            'answer': event.get('answer', ''),
            'has_feedback': 'Yes' if event.get('feedback') else 'No',
            'annotated': 'Yes' if event.get('record_id') in annotations else 'No'
        })
    
    df = pd.DataFrame(df_data)
    return df.sort_values('timestamp', ascending=False).reset_index(drop=True)


def create_review_dataframe(events: List[Dict], annotations: Dict) -> pd.DataFrame:
    review_data = []
    for event in events:
        rid = event.get('record_id', '')
        annotation = annotations.get(rid, {})
        
        question = event.get('question') or ''
        answer = event.get('answer') or ''
        expected_answer = annotation.get('expected_answer') or event.get('expected_answer') or ''
        feedback = annotation.get('feedback', {})
        
        review_data.append({
            'request_id': rid[:30] + '...' if len(rid) > 30 else rid,
            'question': question[:80] + '...' if len(question) > 80 else question,
            'answer': answer[:80] + '...' if len(answer) > 80 else answer,
            'expected_answer': expected_answer[:80] + '...' if len(expected_answer) > 80 else expected_answer,
            'feedback': str(feedback) if feedback else '',
            'annotated': 'Yes' if rid in annotations else 'No'
        })
    
    return pd.DataFrame(review_data)


def get_events_by_scope(events: List[Dict], scope: str, selected_request_ids, annotations: Dict) -> List[Dict]:
    """Filter events based on scope: 'All rows', 'Selected rows', or 'Annotated rows'"""
    if scope == "Selected rows":
        if selected_request_ids:
            return [e for e in events if e.get('record_id') in selected_request_ids]
        else:
            return []
    elif scope == "Annotated rows":
        return [e for e in events if e.get('record_id') in annotations]
    else:  # "All rows"
        return events


def get_eval_dataset_filename(database: str, schema: str, agent_name: str) -> str:
    """Get standardized filename for evaluation dataset."""
    return f"eval_dataset_{database}_{schema}_{agent_name}.json"


def build_feedback_entry(feedback_data: Dict) -> Dict:
    """Build a timestamped feedback entry from feedback data."""
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'positive': feedback_data.get('positive', True),
        'feedback_message': feedback_data.get('feedback_message', ''),
        'categories': feedback_data.get('categories', [])
    }


# ============================================================================
# STORAGE BACKEND FUNCTIONS
# ============================================================================

def get_storage_table_name(database: str, schema: str, agent_name: str) -> str:
    """Get the default storage table name for an agent."""
    return f"{database}.{schema}.AGENT_ANNOTATIONS_{agent_name}"


def create_or_get_storage_table(connection, table_fqn: str) -> bool:
    """
    Create storage table if it doesn't exist.
    
    Args:
        connection: Active Snowflake connection
        table_fqn: Fully qualified table name (DATABASE.SCHEMA.TABLE_NAME)
        
    Returns:
        True if table exists or was created successfully, False otherwise
    """
    try:
        cursor = connection.cursor()
        
        # Use IDENTIFIER() to safely handle dynamic table names (prevents SQL injection)
        create_sql = """
        CREATE TABLE IF NOT EXISTS IDENTIFIER(%s) (
            request_id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP_NTZ,
            database VARCHAR,
            schema VARCHAR,
            agent_name VARCHAR,
            question VARCHAR,
            answer VARCHAR,
            expected_answer VARCHAR,
            trace VARIANT,
            trace_summary VARCHAR,
            feedback ARRAY,
            latest_feedback VARIANT,
            last_updated TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """
        cursor.execute(create_sql, (table_fqn,))
        cursor.close()
        return True
    except Exception as e:
        st.error(f"Error creating storage table: {str(e)}")
        return False


def upsert_event_to_table(
    connection,
    table_fqn: str,
    event: Dict,
    annotation: Optional[Dict],
    database: str,
    schema: str,
    agent_name: str
) -> bool:
    """
    Insert or update an event in the storage table.
    
    If request_id exists, appends new feedback to the feedback array.
    If request_id doesn't exist, inserts a new row.
    
    Args:
        connection: Active Snowflake connection
        table_fqn: Fully qualified table name
        event: Event data dict
        annotation: Annotation data dict (optional)
        database: Database name
        schema: Schema name
        agent_name: Agent name
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cursor = connection.cursor()
        request_id = event.get('record_id', '')
        
        # Build feedback entry with timestamp if annotation exists
        feedback_entry = None
        if annotation and annotation.get('feedback'):
            feedback_entry = build_feedback_entry(annotation.get('feedback', {}))
        
        # Check if record exists (use IDENTIFIER() for safe table reference)
        check_sql = "SELECT feedback FROM IDENTIFIER(%s) WHERE request_id = %s"
        cursor.execute(check_sql, (table_fqn, request_id))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record - append feedback to array if new feedback
            if feedback_entry:
                feedback_json = json.dumps(feedback_entry)
                update_sql = """
                UPDATE IDENTIFIER(%s)
                SET 
                    expected_answer = COALESCE(%s, expected_answer),
                    feedback = ARRAY_APPEND(COALESCE(feedback, ARRAY_CONSTRUCT()), PARSE_JSON(%s)),
                    latest_feedback = PARSE_JSON(%s),
                    last_updated = CURRENT_TIMESTAMP()
                WHERE request_id = %s
                """
                cursor.execute(update_sql, (
                    table_fqn,
                    annotation.get('expected_answer', '') if annotation else None,
                    feedback_json,
                    feedback_json,
                    request_id
                ))
            else:
                # Just update expected_answer if provided
                if annotation and annotation.get('expected_answer'):
                    update_sql = """
                    UPDATE IDENTIFIER(%s)
                    SET expected_answer = %s, last_updated = CURRENT_TIMESTAMP()
                    WHERE request_id = %s
                    """
                    cursor.execute(update_sql, (table_fqn, annotation.get('expected_answer', ''), request_id))
        else:
            # Insert new record using INSERT...SELECT pattern
            # This allows PARSE_JSON to work on bind variables (unlike VALUES clause)
            trace_json = json.dumps(event.get('trace', {}))
            feedback_array = json.dumps([feedback_entry]) if feedback_entry else '[]'
            latest_feedback_json = json.dumps(feedback_entry) if feedback_entry else 'null'
            
            insert_sql = """
            INSERT INTO IDENTIFIER(%s) 
            (request_id, timestamp, database, schema, agent_name, question, answer, expected_answer, trace, feedback, latest_feedback)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), PARSE_JSON(%s)
            """
            cursor.execute(insert_sql, (
                table_fqn,
                request_id,
                event.get('timestamp', ''),
                database,
                schema,
                agent_name,
                event.get('question', ''),
                event.get('answer', ''),
                annotation.get('expected_answer', '') if annotation else '',
                trace_json,
                feedback_array,
                latest_feedback_json
            ))
        
        cursor.close()
        return True
    except Exception as e:
        st.error(f"Error upserting event: {str(e)}")
        return False


def sync_events_to_storage(
    connection,
    table_fqn: str,
    events: List[Dict],
    annotations: Dict,
    database: str,
    schema: str,
    agent_name: str
) -> int:
    """
    Sync all events to Snowflake storage table using batch MERGE.
    
    Args:
        connection: Active Snowflake connection
        table_fqn: Fully qualified table name
        events: List of event dicts
        annotations: Dict mapping request_id to annotation data
        database: Database name
        schema: Schema name
        agent_name: Agent name
        
    Returns:
        Number of records synced
    """
    if not events:
        return 0
    
    try:
        cursor = connection.cursor()
        
        # Build batch data for all events
        batch_data = []
        for event in events:
            request_id = event.get('record_id', '')
            annotation = annotations.get(request_id, {})
            trace_json = json.dumps(event.get('trace', {}))
            
            # Build feedback if annotation exists
            feedback_entry = None
            if annotation and annotation.get('feedback'):
                feedback_entry = build_feedback_entry(annotation.get('feedback', {}))
            
            feedback_array = json.dumps([feedback_entry]) if feedback_entry else '[]'
            latest_feedback_json = json.dumps(feedback_entry) if feedback_entry else 'null'
            
            batch_data.append((
                request_id,
                event.get('timestamp', ''),
                database,
                schema,
                agent_name,
                event.get('question', ''),
                event.get('answer', ''),
                annotation.get('expected_answer', ''),
                trace_json,
                feedback_array,
                latest_feedback_json
            ))
        
        # Use executemany for batch insert (new records only, skip existing)
        # This is faster than individual upserts for initial sync
        insert_sql = """
        INSERT INTO IDENTIFIER(%s) 
        (request_id, timestamp, database, schema, agent_name, question, answer, expected_answer, trace, feedback, latest_feedback)
        SELECT %s, %s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), PARSE_JSON(%s)
        WHERE NOT EXISTS (SELECT 1 FROM IDENTIFIER(%s) WHERE request_id = %s)
        """
        
        synced = 0
        for row in batch_data:
            try:
                cursor.execute(insert_sql, (table_fqn,) + row + (table_fqn, row[0]))
                if cursor.rowcount > 0:
                    synced += 1
            except Exception:
                # Skip duplicates or errors for individual rows
                pass
        
        cursor.close()
        return synced
    except Exception as e:
        st.error(f"Error syncing events: {str(e)}")
        return 0


def save_all_events_to_json(
    events: List[Dict],
    annotations: Dict,
    database: str,
    schema: str,
    agent_name: str
):
    """Save all fetched events (with annotations) to JSON file."""
    filename = get_eval_dataset_filename(database, schema, agent_name)
    filepath = Path(__file__).parent / filename
    
    records = []
    for event in events:
        request_id = event.get('record_id', '')
        annotation = annotations.get(request_id, {})
        
        # Build feedback list - combine event feedback with annotation feedback
        feedback_list = []
        
        # Add existing event feedback
        event_feedback = event.get('feedback', [])
        if event_feedback:
            if isinstance(event_feedback, list):
                feedback_list.extend(event_feedback)
            else:
                feedback_list.append(event_feedback)
        
        # Add annotation feedback if present
        if annotation and annotation.get('feedback'):
            feedback_list.append(build_feedback_entry(annotation.get('feedback', {})))
        
        records.append({
            'timestamp': event.get('timestamp', ''),
            'request_id': request_id,
            'database': database,
            'schema': schema,
            'agent_name': agent_name,
            'question': event.get('question', ''),
            'answer': event.get('answer', ''),
            'expected_answer': annotation.get('expected_answer', ''),
            'trace': event.get('trace', {}),
            'feedback': feedback_list
        })
    
    with open(filepath, 'w') as f:
        json.dump(records, f, indent=2)


def fetch_column_from_table(
    connection,
    table_fqn: str,
    request_id: str,
    column_name: str
) -> Optional[str]:
    """Fetch a single column value for a request_id from the storage table."""
    try:
        cursor = connection.cursor()
        sql = f"SELECT {column_name} FROM IDENTIFIER(%s) WHERE request_id = %s"
        cursor.execute(sql, (table_fqn, request_id))
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result and result[0] else None
    except Exception:
        return None


def save_trace_summary_to_table(
    connection,
    table_fqn: str,
    request_id: str,
    summary: str
) -> bool:
    """Save a trace summary to the storage table."""
    try:
        cursor = connection.cursor()
        sql = """
        UPDATE IDENTIFIER(%s)
        SET trace_summary = %s, last_updated = CURRENT_TIMESTAMP()
        WHERE request_id = %s
        """
        cursor.execute(sql, (table_fqn, summary, request_id))
        cursor.close()
        return True
    except Exception:
        return False


# ============================================================================
# TRACE CHAT FUNCTIONS
# ============================================================================

def query_trace_with_ai_complete(
    connection,
    trace: Dict,
    user_question: str,
    model: str = DEFAULT_CHAT_MODEL,
    chat_history: Optional[List[Dict]] = None
) -> str:
    """
    Query the trace using Snowflake's CORTEX.COMPLETE function.
    
    Args:
        connection: Active Snowflake connection
        trace: The trace data as a dict
        user_question: User's question about the trace
        model: LLM model to use
        chat_history: Previous chat messages for context
        
    Returns:
        AI response string
    """
    try:
        cursor = connection.cursor()
        
        # Build conversation context from history
        history_context = ""
        if chat_history:
            history_context = "\n\nPrevious conversation:\n"
            for msg in chat_history[-5:]:  # Include last 5 messages for context
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                history_context += f"{role.upper()}: {content}\n"
        
        # Format the prompt
        trace_str = json.dumps(trace, indent=2)
        
        # Truncate trace if too long (keep first 50k chars)
        max_trace_len = 50000
        if len(trace_str) > max_trace_len:
            trace_str = trace_str[:max_trace_len] + "\n... [trace truncated]"
        
        prompt = f"""You are an AI assistant helping analyze agent traces. 
The trace below shows the execution flow of a Cortex Agent responding to a user query.

TRACE DATA:
{trace_str}
{history_context}
USER QUESTION: {user_question}

Provide a clear, concise answer based on the trace data. Focus on:
- Tool calls made and their results
- Decision points and reasoning
- Any errors or issues encountered
- The final response generated"""
        
        # Escape single quotes for SQL
        prompt_escaped = prompt.replace("'", "''")
        
        if model not in AVAILABLE_CHAT_MODELS:
            raise ValueError(f"Invalid model: {model}")
        sql = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{prompt_escaped}')"
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        
        if result and result[0]:
            return result[0]
        return "Unable to generate a response."
        
    except Exception as e:
        return f"Error querying trace: {str(e)}"


# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

if 'events_data' not in st.session_state:
    st.session_state.events_data = None
if 'connection' not in st.session_state:
    st.session_state.connection = None
if 'annotations' not in st.session_state:
    st.session_state.annotations = {}
if 'selected_request_ids' not in st.session_state:
    st.session_state.selected_request_ids = None  # None means all rows
if 'current_record_index' not in st.session_state:
    st.session_state.current_record_index = 0
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = {}  # Dict mapping request_id to list of chat messages
if 'storage_table_fqn' not in st.session_state:
    st.session_state.storage_table_fqn = None
if 'chat_model' not in st.session_state:
    st.session_state.chat_model = DEFAULT_CHAT_MODEL


# ============================================================================
# SECTION 1: FETCH AGENT EVENTS
# ============================================================================

st.title("Agent Events Explorer & Annotation Tool")
st.header("1. Fetch Agent Events")

# Set defaults from command line args, environment, or hardcoded defaults
available_connections = get_available_connections()
default_conn = args.connection or os.getenv("SNOWFLAKE_CONNECTION_NAME")
default_database = args.database or os.getenv("SNOWFLAKE_DATABASE")
default_schema = args.schema or os.getenv("SNOWFLAKE_SCHEMA")
default_agent = args.agent or os.getenv("AGENT_NAME")
default_dangerously_fetch = getattr(args, 'dangerously_fetch_events', False)

if default_conn:
    if not available_connections:
        available_connections = [default_conn]
    elif default_conn not in available_connections:
        available_connections.insert(0, default_conn)

with st.form("fetch_events_form"):
    connection_name = st.selectbox(
        "Snowflake Connection Name", 
        options=available_connections,
        index=None,
        help="Select the Snowflake connection to use",
        placeholder="Snowflake connection name e.g., snowhouse"
    )
    
    col1, col2, col3 = st.columns(3)
    with col1:
        agent_name = st.text_input("Agent Name", value=default_agent, placeholder="Agent name e.g., SALES_AGENT")
    with col2:
        database = st.text_input("Database", value=default_database, placeholder="Database where agent is located e.g., SNOWFLAKE_INTELLIGENCE")
    with col3:
        schema = st.text_input("Schema", value=default_schema, placeholder="Schema where agent is located e.g., AGENTS")
    
    where_clause = st.text_input(
        "Additional WHERE clause (optional)", 
        placeholder="e.g., timestamp > '2025-01-01' or ORDER BY timestamp DESC",
        help="Don't include 'WHERE' or 'AND' at the beginning"
    )
    
    st.markdown("**AI Filters (experimental)**")
    col_ai1, col_ai2, col_ai3 = st.columns(3)
    
    with col_ai1:
        question_filter = st.text_input(
            "Filter questions",
            placeholder="e.g., about Streamlit",
            help="Natural language filter for questions"
        )
    
    with col_ai2:
        answer_filter = st.text_input(
            "Filter answers",
            placeholder="e.g., mentions SQL errors",
            help="Natural language filter for answers"
        )
    
    with col_ai3:
        trace_filter = st.text_input(
            "Filter traces",
            placeholder="e.g., used CortexAnalyst tool",
            help="Natural language filter for traces (client-side)"
        )
    
    col4, col5, col6 = st.columns(3)
    with col4:
        limit = st.number_input("Limit records", min_value=0, value=100, step=10, help="0 means no limit")
    with col5:
        unique = st.checkbox("Unique questions only", value=False)
    with col6:
        dangerously_fetch_events = st.checkbox(
            "⚠️ Dangerous mode", 
            value=default_dangerously_fetch,
            help="WARNING: Directly query AI_OBSERVABILITY_EVENTS table, bypassing authorization checks"
        )
    
    st.markdown("**Storage & Chat Settings**")
    col_st1, col_st2 = st.columns(2)
    
    with col_st1:
        # Default storage table: CLI arg > generated from agent info
        default_storage_table = getattr(args, 'storage_table', None)
        storage_table_input = st.text_input(
            "Storage Table FQN",
            value=default_storage_table,
            placeholder="e.g., EVAL_DB.SALES_SCHEMA.SALES_AGENT_ANNOTATIONS",
            help="Table for persisting events and annotations (will be created if it does not exist; make sure you have appropriate permissions to create the table in the corresponding DB/schema)"
        )
    
    with col_st2:
        # Default model: CLI arg > first in list
        default_model = args.model or DEFAULT_CHAT_MODEL
        default_model_index = AVAILABLE_CHAT_MODELS.index(default_model) if default_model in AVAILABLE_CHAT_MODELS else 0
        chat_model = st.selectbox(
            "Chat Model",
            options=AVAILABLE_CHAT_MODELS,
            index=default_model_index,
            help="LLM model for trace chat feature"
        )
    
    fetch_button = st.form_submit_button("Fetch Events")

if fetch_button:
    if not agent_name or not database or not schema:
        st.error("Please provide Agent Name, Database, and Schema")
    else:
        with st.spinner("Fetching events from Snowflake..."):
            try:
                st.session_state.connection = get_snowflake_connection(connection_name)
                
                if dangerously_fetch_events:
                    st.warning("⚠️ WARNING: Using direct table access mode (bypassing authorization checks)")
                
                final_where_clause = build_where_clause_with_ai_filters(where_clause, question_filter, answer_filter)

                # st.markdown("**NL filters:**")
                # st.code(f"{final_where_clause}", language="sql")
                
                events = fetch_events_from_event_table(
                    agent_name=agent_name,
                    database=database,
                    schema=schema,
                    connection_name=connection_name,
                    where_clause=final_where_clause,
                    limit=limit if limit > 0 else None,
                    unique=unique,
                    raw_trace=False,
                    dangerously_fetch_events=dangerously_fetch_events
                )
                
                events = filter_traces_client_side(events, trace_filter, st.session_state.connection)
                
                if len(events) == 0 and trace_filter:
                    st.warning(f"Trace filter '{trace_filter}' matched 0 events. Try a different query or remove the filter.")
                
                st.session_state.events_data = events
                st.session_state.agent_name = agent_name
                st.session_state.database = database
                st.session_state.schema = schema
                st.session_state.connection_name = connection_name
                st.session_state.annotations = {}
                st.session_state.selected_request_ids = None
                st.session_state.current_record_index = 0
                st.session_state.chat_history = {}  # Reset chat history on new fetch
                st.session_state.chat_model = chat_model
                
                st.success(f"Fetched {len(events)} events successfully!")

                # Update storage table FQN based on actual agent info
                actual_storage_table = storage_table_input or get_storage_table_name(database, schema, agent_name)
                st.session_state.storage_table_fqn = actual_storage_table
                
                # Also save to JSON file
                save_all_events_to_json(events, {}, database, schema, agent_name)
                st.info(f"📦 Saved events locally to: `eval_dataset_{database}_{schema}_{agent_name}.json` - {len(events)} events synced")

                # Update Snowflake eval dataset table if needed and sync events
                if create_or_get_storage_table(st.session_state.connection, actual_storage_table):
                    synced = sync_events_to_storage(
                        st.session_state.connection,
                        actual_storage_table,
                        events,
                        {},  # No annotations yet
                        database,
                        schema,
                        agent_name
                    )
                    st.info(f"📦 Saved events online to Snowflake table: `{actual_storage_table}` - {synced} events synced")   
                
            except Exception as e:
                st.error(f"Error fetching events: {str(e)}")
                st.session_state.events_data = None


# ============================================================================
# SECTION 2: VIEW & ANNOTATE
# ============================================================================

if st.session_state.events_data:
    st.header("2. View & Annotate")
    
    events = st.session_state.events_data
    
    df = create_events_dataframe(events, st.session_state.annotations)
    
    # Display current selection status prominently
    if st.session_state.selected_request_ids is not None:
        col_status, col_reset = st.columns([3, 1])
        with col_status:
            st.info(f"📌 Currently annotating **{len(st.session_state.selected_request_ids)} selected rows**")
        with col_reset:
            if st.button("↻ Reset to All Rows", use_container_width=True):
                st.session_state.selected_request_ids = None
                st.session_state.current_record_index = 0
                st.rerun()
    else:
        st.markdown("**Select rows to annotate** (or leave unselected to annotate all)")
        
        selected_rows = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row",
            key="row_selector"
        )
        
        col_sel1, col_sel2 = st.columns([1, 4])
        
        with col_sel1:
            if st.button("✓ Apply Selection", use_container_width=True, type="primary"):
                if selected_rows.selection.rows:
                    # Map selected dataframe rows to request IDs
                    selected_request_ids = df.iloc[selected_rows.selection.rows]['request_id'].tolist()
                    st.session_state.selected_request_ids = selected_request_ids
                    st.session_state.current_record_index = 0
                    st.rerun()
                else:
                    st.warning("No rows selected. Please select at least one row.")
        
        with col_sel2:
            st.info("💡 Select rows above, then click 'Apply Selection' to begin annotating only those rows")
    
    # Show reference view of data
    with st.expander("📋 View All Data", expanded=False):
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.subheader("Annotate Records")
    
    # Get filtered events based on selection
    if st.session_state.selected_request_ids is not None:
        filtered_events = [e for e in events if e.get('record_id') in st.session_state.selected_request_ids]
    else:
        filtered_events = events
    
    total_records = len(filtered_events)
    
    if total_records == 0:
        st.warning("No records available for annotation. Please select rows or reset to all rows.")
        st.stop()
    
    current_idx = st.session_state.current_record_index
    
    # Ensure current index is within bounds
    if current_idx >= total_records:
        st.session_state.current_record_index = 0
        current_idx = 0
    
    # Navigation
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        if st.button("⬅️ Previous", disabled=(current_idx == 0), use_container_width=True):
            st.session_state.current_record_index = max(0, current_idx - 1)
            st.rerun()
    
    with col2:
        selection_info = f" ({len(st.session_state.selected_request_ids)} selected)" if st.session_state.selected_request_ids is not None else " (all)"
        st.markdown(f"<div style='text-align: center; padding: 10px;'>Record {current_idx + 1} of {total_records}{selection_info}</div>", unsafe_allow_html=True)
    
    with col3:
        if st.button("Next ➡️", disabled=(current_idx >= total_records - 1), use_container_width=True):
            st.session_state.current_record_index = min(total_records - 1, current_idx + 1)
            st.rerun()
    
    current_event = filtered_events[current_idx]
    request_id = current_event.get('record_id', '')
    
    st.divider()
    
    # Show metadata
    st.markdown(f"**Request ID:** `{request_id}`")
    st.markdown(f"**Timestamp:** {current_event.get('timestamp', '')}")
    
    # Show feedback submission status
    last_submitted = st.session_state.get('last_feedback_submitted', {})
    if last_submitted.get('request_id') == request_id:
        st.success(f"✅ Just submitted: {'👍 Positive' if last_submitted.get('positive') else '👎 Negative'} - {last_submitted.get('message', 'No message')}")
    
    # Show question, answer, and trace side by side
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.markdown("**Question:**")
        st.info(current_event.get('question', ''))
        
        st.markdown("**Answer:**")
        st.success(current_event.get('answer', ''))
    
    with col_right:
        full_trace = current_event.get('trace', {})
        
        # Trace display - minimized by default
        with st.expander("📋 **Trace**", expanded=False):
            if full_trace:
                st.code(json.dumps(full_trace, indent=2), language="json", height=350)
            else:
                st.caption("No trace data available")
        
        # Chat with Trace interface
        st.markdown("**💬 Chat with Trace**")
        
        # Initialize chat history for this request_id if needed
        if request_id not in st.session_state.chat_history:
            st.session_state.chat_history[request_id] = []
        
        chat_messages = st.session_state.chat_history[request_id]
        
        # Load or generate trace summary as first message
        if full_trace and not chat_messages:
            # First, check if summary exists in storage table (instant)
            stored_summary = None
            if st.session_state.storage_table_fqn and st.session_state.connection:
                stored_summary = fetch_column_from_table(
                    st.session_state.connection,
                    st.session_state.storage_table_fqn,
                    request_id,
                    "trace_summary"
                )
            
            if stored_summary:
                # Use cached summary from database (instant!)
                summary = stored_summary
            else:
                # Generate new summary and save to table
                with st.spinner("Generating trace summary..."):
                    summary = query_trace_with_ai_complete(
                        st.session_state.connection,
                        full_trace,
                        TRACE_SUMMARY_PROMPT,
                        st.session_state.chat_model
                    )
                    # Save to storage table for future use
                    if st.session_state.storage_table_fqn and st.session_state.connection:
                        save_trace_summary_to_table(
                            st.session_state.connection,
                            st.session_state.storage_table_fqn,
                            request_id,
                            summary
                        )
            
            # Add summary as first message in chat
            st.session_state.chat_history[request_id].append({
                "role": "user",
                "content": TRACE_SUMMARY_PROMPT
            })
            st.session_state.chat_history[request_id].append({
                "role": "assistant",
                "content": f"**Trace Summary**\n\n{summary}"
            })
            chat_messages = st.session_state.chat_history[request_id]
        
        # Display chat history in a container
        chat_container = st.container(height=650)
        with chat_container:
            if not chat_messages:
                st.caption("No trace data available.")
            for msg in chat_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        
        # Chat input
        if full_trace:
            chat_input = st.chat_input(
                "Ask about this trace...",
                key=f"chat_input_{request_id}"
            )
            
            if chat_input:
                # Add user message to history
                st.session_state.chat_history[request_id].append({
                    "role": "user",
                    "content": chat_input
                })
                
                # Get AI response
                with st.spinner("Analyzing trace..."):
                    response = query_trace_with_ai_complete(
                        st.session_state.connection,
                        full_trace,
                        chat_input,
                        st.session_state.chat_model,
                        st.session_state.chat_history[request_id]
                    )
                
                # Add assistant response to history
                st.session_state.chat_history[request_id].append({
                    "role": "assistant",
                    "content": response
                })
                
                st.rerun()
        else:
            st.caption("No trace data available for chat.")
    
    st.divider()
    st.subheader("Add Annotation")
    
    # Get existing annotation if any
    annotation = st.session_state.annotations.get(request_id, {})
    
    # Determine expected_answer value with priority:
    # 1. Session state annotation (current session edits)
    # 2. Value from storage table (previously saved)
    # 3. Value from the event itself (fallback)
    default_expected_answer = ''
    if annotation.get('expected_answer'):
        default_expected_answer = annotation.get('expected_answer')
    elif st.session_state.storage_table_fqn and st.session_state.connection:
        # Try to fetch from storage table
        stored_answer = fetch_column_from_table(
            st.session_state.connection,
            st.session_state.storage_table_fqn,
            request_id,
            "expected_answer"
        )
        if stored_answer:
            default_expected_answer = stored_answer
    elif current_event.get('expected_answer'):
        default_expected_answer = current_event.get('expected_answer')
    
    # Expected answer input
    expected_answer = st.text_area(
        "Expected Answer", 
        value=default_expected_answer,
        placeholder="Enter expected answer...",
        key=f"ea_{request_id}"
    )
    
    # Feedback inputs
    st.markdown("**Feedback:**")
    col_fb1, col_fb2 = st.columns(2)
    
    with col_fb1:
        feedback_sentiment = st.radio(
            "Type", 
            ["👍 Positive", "👎 Negative"],
            index=0 if annotation.get('positive', True) else 1,
            horizontal=True,
            key=f"fb_sentiment_{request_id}"
        )
    
    with col_fb2:
        existing_cats = annotation.get('feedback', {}).get('categories', [])
        # Only use existing cats that are in predefined list as defaults
        default_cats = [c for c in existing_cats if c in FEEDBACK_CATEGORIES]
        selected_cats = st.multiselect(
            "Categories (optional)",
            options=FEEDBACK_CATEGORIES,
            default=default_cats,
            key=f"fb_cat_{request_id}"
        )
    
    # Custom categories (for anything not in the predefined list)
    custom_cats_default = ", ".join(c for c in existing_cats if c not in FEEDBACK_CATEGORIES)
    custom_cats_input = st.text_input(
        "Custom categories (optional)",
        value=custom_cats_default,
        placeholder="e.g., Too verbose, Missing charts",
        help="Comma-separated",
        key=f"fb_custom_{request_id}"
    )
    custom_cats = [c.strip() for c in custom_cats_input.split(',') if c.strip()]
    categories = selected_cats + custom_cats
    
    feedback_message = st.text_area(
        "Feedback Message (optional)",
        value=annotation.get('feedback_message', ''),
        placeholder="Enter feedback details...",
        key=f"fb_msg_{request_id}"
    )
    
    # Action buttons
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("Submit & Next", use_container_width=True, type="primary"):
            annotation_data = {
                'expected_answer': expected_answer,
                'feedback': {
                    'entity_type': 'message',
                    'feedback_message': feedback_message,
                    'positive': (feedback_sentiment == "👍 Positive"),
                    'categories': categories
                }
            }
            
            st.session_state.annotations[request_id] = annotation_data
            
            # Auto-save to JSON file
            save_all_events_to_json(
                events, 
                st.session_state.annotations, 
                st.session_state.database,
                st.session_state.schema,
                st.session_state.agent_name
            )
            
            # Sync to Snowflake storage table
            if st.session_state.storage_table_fqn and st.session_state.connection:
                try:
                    upsert_event_to_table(
                        st.session_state.connection,
                        st.session_state.storage_table_fqn,
                        current_event,
                        annotation_data,
                        st.session_state.database,
                        st.session_state.schema,
                        st.session_state.agent_name
                    )
                except Exception as e:
                    st.toast(f"⚠️ Storage sync error: {str(e)}", icon="⚠️")
            
            feedback_submitted = False
            if feedback_message:
                try:
                    result = submit_agent_feedback(
                        database=st.session_state.database,
                        schema=st.session_state.schema,
                        agent_name=st.session_state.agent_name,
                        request_id=request_id,
                        positive=(feedback_sentiment == "👍 Positive"),
                        feedback_message=feedback_message,
                        categories=categories,
                        connection=st.session_state.connection
                    )
                    
                    if result["success"]:
                        feedback_submitted = True
                        st.toast("✅ Feedback submitted successfully!", icon="✅")
                    else:
                        st.toast(f"❌ Error: {result['message']}", icon="❌")
                except Exception as e:
                    st.toast(f"❌ Error submitting feedback: {str(e)}", icon="❌")
            
            if current_idx < total_records - 1:
                st.session_state.current_record_index += 1
            
            if feedback_submitted:
                st.session_state['last_feedback_submitted'] = {
                    'request_id': request_id,
                    'positive': (feedback_sentiment == "👍 Positive"),
                    'message': feedback_message,
                    'categories': categories
                }
            
            st.rerun()
    
    with col_btn2:
        if st.button("Skip", use_container_width=True):
            if current_idx < total_records - 1:
                st.session_state.current_record_index += 1
                st.rerun()
    
    
    # ============================================================================
    # SECTION 3: REVIEW COLLECTED DATA
    # ============================================================================
    
    st.header("3. Review Collected Data")
    
    annotation_count = len(st.session_state.annotations)
    st.markdown(f"**Annotations collected:** {annotation_count} / {len(events)}")
    
    with st.expander("View All Collected Data", expanded=False):
        review_scope = st.radio(
            "Show data for:",
            ["All rows", "Selected rows", "Annotated rows"],
            index=0,
            horizontal=True,
            key="review_scope"
        )
        
        review_events = get_events_by_scope(events, review_scope, st.session_state.selected_request_ids, st.session_state.annotations)
        
        if len(review_events) == 0:
            st.warning(f"No rows to display for '{review_scope}'")
        else:
            st.markdown(f"Showing {len(review_events)} rows")
            review_df = create_review_dataframe(review_events, st.session_state.annotations)
            st.dataframe(review_df, use_container_width=True, hide_index=True)
    
    
    # ============================================================================
    # SECTION 4: EVAL DATASET
    # ============================================================================
    
    st.header("4. Eval Dataset")
    
    # Show storage status
    col_storage1, col_storage2 = st.columns(2)
    
    with col_storage1:
        st.markdown("**JSON File Storage**")
        dataset_filename = get_eval_dataset_filename(
            st.session_state.database, 
            st.session_state.schema, 
            st.session_state.agent_name
        )
        dataset_path = Path(__file__).parent / dataset_filename
        if annotation_count > 0:
            st.success(f"✅ {annotation_count} annotated records saved")
        st.info(f"`{dataset_path}`")
    
    with col_storage2:
        st.markdown("**Snowflake Table Storage**")
        if st.session_state.storage_table_fqn:
            st.success("✅ Synced to table")
            st.info(f"`{st.session_state.storage_table_fqn}`")
        else:
            st.warning("No storage table configured")
    
    if annotation_count == 0:
        st.info("No annotations yet. Start annotating records above to build your evaluation dataset.")
    
    # Always show dataset and feedback information
    st.markdown("""
    **Data Storage:**
    - All fetched events are automatically saved to both JSON file and Snowflake table
    - Each annotation updates both storage locations
    - Feedback is stored as an array column - multiple feedbacks per request_id are supported (appended with timestamps)
    - JSON file: `eval_dataset_{database}_{schema}_{agent_name}.json`
    - Snowflake table: `{database}.{schema}.AGENT_ANNOTATIONS_{agent_name}` (configurable)
    
    **Table Schema:**
    ```
    request_id (PRIMARY KEY), timestamp, database, schema, agent_name,
    question, answer, expected_answer, trace (VARIANT), trace_summary,
    feedback (ARRAY), latest_feedback (VARIANT), last_updated
    ```
    
    - `trace_summary`: AI-generated summary (cached for instant loading)
    - `feedback`: Array of all feedback entries (each with timestamp, positive, feedback_message, categories)
    - `latest_feedback`: Most recent feedback entry for quick access
    
    ⚠️ **Note on feedback submission:**
    - Feedback provided via this Streamlit app is submitted to the [Cortex Agents Feedback REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-feedback-rest-api) 
    and will appear in the event table after processing.
    - Due to the ingestion pipeline, there may be a delay before feedback appears in the Snowflake event table.
    - Multiple feedback submissions are allowed per `request_id`.
    - Please query the feedback table directly for complete feedback history and details. A sample query is provided below.
    ```sql
    SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('SNOWFLAKE_INTELLIGENCE', 'AGENTS', '<AGENT_NAME>', 'CORTEX AGENT')) 
    WHERE RECORD_ATTRIBUTES:"ai.observability.record_id"='<REQUEST_ID>' AND 
    RECORD:name='CORTEX_AGENT_FEEDBACK';
    ```
    """)
