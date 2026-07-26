#!/usr/bin/env python3
"""
Run evaluation questions against an agent and compare to expected answers.

Supports multiple LLM judge types:
- insight: Original judge - evaluates business value and correctness
- answeronly: Answer-only judge - evaluates final answer, ignores methodology
- flex: Flex judge - "Outcome Over Method", accepts valid alternative approaches

Supports split execution modes:
- --testonly: Run agent tests only, save responses to responses/ folder
- --evalonly N: Run LLM judge N times on saved responses

EVALUATION SOURCES:
    - Snowflake table/view name
    - SQL query (must start with SELECT)

REQUIRED COLUMNS:
    - question: The question text to ask the agent
    - expected_answer: The expected answer for comparison

OPTIONAL COLUMNS:
    - expected_sqls: Reference SQL(s) for methodology comparison (flex judge)

OUTPUT:
    Creates a directory with individual responses and evaluation_summary.json
"""

import argparse
import json
import re
import snowflake.connector
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from test_agent import test_agent
from datetime import date, datetime


NUM_THREADS = 8


# =============================================================================
# Response Parsing Helpers
# =============================================================================

def parse_sectioned_judge_response(response: str) -> dict:
    """
    Parse a sectioned judge response (ANALYSIS/REASONING/RATING format).
    
    Used by answeronly and flex judges.
    Ported from cortex/cortexagent/eval/llm_judge.go parseSectionedJudgeResponse()
    
    Args:
        response: Raw LLM response containing ANALYSIS:, REASONING:, RATING: sections
        
    Returns:
        dict: {"analysis": str, "reasoning": str, "rating": int}
        
    Raises:
        ValueError: If no sections found or rating is missing/invalid
    """
    result = {"analysis": "", "reasoning": "", "rating": 0}
    
    # Check for [Output] marker and extract content after it
    output_match = re.search(r'\[Output\](.*?)$', response, re.DOTALL)
    if output_match:
        response = output_match.group(1)
    
    # Find all section headers. Colon is optional and angle brackets are optional
    # to handle nondeterministic LLM formats: "ANALYSIS:", "## ANALYSIS", "<ANALYSIS>", etc.
    sections_regex = re.compile(r'(?m)^(?:#*\s*)?<?(ANALYSIS|REASONING|RATING)>?:?', re.MULTILINE)
    indices = [(m.start(), m.group(1)) for m in sections_regex.finditer(response)]
    
    if not indices:
        raise ValueError(f"No sections found in response: {response[:200]}")
    
    # Extract content for each section
    for i, (start, section_name) in enumerate(indices):
        # Determine end of this section
        end = len(response) if i == len(indices) - 1 else indices[i + 1][0]
        section_content = response[start:end]
        
        # Extract the content after the header
        header_pattern = r'(?:#*\s*)?<?' + section_name + r'>?:?\s*(.*)'
        content_match = re.match(header_pattern, section_content, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
            
            if section_name == "ANALYSIS":
                result["analysis"] = content
            elif section_name == "REASONING":
                result["reasoning"] = content
            elif section_name == "RATING":
                # Extract numeric value from rating
                num_match = re.search(r'\d+', content)
                if num_match:
                    result["rating"] = int(num_match.group())
                else:
                    raise ValueError(f"No numeric rating found in: {content}")
    
    return result


def extract_response_components(response):
    """
    Extract text, tables, and full response components from agent response.
    
    Args:
        response: Raw agent response dict with 'content' key
        
    Returns:
        tuple: (text_answer, table_contents, full_response)
    """
    text_answer_parts = []
    table_contents_parts = []
    full_response_parts = []
    
    if response and 'content' in response:
        for item in response['content']:
            item_type = item.get('type')
            if item_type == 'text':
                text_answer_parts.append(item['text'])
                full_response_parts.append(item['text'])
            elif item_type == 'chart':
                chart_info = item.get('chart', {})
                chart_spec = chart_info.get('chart_spec', '{}')
                full_response_parts.append(f"[CHART: {chart_spec}]")
            elif item_type == 'table':
                # Format table data in a readable way
                table_info = item.get('table', {})
                title = table_info.get('title', 'Table')
                result_set = table_info.get('result_set', {})
                
                # Extract column names from metadata
                metadata = result_set.get('resultSetMetaData', {})
                row_types = metadata.get('rowType', [])
                columns = [col.get('name', f'col_{idx}') for idx, col in enumerate(row_types)]
                
                # Format as markdown table
                data = result_set.get('data', [])
                if columns and data:
                    table_lines = [f"**{title}**"]
                    table_lines.append("| " + " | ".join(columns) + " |")
                    table_lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
                    for row in data:
                        table_lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
                    formatted_table = "\n".join(table_lines)
                    table_contents_parts.append(formatted_table)
                    full_response_parts.append(formatted_table)
                else:
                    table_contents_parts.append(f"[TABLE: {title}]")
                    full_response_parts.append(f"[TABLE: {title}]")
            elif item_type == 'tool_use':
                # Include tool uses for flex judge methodology evaluation
                tool_name = item.get('name', 'unknown')
                tool_input = item.get('input', {})
                full_response_parts.append(f"[TOOL_USE: {tool_name}]\n{json.dumps(tool_input, indent=2)}")
            elif item_type == 'tool_result':
                # Include tool results for flex judge methodology evaluation
                tool_content = item.get('content', '')
                full_response_parts.append(f"[TOOL_RESULT]\n{tool_content[:500]}...")
    
    return (
        "\n\n".join(text_answer_parts),
        "\n\n".join(table_contents_parts),
        "\n\n".join(full_response_parts)
    )


# =============================================================================
# Judge Implementations
# =============================================================================

def evaluate_answer_insight(question, expected_answer, actual_answer, conn):
    """
    Use the original insight LLM judge prompt to evaluate an agent's answer.
    
    Returns JSON format: {"is_correct": bool, "score": float, "reasoning": str}
    
    Args:
        question: The user's question
        expected_answer: Expected answer guidelines
        actual_answer: The agent's actual response
        conn: Snowflake connection
        
    Returns:
        dict: {"is_correct": bool, "score": float, "reasoning": str}
    """
    if not actual_answer or not actual_answer.strip():
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": "No answer provided by agent"
        }
    
    evaluation_prompt = f"""You are a pragmatic and results-oriented expert data analyst. Your task is to act as a judge, evaluating a data analytics response. Your entire evaluation is governed by a single principle: **the business value and correctness of the final answer are what matter most.**

---

[Inputs]

QUESTION: {question}
EXPECTED ANSWER GUIDELINES: {expected_answer}
RESPONSE ANSWER: {actual_answer}

---

[The Golden Rule: Outcome Over Method]

This is the most critical instruction. **A response that arrives at the correct and actionable business answer using a logically sound, alternative method is a perfect-score response (Rating 1).** Do not penalize a response for deviating from the REFERENCE SQL(S) if its own method is valid and successfully answers the user's QUESTION. Your primary job is to assess the final result, not to enforce a specific implementation.

The EXPECTED ANSWER GUIDELINES are **one example of a correct solution, not the only one.** Use them as a benchmark to validate the correctness of the RESPONSE ANSWER, but not as a rigid checklist for the methodology.

---

[Evaluation Process]

Follow these steps in order:

**Step 1: Evaluate the Final Answer's Correctness and Utility.**
First, look only at the RESPONSE ANSWER. Does it directly and accurately answer the user's QUESTION? Does it align with the key findings in the EXPECTED ANSWER GUIDELINES?
* If the answer is factually correct, complete, and provides clear business value, it is a strong candidate for a **Rating 2**. Proceed to Step 2 to validate the methodology.
* If the answer is factually incorrect, misleading, or misses the core business goal, it is a **Rating 0**.

**Step 2: Determine the Final Rating.**
Synthesize your findings into a final rating.

* **2 - CORRECT (Full Points):** The RESPONSE ANSWER is correct, complete, and valuable. The analytical method used was logically sound, *even if it differed from the reference solution.*
* **1 - PARTIALLY CORRECT (Partial Points):** The RESPONSE ANSWER is on the right track but contains minor factual errors, is incomplete, or the methodology has small flaws that detract from the overall quality but don't invalidate the entire result.
* **0 - INCORRECT (No Points):** The RESPONSE ANSWER is factually wrong, misleading, or irrelevant. The methodology is fundamentally flawed.

---

[Common Pitfalls to Avoid]

* **Method Fixation:** Do not downgrade a response simply because it didn't use the exact SQL, functions, or tables listed in the EXPECTED ANSWER GUIDELINES.
* **Ignoring Equivalency:** Recognize that different metrics can often serve as valid proxies for each other (e.g., utilization rate vs. run-rate comparison). If the proxy is logical and yields the right result, the response is correct.

---

[Output]

Respond with ONLY a JSON object in this exact format:
{{"is_correct": true/false, "score": 0.0-2.0, "reasoning": "explanation"}}"""
    
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            'claude-sonnet-4-5',
            %s
        ) as evaluation
        """
        cursor.execute(query, (evaluation_prompt,))
        result = cursor.fetchone()[0]
        cursor.close()
        
        # Extract JSON from response (LLM might add extra text)
        result = result.strip()
        
        # Find JSON object in response
        start = result.find('{')
        end = result.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = result[start:end]
            evaluation = json.loads(json_str)
            return evaluation
        else:
            raise ValueError(f"No JSON object found in response: {result}")
            
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}")
        print(f"Response was: {result[:200]}")
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": f"JSON parse error: {str(e)}"
        }
    except Exception as e:
        print(f"⚠️  Evaluation failed: {e}")
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": f"Evaluation error: {str(e)}"
        }


def evaluate_answer_only(question, expected_answer, actual_answer, conn, 
                         table_contents="", analysis_date="", response_full=""):
    """
    Use the answer-only LLM judge prompt to evaluate an agent's answer.
    
    Evaluates final answer correctness only, ignoring methodology.
    Ported from cortex/cortexagent/orchestrator/prompts/templates/answer_only_eval.tmpl
    
    Args:
        question: The user's question
        expected_answer: Expected answer guidelines
        actual_answer: The agent's actual response text (text only)
        conn: Snowflake connection
        table_contents: Table contents from the response
        analysis_date: Expected analysis date for temporal queries
        response_full: Full response including tool uses and results
        
    Returns:
        dict: {"is_correct": bool, "score": float, "reasoning": str, "analysis": str}
    """
    if not actual_answer or not actual_answer.strip():
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": "No answer provided by agent",
            "analysis": ""
        }
    
    evaluation_prompt = f"""You are an expert data analyst acting as a strict and consistent judge.
