# [Updated version](https://docs.google.com/document/d/1t4Y81P36nn0OR0m5tBwFKYxlfdHw8RNZGNfBhs0YP_w/edit?tab=t.0)

# Latest and greatest as of Oct 14, 2025

# Cortex Agent Configuration Best Practices

**For Snowflake Intelligence & Cortex Agent API**

This guide provides best practices for configuring Cortex Agents, focusing on writing effective instructions and tool descriptions to create reliable, domain-specific agents.

---

## Table of Contents

1. [Understanding Agent Architecture](#understanding-agent-architecture)  
2. [Scoping and Designing your Agent](#scoping-and-designing-your-agent)  
3. [Crafting Tool Descriptions \- The Most Critical Factor](#crafting-tool-descriptions---the-most-critical-factor)  
4. [Writing Effective Instructions](#writing-effective-instructions)  
5. [Testing and Iteration](#testing-and-iteration)  
6. [Performance and Optimization](#performance-and-optimizations)  
7. [Common Pitfalls to Avoid](#common-pitfalls-to-avoid)  
8. [Additional Resources](#additional-resources)  
9. [Example: Complete Configuration](#example:-complete-configuration)

---

## Understanding Agent Architecture {#understanding-agent-architecture}

### How Cortex Agents Work

Cortex Agents using Anthropic Claude models combine two layers:

1. **Base System Prompt** (provided by Snowflake): Includes core functionality like:  
     
   - General tool usage patterns and workflows  
   - Data analysis best practices and validation frameworks  
   - Chart generation and visualization guidelines  
   - Citation rules for search results  
   - Safety guardrails and content moderation

   

2. **Your Configuration** (what you define): Domain-specific customizations including:  
     
   - Agent role and scope  
   - Tool selection guidance for your use case  
   - Domain-specific logic and constraints  
   - Custom workflows and response patterns

**Key Principle:** Your configuration should focus on domain-specific guidance, not duplicate base functionality. Think of it as specializing a general-purpose agent for your specific needs.

---

## Scoping and Designing your Agent {#scoping-and-designing-your-agent}

Before configuring tools or writing instructions, it's critical to consider the agent's purpose and scope. A common mistake is to build a monolithic agent that tries to answer every possible question (e.g., a “All Snowflake Data” agent vs a “Sales” agent), leading to poor performance and reliability. A more effective approach is to create smaller, specialized agents.

**Best Practices for Scoping:**

* **Start with the "Why":** Partner with your business stakeholders to identify the **top 20 most important business questions** they need answers to. This list will define the initial scope and success criteria for your agent. For example, asking business users questions like: "What questions do you run into as you evaluate existing dashboards or reports you would love an agent to be able to answer?", "What are some of the most common data questions you have on a daily basis?"  
* **Favor Micro-Agents:** Instead of one agent that does everything, build specialized agents focused on specific domains (e.g., a "Sales Pipeline Agent," a "Customer Consumption Agent"). A good rule of thumb is to have **5-10 tools per agent** (there are exceptions to this).  
* **Work Backward to the Tools:** Once you have the key questions, work backward to identify the specific data, semantic models, and tools required to answer them.

---

## Crafting Tool Descriptions \- The Most Critical Factor {#crafting-tool-descriptions---the-most-critical-factor}

### Why Tool Descriptions Matter Most

**Tool descriptions are the single most impactful factor in agent quality.** While instructions set the agent's identity and scope, tool descriptions directly govern:

1. **Tool Selection Accuracy** \- Whether the agent picks the right tool for each question  
2. **Parameter Usage** \- Whether the agent provides correct inputs to tools  
3. **Error Prevention** \- Whether the agent avoids misusing tools or making invalid calls  
4. **Consistency** \- Whether the agent behaves predictably across similar questions

### The Compounding Effect

Poor tool descriptions create cascading failures:

```
❌ Vague Tool Description
  ↓
Agent selects wrong tool
  ↓
Gets irrelevant data
  ↓
Makes incorrect inferences
  ↓
Provides wrong answer (hallucination)
```

versus:

```
✅ Precise Tool Description
  ↓
Agent selects correct tool
  ↓
Provides proper parameters
  ↓
Gets relevant data
  ↓
Delivers accurate answer
```

### Core Principle: Write for Disambiguation

Tool descriptions guide the agent on when and how to use each tool. Think of them as documentation for a junior team member \- someone smart but unfamiliar with your systems.

The agent has multiple tools and must quickly decide which to use. Your description must make the choice obvious.

### 1\. Start with a Clear, Specific Name

Tool names are loaded into the agent's context and influence selection.

```
✅ GOOD: "CustomerConsumptionAnalytics"
❌ BAD: "DataTool" or "Tool1"

✅ GOOD: "SalesforcePipelineQuery" 
❌ BAD: "Query" or "SalesData"

✅ GOOD: "ProductDocumentationSearch"
❌ BAD: "Search" or "Docs"
```

**Naming Principles:**

- Include the data domain ("Customer", "Sales", "Product")  
- Include the function ("Analytics", "Query", "Search")  
- Be specific enough to distinguish from similar tools  
- Avoid generic terms like "Data", "Info", "Helper"

### 2\. Write a Purpose-Driven Description

Follow this template:

**\[What it does\] \+ \[What data it accesses\] \+ \[When to use it\] \+ \[When NOT to use it\]**

```
✅ GOOD EXAMPLE:
Name: CustomerConsumptionAnalytics

Description:
Analyzes Snowflake consumption metrics for customer accounts including credit usage,compute hours, and storage. 

Data Coverage: Daily aggregated consumption data for all commercial customers, 
updated nightly. Includes data from the past 2 years.

When to Use:
- Questions about customer usage patterns, trends, or growth
- Queries about specific customers' consumption (e.g., "How much did Acme use?")
- Comparisons between time periods (e.g., "Compare Q1 vs Q2 usage")

When NOT to Use:
- Do NOT use for real-time/current-hour data (data is daily batch, not real-time)
- Do NOT use for trial or non-commercial accounts (not included in dataset)
- Do NOT use for individual query performance (use QueryHistory tool instead)

Key Parameters:
- customer_name: Exact customer name (case-sensitive). Use CustomerList tool first if unsure of exact spelling.
- date_range: ISO format dates (YYYY-MM-DD). Required. Use specific dates, not 
  relative terms like "last month".
- metric: One of: 'credits', 'compute_hours', 'storage_tb'
```

```
❌ BAD EXAMPLE:
Name: ConsumptionTool

Description: Gets consumption data.
```

**Why the "When NOT to Use" section is critical:**

Without it, agents will try to use tools for everything remotely related. "When NOT to Use" creates clear boundaries and redirects the agent to appropriate alternatives.

### 3\. Be Explicit About Parameters

**This is where most tool descriptions fail.** Ambiguous parameters lead to incorrect tool calls and errors.

For each parameter, specify:

- **Type and format** (with examples)  
- **Required vs. optional** (and default values)  
- **Valid values or constraints** (enums, ranges, formats)  
- **Relationship to other parameters** (dependencies, conflicts)  
- **How to obtain the value** (especially for IDs)

```
✅ GOOD EXAMPLE:
Parameters:
  account_id:
    Type: string
    Required: Yes
    Description: Unique Salesforce account ID (18-character alphanumeric)
    Format: Starts with "001" followed by 15 alphanumeric characters
    Example: "001XX000003DHW3QAO"
    How to obtain: Use AccountLookup tool first if you only have account name
    
  start_date:
    Type: string (ISO 8601 date)
    Required: Yes
    Format: "YYYY-MM-DD"
    Example: "2024-01-01"
    Constraints: Must not be more than 2 years in the past, must be before end_date
    
  end_date:
    Type: string (ISO 8601 date)
    Required: No (defaults to today)
    Format: "YYYY-MM-DD"
    Example: "2024-12-31"
    Constraints: Must be after start_date, cannot be in the future
    
  aggregation_level:
    Type: string (enum)
    Required: No (default: "daily")
    Valid values: "daily", "weekly", "monthly", "quarterly"
    Description: Time granularity for aggregating results
    Recommendation: Use "weekly" or "monthly" for date ranges > 90 days
```

```
❌ BAD EXAMPLE:
Parameters:
  account: string
  date: string
  level: string (optional)
```

**Common Parameter Pitfalls:**

1. **Using generic names:** `user` vs `user_id` vs `username`  
     
   - Be specific: `salesforce_user_id` (18-char ID) vs `user_email` (email string)

   

2. **Not specifying formats:** "date" vs "ISO 8601 date (YYYY-MM-DD)"  
     
   - Agents may pass "last month", "Q3", or other invalid formats

   

3. **Not explaining how to obtain IDs:** "Provide customer\_id"  
     
   - Better: "Customer ID from CustomerLookup tool, or directly from user if known"

   

4. **Unclear optionality:** "region (optional)"  
     
   - Better: "region (optional, defaults to 'ALL', returns data for all regions)"

### 4\. Cortex Analyst & Cortex Search Specific Guidance

**For Cortex Analyst (Text-to-SQL) tools:**

Cortex Analyst tools are unique because they accept natural language queries and convert them to SQL. Your description must guide the agent on how to phrase queries effectively.

**Start with Auto-Generation:** Use the "Generate with Cortex" feature in the Admin UI to automatically generate a tool description based on your semantic model. This provides a solid baseline that already includes key information about your data.

Then, enhance the auto-generated description by following these principles:

```
✅ GOOD EXAMPLE:
Name: SalesOpportunities

Type: Cortex Analyst (Text-to-SQL)

Description:
Queries Salesforce opportunity data to answer questions about sales pipeline, 
deal stages, and revenue forecasts. Powered by a semantic model that understands
sales terminology and automatically handles joins between related tables.

Semantic Model Contents:
- Tables: opportunities, accounts, users, products, opportunity_products
- Key Metrics: ARR (Annual Recurring Revenue), TCV (Total Contract Value), 
  opportunity_count, win_rate, average_deal_size
- Time Dimensions: created_date, close_date, stage_change_date (daily granularity)
- Common Filters: stage, region, account_segment, product_line, opportunity_owner

Natural Language Query Best Practices:
1. Be specific about time ranges: 
   ✅ "in Q4 2024" or "between Oct 1 2024 and Dec 31 2024"
   ❌ "recently" or "this quarter" (ambiguous)

2. Define ambiguous metrics explicitly:
   ✅ "What's the total ARR and win rate by region in Q4?"
   ❌ "What's our performance?" (unclear what to measure)

3. Leverage pre-defined metrics by name:
   ✅ "Show me win_rate by region" (uses semantic model definition)
   ❌ "Calculate won deals divided by total deals" (reinventing existing metric)

4. Be explicit about filters:
   ✅ "open opportunities in Enterprise segment"
   ❌ "good opportunities" (unclear criteria)

5. Specify aggregation level for time series:
   ✅ "monthly ARR trend for 2024"
   ❌ "ARR over time" (unclear granularity)

Example Queries:
"What's the total ARR for open opportunities in the Enterprise segment closing in Q4 2024?"

"Show me win rates by region for opportunities created in the last 6 months, 
grouped by month"

"List all opportunities over $100K in the negotiation stage for the AMER region 
with close dates in the next 30 days"

"Compare average deal size between Q3 and Q4 2024 for the Mid-Market segment"

Common Mistakes to Avoid:
❌ Vague time references: "Show me recent opportunities"
   ✅ Instead: "Show me opportunities created in the last 30 days"

❌ Undefined metrics: "What's our best performing region?"
   ✅ Instead: "What region has the highest total ARR in open opportunities?"

❌ Ambiguous filters: "Show me important deals"
   ✅ Instead: "Show me opportunities over $500K in stages Negotiation or later"
```

**For Cortex Search tools:**

Cortex Search tools retrieve relevant documents/records using semantic search. Guide the agent on search query formulation.

```
✅ GOOD EXAMPLE:
Name: ProductDocumentationSearch

Type: Cortex Search Service

Description:
Searches internal product documentation, feature announcements, technical guides, and release notes to answer "what" and "how" questions about Snowflake products.Uses semantic search to find relevant documents even when exact keywords don't match.

Data Sources: 
- Product documentation (updated weekly)
- Feature release notes (updated with each release)
- Technical architecture guides (updated quarterly)
- Best practice documents (updated monthly)
- Last indexed: Timestamp included in each search result

When to Use:
- Questions about product features, capabilities, or specifications
- "How to" questions and configuration instructions
- Feature availability and compatibility questions
- Troubleshooting guidance and best practices

When NOT to Use:
- Customer-specific data or usage (use CustomerMetrics instead)
- Sales/pipeline information (use SalesforcePipeline instead)
- Real-time system status (use HealthMonitor instead)
- Questions requiring computation or data aggregation (use Cortex Analyst tools)

Search Query Best Practices:
1. Use specific product names:
   ✅ "Snowflake Streams change data capture"
   ❌ "streams" (too generic)

2. Include multiple related keywords:
   ✅ "security authentication SSO SAML configuration"
   ❌ "security" (too broad)

3. Use technical terms when appropriate:
   ✅ "materialized view incremental refresh performance"
   ❌ "fast views" (colloquial)

4. If first search returns low relevance, rephrase:
   Try synonyms, expand acronyms, add context

Example Usage:

Scenario 1 - Feature explanation:
User Question: "How do Snowflake Streams work?"
Search Query: "Snowflake Streams change data capture CDC functionality"
Expected Results: 3-5 relevant docs about Streams

Scenario 2 - Configuration question:
User Question: "How do I configure SSO with Okta?"
Search Query: "SSO single sign-on Okta SAML configuration setup"
Expected Results: Step-by-step guides, configuration docs

Scenario 3 - Low relevance handling:
Initial Query: "table optimization"
Results: Low relevance scores (<0.5)
Action: Rephrase search: "table clustering performance optimization best practices"
Then provide results from improved search

Scenario 4 - No relevant results:
Query: "Snowflake integration with [obscure system]"
Results: No results with relevance >0.3
Response: "I couldn't find documentation about this integration. This feature 
may not be supported or documented yet. Please contact Support for specific 
integration questions."
```

---

## Writing Effective Instructions {#writing-effective-instructions}

Agents have several types of instructions that can be useful. Here are how to think about them, followed by some deeper best practices to follow:

**1\. Planning Instructions (Agent-Level):**

* **Purpose:** High-level business logic, rules, and multi-step workflows. Think of this as instructing the agent on how to approach answering the question.   
* **Example:** "When a user asks for an account summary, first use the `CustomerLookup` tool, then the `Analytics` tool, and finally the `SalesforcePipeline` tool."

**2\. Semantic View (Data-Level):**

* **Purpose:** For data-level context and rules. This is the ideal place for instructions on how to query or interpret the data itself. Think of this as instructing the agent on how to best approach generating a SQL statement from a specific question.  
* **Example:** "Default to showing the last 3 months of data if a time range is not specified by the user."

**3\. Tool Descriptions:**

* **Purpose:** To explain precisely what a tool does, what data it accesses, when to use it, and when *not* to use it. This is the most critical factor for accurate tool selection. Think of this as explaining to the agent what types of things the tool (Semantic View, Search Service, or Custom Tool) can do, so it can infer when best to call it.

**4\. Response Instructions (Presentation-Level):**

* **Purpose:** To control the final output format, tone, and communication style.  
* **Example:** "Be concise and professional \- sales teams are busy”

**Best practices for instructions**

### A. Planning Instructions

**Purpose:** Control HOW the agent thinks, reasons, and selects tools. These guide the agent's decision-making process.

**What belongs in Planning Instructions:**

1. **Agent Identity and Scope**

```
✅ ORCHESTRATION INSTRUCTION:
Your Role: You are "SalesBot", a sales intelligence assistant for the Snowflake sales team.

Your Scope: You answer questions about customer accounts, pipeline opportunities, deal history, and product usage. You help sales professionals prepare for 
customer meetings and track account health.

Your Users: Account Executives (AEs), Solution Engineers (SEs), and Sales Leaders who need quick access to customer data and insights.
```

**Why it matters:** Clear identity prevents scope creep and helps the agent stay focused on its intended purpose.

2. **Domain Context**

```
✅ ORCHESTRATION INSTRUCTION:
Domain Context:
- Snowflake uses a "consumption-based" pricing model where customers pay for 
  compute (measured in credits) and storage separately.
- An "opportunity" represents a potential deal tracked in Salesforce with stages: Prospecting → Qualification → Proof of Value → Negotiation → Closed Won/Lost
- "ARR" (Annual Recurring Revenue) is the key metric for subscription value
- Our fiscal year runs Feb 1 - Jan 31
```

**Why it matters:** Domain context helps the agent interpret questions correctly and use appropriate terminology.

3. **Tool Selection Logic**

```
✅ ORCHESTRATION INSTRUCTION:
Tool Selection Guidelines:
- For questions about CURRENT customer data (accounts, usage, credits): 
  Use the "CustomerData" tool
  Examples: "What's Acme Corp's credit usage?", "Show me active accounts"

- For questions about HISTORICAL trends and analytics:
  Use the "Analytics" tool
  Examples: "How has consumption grown over time?", "Compare Q1 vs Q2"

- For questions about sales pipeline and opportunities:
  Use the "SalesforcePipeline" tool
  Examples: "What deals are closing this quarter?", "Show me open opportunities"
```

**Why it matters:** Explicit tool selection logic prevents the agent from choosing the wrong tool and improves consistency.

4. **Boundaries and Limitations**

```
✅ ORCHESTRATION INSTRUCTION:
Limitations and Boundaries:
- You do NOT have access to customer contracts or legal agreements. If asked, respond: "I don't have access to contract details. Please contact Legal."

- You do NOT have real-time data. Your data is refreshed daily at 2 AM UTC. 
  If asked about "right now", clarify: "My data is current as of this morning's refresh."

- Do NOT calculate financial forecasts or make predictions about future revenue. 
  You can show historical trends but should not extrapolate future values.

- Do NOT provide customer contact information (emails, phone numbers) for 
  privacy reasons.
```

**Why it matters:** Clear boundaries prevent hallucinations and inappropriate responses. Users will inevitably ask questions outside your agent's scope.

5. **Business Rules and Conditional Logic**

```
✅ ORCHESTRATION INSTRUCTION:
Business Rules:
- When a user asks about a customer by name (not ID), ALWAYS use CustomerLookup 
  tool first to get the customer_id before calling other tools
  
- If a query result returns more than 100 rows, ALWAYS aggregate or filter the 
  data before presenting. Do NOT display all rows.
  
- For any consumption questions about dates within the last 7 days, remind users that data has a 24-hour delay and today's data is not yet available
  
- When multiple regions match a query, ALWAYS ask for clarification rather than 
  assuming which region the user meant
  
- If a tool returns an error code "INSUFFICIENT_PERMISSIONS", respond with: 
  "You don't have access to this data. Please contact your Snowflake admin to 
  request access."
```

**Why it matters:** Business rules encode domain-specific logic and ensure consistent handling of common scenarios, edge cases, and error conditions.

6. **Domain-Specific Workflows**

```
✅ ORCHESTRATION INSTRUCTION:
Account Summary Workflow:
When a user asks to "summarize my accounts" or "give me a book of business update":

1. Use CustomerData tool to get the user's assigned accounts list
2. Use Analytics tool to show each account's':
   - Last 90-day consumption and growth rate
   - Total ARR and change from last quarter
3. Use SalesforcePipeline tool to show:
   - Top 5 open opportunities by value
   - Any opportunities closing in next 30 days
4. Use SupportTickets tool to flag any critical severity tickets in last 7 days

Present results in tables with clear sections.
```

**Why it matters:** Workflow automation delivers consistent value and reduces the need for users to ask complex multi-part questions.

---

### B. Response Instructions

**Purpose:** Control HOW the agent formats and presents answers to users. These guide the agent's communication style.

**What belongs in Response Instructions:**

1. **Tone and Communication Style**

```
✅ RESPONSE INSTRUCTION:
Response Style:
- Be concise and professional - sales teams are busy
- Lead with the direct answer, then provide supporting details
- Avoid hedging language like "it seems" or "it appears" - be direct with data
- Use active voice and clear statements
```

2. **Data Presentation Formats**

```
✅ RESPONSE INSTRUCTION:
Data Presentation:
- Use tables for multi-row data (>3 items)
- Use charts for comparisons, trends, and rankings
- For single values, state them directly without tables
- Always include units (credits, dollars, %) with numbers
- Include data freshness timestamp in responses
```

3. **Response Structure Templates**

```
✅ RESPONSE INSTRUCTION:
Response Structure:
For "What is X?" questions:
- Lead with direct answer
- Follow with supporting context if relevant
Example: "Acme Corp used 12,450 credits last month (up 8% from September)."

For "Show me X" questions:
- Brief summary sentence
- Table or chart with data
- Key insights or highlights
Example: "You have $2.4M in open Q4 pipeline across 12 opportunities. [table]"

For "Compare X and Y" questions:
- Summary of comparison result
- Chart showing comparison visually
- Notable differences highlighted
```

4. **Error and Edge Case Messaging**

```
✅ RESPONSE INSTRUCTION:
Error Handling:
- When data is unavailable: "I don't have access to [data type]. You can find 
  this information in [alternative source] or contact [team]."
  
- When query is ambiguous: "To provide accurate data, I need clarification: 
  [specific question]. Did you mean [option A] or [option B]?"
  
- When results are empty: "No results found for [criteria]. This could mean 
  [possible reason]. Would you like to try [alternative approach]?"
```

---

### Orchestration vs Response: Quick Decision Guide

Ask yourself: "Does this instruction affect..."

| If it affects... | Put it in... | Example |
| :---- | :---- | :---- |
| Which tool to select | Orchestration | "Use CustomerData for current metrics" |
| What data to retrieve | Orchestration | "Include last 90 days of usage data" |
| How to interpret user intent | Orchestration | "When user says 'recent', use last 30 days" |
| How to sequence tool calls | Orchestration | "Always call CustomerLookup before CustomerMetrics" |
| Conditional logic and rules | Orchestration | "If result \> 100 rows, aggregate before displaying" |
| What to do in specific scenarios | Orchestration | "When error code X occurs, try alternative tool Y" |
| How to format the answer | Response | "Use tables for multi-row results" |
| What tone to use | Response | "Be concise and professional" |
| How to structure text | Response | "Lead with direct answer, then details" |
| What to say when errors occur | Response | "Explain limitation and suggest alternatives" |

---

## Testing and Iteration {#testing-and-iteration}

### Build a Test Question Set

Create a comprehensive test set covering:

1. **In-scope questions** (agent should answer correctly)  
2. **Out-of-scope questions** (agent should gracefully decline)  
3. **Edge cases** (ambiguous, missing data, error conditions)  
4. **Variations** (different phrasings of same question)  
5. **Tool selection challenges** (questions that could match multiple tools)

**Example Test Structure:**

| User Persona | Question | Should Answer? | Expected Tool | Expected Behavior |
| :---- | :---- | :---- | :---- | :---- |
| Sales AE | "What's my Q4 pipeline?" | Yes | SalesforcePipeline | Show opportunities closing in Q4 with table |
| Sales AE | "What's Acme Corp's contract value?" | No | None | Decline \- no contract data access |
| Sales Leader | "Summarize my team's performance" | Yes | Multiple | Aggregate metrics across team members |
| Sales AE | "What's happening with my accounts?" | Yes | Multiple (workflow) | Trigger account summary workflow |
| External user | "Show me all customer data" | No | None | Decline \- security violation |
| Sales AE | "Compare Acme vs Beta consumption" | Yes | CustomerMetrics | Call tool twice, compare results |

**Target 50-100 test questions** to establish a baseline. Track:

- **Accuracy** (correct answer)  
- **Tool selection accuracy** (chose right tool)  
- **Stability** (consistent behavior across runs)  
- **Error rate** (failed tool calls, exceptions)  
- **Response quality** (clear, well-formatted)

### Iterative Improvement Process

1. **Test** → Run question set, identify failure patterns  
2. **Diagnose** → Is it instructions, tool descriptions, or data quality?  
3. **Refine** → Make targeted improvements (focus on tool descriptions first)  
4. **Re-test** → Measure impact on accuracy and stability  
5. **Repeat** → Continue until quality targets are met

**Failure Pattern Analysis:**

| Pattern | Likely Cause | Fix |
| :---- | :---- | :---- |
| Wrong tool selected | Vague "When to Use" | Add specific examples and "When NOT to Use" |
| Parameter errors | Ambiguous parameter specs | Add format, examples, constraints |
| Hallucinations | Agent using wrong tool | Strengthen tool boundaries, add negative examples |
| Inconsistent answers | Multiple tools overlap | Clarify tool selection criteria, add disambiguation |
| Empty results | Agent using correct tool incorrectly | Add example queries, clarify parameter relationships |

---

## Performance and Optimizations {#performance-and-optimizations}

Agent performance is not just about the quality of the instructions; it's also heavily dependent on the underlying data engineering. Slow or inconsistent agents are often a symptom of inefficient data models or overly complex queries.

**Key Principle: Data Engineering \> Prompt Engineering**

An ounce of data engineering is worth a pound of prompt engineering. Optimizing your underlying data models, pre-aggregating common metrics, and using clear, consistent column names will have a greater impact on performance than tweaking instructions.

**Troubleshooting Slowness:**

* **Use Agent Traces:** To diagnose a slow agent, use the **agent traces in the monitoring tab**. These traces show the logical path the agent took and how long each step lasted, allowing you to pinpoint the exact bottleneck.  
* **Pre-define Verified Queries:** For common or complex analytics, you can pre-define and verify the queries directly in your Semantic Views. This ensures the agent uses an optimized, predictable query path for those questions.  
* **Focus Your Agents:** Smaller, specialized agents with fewer tools (5-10) will generally perform faster and more reliably than large, monolithic agents.

---

## Common Pitfalls to Avoid {#common-pitfalls-to-avoid}

### 1\. ❌ Over-Specifying Base Functionality

```
❌ DON'T:
"When you receive a question, first analyze it carefully, then select appropriate tools, call them in sequence, and format results properly..."
```

**Why:** The base system prompt already handles general workflow. Focus on domain-specific logic.

### 2\. ❌ Vague Tool Descriptions (THE MOST COMMON MISTAKE)

```
❌ DON'T:
"CustomerTool: Gets customer data"

✅ DO:
"CustomerAccountMetrics: Retrieves account-level consumption, billing, and 
contract data for commercial customers from the enterprise data warehouse. 
Updated nightly at 2 AM UTC. Use for questions about specific customer usage 
patterns, growth rates, and spend trends over time. Do NOT use for real-time 
data, trial accounts, or individual user-level information."
```

**Impact:** This single improvement can increase tool selection accuracy by 30-40%.

### 3\. ❌ Ambiguous Parameters

```
❌ DON'T:
Parameter: "date" (string)

✅ DO:
Parameter: "start_date"
  Type: string (ISO 8601 date format)
  Required: Yes
  Format: "YYYY-MM-DD"
  Example: "2024-01-15"
  Constraints: Must be within last 2 years, must be before end_date
  How to obtain: Parse from user's natural language date reference
```

### 4\. ❌ Inconsistent Terminology

```
❌ DON'T:
Instructions say "customers" but tool descriptions say "accounts"

✅ DO:
Pick one term and use it consistently everywhere. If your domain has multiple 
terms for the same concept, define them explicitly:
"Account (also called 'customer' in billing context): A business entity that..."
```

### 5\. ❌ Mixing Orchestration and Response Instructions

```
❌ DON'T:
Combine tool selection logic with response formatting in one section

✅ DO:
Separate orchestration (what to do, which tools) from response (how to format, 
what tone) into distinct instruction sections
```

---

## Additional Resources {#additional-resources}

- **Snowflake Cortex Analyst Documentation:** [https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)  
- **Snowflake Cortex Search Documentation:** [https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search)

---

## Example: Complete Configuration {#example:-complete-configuration}

Here's a comprehensive example bringing it all together using "CarAnalytics Pro", an automotive marketplace analytics agent:

### Orchestration Instructions

```
**Role:**

You are "CarAnalytics Pro", an automotive data analytics assistant for AutoMarket, 
an online car marketplace. You help data scientists, analysts, product managers, 
and pricing strategists gain insights from vehicle listings, customer behavior, 
market trends, and platform performance data.

**Users:**

Your primary users are:
- Data scientists building predictive models and statistical analyses
- Business analysts tracking KPIs and generating reports
- Product managers optimizing platform features and user experience
- Pricing strategists developing competitive pricing recommendations

They typically need to analyze large datasets, understand market dynamics, 
and create data-driven recommendations for business strategy.

**Context:**

Business Context:
- AutoMarket is a leading online car marketplace in North America
- We facilitate both B2C (dealer) and C2C (private party) transactions
- Platform handles 50,000+ active vehicle listings
- Revenue from listing fees, transaction commissions, and premium dealer services
- Data refreshes: Daily at 2 AM PST

Key Business Terms:
- Listing Velocity: Days from listing creation to sale (target: <30 days)
- Price-to-Market Ratio (PMR): Listing price ÷ market value (1.0 = fair price)
- Days to Sale (DTS): Time from listing to completed transaction
- Take Rate: Platform commission as % of transaction value (avg 3-5%)
- GMV: Gross Merchandise Value (total $ of all transactions)

Market Segments:
- Luxury: Vehicles >$50K (BMW, Mercedes, Audi, Lexus)
- Mid-Market: $15K-$50K (Honda, Toyota, Ford, Chevy)
- Budget: <$15K (older vehicles, high mileage)
- Electric/Hybrid: Alternative fuel vehicles (25% YoY growth)
- Trucks & SUVs: 40% of our GMV

**Tool Selection:**

- Use "VehicleAnalytics" for vehicle inventory, pricing, and listing performance
  Examples: "What's the average Days to Sale for 2020 Honda Accords?", 
  "Show listing velocity by segment", "Which vehicles are overpriced vs market?"

- Use "CustomerBehavior" for buyer/seller behavior, conversion, and segmentation
  Examples: "What's the customer journey from search to purchase?", 
  "Show conversion rates by demographics", "Which segments have highest LTV?"

- Use "MarketIntelligence" for competitive analysis and market research
  Examples: "How do our prices compare to Carvana?", "What's our market share 
  by region?", "Which markets have highest growth potential?"

- Use "RevenueAnalytics" for financial metrics, GMV, take rate, and commissions
  Examples: "What's our take rate by transaction type?", "Show GMV trends and 
  seasonality", "Calculate CAC by acquisition channel"

**Boundaries:**

- You do NOT have access to individual customer PII (names, emails, addresses, 
  phone numbers). Only use aggregated/anonymized data per GDPR/CCPA compliance.

- You do NOT have real-time competitor pricing beyond daily intelligence feeds. 
  For live competitive data, direct users to external market research tools.

- You CANNOT execute pricing changes, adjust live listings, or make binding 
  business commitments. All recommendations are analytical only.

- You do NOT have access to internal HR data, employee performance, or 
  confidential strategic plans outside data analytics scope.

- For questions about legal compliance, contracts, or regulations, respond: 
  "I can provide data analysis but not legal advice. Please consult Legal for 
  compliance questions."

**Business Rules:**

- When analyzing seasonal trends, ALWAYS apply Seasonal Adjustment Factor for 
  vehicle types with known seasonality (convertibles, 4WD trucks, etc.)

- If query returns >500 listings, aggregate by make/model/segment rather than 
  showing individual listings

- For price recommendations, ALWAYS include confidence intervals and sample 
  size. Do not recommend pricing without statistical validation.

- When comparing time periods, check for sufficient sample size (minimum 30 
  transactions per period). Flag low-sample warnings.

- If VehicleAnalytics returns PMR outliers (>1.5 or <0.5), flag as potential 
  data quality issues and recommend manual review.

**Workflows:**

Pricing Strategy Analysis:
When user asks "Analyze pricing for [segment/make/model]" or "Should we adjust 
pricing for [category]":

1. Use VehicleAnalytics to get current listing data:
   - Average prices, Days to Sale, Price-to-Market Ratios
   - Compare vs 3-month and 12-month historical trends
   - Segment by condition, mileage, regional variations

2. Use MarketIntelligence for competitive context:
   - Compare our prices vs competitors (Carvana, CarMax, dealers)
   - Identify price gaps and positioning opportunities
   - Analyze competitor inventory levels and velocity

3. Use CustomerBehavior for demand signals:
   - View-to-inquiry and inquiry-to-offer conversion rates
   - Price sensitivity analysis by segment
   - Historical elasticity data

4. Present findings:
   - Executive summary with specific pricing recommendation
   - Expected impact on DTS and conversion with confidence intervals
   - A/B testing plan and monitoring KPIs


```

### Response Instructions

```
**Style:**

- Be direct and data-driven - analysts value precision over politeness
- Lead with the answer, then provide supporting analysis
- Use statistical terminology appropriately (p-values, confidence intervals, 
  correlation vs causation)
- Flag data limitations, sample size constraints, and seasonality effects
- Avoid hedging with business metrics - state numbers clearly

**Presentation:**

- Use tables for comparisons across multiple vehicles/segments (>4 rows)
- Use line charts for time-series trends and seasonality
- Use bar charts for rankings and segment comparisons
- For single metrics, state directly: "Average DTS is 23 days (±3 days, 95% CI)"
- Always include data freshness, sample size, and time period in responses

**Response Structure:**

For trend analysis questions:
"[Summary of trend direction] + [chart] + [statistical significance] + [context]"
Example: "Luxury segment DTS decreased 15% QoQ (p<0.01). [chart showing 
monthly trend]. This decline is statistically significant and driven primarily 
by 20% increase in Electric/Hybrid luxury inventory."

For pricing questions:
"[Direct recommendation] + [supporting data] + [expected impact] + [caveats]"
Example: "Recommend 5-8% price reduction for 2019-2020 Honda Accord listings. 
Current PMR is 1.12 vs market (overpriced). Expected to reduce DTS from 35 
to 25 days based on historical elasticity. Caveat: Limited to 45 listings, 
monitor first 2 weeks before broader rollout."
```

### Tool: VehicleAnalytics

```
**Name:** VehicleAnalytics

**Type:** cortex_analyst

**Description:**

Analyzes vehicle inventory, pricing trends, listing performance, and market 
positioning metrics. Covers all active and sold listings on AutoMarket platform.

Data Coverage:
- Historical: Past 3 years of listing and transaction data
- Active listings: All current platform inventory (~50K listings)
- Sold listings: Completed transactions with final sale price
- Removed listings: Listings removed without sale (expired, withdrawn)
- Refresh: Daily at 2 AM PST (21-hour lag from current time)

Data Sources: listings table, transactions table, vehicle_valuations table

**When to Use:**

- Questions about vehicle pricing, inventory levels, or listing counts
- Listing performance metrics (Days to Sale, listing velocity, PMR)
- Historical price trends and seasonality analysis
- Vehicle-level or segment-level aggregations
- "Which vehicles/segments" queries (rankings, comparisons, distributions)

**When NOT to Use:**

- Do NOT use for buyer/seller behavior or conversion funnels (use CustomerBehavior)
- Do NOT use for competitive pricing outside AutoMarket (use MarketIntelligence)
- Do NOT use for financial metrics like GMV, commissions, revenue (use RevenueAnalytics)
- Do NOT use for real-time data (21-hour lag, updated daily only)
- Do NOT use for individual customer purchase history (PII restricted)

<Auto-generated descriptions by Cortex>
```

