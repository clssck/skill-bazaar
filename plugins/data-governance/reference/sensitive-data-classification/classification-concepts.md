# Classification Concepts

## Overview

Snowflake provides built-in data classification capabilities to automatically discover and tag sensitive data. Understanding these concepts is essential before working with classification workflows.

## Key Concepts

### 1. Data Classification

Data classification is the process of analyzing column data to identify sensitive information like PII (Personally Identifiable Information), PCI (Payment Card Industry) data, and other sensitive categories.

**Two approaches:**

| Approach | Description | Use Case |
|----------|-------------|----------|
| **Manual Classification** | Run `SYSTEM$CLASSIFY` on specific tables | One-time analysis, testing |
| **Automatic Classification** | Classification profiles monitor databases continuously | Production, ongoing governance |

### 2. Classification Profiles

A **Classification Profile** defines how automatic classification works:

```sql
CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE <profile_name>(
  'minimum_object_age_for_classification_days': 1,
  'maximum_classification_validity_days': 90,
  'auto_tag': FALSE
);
```

**Key Attributes:**

| Attribute | Default | Description |
|-----------|---------|-------------|
| `minimum_object_age_for_classification_days` | 1 | Days before classification |
| `maximum_classification_validity_days` | 90 | Days before re-classification |
| `auto_tag` | FALSE | Automatically apply tags to classified columns |

### 3. Semantic Categories

Snowflake recognizes these built-in semantic categories:

**Privacy Categories:**

| Category | Tag | Examples |
|----------|-----|----------|
| Name | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:NAME` | First name, last name, full name |
| Email | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:EMAIL` | Email addresses |
| Phone | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:PHONE_NUMBER` | Phone numbers |
| Address | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:ADDRESS` | Street addresses |
| SSN | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:US_SSN` | US Social Security Numbers |
| Date of Birth | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:DATE_OF_BIRTH` | Birth dates |
| Gender | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:GENDER` | Gender identifiers |
| Age | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:AGE` | Age values |

**Financial Categories:**

| Category | Tag | Examples |
|----------|-----|----------|
| Credit Card | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:PAYMENT_CARD` | Credit/debit card numbers |
| Bank Account | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:BANK_ACCOUNT` | Bank account numbers |
| IBAN | `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:IBAN` | International Bank Account Numbers |

**⚠️ NOT Built-in (Require Custom Classifiers):**

The following data types are NOT in Snowflake's built-in semantic categories and require custom classifiers:

| Category | Examples | Why Not Built-in |
|----------|----------|------------------|
| Country-specific IDs | Chinese passport, UK NINO, Indian Aadhaar | Regional formats vary |
| Employee IDs | EMP-12345, STAFF_001 | Company-specific formats |
| Internal codes | Project codes, account numbers | Organization-specific |
| Industry IDs | Medical record numbers, VINs | Industry-specific formats |
| Custom business data | Customer refs, order IDs | Unique to each business |

**When a data type is NOT built-in:**
1. Auto-classification and manual classification (SYSTEM$CLASSIFY) will NOT detect it
2. You'll need to create a custom classifier first
3. Then you can add the custom classifier to a classification profile
4. Only then will auto-classification detect your custom data type

### 4. Auto-Tagging

When `auto_tag` is enabled on a classification profile:

1. Classification runs automatically on new/modified tables
2. Discovered sensitive columns are tagged with semantic category tags
3. Tags can drive masking policies and access controls

**⚠️ Important Considerations:**

- Auto-tagging modifies your schema metadata
- Tags are visible in `INFORMATION_SCHEMA` and `ACCOUNT_USAGE`
- Consider governance implications before enabling

### 5. Custom Classifiers

For data types Snowflake doesn't recognize, create **Custom Classifiers** (two-step process):

```sql
-- Step 1: Create the classifier instance
CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER <classifier_name>();

-- Step 2: Add regex pattern(s) to the classifier
CALL <classifier_name>!ADD_REGEX(
  '<semantic_category>',    -- e.g., 'EMPLOYEE_ID'
  '<privacy_category>',     -- 'IDENTIFIER', 'QUASI_IDENTIFIER', or 'SENSITIVE'
  '<regex_pattern>',        -- e.g., '^EMP-[0-9]{5}$'
  '<description>'           -- e.g., 'Detects employee IDs in format EMP-XXXXX'
);
```

