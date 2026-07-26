# Sensitive Data Governance - Examples

## Overview

This document provides example queries and interactions for the Sensitive Data Governance skill. Use these examples to understand how to invoke different workflows.

## Auto-Classification Examples

### Example 1: Initial Setup

**User Query:**
```
Help me detect PII in my customer database
```

**Expected Workflow:** Auto-Classification → Phase 1-4

**What Happens:**
1. Agent checks for existing classification profiles
2. Explains auto-classification benefits
3. Guides through profile creation
4. Sets up monitoring on customer database

---

### Example 2: Quick Scan

**User Query:**
```
Can you scan the CUSTOMERS table for sensitive data?
```

**Expected Workflow:** Auto-Classification → Manual Classification Path

**What Happens:**
1. Agent offers manual classification option
2. Runs `SYSTEM$CLASSIFY('db.schema.CUSTOMERS')`
3. Presents results in readable format
4. Suggests setting up auto-classification

---

### Example 3: Existing Governance

**User Query:**
```
I already have a script that detects PII, but I want to explore Snowflake's options
```

**Expected Workflow:** Auto-Classification → Honor User Preferences

**What Happens:**
1. Agent acknowledges existing solution
2. Presents comparison of approaches
3. Offers Semantic Views as integration point
4. Provides clean exit option

---

## Custom Classifier Examples

### Example 4: Employee ID Classifier

**User Query:**
```
I need to detect employee IDs in my data - they look like EMP-12345
```

**Expected Workflow:** Custom Classifier → Full workflow

**What Happens:**
1. Agent asks for more sample values
2. Suggests regex pattern: `^EMP-[0-9]{5}$`
3. Creates custom classifier
4. Offers to add to classification profile

---

### Example 5: From Table Reference

**User Query:**
```
Create a classifier for the data in HR_DB.EMPLOYEES.INTERNAL_CODE column
```

**Expected Workflow:** Custom Classifier → Sample from table

**What Happens:**
1. Agent queries sample data from the column
2. Analyzes patterns in the data
3. Suggests appropriate regex
4. Creates classifier after confirmation

---

### Example 6: Multiple Patterns

**User Query:**
```
We have account numbers that can be ACC-123456 or ACCT-123456
```

**Expected Workflow:** Custom Classifier → Complex regex

**What Happens:**
1. Agent analyzes both patterns
2. Suggests combined regex: `^ACC(T)?-[0-9]{6}$`
3. Tests against both example formats
4. Creates classifier with flexible pattern

---

## Conversation Examples

### Example 7: Full Auto-Classification Dialog

```
User: I want to set up automatic PII detection on my analytics database

Agent: I'll help you set up automatic PII detection. Let me first check your 
current context and any existing classification profiles.

[Runs context query]

Current Context:
| Field     | Value         |
|-----------|---------------|
| User      | JOHN_DOE      |
| Role      | DATA_ENGINEER |
| Database  | ANALYTICS_DB  |
| Warehouse | COMPUTE_WH    |

[Checks for existing profiles]

No classification profiles found in your account.

Snowflake Auto-Classification can automatically detect sensitive data like:
- PII (names, emails, phone numbers, SSN)
- Financial data (credit cards, bank accounts)
- Health information

Would you like to:
  a) Set up a new classification profile (recommended for ongoing monitoring)
  b) Run manual classification on specific tables first (one-time scan)
  c) Exit - I already have a data governance approach

Please select (a/b/c):

User: a

Agent: Let's set up your classification profile.

Where would you like to store the profile?
- Database: [e.g., GOVERNANCE_DB]
- Schema: [e.g., CLASSIFIERS]

User: Use ANALYTICS_DB.GOVERNANCE

Agent: I'll use these recommended defaults:
- Min Object Age: 1 day
- Max Classification Validity: 90 days

Would you like to enable auto-tagging?
  a) Yes - automatically tag sensitive columns (recommended)
  b) No - detect only, I'll apply tags manually

User: a

Agent: Please confirm the classification profile settings:

| Setting                     | Value                   |
|-----------------------------|-------------------------|
| Profile Name                | pii_classifier          |
| Location                    | ANALYTICS_DB.GOVERNANCE |
| Min Object Age              | 1 day                   |
| Max Classification Validity | 90 days                 |
| Auto-Tag Columns            | Yes                     |

Ready to create this profile? (yes / no / edit)

User: yes

Agent: ✅ Classification profile created successfully!

Which database would you like to monitor for sensitive data?

User: ANALYTICS_DB

Agent: ✅ Auto-classification is now active on ANALYTICS_DB!

📊 Viewing Results:
[Provides query for viewing results]

📝 Session Summary:
| Item               | Value                  |
|--------------------|------------------------|
| Outcome            | ✅ Auto-classification |
| Profile Created    | pii_classifier         |
| Database Monitored | ANALYTICS_DB           |
| Auto-Tag Enabled   | Yes                    |
```

---

### Example 8: Non-Built-in Category (Custom Classifier Required)