Your job is to evaluate the final RESPONSE ANSWER and the TABLE CONTENTS only, using the correctness requirements defined in the EXPECTED ANSWER GUIDELINES.
You must score deterministically.

# Primary Rule: Correctness Is 100% Determined by EXPECTED ANSWER GUIDELINES
IMPORTANT: The analysis was performed on the EXPECTED ANALYSIS DATE or assumed to be happened on the EXPECTED ANALYSIS DATE. So, do not penalize the response for not including data after this date, or for including/mentioning some data after this date, as long as the answer correctly achieve the result specified in the EXPECTED ANSWER GUIDELINES and extracts data as described.

Follow the EXPECTED ANSWER GUIDELINES exactly as written.
- If the guidelines require exact numeric matches, allow for minor numerical differences due to rounding or formatting. Examples: $4.78M and 4775329.3 are EQUIVALENT; $2.16M and 2162127.57 are EQUIVALENT; 24.2% and 24% are EQUIVALENT. These are simply different representations of the same number. Focus on whether the numbers convey the same business insight rather than exact digit-by-digit matching. Do NOT reduce the rating when numbers match in value but differ only in format (millions abbreviation vs decimal, percentage with/without decimals, etc.).
- If the guidelines require listing items (e.g., "list all categories"), allow partial listings that show the most significant items (e.g., "top 5 by revenue") AND group remaining less significant items (e.g., "Others - $10K combined" IS a complete list. Do NOT penalize for "missing detailed breakdown" of insignificant items.) as long as they correctly represent the key business insights and ordering. Do not penalize for omitting granular details of less significant items unless the guidelines explicitly require and emphasize completeness of all items.
- If the response includes common default/system categories (e.g., "Anonymous User", "Unknown", "Default") that are not in the expected answer, do NOT give rating 0 immediately. Instead, check the answer more carefully and give partial credit (Rating 1) if the top 4-5 results (after removing the default category) are correct and properly ordered. This is a filtering issue, but not an unrecoverable error if the others in the list still reflect the correct business/data-analysis insight.
- If the response lists categories in numbered/bulleted format with correct amounts (e.g., "1. Japan Market - $3.87B...some more details...., 2. Germany Market - $2.38B...some more details...."), this SATISFIES the "list all categories" requirement even if presented narratively. Only penalize if MAJOR categories are completely missing or if the top items are incorrect.
- If the guidelines require or mention charts/tables ideally or optionally, recognize that `<chart>` tags in RESPONSE ANSWER represent actual visualizations/charts that contain the detailed tabular data. Always check TABLE CONTENTS for the actual tabular breakdown from these charts. Do NOT penalize if TABLE CONTENTS is empty but `<chart>` tags are present in the response - the charts contain the data.
- If the response includes additional context, monthly trends, or extra analysis beyond what was explicitly required, this is a POSITIVE attribute that demonstrates thoroughness and should NOT reduce the rating. Do NOT penalize for "extraneous information" or "extensive additional analysis" as long as the core requirements are met. Additional insights are helpful, not harmful, and do not make an otherwise correct answer incorrect.
- The analysis was performed on the EXPECTED ANALYSIS DATE shown below. If the EXPECTED ANSWER GUIDELINES mention "current fiscal year" or "through today" or even not mentioning any time period, interpret "today" as the EXPECTED ANALYSIS DATE (not the actual current date when this evaluation is run). If the response explicitly states data ends at a certain date near the EXPECTED ANALYSIS DATE (e.g., "revenue ceased after May 2023", "no activity from March-May"), this is the agent correctly reporting the extent of available data, NOT an error. Do NOT penalize for accurately describing the temporal boundaries of the data available at the analysis date. Only penalize if the response is missing data that should have been available BEFORE or AT the EXPECTED ANALYSIS DATE.
- If the guidelines allow directional correctness, then the RESPONSE ANSWER may differ numerically but must preserve the same overall business conclusion.
- If the guidelines say an error is unacceptable, then it is unacceptable.
- MUST pay attention closely to the whole RESPONSE ANSWER to extract information and understand the insight and data of the answer. Do NOT concentrate solely on the summary at the end or beginning of the answer.
- Do not penalize for presenting information in narrative form if the required numbers are clearly stated with correct values, proper ordering, and key insights, even if not in a strict tabular format in the answer text itself. A narrative response that embeds the data (e.g., "1. Japan Market provided $3.87B...some more details...., 2. Germany Market provided $2.38B...some more details...., 3. Other Countries provided $10M in combination") contains the SAME information as a numbered list (e.g., "1. Japan: $3.87B\\n2. Germany: $2.38B\\n3. East Europe: $7.0M\\n4. ASEAN: $2.8M"). Both formats are correct if all required data is present with correct values and ordering. Do NOT reduce the rating solely because the response uses narrative/paragraph format instead of a numbered list format.
- Pay attention if EXPECTED ANSWER GUIDELINES contains "... is fine too", "... is sufficient", "... is also good", it usually means those are the idicators of main metrics to measure and can give rating 2 if those main factors are correctly cover/compute in the answer.
- Do not loosen or reinterpret the guidelines beyond reasonable numerical tolerance (typically <1-2% difference for percentages, or equivalent unit conversions for absolute numbers).
- Do not consider methodology, tools, SQL, or reasoning steps — only the final answer.
- TABLE CONTENTS contains all tables that have been outputted in the final response. It is imperative to pay attention to it rating.

