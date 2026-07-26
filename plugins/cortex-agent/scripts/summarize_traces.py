"""
Summarize OpenTelemetry traces from Cortex Agent executions into dense dictionaries.

Supports two input formats:
1. Spans list format: trace = {"spans": [...]}
2. DataFrame format: trace = {"timestamp": {...}, "record": {...}, "record_attributes": {...}, ...}
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from trulens.otel.semconv.trace import SpanAttributes as TruLensSpanAttributes

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from utils.span_utils import CortexAgentSpanAttributes  # noqa: E402


# Span name keywords for matching
# NOTE: the filtering logic below is a parallel of the filtering logic used for frontend rendering of spans.
# See: https://github.com/snowflake-eng/snapps/blob/edb2c90970cacbbfc7ba4cab5f5bb21ab540e350/pep/ui/apps/snowsight/src/components/intelligenceAdmin/src/traces/ExecutionTraceBreakdown/utils/displayNames.ts#L17-L27
class SpanNameKeywords:
    """Keywords for case-insensitive span name matching in Cortex Agent traces."""
    
    # Meta spans (filtered from timeline)
    AGENT_V2_REQUEST_RESPONSE_INFO = "AgentV2RequestResponseInfo"
    AGENT = "Agent"
    CORTEX_AGENT_REQUEST = "CORTEX_AGENT_REQUEST"
    
    # Reasoning spans (lowercase keywords for case-insensitive matching)
    REASONING_PLANNING_KEYWORD = "reasoningagentstepplanning"
    RESPONSE_GENERATION_KEYWORD = "responsegeneration"
    RESPONSE_KEYWORD = "response"
    GENERATION_KEYWORD = "generation"
    
    # Tool spans (lowercase keywords for case-insensitive matching)
    ANALYST_KEYWORD = "analyst"
    SQL_EXECUTION_KEYWORD = "sqlexecution_cortexanalyst"
    CHART_GENERATION_KEYWORD = "cortexcharttoolimpl"
    WEB_SEARCH_KEYWORD = "web"
    CORTEX_SEARCH_KEYWORD = "search"
    CUSTOM_TOOL_KEYWORD = "toolcall"
    
    # Legacy patterns (kept for compatibility)
    CORTEX_ANALYST_TOOL_PREFIX = "CortexAnalystTool_"


def summarize_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize an OpenTelemetry trace into a dense dictionary.
    
    Args:
        trace: Dictionary containing trace data in one of two formats:
               - Spans list format: {"spans": [...]}
               - DataFrame format: {"timestamp": {...}, "record": {...}, ...}
        
    Returns:
        Dense dictionary with agent name, input/output, and execution timeline
    """
    # Convert DataFrame format to spans list format if needed
    if "spans" not in trace and "record" in trace:
        spans = _convert_dataframe_to_spans(trace)
    else:
        spans = trace.get("spans", [])
    
    # Extract basic information from parent span
    summary = _extract_basic_info(spans)
    
    # Create execution trace maintaining original span order
    summary["execution_trace"] = _extract_execution_timeline(spans)
    
    # Extract execution metadata
    summary["metadata"] = _extract_metadata(spans)
    
    return summary


def _convert_dataframe_to_spans(df_trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert DataFrame format trace to spans list format.
    
    DataFrame format has structure:
    {
        "timestamp": {"0": "...", "1": "...", ...},
        "trace": {"0": {"span_id": "...", "trace_id": "..."}, ...},
        "record": {"0": {"name": "...", ...}, ...},
        "record_attributes": {"0": {...}, ...}
    }
    
    Convert to spans list format:
    [
        {
            "span_id": "...",
            "parent_span_id": None,
            "span_name": "...",
            "attributes": {...}
        },
        ...
    ]
    """
    spans = []
    
    trace_info = df_trace.get("trace", {})
    records = df_trace.get("record", {})
    record_attrs = df_trace.get("record_attributes", {})
    
    # Iterate through each index
    for idx in sorted(records.keys(), key=lambda x: int(x)):
        record = records[idx]
        attrs = record_attrs.get(idx, {})
        trace_data = trace_info.get(idx, {}) or {}
        
        span = {
            "span_id": trace_data.get("span_id"),
            "parent_span_id": trace_data.get("parent_span_id") or None,
            "span_name": record.get("name", ""),
            "attributes": attrs,
        }
        
        spans.append(span)
    
    return spans


def _parse_json_array(json_str: Optional[str]) -> Optional[List[Any]]:
    """Parse JSON array string, handling failures gracefully."""
    if not json_str:
        return None
    
    try:
        import json
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return json_str


# Reasoning/Planning formatting functions
def _format_reasoning_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format reasoning/planning data as a summary span."""
    step_number = span_name.split("-")[-1]
    return {
        "type": "reasoning",
        "step_number": step_number,
        "span_name": span_name,
        "thinking": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_THINKING_RESPONSE),
        "duration_ms": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_DURATION),
        "model": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_MODEL),
        "status": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_STATUS),
        "tools_selected": _parse_json_array(attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOOL_SEL_NAME)),
        "token_usage": {
            "input": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_INPUT),
            "output": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_OUTPUT),
            "cache_read": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_CACHE_READ_INPUT),
            "cache_write": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_CACHE_WRITE_INPUT),
        },
    }