**Demonstrates: When data type is not in Snowflake's built-in categories, only custom classifier is offered**

```
User: I need to detect Chinese passport numbers in my database

Agent: I can see that Snowflake doesn't have a built-in semantic category for 
Chinese passport numbers.

To detect this data, we'll need to create a custom classifier:

  1. Create a custom classifier with a regex pattern
  2. Test it against your data  
  3. Then add it to a classification profile for automatic detection

Would you like to proceed? (yes / no)

If yes, please provide:
  - Sample data or a table.column I can analyze (recommended), OR
  - Confirm you want to use the standard Chinese passport format

User: yes, use the standard format

Agent: I'll use the standard Chinese passport format. Please confirm this matches your data:

Chinese passport numbers follow this pattern:
- Format: 1 letter + 8 digits (e.g., G12345678, E12345678)
- Rules:
  - First letter is typically G (regular) or E (electronic)
  - Followed by exactly 8 digits

Does your data follow this standard format? (yes / no / show me samples first)

User: yes

Agent: Creating custom classifier for Chinese passport numbers...

[Creates classifier, then runs test & validation]

✅ Custom classifier created and validated!

📊 Test Results: 5/5 passed

Now, would you like to add this classifier to a Classification Profile?
This will enable automatic detection when auto-classification runs.

  a) Yes, add to an existing profile
  b) Yes, create a new profile with this classifier
  c) No, I'll use it manually with SYSTEM$CLASSIFY for now

Please select (a/b/c):

User: a

Agent: [Shows existing profiles, user selects one, classifier is added to profile]

✅ Classifier added to profile. Auto-classification will now detect 
Chinese passport numbers in monitored databases.
```

**Key Point**: Notice that manual classification (SYSTEM$CLASSIFY) and auto-classification 
were NOT offered as initial options because Chinese passport is not a built-in category. 
The only path is: Create custom classifier → Test → Then optionally add to profile.

---

### Example 9: Custom Classifier - User Sample Data

```
User: I need to detect our internal project codes - they look like PRJ-ABC-001

Agent: I'll help you create a custom classifier for project codes.

Do you have:

  a) Sample data or a table.column I can analyze (recommended)
  b) Use a standard format (if applicable)

Please select (a/b):

User: a

Agent: Please provide at least 3 sample values:

User: PRJ-ABC-001, PRJ-XYZ-123, PRJ-DEV-999

Agent: Based on your examples, I suggest this regex pattern:
  ^PRJ-[A-Z]{3}-[0-9]{3}$

This will match:
  ✅ PRJ-ABC-001
  ✅ PRJ-XYZ-123
  ✅ PRJ-DEV-999

This will NOT match:
  ❌ PRJ-AB-001 (only 2 letters)
  ❌ prj-ABC-001 (lowercase)
  ❌ PROJECT-ABC-001 (different prefix)

Does this pattern look correct? (yes / no / modify)

User: yes

Agent: Let's finalize the classifier details:

Classifier Name: [e.g., project_code_classifier]
Where to create it:
- Database: [e.g., GOVERNANCE_DB]
- Schema: [e.g., CLASSIFIERS]

User: project_code_classifier in ANALYTICS_DB.GOVERNANCE

Agent: Please confirm the custom classifier configuration:

| Setting           | Value                              |
|-------------------|-------------------------------------|
| Classifier Name   | project_code_classifier             |
| Location          | ANALYTICS_DB.GOVERNANCE             |
| Regex Pattern     | `^PRJ-[A-Z]{3}-[0-9]{3}$`          |
| Description       | Detects project codes (PRJ-XXX-NNN) |

Ready to create this classifier? (yes / no / edit)

User: yes

Agent: ✅ Custom classifier created successfully!

Now I'd like to test the classifier to ensure it works correctly.

For testing, I recommend using a dedicated temporary database to keep your 
production schemas clean.

Do you have a preferred location for test data?

  a) Use DG_TEMP_DB.project_code_classifier_test (recommended)
  b) Use a different database/schema
  c) Skip testing

Please select (a/b/c):

User: a

Agent: Creating test schema DG_TEMP_DB.project_code_classifier_test...
Running validation tests...

📊 Classifier Test Results:

| Test Value    | Expected | Type               | Actual   | Result  |
|---------------|----------|--------------------|----------|---------|
| PRJ-ABC-001   | ✅ Match | user_sample        | ✅ Match | ✅ PASS |
| PRJ-XYZ-123   | ✅ Match | user_sample        | ✅ Match | ✅ PASS |
| PRJ-DEV-999   | ✅ Match | user_sample        | ✅ Match | ✅ PASS |
| PRJ-AB-001    | ❌ No    | generated_negative | ❌ No    | ✅ PASS |
| prj-ABC-001   | ❌ No    | generated_negative | ❌ No    | ✅ PASS |

Summary: 5/5 tests passed ✅

Testing complete! The test data is stored in:
  Database: DG_TEMP_DB
  Schema:   project_code_classifier_test

Would you like to clean up the test data?

  a) Yes, drop the test schema
  b) Keep the test data for future reference
  c) Drop only the test table, keep the schema

Please select (a/b/c):

User: a

Agent: 🧹 Test schema DG_TEMP_DB.project_code_classifier_test has been removed.

Would you like to add this classifier to a Classification Profile?
  a) Yes, add to existing profile
  b) Yes, create a new profile with this classifier
  c) No, I'll use it manually with SYSTEM$CLASSIFY

User: a

Agent: [Shows existing profiles, user selects one, profile is updated]

📝 Session Summary:
| Item                | Value                           |
|---------------------|---------------------------------|
| Outcome             | ✅ Custom classifier created    |
| Classifier Name     | project_code_classifier         |
| Pattern             | `^PRJ-[A-Z]{3}-[0-9]{3}$`       |
| Profile Integration | Added to pii_classifier         |
```

