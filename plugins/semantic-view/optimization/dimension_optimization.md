---
name: Dimension and Fact Enhancement
description: Improve existing dimension/fact metadata (cannot add new ones)
parent_skill: semantic-view-patterns
priority: 1
---

# Dimension and Fact Enhancement

## When to Load

- LLM doesn't understand when to use existing columns
- Synonym mismatches
- Need better column descriptions

## Core Principle

**Dimensions and facts are physical database columns** - you CANNOT add new ones.

You CAN enhance with: descriptions, synonyms, sample_values, unique flag.

## Enhancement Strategies

### 1. Rich Descriptions

Transform "Account ID" into contextual explanation:

- What the column represents
- How it's commonly used
- Relationships to other data
- Business context

Example: "Unique identifier for Snowflake accounts. Used to track usage and link with customer information."

### 2. Synonyms for Matching

Add alternative terms users might use:

- Business terminology variants
- Abbreviations
- Domain-specific names
- Common misspellings or alternate phrasings

### 3. Sample Values for Context

For categorical dimensions, provide representative values:

- Helps LLM understand data distribution
- Enables better filter generation
- Shows valid value patterns

### 4. Unique Flag

Mark columns with unique values to prevent unnecessary DISTINCT operations.

## Proto Fields

**Dimension** (proto lines 105-134):

- name, synonyms, description, expr, data_type, unique, sample_values

**Fact** (proto lines 174-199):

- name, synonyms, description, expr, data_type, access_modifier, sample_values

## Example Enhancement

**Before**: Minimal metadata

```yaml
- name: ACCOUNT_ID
  description: Account ID
  expr: account_id
  data_type: NUMBER(38,0)
```

**After**: Rich metadata

```yaml
- name: ACCOUNT_ID
  description: "Unique identifier for Snowflake accounts. Used to track usage and link with customer information. Commonly used for account-level analysis."
  expr: account_id
  data_type: NUMBER(38,0)
  unique: true
```

## Common Mistakes

❌ `default_aggregation` (deprecated)
❌ Empty/repetitive descriptions
❌ Missing synonyms for common terms
❌ Wrong data types

## Validation

Test that enhancements improve SQL generation without breaking existing queries.

## Applying This Optimization

Use `semantic_view_set.py` to apply. See [semantic_view_set.md](../reference/semantic_view_set.md) for complete JSON syntax.

**Example operation for updating dimension description**:

```json
{
  "operation": "update",
  "component": "column",
  "table_name": "ORDERS",
  "column_name": "ACCOUNT_ID",
  "property": "description",
  "value": "Unique identifier for Snowflake accounts. Used to track usage and link with customer information."
}
```

**Example operation for adding synonyms**:

```json
{
  "operation": "update",
  "component": "column",
  "table_name": "ACCOUNTS",
  "column_name": "SALESFORCE_ACCOUNT_NAME",
  "property": "synonyms",
  "value": ["company name", "customer name", "account name"],
  "mode": "append"
}
```