def _format_response_generation_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format response generation data as a summary span."""
    step_number = span_name.split("-")[-1]
    return {
        "type": "response_generation",
        "step_number": step_number,
        "span_name": span_name,
        "response": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_RESPONSE),
        "duration_ms": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_DURATION),
        "model": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_MODEL),
        "token_usage": {
            "input": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_INPUT),
            "output": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_OUTPUT),
            "cache_read": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_CACHE_READ_INPUT),
        },
    }


# Tool formatting functions - extract and format in one step
def _format_sql_execution_as_tool_call(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format SQL execution data as a tool call."""
    return {
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "tool_type": "sql_execution",
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_QUERY),
        },
        "output": {
            "result": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_RESULT),
            "query_id": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_QUERY_ID),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_STATUS),
            "status_code": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_STATUS_CODE),
            "status_description": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_STATUS_DESCRIPTION),
            "request_id": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_REQUEST_ID),
        },
    }


def _format_cortex_analyst_as_tool_call(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format Cortex Analyst data as a tool call."""
    return {
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "tool_type": "cortex_analyst",
        "tool_name": span_name.replace(SpanNameKeywords.CORTEX_ANALYST_TOOL_PREFIX, ""),
        "input": {
            "messages": _parse_json_array(attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_MESSAGES)),
            "semantic_model": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_SEMANTIC_MODEL),
        },
        "output": {
            "sql_query": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_SQL_QUERY),
            "text": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_TEXT),
            "thinking": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_THINK),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_STATUS),
            "status_code": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_STATUS_CODE),
            "question_category": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_QUESTION_CATEGORY),
            "request_id": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_REQUEST_ID),
            "verified_queries_used": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_VERIFIED_QUERIES_USED),
        },
    }


def _format_chart_generation_as_tool_call(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format chart generation data as a tool call."""
    return {
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "tool_type": "chart_generation",
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.CHART_GEN_QUERY),
            "data": attrs.get(CortexAgentSpanAttributes.CHART_GEN_DATA),
        },
        "output": {
            "response": attrs.get(CortexAgentSpanAttributes.CHART_GEN_RESPONSE),
            "response_type": attrs.get(CortexAgentSpanAttributes.CHART_GEN_RESPONSE_TYPE),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CHART_GEN_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CHART_GEN_STATUS),
            "status_code": attrs.get(CortexAgentSpanAttributes.CHART_GEN_STATUS_CODE),
            "request_id": attrs.get(CortexAgentSpanAttributes.CHART_GEN_REQUEST_ID),
        },
    }


def _format_web_search_as_tool_call(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format web search data as a tool call."""
    return {
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "tool_type": "web_search",
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_QUERY),
            "limit": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_LIMIT),
            "filter": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_FILTER),
        },
        "output": {
            "results": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_RESULTS),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_STATUS),
            "status_code": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_STATUS_CODE),
            "status_description": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_STATUS_DESCRIPTION),
            "request_id": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_REQUEST_ID),
        },
    }


def _format_cortex_search_as_tool_call(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format cortex search data as a tool call."""
    return {
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "tool_type": "cortex_search",
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_QUERY),
            "name": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_NAME),
            "limit": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_LIMIT),
            "filter": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_FILTER),
            "columns": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_COLUMNS),
            "scoring_config": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_SCORING_CONFIG),
        },
        "output": {
            "results": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_RESULTS),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_STATUS),
            "status_code": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_STATUS_CODE),
            "status_description": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_STATUS_DESCRIPTION),
            "service_id": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_SERVICE_ID),
            "request_id": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_REQUEST_ID),
        },
    }