---

## Edge Case Examples

### Example 10: SQL Execution Failure (CRITICAL - Proper Error Handling)

**Demonstrates: NEVER mark a step successful if SQL execution failed**

```
User: Create a custom classifier for Chinese passport numbers

Agent: [Attempts to create classifier]

Executing: CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER passport_cn();

[SQL Result: Statement 1 failed - SQL compilation error: syntax error...]

❌ Error creating custom classifier

The CREATE statement failed with an error:
"SQL compilation error: syntax error at position X..."

This step was NOT successful. The classifier was not created.

Would you like to:
  a) Review the error - I'll help troubleshoot
  b) Try a different approach
  c) Exit

Please select:
```

**🚨 WRONG BEHAVIOR (Never do this):**
```
Agent: [SQL fails with error]

✅ Custom classifier created successfully!  <-- WRONG! SQL failed!

[Proceeds to next step...]  <-- WRONG! Should have stopped!
```

**The agent MUST:**
1. Check actual SQL execution result
2. If `failed`, `error`, or any error message appears → step FAILED
3. Never say "successfully" when SQL returned an error
4. Stop and present the error to the user

---

### Example 11: Verification After Creation

**Demonstrates: Always verify objects were created before claiming success**

```
User: Create a classifier for project codes

Agent: Creating custom classifier...

[Executes: CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER project_code();]
[Result: Instance PROJECT_CODE successfully created.]

[Executes: CALL project_code!ADD_REGEX('PROJECT_CODE', 'QUASI_IDENTIFIER', '^PRJ-[A-Z]{3}-[0-9]{3}$', 'Project codes');]
[Result: Statement executed successfully.]

Now verifying the classifier was created...

[Executes: SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER LIKE 'project_code';]
[Result: 1 row returned - project_code found]

✅ Custom classifier created and verified!

| Field      | Value                        |
|------------|------------------------------|
| Classifier | project_code                 |
| Location   | GOVERNANCE_DB.CLASSIFIERS    |
| Category   | PROJECT_CODE                 |
| Pattern    | `^PRJ-[A-Z]{3}-[0-9]{3}$`   |
| Verified   | ✅ Confirmed in SHOW results |

Would you like to test this classifier with sample data?
```

---

### Example 12: Insufficient Privileges

```
User: Set up auto-classification

Agent: [After context check and profile creation attempt]

❌ Error: Insufficient privileges to create classification profile.

Your role DATA_ANALYST needs CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE on 
ANALYTICS_DB.GOVERNANCE.

Options:
  a) Try a different role (I'll help you switch)
  b) Try a different database/schema
  c) Continue with manual classification instead

Please select (a/b/c):
```

---

### Example 13: User Has Existing Solution

```
User: We already use a third-party tool for PII detection

Agent: That's great that you have a governance solution in place!

Would you like to:
  a) See how Snowflake's built-in classification compares
  b) Explore Semantic Views to expose your classifications to Snowflake features
  c) Exit and continue with your current approach

Please select (a/b/c):

User: b

Agent: Semantic Views can help you integrate your existing classifications 
with Snowflake's ecosystem. They allow you to:

- Expose your PII tags to Cortex Analyst
- Enable tag-based masking policies
- Provide consistent governance metadata

Would you like me to explain how to set up a Semantic View for your 
classified data? (yes/no)
```

---

## Quick Reference

| Intent | Example Query | Workflow |
|--------|---------------|----------|
| Detect PII | "Find sensitive data in my database" | Auto-Classification |
| One-time scan | "Scan CUSTOMERS table for PII" | Manual Classification |
| Ongoing monitoring | "Set up automatic PII detection" | Auto-Classification |
| Custom data | "Detect employee IDs like EMP-12345" | Custom Classifier |
| Standard format | "Detect UK NINOs" | Custom Classifier (ask for samples first) |
| Existing solution | "I have my own PII detection" | Honor Preferences |

## Key Principle: User Data First

When creating custom classifiers for well-known formats (UK NINO, SSN, etc.):

1. ✅ **RIGHT**: "Do you have sample data, or should I use the standard format?"
2. ❌ **WRONG**: "UK NINOs follow this pattern..." (assuming without asking)