**Privacy Categories:**
- `IDENTIFIER` - Uniquely identifies an individual
- `QUASI_IDENTIFIER` - Can identify when combined with other data
- `SENSITIVE` - Sensitive but not directly identifying

**Use cases:**

- Employee IDs with company-specific formats
- Internal account numbers
- Custom identifiers
- Industry-specific codes
- Country-specific document numbers (passports, IDs)

### 6. SYSTEM$CLASSIFY Function

Manual classification using the built-in function:

```sql
-- IMPORTANT: Use CALL, not SELECT
-- Classify a single table
CALL SYSTEM$CLASSIFY('database.schema.table');

-- Classify with options
CALL SYSTEM$CLASSIFY('database.schema.table', 
  {'auto_tag': true, 'sample_count': 10000});
```

**Returns:** JSON with classification results including:
- Column name
- Detected category
- Confidence score
- Sample matches

**⚠️ Note:** If you get "Unknown function SYSTEM$CLASSIFY", this is a **syntax error** - use `CALL` not `SELECT`. If you get "Insufficient privileges", check the **Privilege Requirements** section below.

### 7. Viewing Classification Results

**For manual classification:**

```sql
-- Results returned directly from SYSTEM$CLASSIFY
CALL SYSTEM$CLASSIFY('my_db.my_schema.customers');
```

**For automatic classification:**

```sql
-- Query account usage for classification results
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
WHERE DATABASE_NAME = 'MY_DATABASE'
ORDER BY LAST_CLASSIFIED_ON DESC;
```

## Privilege Requirements

| Operation | Required Privilege | Object Level | Check Query |
|-----------|-------------------|--------------|-------------|
| SYSTEM$CLASSIFY (manual) | SELECT on table/view | Table/View | `SHOW GRANTS ON TABLE <table>` |
| SYSTEM$CLASSIFY with `auto_tag: true` | OWNERSHIP on schema | Schema | `SHOW GRANTS ON SCHEMA <schema>` |
| SYSTEM$CLASSIFY | SNOWFLAKE.CORE_VIEWER database role | SNOWFLAKE DB | `SHOW GRANTS TO ROLE <role>` |
| Create Classification Profile | CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE | Schema | `SHOW GRANTS ON SCHEMA <schema>` |
| Create Classification Profile | SNOWFLAKE.CLASSIFICATION_ADMIN database role | SNOWFLAKE DB | `SHOW GRANTS TO ROLE <role>` |
| Set Profile on DB/Schema | EXECUTE AUTO CLASSIFICATION | Account/Database/Schema | `SHOW GRANTS ON ACCOUNT` or `SHOW GRANTS ON DATABASE <db>` |
| Set Profile on DB/Schema | APPLY TAG | Account | `SHOW GRANTS ON ACCOUNT` |
| Alter Database settings | MODIFY | Database | `SHOW GRANTS ON DATABASE <db>` |

**⚠️ Pre-check privileges before attempting operations.** If you get "Insufficient privileges" errors, verify the current role has the required grants.

## Troubleshooting SYSTEM$CLASSIFY Errors

If `SYSTEM$CLASSIFY` returns an error, it's either a **syntax error** or **missing privilege**:

### Error: "Unknown function SYSTEM$CLASSIFY"

This is a **syntax error**. Common causes:

1. **Wrong syntax**: Using `SELECT` instead of `CALL`
   ```sql
   -- WRONG:
   SELECT SYSTEM$CLASSIFY('db.schema.table');
   
   -- CORRECT:
   CALL SYSTEM$CLASSIFY('db.schema.table');
   ```

2. **Load the template**: Always load `templates/manual-classify.sql` and follow the exact syntax.

### Error: "Insufficient privileges"

This is a **privilege issue**. Check:

1. **Verify role grants**:
   ```sql
   SHOW GRANTS TO ROLE <current_role>;
   ```