def _format_custom_tool_as_tool_call(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format custom tool data as a tool call."""
    return {
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "tool_type": "custom_tool",
        "input": {
            "name": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_NAME),
            "argument_name": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_ARG_NAME),
            "argument_value": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_ARG_VALUE),
        },
        "output": {
            "results": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_RESULTS),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_STATUS),
            "status_code": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_STATUS_CODE),
            "status_description": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_STATUS_DESCRIPTION),
            "request_id": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_REQUEST_ID),
        },
    }


def _format_sql_execution_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format SQL execution data as a summary span."""
    return {
        "type": "tool_call",
        "tool_type": "sql_execution",
        "span_name": span_name,
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_QUERY),
        },
        "output": {
            "result": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_RESULT),
            "query_id": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_QUERY_ID),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_STATUS),
            "status_description": attrs.get(CortexAgentSpanAttributes.SQL_EXEC_STATUS_DESCRIPTION),
        },
    }


def _format_cortex_analyst_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format Cortex Analyst data as a summary span."""
    tool_name = span_name.replace(SpanNameKeywords.CORTEX_ANALYST_TOOL_PREFIX, "")
    return {
        "type": "tool_call",
        "tool_type": "cortex_analyst",
        "tool_name": tool_name,
        "span_name": span_name,
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "input": {
            "messages": _parse_json_array(attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_MESSAGES)),
            "semantic_model": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_SEMANTIC_MODEL),
        },
        "output": {
            "sql_query": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_SQL_QUERY),
            "text": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_TEXT),
            "thinking": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_THINK),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_STATUS),
            "question_category": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_QUESTION_CATEGORY),
            "verified_queries_used": attrs.get(CortexAgentSpanAttributes.CORTEX_ANALYST_VERIFIED_QUERIES_USED),
        },
    }


def _format_chart_generation_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format chart generation data as a summary span."""
    return {
        "type": "tool_call",
        "tool_type": "chart_generation",
        "span_name": span_name,
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.CHART_GEN_QUERY),
            "data": attrs.get(CortexAgentSpanAttributes.CHART_GEN_DATA),
        },
        "output": {
            "response": attrs.get(CortexAgentSpanAttributes.CHART_GEN_RESPONSE),
            "response_type": attrs.get(CortexAgentSpanAttributes.CHART_GEN_RESPONSE_TYPE),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CHART_GEN_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CHART_GEN_STATUS),
        },
    }


def _format_web_search_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format web search data as a summary span."""
    return {
        "type": "tool_call",
        "tool_type": "web_search",
        "span_name": span_name,
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_QUERY),
            "limit": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_LIMIT),
            "filter": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_FILTER),
        },
        "output": {
            "results": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_RESULTS),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_STATUS),
            "status_description": attrs.get(CortexAgentSpanAttributes.WEB_SEARCH_STATUS_DESCRIPTION),
        },
    }


def _format_cortex_search_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format cortex search data as a summary span."""
    return {
        "type": "tool_call",
        "tool_type": "cortex_search",
        "span_name": span_name,
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "input": {
            "query": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_QUERY),
            "name": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_NAME),
            "limit": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_LIMIT),
            "filter": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_FILTER),
            "columns": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_COLUMNS),
        },
        "output": {
            "results": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_RESULTS),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_STATUS),
            "service_id": attrs.get(CortexAgentSpanAttributes.CORTEX_SEARCH_SERVICE_ID),
        },
    }


def _format_custom_tool_summary_span(attrs: Dict[str, Any], span_name: str) -> Dict[str, Any]:
    """Extract and format custom tool data as a summary span."""
    return {
        "type": "tool_call",
        "tool_type": "custom_tool",
        "span_name": span_name,
        "tool_id": attrs.get(CortexAgentSpanAttributes.AGENT_TOOL_ID),
        "input": {
            "name": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_NAME),
            "argument_name": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_ARG_NAME),
            "argument_value": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_ARG_VALUE),
        },
        "output": {
            "results": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_RESULTS),
        },
        "metadata": {
            "duration_ms": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_DURATION),
            "status": attrs.get(CortexAgentSpanAttributes.CUSTOM_TOOL_STATUS),
        },
    }


