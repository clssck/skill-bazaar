"""AI Observability OTEL span attribute keys used across agent orchestrator.

See SI Tracing Span Attributes: https://docs.google.com/spreadsheets/d/1g_KcuBh0BamGGhPf0Me-R-oZx4MgBCQjg7GCdCI7NFs/edit?gid=0#gid=0
"""

from enum import Enum

_PREFIX = "snow.ai.observability.agent"


class CortexAgentSpanAttributes(str, Enum):
    """OpenTelemetry span attribute keys for Snowflake AI Observability."""
    
    def __str__(self) -> str:
        """Return the enum value instead of the enum name when used in f-strings."""
        return self.value

    # GS-instrumented attributes
    AGENT_NAME = "snow.ai.observability.object.name"
    DATABASE_NAME = "snow.ai.observability.database.name"
    SCHEMA_NAME = "snow.ai.observability.schema.name"
    
    # Agent-level attributes
    AGENT_REQUEST_ID = f"{_PREFIX}.request_id"
    AGENT_THREAD_ID = f"{_PREFIX}.thread_id"
    AGENT_PARENT_MESSAGE_ID = f"{_PREFIX}.parent_message_id"
    # NOTE: this is the full user/assistant conversation history
    AGENT_THREAD_ID_MESSAGES = f"{_PREFIX}.thread_id.messages"
    # NOTE: this is the first message in the thread (i.e. the first user message in the request)
    AGENT_FIRST_MESSAGE_IN_THREAD = f"{_PREFIX}.first_message_in_thread"
    # NOTE: the attribute naming is confusing, but this is intended to be the most recent user message/query
    # The reason why this is named "messages" is to be in sync with the REST API spec
    # See Agent API spec: https://docs.google.com/document/d/1CP_kj6EF5xSAHAYSseqYXGohhHkk81LiP9bhO4m40nM/edit?tab=t.1dx076quyx32#heading=h.uzd2p0rhh6q2
    AGENT_LAST_USER_MESSAGE = f"{_PREFIX}.messages"
    AGENT_TOOL_CHOICE_TYPE = f"{_PREFIX}.tool_choice.type"
    AGENT_TOOL_CHOICE_NAMES = f"{_PREFIX}.tool_choice.names"
    AGENT_TOOL_CHOICE_INPUT_TIMESTAMP = f"{_PREFIX}.tool_choice.input_timestamp"
    AGENT_DURATION = f"{_PREFIX}.duration"
    AGENT_STATUS = f"{_PREFIX}.status"
    AGENT_STATUS_CODE = f"{_PREFIX}.status.code"
    AGENT_STATUS_DESCRIPTION = f"{_PREFIX}.status.description"
    AGENT_THINKING_RESPONSE = f"{_PREFIX}.thinking_response"
    AGENT_RESPONSE = f"{_PREFIX}.response"
    AGENT_SUGGESTED_QUERIES = f"{_PREFIX}.suggested_queries"
    AGENT_RESEARCH_MODE = f"{_PREFIX}.research_mode"
    
    # LLM planning/response generation step attributes
    AGENT_PLANNING_STATUS = f"{_PREFIX}.planning.status"
    AGENT_PLANNING_STATUS_CODE = f"{_PREFIX}.planning.status.code"
    AGENT_PLANNING_STATUS_DESCRIPTION = f"{_PREFIX}.planning.status.description"
    AGENT_PLANNING_QUERY = f"{_PREFIX}.planning.query"
    AGENT_PLANNING_MODEL = f"{_PREFIX}.planning.model"
    AGENT_PLANNING_CUSTOM_INSTR = f"{_PREFIX}.planning.custom_orchestration_instructions"
    AGENT_PLANNING_INSTRUCTION = f"{_PREFIX}.planning.instruction"
    AGENT_PLANNING_THINKING_RESPONSE = f"{_PREFIX}.planning.thinking_response"
    AGENT_PLANNING_RESPONSE = f"{_PREFIX}.planning.response"
    AGENT_PLANNING_TOKEN_COUNT_INPUT = f"{_PREFIX}.planning.token_count.input"
    AGENT_PLANNING_TOKEN_COUNT_CACHE_READ_INPUT = f"{_PREFIX}.planning.token_count.cache_read_input"
    AGENT_PLANNING_TOKEN_COUNT_CACHE_WRITE_INPUT = f"{_PREFIX}.planning.token_count.cache_write_input"
    AGENT_PLANNING_TOKEN_COUNT_OUTPUT = f"{_PREFIX}.planning.token_count.output"
    AGENT_PLANNING_TOKEN_COUNT_TOTAL = f"{_PREFIX}.planning.token_count.total"
    AGENT_PLANNING_TOKEN_COUNT_PLAN = f"{_PREFIX}.planning.token_count.plan"
    AGENT_PLANNING_MESSAGES = f"{_PREFIX}.planning.messages"
    AGENT_PLANNING_DURATION = f"{_PREFIX}.planning.duration"
    AGENT_PLANNING_TOOL_TYPE = f"{_PREFIX}.planning.tool.type"
    AGENT_PLANNING_TOOL_NAME = f"{_PREFIX}.planning.tool.name"
    AGENT_PLANNING_TOOL_DESCRIPTION = f"{_PREFIX}.planning.tool.description"
    AGENT_PLANNING_TOOL_PARAMETERS = f"{_PREFIX}.planning.tool.parameters"
    AGENT_PLANNING_TOOL_SEL_ID = f"{_PREFIX}.planning.tool_selection.id"
    AGENT_PLANNING_TOOL_SEL_TYPE = f"{_PREFIX}.planning.tool_selection.type"
    AGENT_PLANNING_TOOL_SEL_NAME = f"{_PREFIX}.planning.tool_selection.name"
    AGENT_PLANNING_TOOL_SEL_DESCRIPTION = f"{_PREFIX}.planning.tool_selection.description"
    AGENT_PLANNING_TOOL_SEL_ARG_NAME = f"{_PREFIX}.planning.tool_selection.argument.name"
    AGENT_PLANNING_TOOL_SEL_ARG_VALUE = f"{_PREFIX}.planning.tool_selection.argument.value"
    AGENT_PLANNING_TOOL_EXEC_TYPE = f"{_PREFIX}.planning.tool_execution.type"
    AGENT_PLANNING_TOOL_EXEC_ID = f"{_PREFIX}.planning.tool_execution.id"
    AGENT_PLANNING_TOOL_EXEC_NAME = f"{_PREFIX}.planning.tool_execution.name"
    AGENT_PLANNING_TOOL_EXEC_DESCRIPTION = f"{_PREFIX}.planning.tool_execution.description"
    AGENT_PLANNING_TOOL_EXEC_RESULTS = f"{_PREFIX}.planning.tool_execution.results"
    AGENT_PLANNING_TOOL_EXEC_ARG_NAME = f"{_PREFIX}.planning.tool_execution.argument.name"
    AGENT_PLANNING_TOOL_EXEC_ARG_VALUE = f"{_PREFIX}.planning.tool_execution.argument.value"
    AGENT_PLANNING_REQUEST_ID = f"{_PREFIX}.planning.request_id"
    
    # Generic/custom tool attributes
    AGENT_TOOL_ID = f"{_PREFIX}.tool.id"
    CUSTOM_TOOL_REQUEST_ID = f"{_PREFIX}.tool.custom_tool.request_id"
    CUSTOM_TOOL_NAME = f"{_PREFIX}.tool.custom_tool.name"
    CUSTOM_TOOL_ARG_NAME = f"{_PREFIX}.tool.custom_tool.argument.name"
    CUSTOM_TOOL_ARG_VALUE = f"{_PREFIX}.tool.custom_tool.argument.value"
    CUSTOM_TOOL_DURATION = f"{_PREFIX}.tool.custom_tool.duration"
    CUSTOM_TOOL_RESULTS = f"{_PREFIX}.tool.custom_tool.results"
    CUSTOM_TOOL_STATUS = f"{_PREFIX}.tool.custom_tool.status"
    CUSTOM_TOOL_STATUS_CODE = f"{_PREFIX}.tool.custom_tool.status.code"
    CUSTOM_TOOL_STATUS_DESCRIPTION = f"{_PREFIX}.tool.custom_tool.status.description"
    
    # Chart generation tool attributes
    CHART_GEN_QUERY = f"{_PREFIX}.tool.chart_generation.query"
    CHART_GEN_DATA = f"{_PREFIX}.tool.chart_generation.data"
    CHART_GEN_REQUEST_ID = f"{_PREFIX}.tool.chart_generation.request_id"
    CHART_GEN_DURATION = f"{_PREFIX}.tool.chart_generation.duration"
    CHART_GEN_STATUS = f"{_PREFIX}.tool.chart_generation.status"
    CHART_GEN_STATUS_CODE = f"{_PREFIX}.tool.chart_generation.status.code"
    CHART_GEN_STATUS_DESCRIPTION = f"{_PREFIX}.tool.chart_generation.status.description"
    CHART_GEN_RESPONSE = f"{_PREFIX}.tool.chart_generation.response"
    CHART_GEN_RESPONSE_TYPE = f"{_PREFIX}.tool.chart_generation.response.type"  # Not visible to user
    
    # Web search tool attributes
    WEB_SEARCH_QUERY = f"{_PREFIX}.tool.web_search.query"
    WEB_SEARCH_DURATION = f"{_PREFIX}.tool.web_search.duration"
    WEB_SEARCH_REQUEST_ID = f"{_PREFIX}.tool.web_search.request_id"
    WEB_SEARCH_STATUS = f"{_PREFIX}.tool.web_search.status"
    WEB_SEARCH_STATUS_CODE = f"{_PREFIX}.tool.web_search.status.code"
    WEB_SEARCH_STATUS_DESCRIPTION = f"{_PREFIX}.tool.web_search.status.description"
    WEB_SEARCH_RESULTS = f"{_PREFIX}.tool.web_search.results"
    WEB_SEARCH_LIMIT = f"{_PREFIX}.tool.web_search.limit"
    WEB_SEARCH_FILTER = f"{_PREFIX}.tool.web_search.filter"
    # NOTE: Given that paramsOverride.Experimental is still in development, we do not want to expose it to the user.
    # spanutils.AddIfNotEmpty(attrs, "snow.ai.observability.agent.tool.web_search.params_override.experimental", paramsOverride.Experimental)
    
    # SQL execution tool attributes
    SQL_EXEC_QUERY = f"{_PREFIX}.tool.sql_execution.query"
    SQL_EXEC_REQUEST_ID = f"{_PREFIX}.tool.sql_execution.request_id"
    SQL_EXEC_QUERY_ID = f"{_PREFIX}.tool.sql_execution.query_id"
    SQL_EXEC_DURATION = f"{_PREFIX}.tool.sql_execution.duration"
    SQL_EXEC_RESULT = f"{_PREFIX}.tool.sql_execution.result"
    SQL_EXEC_STATUS = f"{_PREFIX}.tool.sql_execution.status"
    SQL_EXEC_STATUS_CODE = f"{_PREFIX}.tool.sql_execution.status.code"
    SQL_EXEC_STATUS_DESCRIPTION = f"{_PREFIX}.tool.sql_execution.status.description"
    
    # Cortex Search tool attributes
    CORTEX_SEARCH_STATUS = f"{_PREFIX}.tool.cortex_search.status"
    CORTEX_SEARCH_STATUS_CODE = f"{_PREFIX}.tool.cortex_search.status.code"
    CORTEX_SEARCH_STATUS_DESCRIPTION = f"{_PREFIX}.tool.cortex_search.status.description"
    CORTEX_SEARCH_QUERY = f"{_PREFIX}.tool.cortex_search.query"
    CORTEX_SEARCH_DURATION = f"{_PREFIX}.tool.cortex_search.duration"
    CORTEX_SEARCH_NAME = f"{_PREFIX}.tool.cortex_search.name"
    CORTEX_SEARCH_SERVICE_ID = f"{_PREFIX}.tool.cortex_search.service_id"
    CORTEX_SEARCH_LIMIT = f"{_PREFIX}.tool.cortex_search.limit"
    CORTEX_SEARCH_FILTER = f"{_PREFIX}.tool.cortex_search.filter"
    CORTEX_SEARCH_COLUMNS = f"{_PREFIX}.tool.cortex_search.columns"
    CORTEX_SEARCH_REQUEST_ID = f"{_PREFIX}.tool.cortex_search.request_id"
    CORTEX_SEARCH_SCORING_CONFIG = f"{_PREFIX}.tool.cortex_search.scoring_config"
    CORTEX_SEARCH_RESULTS = f"{_PREFIX}.tool.cortex_search.results"
    
    # Cortex Analyst tool attributes
    CORTEX_ANALYST_DURATION = f"{_PREFIX}.tool.cortex_analyst.duration"
    CORTEX_ANALYST_MODEL_NAME = f"{_PREFIX}.tool.cortex_analyst.model_name"
    CORTEX_ANALYST_STATUS = f"{_PREFIX}.tool.cortex_analyst.status"
    CORTEX_ANALYST_STATUS_CODE = f"{_PREFIX}.tool.cortex_analyst.status.code"
    CORTEX_ANALYST_STATUS_DESCRIPTION = f"{_PREFIX}.tool.cortex_analyst.status.description"
    CORTEX_ANALYST_SEMANTIC_MODEL = f"{_PREFIX}.tool.cortex_analyst.semantic_model"
    CORTEX_ANALYST_REQUEST_ID = f"{_PREFIX}.tool.cortex_analyst.request_id"
    CORTEX_ANALYST_MESSAGES = f"{_PREFIX}.tool.cortex_analyst.messages"
    CORTEX_ANALYST_SQL_QUERY = f"{_PREFIX}.tool.cortex_analyst.sql_query"
    CORTEX_ANALYST_SUGGESTED_QUERIES = f"{_PREFIX}.tool.cortex_analyst.suggested_queries"
    CORTEX_ANALYST_VERIFIED_QUERIES_USED = f"{_PREFIX}.tool.cortex_analyst.verified_queries_used"
    CORTEX_ANALYST_THINK = f"{_PREFIX}.tool.cortex_analyst.think"
    CORTEX_ANALYST_TEXT = f"{_PREFIX}.tool.cortex_analyst.text"
    CORTEX_ANALYST_QUESTION_CATEGORY = f"{_PREFIX}.tool.cortex_analyst.question_category"
    CORTEX_ANALYST_WARNINGS = f"{_PREFIX}.tool.cortex_analyst.warnings"
    CORTEX_ANALYST_EXPLANATION = f"{_PREFIX}.tool.cortex_analyst.explanation"
    
    # Testing attributes
    TEST = f"{_PREFIX}.test"
    TEST_STEP = f"{_PREFIX}.test.step"