# [Output Format]

ANALYSIS: State whether the RESPONSE ANSWER satisfies the EXPECTED ANSWER GUIDELINES. Explain specifically: which correctness criteria were met or violated, which numbers or conclusions differed (if any), and whether the deviations affect business correctness as defined by the guidelines.
REASONING: One-sentence justification of the score.
RATING: A single number: 2, 1, or 0

# [Inputs]

QUESTION: {question}
EXPECTED ANALYSIS DATE: {analysis_date}
EXPECTED ANSWER GUIDELINES: {expected_answer}
RESPONSE ANSWER: {actual_answer}
TABLE CONTENTS:
{table_contents}
RESPONSE TOOL USES AND RESULTS: {response_full}

---

[Output]
ANALYSIS:
REASONING: 
RATING:"""
    
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            'claude-sonnet-4-5',
            %s
        ) as evaluation
        """
        cursor.execute(query, (evaluation_prompt,))
        result = cursor.fetchone()[0]
        cursor.close()
        
        # Parse sectioned response (ANALYSIS/REASONING/RATING format)
        parsed = parse_sectioned_judge_response(result)
        
        # Convert to standard return format
        score = float(parsed["rating"])
        is_correct = parsed["rating"] == 2
        
        return {
            "is_correct": is_correct,
            "score": score,
            "reasoning": parsed["reasoning"],
            "analysis": parsed["analysis"]
        }
            
    except ValueError as e:
        print(f"⚠️  Parse error: {e}")
        print(f"Response was: {result[:500] if 'result' in dir() else 'N/A'}")
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": f"Parse error: {str(e)}",
            "analysis": ""
        }
    except Exception as e:
        print(f"⚠️  Evaluation failed: {e}")
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": f"Evaluation error: {str(e)}",
            "analysis": ""
        }