2. **Check table access**:
   ```sql
   SHOW GRANTS ON TABLE <database>.<schema>.<table>;
   ```

3. **Check account-level privileges** (for EXECUTE DATA METRIC FUNCTION):
   ```sql
   SHOW GRANTS ON ACCOUNT;
   ```

**Resolution**: Inform the user they need the required privilege (see table above) and suggest they contact their Snowflake administrator.

## Best Practices

1. **Start with manual classification** to understand what's in your data
2. **Test auto-tag=false first** before enabling automatic tagging
3. **Use classification profiles** for ongoing governance, not one-time scans
4. **Create custom classifiers** for domain-specific sensitive data
5. **Review results regularly** using ACCOUNT_USAGE views
6. **Combine with masking policies** for complete data protection

## 🚨 SQL Verification (CRITICAL)

**Always verify SQL execution results before claiming success.**

### Verification Commands

After creating objects, verify they exist:

```sql
-- Verify custom classifier was created
SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER LIKE '<classifier_name>';

-- Verify classification profile was created
SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE LIKE '<profile_name>';

-- Verify database has classification enabled
SHOW PARAMETERS LIKE 'CLASSIFICATION_PROFILE' IN DATABASE <database>;
```

### Error Indicators

If SQL execution response contains any of these, the step FAILED:
- `Statement X failed`
- `SQL compilation error`
- `error`
- `Unknown user-defined function`
- `Object does not exist`
- `Insufficient privileges`

**Never mark a step successful if any error indicator is present.**

## Workflow Integration

```
                    ┌─────────────────────┐
                    │   Classification    │
                    │      Profile        │
                    └──────────┬──────────┘
                               │
                               ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│    Database     │──▶│  Auto-Classify  │──▶│   Apply Tags    │
│   (monitored)   │   │   (scheduled)   │   │  (if auto_tag)  │
└─────────────────┘   └─────────────────┘   └────────┬────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │ Masking Policies│
                                            │  (tag-based)    │
                                            └─────────────────┘
```

## Snowflake Storage Convention

This skill uses Snowflake as the system of record for all governance data:

### DG_TEMP_DB - Testing & Validation

```sql
-- Dedicated database for testing
CREATE DATABASE IF NOT EXISTS DG_TEMP_DB
  COMMENT = 'Temporary database for data governance testing';

-- Case-specific test schemas
CREATE SCHEMA IF NOT EXISTS DG_TEMP_DB.<classifier_name>_test;
```

**Contents:**
- Test data tables for classifier validation
- Temporary scripts and results
- Can be cleaned up after successful testing

### DG_KNOWLEDGE - Customer Terminology (Optional)

```sql
-- Store customer-specific knowledge in Snowflake
CREATE DATABASE IF NOT EXISTS DG_KNOWLEDGE
  COMMENT = 'Customer-specific data governance knowledge';

CREATE SCHEMA IF NOT EXISTS DG_KNOWLEDGE.TERMS;

-- Semantic view for customer terminology
CREATE OR REPLACE VIEW DG_KNOWLEDGE.TERMS.CUSTOM_DEFINITIONS AS
SELECT 
    term_name,
    description,
    regex_pattern,
    example_column,
    created_at
FROM DG_KNOWLEDGE.TERMS.DEFINITIONS_TABLE;
```

**Why store knowledge in Snowflake:**
- Persistent across sessions (not lost when conversation ends)
- Shareable with team members
- Can be referenced by classification profiles
- Auditable and governed

### Storage Summary

| Purpose | Location | Persistence |
|---------|----------|-------------|
| Testing classifiers | `DG_TEMP_DB.<case>_test` | Temporary |
| Customer terminology | `DG_KNOWLEDGE.TERMS` | Permanent |
| Classification profiles | User-specified schema | Permanent |
| Custom classifiers | User-specified schema | Permanent |
| Results | `ACCOUNT_USAGE` views | Automatic |

## Next Steps

After understanding these concepts, return to the main SKILL.md workflow to:

1. **For automatic detection**: Create a classification profile (Step 1) and associate with databases (Step 5)
2. **For custom data types**: Create custom classifiers (Step 3)
