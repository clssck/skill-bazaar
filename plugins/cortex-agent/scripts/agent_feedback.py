#!/usr/bin/env python3
"""
Submit feedback for Cortex Agent requests via the Feedback REST API.

This script allows submitting positive or negative feedback for agent responses,
including optional feedback messages and categories.

COMMAND-LINE USAGE:
    python agent_feedback.py --agent-name AGENT --database DB --schema SCHEMA \
        --request-id REQUEST_ID --positive --message "Great response!"

COMMAND-LINE OPTIONS:
    --agent-name NAME          Name of the agent
    --database DATABASE        Database where the agent is located
    --schema SCHEMA            Schema where the agent is located
    --request-id ID            Original request ID to provide feedback for
    --positive                 Submit positive feedback (default)
    --negative                 Submit negative feedback
    --message MESSAGE          Feedback message text (optional)
    --categories CAT1,CAT2     Comma-separated list of feedback categories (optional)
    --connection CONNECTION    Snowflake connection name (default: snowhouse)

COMMAND-LINE EXAMPLES:
    # Submit positive feedback:
    python agent_feedback.py --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \
        --request-id "abc-123-def" --positive --message "Accurate answer!"

    # Submit negative feedback with categories:
    python agent_feedback.py --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \
        --request-id "abc-123-def" --negative --message "Wrong data returned" \
        --categories "incorrect_data,wrong_tool"

LIBRARY USAGE:
    from agent_feedback import submit_agent_feedback
    import snowflake.connector

    conn = snowflake.connector.connect(connection_name="snowhouse")
    result = submit_agent_feedback(
        database="MY_DB",
        schema="MY_SCHEMA",
        agent_name="MY_AGENT",
        request_id="abc-123-def",
        positive=True,
        feedback_message="Great response!",
        categories=["accurate"],
        connection=conn
    )
    print(result)  # {'success': True, 'message': 'Feedback submitted successfully'}
"""

import argparse
import logging
from typing import Any, Dict, List

import requests
import snowflake.connector

# Configure logging
logger = logging.getLogger(__name__)


def submit_agent_feedback(
    database: str,
    schema: str,
    agent_name: str,
    request_id: str,
    positive: bool,
    feedback_message: str,
    categories: List[str],
    connection
) -> Dict[str, Any]:
    """
    Submit feedback for an agent request via Cortex Agents Feedback REST API.
    
    Args:
        database: Database where the agent is located
        schema: Schema where the agent is located
        agent_name: Name of the agent
        request_id: Original request ID to provide feedback for
        positive: True for positive feedback, False for negative
        feedback_message: Feedback message text
        categories: List of feedback category strings
        connection: Active Snowflake connection (for host and token)
        
    Returns:
        Dictionary with 'success' (bool) and 'message' (str) keys
    """
    host = connection.host
    token = connection.rest.token
    
    url = f"https://{host}/api/v2/databases/{database}/schemas/{schema}/agents/{agent_name}:feedback"
    
    payload = {
        "orig_request_id": request_id,
        "positive": positive,
        "feedback_message": feedback_message,
        "categories": categories
    }
    
    headers = {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code < 400:
        return {"success": True, "message": "Feedback submitted successfully"}
    else:
        return {"success": False, "message": f"Error: {response.status_code} - {response.text}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Submit feedback for Cortex Agent requests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Submit positive feedback:
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --request-id "abc-123-def" --positive --message "Accurate answer!"

  # Submit negative feedback with categories:
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --request-id "abc-123-def" --negative --message "Wrong data returned" \\
      --categories "incorrect_data,wrong_tool"

  # Minimal positive feedback (no message):
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema MY_SCHEMA \\
      --request-id "abc-123-def" --positive
        """
    )
    
    # Required arguments
    parser.add_argument("--agent-name", required=True, help="Name of the agent")
    parser.add_argument("--database", required=True, help="Database where agent is located")
    parser.add_argument("--schema", required=True, help="Schema where agent is located")
    parser.add_argument("--request-id", required=True, help="Original request ID to provide feedback for")
    
    # Feedback type (mutually exclusive)
    feedback_group = parser.add_mutually_exclusive_group(required=True)
    feedback_group.add_argument(
        "--positive",
        action="store_true",
        help="Submit positive feedback"
    )
    feedback_group.add_argument(
        "--negative",
        action="store_true",
        help="Submit negative feedback"
    )
    
    # Optional arguments
    parser.add_argument(
        "--message",
        default="",
        help="Feedback message text (optional)"
    )
    parser.add_argument(
        "--categories",
        default="",
        help="Comma-separated list of feedback categories (optional)"
    )
    parser.add_argument(
        "--connection",
        default="snowhouse",
        help="Snowflake connection name (default: snowhouse)"
    )
    
    args = parser.parse_args()
    
    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    
    # Parse categories
    categories = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else []
    
    # Determine positive/negative
    is_positive = args.positive
    
    logger.info("\nSubmitting Feedback to Cortex Agent")
    logger.info("=" * 60)
    logger.info(f"Agent: {args.database}.{args.schema}.{args.agent_name}")
    logger.info(f"Request ID: {args.request_id}")
    logger.info(f"Feedback: {'Positive 👍' if is_positive else 'Negative 👎'}")
    if args.message:
        logger.info(f"Message: {args.message}")
    if categories:
        logger.info(f"Categories: {', '.join(categories)}")
    logger.info("=" * 60 + "\n")
    
    # Connect and submit feedback
    conn = snowflake.connector.connect(connection_name=args.connection)
    
    try:
        result = submit_agent_feedback(
            database=args.database,
            schema=args.schema,
            agent_name=args.agent_name,
            request_id=args.request_id,
            positive=is_positive,
            feedback_message=args.message,
            categories=categories,
            connection=conn
        )
        
        if result["success"]:
            logger.info(f"✓ {result['message']}")
        else:
            logger.error(f"✗ {result['message']}")
            exit(1)
    finally:
        conn.close()