def evaluate_answer_flex(question, expected_answer, actual_answer, conn,
                         expected_sqls="", response_full=""):
    """
    Use the flex LLM judge prompt (Outcome Over Method) to evaluate an agent's answer.
    
    Accepts valid alternative methodologies.
    Ported from cortex/cortexagent/orchestrator/prompts/templates/insight_eval.tmpl
    
    Args:
        question: The user's question
        expected_answer: Expected answer guidelines
        actual_answer: The agent's actual response text
        conn: Snowflake connection
        expected_sqls: Reference SQL(s) for methodology comparison
        response_full: Full response including tool uses and results
        
    Returns:
        dict: {"is_correct": bool, "score": float, "reasoning": str, "analysis": str}
    """
    if not actual_answer or not actual_answer.strip():
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": "No answer provided by agent",
            "analysis": ""
        }
    
    evaluation_prompt = f"""You are a pragmatic and results-oriented expert data analyst. Your task is to act as a judge, evaluating a data analytics response. Your entire evaluation is governed by a single principle: **the business value and correctness of the final answer are what matter most.**


[Output Format]

ANALYSIS: Provide a detailed evaluation. Start by stating whether the final RESPONSE ANSWER was correct. Then, explain *why* the agent's methodology was sound (or flawed), explicitly addressing whether it was a valid alternative to the reference solution. For ratings of 0 or 1, pinpoint the specific errors.
REASONING: A concise, one-sentence summary of your final rating decision.
RATING: The final numerical rating (2, 1, or 0).

---

[Inputs]

QUESTION: {question}
EXPECTED ANSWER GUIDELINES: {expected_answer}
RESPONSE ANSWER: {actual_answer}
REFERENCE SQL(S): {expected_sqls}
RESPONSE TOOL USES AND RESULTS: {response_full}

---

[The Golden Rule: Outcome Over Method]

This is the most critical instruction. **A response that arrives at the correct and actionable business answer using a logically sound, alternative method is a perfect-score response (Rating 2).** Do not penalize a response for deviating from the REFERENCE SQL(S) if its own method is valid and successfully answers the user's QUESTION. Your primary job is to assess the final result, not to enforce a specific implementation.

The REFERENCE SQL(S) and EXPECTED ANSWER GUIDELINES are **one example of a correct solution, not the only one.** Use them as a benchmark to validate the correctness of the RESPONSE ANSWER, but not as a rigid checklist for the methodology.

---

[Evaluation Process]

Follow these steps in order:

**Step 1: Evaluate the Final Answer's Correctness and Utility.**
First, look only at the RESPONSE ANSWER. Does it directly and accurately answer the user's QUESTION? Does it align with the key findings in the EXPECTED ANSWER GUIDELINES?
* If the answer is factually correct, complete, and provides clear business value, it is a strong candidate for a **Rating 2**. Proceed to Step 2 to validate the methodology.
* If the answer is factually incorrect, misleading, or misses the core business goal, it is a **Rating 0**. Use the RESPONSE TOOL USES AND RESULTS to explain the flaw in your analysis.

**Step 2: Evaluate the Analytical Methodology.**
Now, review the RESPONSE TOOL USES AND RESULTS to understand the agent's logic.
* **Was the method logically sound?** An acceptable method must use the correct data and have a valid analytical process that leads to the correct final answer.
* **Is it different but valid?** The agent might use different tables, calculations, or logic than the REFERENCE SQL(S). This is perfectly acceptable and still warrants a **Rating 2** if the approach is logically equivalent and effective.
    * **Example of a Valid Alternative:** If the goal is to find under-utilized accounts, using "absolute unused capacity" and "utilization rate %" is a logically equivalent approach to comparing a "30-day run rate" against total capacity, as both methods effectively measure the same business concept. 

**Step 3: Determine the Final Rating.**
Synthesize your findings into a final rating.

* **2 - CORRECT (Full Points):** The RESPONSE ANSWER is correct, complete, and valuable. The analytical method used was logically sound, *even if it differed from the reference solution.*
* **1 - PARTIALLY CORRECT (Partial Points):** The RESPONSE ANSWER is on the right track but contains minor factual errors, is incomplete, or the methodology has small flaws that detract from the overall quality but don't invalidate the entire result.
* **0 - INCORRECT (No Points):** The RESPONSE ANSWER is factually wrong, misleading, or irrelevant. The methodology is fundamentally flawed.

---

[Common Pitfalls to Avoid]

* **Method Fixation:** Do not downgrade a response simply because it didn't use the exact SQL, functions, or tables listed in the REFERENCE SQL(S).
* **Ignoring Equivalency:** Recognize that different metrics can often serve as valid proxies for each other (e.g., utilization rate vs. run-rate comparison). If the proxy is logical and yields the right result, the response is correct.

---

[Output]
ANALYSIS:
REASONING: 
RATING:"""
    
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            'claude-sonnet-4-5',
            %s
        ) as evaluation
        """
        cursor.execute(query, (evaluation_prompt,))
        result = cursor.fetchone()[0]
        cursor.close()
        
        # Parse sectioned response (ANALYSIS/REASONING/RATING format)
        parsed = parse_sectioned_judge_response(result)
        
        # Convert to standard return format
        score = float(parsed["rating"])
        is_correct = parsed["rating"] == 2
        
        return {
            "is_correct": is_correct,
            "score": score,
            "reasoning": parsed["reasoning"],
            "analysis": parsed["analysis"]
        }
            
    except ValueError as e:
        print(f"⚠️  Parse error: {e}")
        print(f"Response was: {result[:500] if 'result' in dir() else 'N/A'}")
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": f"Parse error: {str(e)}",
            "analysis": ""
        }
    except Exception as e:
        print(f"⚠️  Evaluation failed: {e}")
        return {
            "is_correct": False,
            "score": 0.0,
            "reasoning": f"Evaluation error: {str(e)}",
            "analysis": ""
        }


# =============================================================================
# Data Fetching
# =============================================================================

def fetch_evaluation_questions(source, connection_name="snowhouse"):
    """
    Fetch evaluation questions from a Snowflake table or query.
    
    This function automatically detects whether the source is a table name or SQL query:
    - If source starts with "SELECT", it's treated as a SQL query
    - Otherwise, it's treated as a table name and wrapped in "SELECT * FROM ..."
    
    Args:
        source (str): Either a fully qualified table name (e.g., "db.schema.table")
                     or a SQL query (e.g., "SELECT question, expected_answer FROM ...")
        connection_name (str): Snowflake connection name (default: "snowhouse")
        
    Returns:
        list[dict]: List of question dictionaries, each containing:
                   - question (str): The question text
                   - expected_answer (str): The expected answer
                   - Plus any optional metadata fields present in the source
        
    Raises:
        ValueError: If required columns 'question' or 'expected_answer' are missing
        
    Example:
        # From a table:
        questions = fetch_evaluation_questions("my_db.my_schema.eval_table")
        
        # From a query:
        questions = fetch_evaluation_questions(
            "SELECT question, expected_answer FROM my_table WHERE category = 'finance'"
        )
    """
    conn = snowflake.connector.connect(connection_name=connection_name)
    try:
        cursor = conn.cursor()
        
        # Determine if source is a table name or query
        if source.strip().upper().startswith("SELECT"):
            sql = source
            print("Executing custom query...")
        else:
            sql = f"SELECT * FROM {source}"
            print(f"Fetching from table: {source}")
        
        cursor.execute(sql)
        
        # Get column names from cursor description (case-insensitive)
        column_names = [desc[0].lower() for desc in cursor.description]
        print(f"Columns found: {', '.join(column_names)}")
        
        # Validate required columns
        if 'question' not in column_names:
            raise ValueError(
                f"Required column 'question' not found in result set. "
                f"Available columns: {column_names}"
            )
        if 'expected_answer' not in column_names:
            raise ValueError(
                f"Required column 'expected_answer' not found in result set. "
                f"Available columns: {column_names}"
            )
        
        # Build questions list
        questions = []
        for row in cursor.fetchall():
            # Create dict from row data
            row_dict = dict(zip(column_names, row))
            
            # Extract required fields
            question_data = {
                "question": row_dict["question"],
                "expected_answer": row_dict["expected_answer"]
            }
            
            # Add optional fields if present (common metadata columns)
            optional_fields = [
                "expected_sqls",  # For flex judge
                "tool_used", "author", "date_added", 
                "category", "difficulty", "id", "question_id", 
                "enable_research_mode", "current_date_override"
            ]
            for field in optional_fields:
                if field in row_dict:
                    value = row_dict[field]
                    # Convert date objects to strings for JSON serialization
                    if isinstance(value, (date, datetime)):
                        value = value.isoformat()
                    question_data[field] = value
            
            questions.append(question_data)
        
        return questions
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# Test-Only Mode
# =============================================================================

def run_test_only(agent_name, database, schema, eval_source, output_dir, connection_name="snowhouse"):
    """
    Run agent tests only and save responses to responses/ folder.
    
    This function:
    1. Fetches questions from the evaluation source
    2. Runs each question through the agent
    3. Saves responses with metadata to responses/ subfolder
    
    Args:
        agent_name (str): Name of the agent to evaluate
        database (str): Database where agent is located
        schema (str): Schema where agent is located
        eval_source (str): Table name or SQL query for evaluation questions
        output_dir (str): Base directory for results
        connection_name (str): Snowflake connection name (default: "snowhouse")
        
    Output Structure:
        <output_dir>/
        └── responses/
            ├── q01.json    # Response + metadata for question 1
            ├── q02.json    # Response + metadata for question 2
            └── ...
    """
    # Create output directories
    output_path = Path(output_dir)
    responses_path = output_path / "responses"
    responses_path.mkdir(parents=True, exist_ok=True)
    
    # Fetch questions from source
    print("="*80)
    questions = fetch_evaluation_questions(eval_source, connection_name)
    print(f"Found {len(questions)} evaluation questions\n")
    
    def process_question(i, q):
        """Process a single question (test only, no evaluation)."""
        print(f"\n{'='*80}")
        print(f"Question {i}/{len(questions)} (Test Only)")
        print(f"{'='*80}")
        
        question_text = q["question"]
        
        # Print metadata if available
        if "category" in q:
            print(f"Category: {q['category']}")
        if "difficulty" in q:
            print(f"Difficulty: {q['difficulty']}")
        print(f"Question: {question_text[:100]}...")
        print()
        
        # Temporary file for test_agent output
        temp_response_file = responses_path / f"q{i:02d}_raw.json"
        
        # Run the question through test_agent
        response = test_agent(
            agent_name=agent_name,
            question=question_text,
            output_file=str(temp_response_file),
            database=database,
            schema=schema,
            connection_name=connection_name,
            enable_research_mode=q.get("enable_research_mode", False),
            current_date_override=q.get("current_date_override", None),
        )
        
        # Extract response components
        text_answer, table_contents, full_response = extract_response_components(response)
        
        # Save response with metadata
        response_data = {
            "question_number": i,
            "question": question_text,
            "expected_answer": q["expected_answer"],
            "expected_sqls": q.get("expected_sqls", ""),
            "current_date_override": q.get("current_date_override", ""),
            "metadata": {k: v for k, v in q.items() if k not in ["question", "expected_answer", "expected_sqls", "current_date_override"]},
            "extracted": {
                "text_answer": text_answer,
                "table_contents": table_contents,
                "full_response": full_response
            },
            "raw_response": response
        }
        
        # Save to final location
        response_file = responses_path / f"q{i:02d}.json"
        with open(response_file, 'w') as f:
            json.dump(response_data, f, indent=2)
        
        # Remove temporary file
        if temp_response_file.exists():
            temp_response_file.unlink()
        
        print(f"✓ Saved response to {response_file}")
        return i
    
    # Process questions in parallel
    results = []
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_to_index = {
            executor.submit(process_question, i, q): i
            for i, q in enumerate(questions, 1)
        }
        for future in as_completed(future_to_index):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                index = future_to_index[future]
                print(f"\n⚠️  Error processing question {index}: {e}")
    
    # Print summary
    print(f"\n{'='*80}")
    print("TEST ONLY COMPLETE")
    print(f"{'='*80}")
    print(f"Responses saved to: {responses_path}")
    print(f"Total questions processed: {len(results)}/{len(questions)}")
    print(f"\nTo run evaluation on these responses:")
    print(f"  python run_evaluation.py --evalonly N --output-dir {output_dir} --judge <judge_type>")


# =============================================================================
# Eval-Only Mode
# =============================================================================

def run_eval_only(output_dir, connection_name="snowhouse", judge_type="insight", num_runs=1):
    """
    Run LLM judge on saved responses N times.
    
    This function:
    1. Loads responses from responses/ subfolder
    2. Runs the LLM judge N times on each response
    3. Aggregates results and saves summary
    
    Args:
        output_dir (str): Directory containing responses/ subfolder
        connection_name (str): Snowflake connection name (default: "snowhouse")
        judge_type (str): Judge type - "insight", "answeronly", or "flex"
        num_runs (int): Number of times to run the judge (default: 1)
        
    Output Structure:
        <output_dir>/
        ├── responses/                              # Input (from --testonly)
        │   ├── q01.json
        │   └── ...
        └── eval_20260211_143022_answeronly/        # Timestamped batch folder
            ├── run_1/
            │   └── evaluation_summary.json
            ├── run_2/                              # (if N > 1)
            │   └── evaluation_summary.json
            └── aggregate.json
    """
    output_path = Path(output_dir)
    responses_path = output_path / "responses"
    
    # Create timestamped batch folder
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_name = f"eval_{timestamp}_{judge_type}"
    batch_path = output_path / batch_name
    
    # Validate responses folder exists
    if not responses_path.exists():
        raise ValueError(f"Responses folder not found: {responses_path}\n"
                        f"Run with --testonly first to generate responses.")
    
    # Load all response files
    response_files = sorted(responses_path.glob("q*.json"))
    if not response_files:
        raise ValueError(f"No response files found in {responses_path}")
    
    print("="*80)
    print(f"Loading {len(response_files)} responses from {responses_path}")
    
    responses = []
    for f in response_files:
        with open(f) as fp:
            responses.append(json.load(fp))
    
    print(f"Running {judge_type} judge {num_runs} time(s)\n")
    
    # Create connection for evaluations
    eval_conn = snowflake.connector.connect(connection_name=connection_name)
    
    all_run_results = []
    
    for run_num in range(1, num_runs + 1):
        print(f"\n{'='*80}")
        print(f"EVALUATION RUN {run_num}/{num_runs}")
        print(f"{'='*80}")
        
        run_results = []
        
        def evaluate_response(resp):
            """Evaluate a single response."""
            i = resp["question_number"]
            question_text = resp["question"]
            expected = resp["expected_answer"]
            expected_sqls = resp.get("expected_sqls", "")
            
            extracted = resp.get("extracted", {})
            text_answer = extracted.get("text_answer", "")
            table_contents = extracted.get("table_contents", "")
            full_response = extracted.get("full_response", "")
            
            print(f"  Evaluating Q{i}...")
            
            # Evaluate based on judge type
            if judge_type == "answeronly":
                analysis_date = resp.get("current_date_override", "")
                evaluation = evaluate_answer_only(
                    question_text, expected, text_answer, eval_conn,
                    table_contents=table_contents,
                    analysis_date=analysis_date,
                    response_full=full_response
                )
            elif judge_type == "flex":
                evaluation = evaluate_answer_flex(
                    question_text, expected, text_answer, eval_conn,
                    expected_sqls=expected_sqls,
                    response_full=full_response
                )
            else:
                # Insight judge: combined answer
                actual_answer_combined = text_answer + "\n\n" + table_contents if table_contents else text_answer
                evaluation = evaluate_answer_insight(
                    question_text, expected, actual_answer_combined, eval_conn
                )
            
            result = {
                "question_number": i,
                "question": question_text,
                "expected_answer": expected,
                "actual_answer": text_answer,
                "is_correct": evaluation["is_correct"],
                "score": evaluation["score"],
                "reasoning": evaluation["reasoning"],
                "judge_type": judge_type,
                "run_number": run_num
            }
            
            if judge_type in ["answeronly", "flex"]:
                result["analysis"] = evaluation.get("analysis", "")
            
            # Add metadata
            for k, v in resp.get("metadata", {}).items():
                result[k] = v
            
            return result
        
        # Process responses in parallel
        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            future_to_index = {
                executor.submit(evaluate_response, resp): resp["question_number"]
                for resp in responses
            }
            results_map = {}
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result()
                    results_map[index] = result
                except Exception as e:
                    print(f"\n⚠️  Error evaluating question {index}: {e}")
                    results_map[index] = {
                        "question_number": index,
                        "is_correct": False,
                        "score": 0.0,
                        "reasoning": f"Error: {str(e)}",
                        "judge_type": judge_type,
                        "run_number": run_num,
                        "error": str(e)
                    }
        
        # Sort results by question number
        run_results = [results_map[i] for i in sorted(results_map.keys())]
        all_run_results.append(run_results)
        
        # Save run results
        run_dir = batch_path / f"run_{run_num}"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        summary_file = run_dir / "evaluation_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(run_results, f, indent=2)
        
        # Print run summary
        correct = sum(1 for r in run_results if r["is_correct"])
        avg_score = sum(r["score"] for r in run_results) / len(run_results) if run_results else 0
        print(f"\n  Run {run_num} Results: {correct}/{len(run_results)} correct ({100*correct/len(run_results):.1f}%), avg score: {avg_score:.2f}")
    
    # Close connection
    eval_conn.close()
    
    # Aggregate results across all runs
    aggregate = {
        "num_runs": num_runs,
        "judge_type": judge_type,
        "questions": []
    }
    
    for q_idx in range(len(responses)):
        q_results = {
            "question_number": q_idx + 1,
            "question": responses[q_idx]["question"],
            "scores": [all_run_results[run][q_idx]["score"] for run in range(num_runs)],
            "is_correct_counts": sum(1 for run in range(num_runs) if all_run_results[run][q_idx]["is_correct"]),
            "reasonings": [all_run_results[run][q_idx]["reasoning"] for run in range(num_runs)]
        }
        q_results["avg_score"] = sum(q_results["scores"]) / num_runs
        q_results["correct_rate"] = q_results["is_correct_counts"] / num_runs
        aggregate["questions"].append(q_results)
    
    # Overall aggregate stats
    aggregate["overall"] = {
        "avg_score": sum(q["avg_score"] for q in aggregate["questions"]) / len(aggregate["questions"]),
        "avg_correct_rate": sum(q["correct_rate"] for q in aggregate["questions"]) / len(aggregate["questions"])
    }
    
    # Save aggregate
    aggregate_file = batch_path / "aggregate.json"
    with open(aggregate_file, 'w') as f:
        json.dump(aggregate, f, indent=2)
    
    # Print final summary
    print(f"\n{'='*80}")
    judge_labels = {
        "insight": "Insight Judge",
        "answeronly": "Answer-Only Judge",
        "flex": "Flex Judge (Outcome Over Method)"
    }
    print(f"EVALUATION COMPLETE ({judge_labels.get(judge_type, judge_type)})")
    print(f"{'='*80}")
    print(f"Runs completed: {num_runs}")
    print(f"Results saved to: {batch_path}")
    print(f"Aggregate summary: {aggregate_file}")
    print(f"\nOverall Results ({num_runs} runs):")
    print(f"  Average score: {aggregate['overall']['avg_score']:.2f}/2.0")
    print(f"  Average correct rate: {aggregate['overall']['avg_correct_rate']*100:.1f}%")
    
    if num_runs > 1:
        print(f"\nPer-question variance (across {num_runs} runs):")
        for q in aggregate["questions"]:
            scores = q["scores"]
            variance = sum((s - q["avg_score"])**2 for s in scores) / num_runs
            print(f"  Q{q['question_number']}: avg={q['avg_score']:.2f}, var={variance:.3f}, correct={q['is_correct_counts']}/{num_runs}")
    
    return aggregate


# =============================================================================
# Main Evaluation Runner (Full Mode)
# =============================================================================

def run_evaluation(agent_name, database, schema, eval_source, output_dir, 
                   connection_name="snowhouse", judge_type="insight"):
    """
    Run all evaluation questions against an agent and save results.
    
    This function:
    1. Fetches questions from the evaluation source (table or query)
    2. Runs each question through the agent via test_agent()
    3. Evaluates answers using the selected LLM judge
    4. Saves individual responses as JSON files (q01_response.json, q02_response.json, etc.)
    5. Creates a summary JSON with all results
    
    Args:
        agent_name (str): Name of the agent to evaluate
        database (str): Database where agent is located
        schema (str): Schema where agent is located
        eval_source (str): Table name or SQL query for evaluation questions
        output_dir (str): Directory to save evaluation results
        connection_name (str): Snowflake connection name (default: "snowhouse")
        judge_type (str): Judge type - "insight", "answeronly", or "flex" (default: "insight")
        
    Returns:
        list[dict]: List of result dictionaries containing:
                   - question_number: Sequential number (1-N)
                   - question: The question text
                   - expected_answer: Expected answer
                   - actual_answer: Agent's actual answer
                   - response_file: Path to detailed response JSON
                   - is_correct: Whether answer is correct (LLM-judged)
                   - score: Correctness score (0-2)
                   - reasoning: Evaluation reasoning
                   - Plus any metadata from evaluation source
    
    Output Structure:
        <output_dir>/
        ├── q01_response.json       # Full response for question 1
        ├── q02_response.json       # Full response for question 2
        ├── ...
        └── evaluation_summary.json # Summary of all results
        
    Example:
        results = run_evaluation(
            agent_name="MY_AGENT",
            database="TEMP",
            schema="MY_SCHEMA",
            eval_source="snowscience.semantic_views.agent_eval",
            output_dir="./eval_results",
            connection_name="snowhouse",
            judge_type="flex"
        )
        print(f"Correct: {sum(1 for r in results if r['is_correct'])}/{len(results)}")
    """
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Fetch questions from source
    print("="*80)
    questions = fetch_evaluation_questions(eval_source, connection_name)
    print(f"Found {len(questions)} evaluation questions\n")
    
    # Create connection for evaluations
    eval_conn = snowflake.connector.connect(connection_name=connection_name)
    
    # Helper function to process a single question
    def process_question(i, q):
        """Process a single evaluation question."""
        print(f"\n{'='*80}")
        print(f"Question {i}/{len(questions)}")
        print(f"{'='*80}")
        
        question_text = q["question"]
        expected = q["expected_answer"]
        expected_sqls = q.get("expected_sqls", "")
        
        # Save response to file (q01_response.json, q02_response.json, etc.)
        response_file = output_path / f"q{i:02d}_response.json"
        
        # Print metadata if available
        if "tool_used" in q:
            print(f"Tool: {q['tool_used']}")
        if "category" in q:
            print(f"Category: {q['category']}")
        if "difficulty" in q:
            print(f"Difficulty: {q['difficulty']}")
        if "enable_research_mode" in q:
            print(f"Enable research mode: {q['enable_research_mode']}")
        if "current_date_override" in q:
            print(f"Current date override: {q['current_date_override']}")
        if expected_sqls and judge_type == "flex":
            print(f"Reference SQL: {expected_sqls[:100]}...")
        print(f"Expected: {expected[:100]}...")
        print()
        
        # Run the question through test_agent
        response = test_agent(
            agent_name=agent_name,
            question=question_text,
            output_file=str(response_file),
            database=database,
            schema=schema,
            connection_name=connection_name,
            enable_research_mode=q.get("enable_research_mode", False),
            current_date_override=q.get("current_date_override", None),
        )
        
        # Extract response components
        actual_answer_text, table_contents, full_response = extract_response_components(response)
        
        # Evaluate based on judge type
        if judge_type == "answeronly":
            # Answer-only judge: text only + separate table contents
            analysis_date = q.get("current_date_override", "")
            evaluation = evaluate_answer_only(
                question_text, expected, actual_answer_text, eval_conn,
                table_contents=table_contents,
                analysis_date=analysis_date,
                response_full=full_response
            )
        elif judge_type == "flex":
            # Flex judge: accepts alternative methodologies
            evaluation = evaluate_answer_flex(
                question_text, expected, actual_answer_text, eval_conn,
                expected_sqls=expected_sqls,
                response_full=full_response
            )
        else:
            # Insight judge (default): original behavior - combined answer
            actual_answer_combined = actual_answer_text + "\n\n" + table_contents if table_contents else actual_answer_text
            evaluation = evaluate_answer_insight(
                question_text, expected, actual_answer_combined, eval_conn
            )
        
        # Build result dict with all available metadata
        result = {
            "question_number": i,
            "question": question_text,
            "expected_answer": expected,
            "actual_answer": actual_answer_text,
            "response_file": str(response_file),
            "is_correct": evaluation["is_correct"],
            "score": evaluation["score"],
            "reasoning": evaluation["reasoning"],
            "judge_type": judge_type
        }
        
        # Add judge-specific fields
        if judge_type in ["answeronly", "flex"]:
            result["analysis"] = evaluation.get("analysis", "")
            result["full_response"] = full_response
        if judge_type == "answeronly":
            result["table_contents"] = table_contents
        if judge_type == "flex":
            result["expected_sqls"] = expected_sqls
        
        # Add optional metadata fields from source
        for field in ["tool_used", "author", "date_added", "category", "difficulty", "id", "question_id"]:
            if field in q:
                result[field] = q[field]
        
        return result
    
    results = [None] * len(questions)
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_to_index = {
            executor.submit(process_question, i, q): i-1
            for i, q in enumerate(questions, 1)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                result = future.result()
                results[index] = result
            except Exception as e:
                print(f"\n⚠️  Error processing question {index + 1}: {e}")
                results[index] = {
                    "question_number": index + 1,
                    "question": questions[index]["question"],
                    "expected_answer": questions[index]["expected_answer"],
                    "actual_answer": "",
                    "response_file": str(output_path / f"q{index+1:02d}_response.json"),
                    "is_correct": False,
                    "score": 0.0,
                    "reasoning": f"Error: {str(e)}",
                    "judge_type": judge_type,
                    "error": str(e)
                }
    
    # Close evaluation connection
    eval_conn.close()
    
    # Save summary of all results
    summary_file = output_path / "evaluation_summary.json"
    with open(summary_file, 'w') as f:
        try:
            json.dump(results, f, indent=2)
        except Exception as e:
            print(f"Error saving summary: {e}")
            print(f"Results: {results}")
            f.write(results)
            raise e
    
    # Print completion summary
    print(f"\n{'='*80}")
    judge_labels = {
        "insight": "Insight Judge",
        "answeronly": "Answer-Only Judge",
        "flex": "Flex Judge (Outcome Over Method)"
    }
    print(f"EVALUATION COMPLETE ({judge_labels.get(judge_type, judge_type)})")
    print(f"{'='*80}")
    print(f"Results saved to: {output_dir}")
    print(f"Summary: {summary_file}")
    
    correct = sum(1 for r in results if r["is_correct"])
    total_score = sum(r["score"] for r in results)
    avg_score = total_score / len(results) if results else 0.0
    
    print(f"\nCorrect answers (Rating 2): {correct}/{len(results)} ({100*correct/len(results):.1f}%)")
    print(f"Average score: {avg_score:.2f}/2.0")
    
    # Score distribution for all judges
    rating_2 = sum(1 for r in results if r["score"] == 2)
    rating_1 = sum(1 for r in results if r["score"] == 1)
    rating_0 = sum(1 for r in results if r["score"] == 0)
    print(f"\nScore distribution:")
    print(f"  Rating 2 (Correct):   {rating_2}")
    print(f"  Rating 1 (Partial):   {rating_1}")
    print(f"  Rating 0 (Incorrect): {rating_0}")
    
    return results


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run evaluation questions against an agent using configurable LLM judges",
        epilog="""