def _extract_basic_info(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract agent name, user input, and agent output from spans."""
    info = {
        "agent_name": None,
        "user_input": None,
        "agent_output": None,
        "database": None,
        "schema": None,
    }
    
    # Look for AgentV2RequestResponseInfo span
    for span in spans:
        if span.get("span_name") == SpanNameKeywords.AGENT_V2_REQUEST_RESPONSE_INFO:
            attrs = span.get("attributes", {})
            info["agent_name"] = attrs.get(CortexAgentSpanAttributes.AGENT_NAME)
            info["user_input"] = attrs.get(TruLensSpanAttributes.RECORD_ROOT.INPUT)
            info["agent_output"] = attrs.get(TruLensSpanAttributes.RECORD_ROOT.OUTPUT)
            info["database"] = attrs.get(CortexAgentSpanAttributes.DATABASE_NAME)
            info["schema"] = attrs.get(CortexAgentSpanAttributes.SCHEMA_NAME)
            info["status"] = attrs.get(CortexAgentSpanAttributes.AGENT_STATUS)
            info["status_description"] = attrs.get(CortexAgentSpanAttributes.AGENT_STATUS_DESCRIPTION)
            break
    
    return info


def _extract_reasoning_steps(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract reasoning/planning steps from spans."""
    reasoning_steps = []
    
    for span in spans:
        span_name = span.get("span_name", "")
        lower_span_name = span_name.lower()
        
        if SpanNameKeywords.REASONING_PLANNING_KEYWORD in lower_span_name:
            attrs = span.get("attributes", {})
            
            step = {
                "step_number": span_name.split("-")[-1],
                "thinking": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_THINKING_RESPONSE),
                "duration_ms": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_DURATION),
                "model": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_MODEL),
                "status": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_STATUS),
                "token_usage": {
                    "input": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_INPUT),
                    "output": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_OUTPUT),
                    "cache_read": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_CACHE_READ_INPUT),
                    "cache_write": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_CACHE_WRITE_INPUT),
                    "total": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_TOTAL),
                },
                "tools_selected": _parse_json_array(attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOOL_SEL_NAME)),
            }
            
            reasoning_steps.append(step)
        
        elif SpanNameKeywords.RESPONSE_GENERATION_KEYWORD in lower_span_name or (SpanNameKeywords.RESPONSE_KEYWORD in lower_span_name and SpanNameKeywords.GENERATION_KEYWORD in lower_span_name):
            attrs = span.get("attributes", {})
            
            step = {
                "step_number": span_name.split("-")[-1],
                "step_type": "response_generation",
                "response": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_RESPONSE),
                "duration_ms": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_DURATION),
                "model": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_MODEL),
                "token_usage": {
                    "input": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_INPUT),
                    "output": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_OUTPUT),
                    "cache_read": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_CACHE_READ_INPUT),
                    "total": attrs.get(CortexAgentSpanAttributes.AGENT_PLANNING_TOKEN_COUNT_TOTAL),
                },
            }
            
            reasoning_steps.append(step)
    
    return reasoning_steps


