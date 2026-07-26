---
name: Issue Diagnosis
description: Get problematic question and generate SQL
parent_skill: semantic-view-debug
---

# Issue Diagnosis

## When to Load

Debug mode Step 1: User reports problematic question.

## Task

Get user's question and generate SQL with current semantic view.

## Steps

### 1. Get Questions

Ask user for the problematic natural language question(s). User may provide one or more questions to debug.

### 2. Generate SQL

**For multiple questions**: Use parallel `snowflake_multi_cortex_analyst` calls with local file path without the '@' to generate SQL for all questions at once:

```python
# Batch all Cortex Analyst calls in parallel
snowflake_multi_cortex_analyst(query="{question_1}", semantic_model_file="{WORKING_DIR}/optimization/<semantic_view_name>_semantic_model.yaml")
snowflake_multi_cortex_analyst(query="{question_2}", semantic_model_file="{WORKING_DIR}/optimization/<semantic_view_name>_semantic_model.yaml")
snowflake_multi_cortex_analyst(query="{question_3}", semantic_model_file="{WORKING_DIR}/optimization/<semantic_view_name>_semantic_model.yaml")
```

**For single question**: Use `snowflake_multi_cortex_analyst` tool with local file path directly:

```python
snowflake_multi_cortex_analyst(
    query="{user question}",
    semantic_model_file="{WORKING_DIR}/optimization/<semantic_view_name>_semantic_model.yaml"
)
```

### 3. Present Generated SQL

**For each question**, show:

- Question
- Generated SQL

## Output

- Question(s) captured
- Generated SQL available for all questions
- Ready for root cause analysis

## Next Skill

Load `root_cause_analysis.md` and execute all steps to identify issues before requesting user feedback.