Examples:
  # Full evaluation (test + eval):
  %(prog)s --agent-name MY_AGENT --database TEMP --schema MY_SCHEMA --eval-source my_table

  # Test only (save responses for later evaluation):
  %(prog)s --agent-name MY_AGENT --database TEMP --schema MY_SCHEMA --eval-source my_table --testonly

  # Eval only (run judge on saved responses):
  %(prog)s --evalonly 3 --output-dir ./eval_results --judge flex

  # Using different judges:
  %(prog)s --agent-name MY_AGENT --database TEMP --schema MY_SCHEMA --eval-source my_table --judge answeronly
  %(prog)s --agent-name MY_AGENT --database TEMP --schema MY_SCHEMA --eval-source my_table --judge flex

Required columns: question, expected_answer
Optional columns: expected_sqls (for flex judge methodology comparison)

Judge Types:
  insight    - Original judge: evaluates business value and final answer correctness
  answeronly - Answer-only judge: evaluates final answer only, ignores methodology
  flex       - Flex judge: "Outcome Over Method", accepts valid alternative approaches

Execution Modes:
  (default)  - Run both test and eval in one pass
  --testonly - Run agent tests only, save responses to responses/ folder
  --evalonly N - Run LLM judge N times on saved responses (requires prior --testonly run)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Agent arguments (required for full mode and test-only mode)
    parser.add_argument("--agent-name", help="Name of the agent to evaluate")
    parser.add_argument("--database", help="Database where agent is located")
    parser.add_argument("--schema", help="Schema where agent is located")
    parser.add_argument("--eval-source", help="Table name or SQL query for evaluation questions")
    
    # Common arguments
    parser.add_argument("--output-dir", help="Directory for results (default: ./eval_<agent_name>)")
    parser.add_argument("--connection", default="snowhouse", help="Snowflake connection name (default: snowhouse)")
    parser.add_argument(
        "--judge",
        choices=["insight", "answeronly", "flex"],
        default="insight",
        help="Judge type: insight (original), answeronly (answer-focused), flex (outcome over method). Default: insight"
    )
    
    # Execution mode arguments
    parser.add_argument(
        "--testonly",
        action="store_true",
        help="Run agent tests only, save responses to responses/ folder (no evaluation)"
    )
    parser.add_argument(
        "--evalonly",
        type=int,
        metavar="N",
        help="Run LLM judge N times on saved responses (requires prior --testonly run)"
    )
    
    args = parser.parse_args()
    
    # Validate argument combinations
    if args.testonly and args.evalonly:
        parser.error("Cannot use --testonly and --evalonly together")
    
    if args.evalonly:
        # Eval-only mode: only need output-dir
        if not args.output_dir:
            parser.error("--evalonly requires --output-dir to specify where responses are stored")
        
        print("\nAgent Evaluation (Eval-Only Mode)")
        print(f"{'='*80}")
        print(f"Output Directory: {args.output_dir}")
        print(f"Connection: {args.connection}")
        print(f"Judge Type: {args.judge}")
        print(f"Number of runs: {args.evalonly}")
        print(f"{'='*80}\n")
        
        run_eval_only(
            output_dir=args.output_dir,
            connection_name=args.connection,
            judge_type=args.judge,
            num_runs=args.evalonly
        )
    
    elif args.testonly:
        # Test-only mode: need agent args
        if not all([args.agent_name, args.database, args.schema, args.eval_source]):
            parser.error("--testonly requires --agent-name, --database, --schema, and --eval-source")
        
        output_dir = args.output_dir or f"./eval_{args.agent_name}"
        
        print("\nAgent Evaluation (Test-Only Mode)")
        print(f"{'='*80}")
        print(f"Agent: {args.database}.{args.schema}.{args.agent_name}")
        print(f"Evaluation Source: {args.eval_source if len(args.eval_source) < 60 else args.eval_source[:60] + '...'}")
        print(f"Output Directory: {output_dir}")
        print(f"Connection: {args.connection}")
        print(f"{'='*80}\n")
        
        run_test_only(
            agent_name=args.agent_name,
            database=args.database,
            schema=args.schema,
            eval_source=args.eval_source,
            output_dir=output_dir,
            connection_name=args.connection
        )
    
    else:
        # Full mode: need all agent args
        if not all([args.agent_name, args.database, args.schema, args.eval_source]):
            parser.error("Full evaluation requires --agent-name, --database, --schema, and --eval-source")
        
        output_dir = args.output_dir or f"./eval_{args.agent_name}"
        
        judge_labels = {
            "insight": "Insight (Original)",
            "answeronly": "Answer-Only",
            "flex": "Flex (Outcome Over Method)"
        }
        
        print("\nAgent Evaluation")
        print(f"{'='*80}")
        print(f"Agent: {args.database}.{args.schema}.{args.agent_name}")
        print(f"Evaluation Source: {args.eval_source if len(args.eval_source) < 60 else args.eval_source[:60] + '...'}")
        print(f"Output Directory: {output_dir}")
        print(f"Connection: {args.connection}")
        print(f"Judge Type: {judge_labels.get(args.judge, args.judge)}")
        print(f"{'='*80}\n")
        
        run_evaluation(
            args.agent_name, 
            args.database, 
            args.schema, 
            args.eval_source, 
            output_dir, 
            args.connection,
            judge_type=args.judge
        )