def _extract_tool_calls(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract tool calls with inputs, outputs, and metadata."""
    tool_calls = []
    
    for span in spans:
        span_name = span.get("span_name", "")
        lower_span_name = span_name.lower()
        attrs = span.get("attributes", {})
        
        # SQL Execution for Cortex Analyst (more specific, check first)
        if SpanNameKeywords.SQL_EXECUTION_KEYWORD in lower_span_name:
            tool_calls.append(_format_sql_execution_as_tool_call(attrs))
        
        # Cortex Analyst tool calls (more general, check after SQL execution)
        elif SpanNameKeywords.ANALYST_KEYWORD in lower_span_name:
            tool_calls.append(_format_cortex_analyst_as_tool_call(attrs, span_name))
        
        # Chart generation tool
        elif SpanNameKeywords.CHART_GENERATION_KEYWORD in lower_span_name:
            tool_calls.append(_format_chart_generation_as_tool_call(attrs))
        
        # Web search tool
        elif SpanNameKeywords.WEB_SEARCH_KEYWORD in lower_span_name:
            tool_calls.append(_format_web_search_as_tool_call(attrs))
        
        # Cortex search tool
        elif SpanNameKeywords.CORTEX_SEARCH_KEYWORD in lower_span_name and SpanNameKeywords.WEB_SEARCH_KEYWORD not in lower_span_name:
            tool_calls.append(_format_cortex_search_as_tool_call(attrs))
        
        # Custom tool
        elif SpanNameKeywords.CUSTOM_TOOL_KEYWORD in lower_span_name:
            tool_calls.append(_format_custom_tool_as_tool_call(attrs))
    
    return tool_calls


def _extract_metadata(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract overall execution metadata."""
    metadata = {
        "total_spans": len(spans),
        "span_types": [],
        "total_reasoning_steps": 0,
        "total_tool_calls": 0,
    }
    
    span_types = set()
    for span in spans:
        span_name = span.get("span_name", "")
        lower_span_name = span_name.lower()
        span_types.add(span_name)
        
        if SpanNameKeywords.REASONING_PLANNING_KEYWORD in lower_span_name:
            metadata["total_reasoning_steps"] += 1
        elif (SpanNameKeywords.SQL_EXECUTION_KEYWORD in lower_span_name or
              SpanNameKeywords.ANALYST_KEYWORD in lower_span_name or 
              SpanNameKeywords.CHART_GENERATION_KEYWORD in lower_span_name or
              SpanNameKeywords.WEB_SEARCH_KEYWORD in lower_span_name or
              (SpanNameKeywords.CORTEX_SEARCH_KEYWORD in lower_span_name and SpanNameKeywords.WEB_SEARCH_KEYWORD not in lower_span_name) or
              SpanNameKeywords.CUSTOM_TOOL_KEYWORD in lower_span_name):
            metadata["total_tool_calls"] += 1
    
    metadata["span_types"] = sorted(list(span_types))
    
    return metadata


def _extract_execution_timeline(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract execution timeline maintaining original span order."""
    timeline = []
    
    for span in spans:
        span_name = span.get("span_name", "")
        lower_span_name = span_name.lower()
        attrs = span.get("attributes", {})
        
        # Skip meta spans
        if span_name in [SpanNameKeywords.AGENT_V2_REQUEST_RESPONSE_INFO, SpanNameKeywords.AGENT, SpanNameKeywords.CORTEX_AGENT_REQUEST]:
            continue
        
        # Reasoning/Planning steps
        if SpanNameKeywords.REASONING_PLANNING_KEYWORD in lower_span_name:
            timeline.append(_format_reasoning_summary_span(attrs, span_name))
        
        # Response generation
        elif SpanNameKeywords.RESPONSE_GENERATION_KEYWORD in lower_span_name or (SpanNameKeywords.RESPONSE_KEYWORD in lower_span_name and SpanNameKeywords.GENERATION_KEYWORD in lower_span_name):
            timeline.append(_format_response_generation_summary_span(attrs, span_name))
        
        # SQL Execution (more specific, check first)
        elif SpanNameKeywords.SQL_EXECUTION_KEYWORD in lower_span_name:
            timeline.append(_format_sql_execution_summary_span(attrs, span_name))
        
        # Cortex Analyst tool calls (more general, check after SQL execution)
        elif SpanNameKeywords.ANALYST_KEYWORD in lower_span_name:
            timeline.append(_format_cortex_analyst_summary_span(attrs, span_name))
        
        # Chart generation
        elif SpanNameKeywords.CHART_GENERATION_KEYWORD in lower_span_name:
            timeline.append(_format_chart_generation_summary_span(attrs, span_name))
        
        # Web search
        elif SpanNameKeywords.WEB_SEARCH_KEYWORD in lower_span_name:
            timeline.append(_format_web_search_summary_span(attrs, span_name))
        
        # Cortex search
        elif SpanNameKeywords.CORTEX_SEARCH_KEYWORD in lower_span_name and SpanNameKeywords.WEB_SEARCH_KEYWORD not in lower_span_name:
            timeline.append(_format_cortex_search_summary_span(attrs, span_name))
        
        # Custom tool
        elif SpanNameKeywords.CUSTOM_TOOL_KEYWORD in lower_span_name:
            timeline.append(_format_custom_tool_summary_span(attrs, span_name))
    
    return timeline


def summarize_question_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize a complete question record with trace.
    
    Args:
        record: Dictionary with 'question', 'answer', 'ground_truth', 'record_id', and 'trace'
        
    Returns:
        Dense summary including question metadata and trace summary
    """
    summary = {
        "record_id": record.get("record_id"),
        "question": record.get("question"),
        "answer": record.get("answer"),
        "ground_truth": record.get("ground_truth"),
    }
    
    if "trace" in record:
        summary["trace_summary"] = summarize_trace(record["trace"])
    
    return summary


def summarize_all_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Summarize all question records.
    
    Args:
        questions: List of question records
        
    Returns:
        List of dense summaries
    """
    return [summarize_question_record(q) for q in questions]


if __name__ == "__main__":
    import json
    
    parser = argparse.ArgumentParser(
        description="Summarize OpenTelemetry traces from Cortex Agent executions",
        epilog="""
Examples:
  %(prog)s --input-file traces.json
  %(prog)s --input-file traces.json --output-file output_summary.json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input-file", required=True, help="Input JSON file with traces")
    parser.add_argument("--output-file", help="Output JSON file for summaries (default: <input_file>_summary.json)")
    
    args = parser.parse_args()
    
    output_file = args.output_file or args.input_file.replace(".json", "_summary.json")
    
    with open(args.input_file, 'r') as f:
        questions = json.load(f)
    
    summaries = summarize_all_questions(questions)
    
    with open(output_file, 'w') as f:
        json.dump(summaries, f, indent=2)
    
    print(f"Summarized {len(summaries)} questions to {output_file}")
