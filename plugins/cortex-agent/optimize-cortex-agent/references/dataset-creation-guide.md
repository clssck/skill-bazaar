# Evaluation Dataset Creation Guide

**Purpose:** Detailed workflows for creating evaluation datasets from production data or from scratch.
**Used by:** Phase 2 of the optimization workflow.

---

## Check for Existing Dataset

Ask user:
```
Do you already have an evaluation dataset for this agent? 

For example:
- A table with test questions and expected answers
- A spreadsheet or document with evaluation cases
- Production queries you've been tracking
- Known failure cases you want to test

If yes, where is it located?
```

### If Dataset Exists

- Query the table/file to see existing questions
- Count total questions, review coverage across agent capabilities
- Validate expected answers are specific enough
- Assess if additional questions are needed

**Required columns:** `question` (required), `expected_answer` (required)
**Optional columns:** `tool_used`, `category`, `difficulty`, `author`, `date_added`, or any other metadata

---

## Option A: Create from Production Data (Recommended)

If your agent has been running in production, use the Agent Events Explorer.

### Launch the Agent Events Explorer
```bash
uv run streamlit run ../scripts/agent_events_explorer.py -- \
  --connection CONNECTION_NAME \
  --database DATABASE \
  --schema SCHEMA \
  --agent AGENT_NAME
```

### Workflow in the Agent Events Explorer

1. **Fetch Events** — Query production agent events with filters:
   - Set time range, question filters, answer filters
   - Use AI filters to find specific patterns (e.g., "questions about SQL errors")
   - Limit results to manageable size (e.g., 50-100 events)

2. **Review & Annotate** — For each event:
   - See the question, answer, and full trace (scrollable JSON view)
   - Add expected answer for the question
   - Provide feedback (positive/negative, message, categories)
   - Dataset auto-saves after each "Submit & Next"
   - Skip records as needed

3. **Dataset Auto-Saved** — After each annotation:
   - Saved to `eval_dataset_{DATABASE}_{SCHEMA}_{AGENT}.json`
   - Includes all annotated records with question, answer, expected_answer, feedback, trace
   - Optional: Export directly to Snowflake table from the UI

### Loading the Auto-Saved Dataset into Snowflake

```bash
uv run python ../scripts/load_eval_data_from_json.py \
    --json-file eval_dataset_{DATABASE}_{SCHEMA}_{AGENT}.json \
    --database DATABASE \
    --schema SCHEMA \
    --agent-name AGENT_NAME \
    --connection CONNECTION_NAME
```

Creates table `{DATABASE}.{SCHEMA}.EVAL_DATASET_{AGENT_NAME}` with schema:
- `timestamp` (TIMESTAMP), `request_id` (VARCHAR)
- `question` (VARCHAR), `answer` (VARCHAR), `expected_answer` (VARCHAR)
- `feedback` (VARIANT), `trace` (VARIANT)

**Benefits:** Real user questions, includes edge cases, shows current failure patterns, faster than from-scratch creation.

---

## Option B: Create from Scratch

### Question Distribution Target (15-20 questions)

| Category | Percentage | Purpose |
|----------|-----------|---------|
| **A. Core Use Cases** | 40% | Primary questions the agent was built for |
| **B. Tool Routing Tests** | 25% | Verify correct semantic model selection |
| **C. Edge Cases** | 15% | Boundary conditions, unusual requests |
| **D. Ambiguous Queries** | 10% | Questions requiring interpretation |
| **E. Data Validation** | 10% | Questions requiring quality checks |

### Category Details

**A. Core Use Cases (40%):**
- Basic queries for each tool
- Common aggregations and filters
- Standard time period queries

**B. Tool Routing Tests (25%):**
- **Clear routing:** Questions that clearly map to one tool
  - Example: "How many Streamlit apps were viewed?" → feature_usage tool
- **Ambiguous routing:** Questions where tool choice isn't obvious
  - Test if agent asks for clarification
- **Multi-tool coordination:** Questions requiring multiple tools
  - Example: "Compare Notebooks adoption vs Streamlit adoption"
- **Negative routing:** Questions that might route to wrong tool
  - Example: Ensure "Streamlit Open Source" doesn't use "Streamlit in Snowflake" tool

**C. Edge Cases (15%):** Missing data scenarios, outlier detection, empty result sets

**D. Ambiguous Queries (10%):** Vague time periods ("lately"), implicit comparisons ("better"), undefined metrics ("adoption")

**E. Data Validation (10%):** Incomplete time coverage, double-counting risks, scale reasonableness

### Creating the Evaluation Table

```sql
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.agent_eval (
    question_id INT AUTOINCREMENT,
    question TEXT NOT NULL,
    expected_answer TEXT NOT NULL,
    tool_used TEXT,
    author VARCHAR(100),
    date_added DATE DEFAULT CURRENT_DATE(),
    notes TEXT,
    PRIMARY KEY (question_id)
);

INSERT INTO agent_eval (question, expected_answer, tool_used, author, notes)
VALUES (...);
```

### Iteration with User

- Propose specific questions based on tools and use cases
- Ask user to refine or confirm each question
- For each question, ask: "What should the expected answer be?"
- Help format expected answers with specific, verifiable details

---

## Validation Checklist

Before proceeding to evaluation:
- [ ] Tool coverage: routing questions for X out of Y tools
- [ ] Single-tool questions: each tool has at least 1-2 clear routing questions
- [ ] Multi-tool questions: N questions testing tool coordination
- [ ] Ambiguous scenarios: tests if agent asks for clarification
- [ ] Negative routing: verifies agent doesn't use wrong tools
- [ ] Question diversity: spans different types (aggregation, filtering, etc.)
- [ ] Gaps identified and addressed

### Log to Optimization Log

Update `<WORKSPACE_DIR>/optimization_log.md`:
```
## Evaluation dataset
- Location: DATABASE.SCHEMA.agent_eval
- Coverage: 18 questions, covering core use cases (7), tool routing (5), edge cases (3), ambiguous queries (2), data validation (1)
```
