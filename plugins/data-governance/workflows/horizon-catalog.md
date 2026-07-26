---
name: horizon-catalog
parent_skill: data-governance
description: "Snowflake Horizon catalog analysis via ACCOUNT_USAGE views. Covers the full catalog: access history, users, roles, grants, permissions, role hierarchies, object dependencies, tags, compliance monitoring, query history. Also serves as a fallback for any data-governance question not handled by data-policy or sensitive-data-classification. Triggers: access history, who has access, who accessed, permissions, grants, roles, audit trail, compliance, object dependencies, catalog, query history."
---

# Data Governance Instructions

Generate SQL queries against Snowflake ACCOUNT_USAGE governance data using the embedded semantic model.

## When to Use

**Access & Audit:** User access patterns, permissions, role hierarchies, query history, activity tracking, accessed table/data  
**Compliance:** Policy analysis (masking, row access, aggregation), grant analysis, audit trails  
**Advanced:** Cross-database access patterns, object dependencies, role effectiveness analysis

**NOTE:** For PII detection, sensitive data classification, or setting up auto-classification, the parent `data-governance` skill routes to `sensitive-data-classification`. For data masking policy, row access policy, or projection policy work, it routes to `data-policy`. This skill (`horizon-catalog`) is also the fallback for any governance question those two sub-skills or other top level skills such as data quality and lineage, etc. cannot answer.

## Workflow

### Step 1: Parse Question → Identify Domain

- Access/audit → ACCESS_HISTORY, GRANTS_*
- Classification/PII → DATA_CLASSIFICATION_LATEST, TAGS
- Policies → *_POLICIES, POLICY_REFERENCES
- Objects → TABLES, VIEWS, COLUMNS, OBJECT_DEPENDENCIES
- Schema/column change detection → "Has column X changed?", "What is the current data type of column Y?", "Show DDL history for table T" → query ACCOUNT_USAGE.COLUMNS for current definition, ACCOUNT_USAGE.TABLES for last_altered, ACCOUNT_USAGE.QUERY_HISTORY for recent DDL (query_type IN ('ALTER_TABLE','ALTER','CREATE_TABLE_AS_SELECT')). Note: ACCOUNT_USAGE has 45min–3h latency; also query INFORMATION_SCHEMA.COLUMNS for the current real-time definition.

### Step 2: Check Verified Queries FIRST

Search the embedded semantic model's `verified_queries` section (100+ queries) for matching patterns:
- "who has access" → Roles/users with privileges queries
- Sensitive data → Classification and policy protection queries
- Access history → LATERAL FLATTEN patterns
- Policies → Policy-specific queries

**If match found:** Adapt the verified query SQL (adjust time filters, object names). Replace `__table_name` with `SNOWFLAKE.ACCOUNT_USAGE.TABLE_NAME` from base_table definition.

**If no match:** Generate SQL using semantic model table definitions and similar verified queries as structural reference.

### Step 3: SQL Construction Guidelines

- All tables in `SNOWFLAKE.ACCOUNT_USAGE` schema
- JSON columns (DIRECT_OBJECTS_ACCESSED, BASE_OBJECTS_ACCESSED, OBJECTS_MODIFIED) require LATERAL FLATTEN
- Use UPPER() for case-insensitive identifier matching
- Add time filters for ACCESS_HISTORY queries (QUERY_START_TIME)

### Step 4: Execute Query

Return generated SQL and results.

## Key Notes

- ACCESS_HISTORY requires LATERAL FLATTEN for column-level analysis
- Tables have up to 120 minute latency
- 100+ verified queries embedded below with proven patterns
- Use UPPER() for identifier matching

---

## Semantic Model

Semantic model embedded below:

# the list of supported account_usage views
# Category 1: Historical Data
#       ACCESS_HISTORY [TODO verify definition]
#       QUERY_HISTORY [TODO verify definition]
# Category 2: Tags, Policies, Sensitivity and Classifications
#       AGGREGATION_POLICIES
#       MASKING_POLICIES
#       ROW_ACCESS_POLICIES
#       PROJECTION_POLICIES
#       TAGS
#       TAG_REFERENCES
#       DATA_CLASSIFICATION_LATEST [TODO verify definition]
#       POLICY_REFERENCES
# Category 3: Data Objects
#       COLUMNS
#       DATABASES
#       SCHEMATA
#       TABLES
#       VIEWS
#       OBJECT_DEPENDENCIES [TODO verify definition]
# Category 4: Security and Sensitivity
#       GRANTS_TO_ROLES
#       GRANTS_TO_USERS
#       ROLES
#       USERS

name: Governance
custom_instructions: >

  1. Identifier Case Sensitivity and Formatting:

  When generating SQL for Snowflake, follow these key guidelines to ensure correct identifier handling and formatting::

    Unquoted identifiers (e.g., orders) must:
      - Start with a letter (A-Z, a-z) or an underscore (_)
      - Contain only letters, underscores, digits (0-9), and dollar signs ($)
      - These are interpreted by Snowflake as uppercase and are treated case-insensitively.
    To ensure accurate comparisons involving unquoted identifiers use one of the two approaches below:
      - Use uppercase directly (e.g., WHERE table_name = 'ORDERS')
      - Use the UPPER() function (e.g., WHERE table_name = UPPER('orders'))

    Quoted identifiers (e.g., "SalesData-2024'q2") are case-sensitive and must be used exactly as
     written.
      - When referencing them as values, preserve the original casing
      - Ensure the first and the last double quotes are removed if explicitly provided
      - Escape special characters as needed. Example Filter: WHERE table_name = 'SalesData-2024\\'q2'

    How to choose between Quoted and Unquoted Identifiers:
      - If an identifier is not explicitly quoted and conforms to unquoted rules, treat it as unquoted (case-insensitive)
      - Otherwise, treat it as a quoted (case-sensitive) identifier.

  2. Fully-Qualified Object Names:

    - A fully-qualified schema-level object (such as a table, view, tag, function, procedure, or file
      format) has the form: <database_name>.<schema_name>.<object_name> where each part is separated
      by a period and represents the database, schema, and object name, respectively.

    - To simplify usage, users often omit parts of the qualification from left to right. For example:
      both <schema_name>.<object_name> and <object_name> may be used to refer to objects.

    - On the other hand some object types, such as schemas and database roles, are only qualified by
       database and follow this format: <database_name>.<object_name>

    - Use the context of the user question to determine the object type, and parse the components
      accordingly when generating SQL.

  3. Query Behavior Expectations:

    - Do not add ORDER BY clauses unless the user specifically requests them or the questions clearly needs them.
    - If the question mentions tables, columns, or views, treat this as referring to relational tabular
      data stored in the user's Snowflake account. Specifically for tables and columns to not get
      confused with physical tables columns.


  4. Using ACCESS_HISTORY table and JSON data Handling:

    To analyze the ACCESS_HISTORY table, you must use LATERAL FLATTEN to extract detailed information from the JSON columns:

      - DIRECT_OBJECTS_ACCESSED
          Raw JSON array of data objects explicitly named in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

      - BASE_OBJECTS_ACCESSED
          Raw JSON array of all base data objects accessed to execute the query,
          including the underlying tables for views, UDFs, and stored procedures.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

      - OBJECTS_MODIFIED
          Raw JSON array specifying the objects that were associated with a write
          operation in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of modified columns with source information

      - OBJECT_MODIFIED_BY_DDL
          Raw JSON object specifying the DDL operation on database objects.

          STRUCTURE:
          This is an object with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Object identifier
          - operationType: SQL operation (CREATE, ALTER, DROP, etc.)
          - properties: Array of object properties

    EXAMPLE QUERY:

      CREATE OR REPLACE VIEW ACCESS_HISTORY_FLATTENED AS
      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'direct_objects' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
          LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened

      UNION ALL

      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'base_objects' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
          LATERAL FLATTEN(input => BASE_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened

      UNION ALL

      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'objects_modified' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
          LATERAL FLATTEN(input => OBJECTS_MODIFIED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened

  5. Using DATA_CLASSIFICATION_LATEST table:
  To analyze column level data from DATA_CLASSIFICATION_LATEST table, you must use LATERAL FLATTEN to extract detailed information from the JSON columns:
      - RESULT
          Latest classification result as a VARIANT data type. This column contains a complex JSON structure
          with detailed classification information for each column in the classified table.

          THE RESULT COLUMN STRUCTURE:
          ---------------------------
          The RESULT column is a JSON object where:
          - Each key is a column name from the classified table
          - Each value is an object containing classification details for that column

          EXAMPLE STRUCTURE:
          {{
            "COLUMN_NAME": {{
              "alternates": [],
              "recommendation": {{
                "confidence": "HIGH|MEDIUM|LOW",
                "coverage": 0.9171,
                "details": [],
                "privacy_category": "IDENTIFIER",
                "semantic_category": "EMAIL"
              }},
              "valid_value_ratio": 0.9171
            }},
            "ANOTHER_COLUMN": {{
              ...
            }}
          }}

      EXAMPLE QUERY:
      WITH base_classification AS (
        SELECT
          DATABASE_NAME,
          SCHEMA_NAME,
          TABLE_NAME,
          RESULT
        FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
      ),
      column_categories AS (
        SELECT
          f.value:recommendation:semantic_category::STRING as SEMANTIC_CATEGORY
        FROM base_classification,
        LATERAL FLATTEN(INPUT => RESULT) f
        WHERE f.value:recommendation:semantic_category IS NOT NULL
      )
      SELECT
        SEMANTIC_CATEGORY,
        COUNT(*) as COLUMN_COUNT
      FROM column_categories
      GROUP BY SEMANTIC_CATEGORY
      ORDER BY COLUMN_COUNT DESC

  6. Consistent State of Governance Tables:

  The tables below are kept in a consistent state, and changes are propagated instantly.
  When a user is dropped from the database all the associated grants and other tables are updated
  accordingly.  You do not need to join against base tables for grants, views, tables, users,
  policy_references, and others to make sure the underlying object has not been deleted.

  7. Default User Filtering:

  When querying the USERS table, always exclude disabled and deleted users by default:
    - Add DELETED_ON IS NULL to filter out deleted users
    - Add DISABLED = 'false' to filter out disabled user accounts
  Only include disabled or deleted users if the user explicitly asks about them
  (e.g., "show disabled users", "list deleted accounts", "include inactive users").

tables:
  - name: ACCESS_HISTORY
    description: >
      The table contains records of user access history, specifically queries executed by users.
      Each record represents a single query and includes details about the user, query execution,
      and accessed objects.
      This view is available in Enterprise Edition or higher and tracks access history
      for the last 365 days (1 year).

      Note: This table contains complex JSON arrays (DIRECT_OBJECTS_ACCESSED, BASE_OBJECTS_ACCESSED,
      and OBJECTS_MODIFIED) that require LATERAL FLATTEN operations for detailed analysis.
      Since LATERAL FLATTEN cannot be used directly in semantic model expressions, this model
      provides simplified dimensions and metrics based on these JSON columns. For detailed
      column-level access analysis, use the verified queries that demonstrate proper JSON handling
      with LATERAL FLATTEN in subsequent operations.

    synonyms:
      - "data access"
      - "object access"
      - "access audit"
      - "access logs"

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: ACCESS_HISTORY

    primary_key:
      columns:
        - QUERY_ID

    time_dimensions:
      - name: QUERY_START_TIME
        description: >
          The timestamp when the query was started (in UTC time zone).
          This can be used for time-based analysis of access patterns.
        synonyms:
          - "access time"
          - "query time"
        expr: QUERY_START_TIME
        data_type: TIMESTAMP_LTZ

      - name: ACCESS_DATE
        description: "Date part of when the access occurred (without time)"
        expr: DATE(QUERY_START_TIME)
        data_type: DATE

      - name: ACCESS_MONTH
        description: "Month when the access occurred, useful for monthly reporting"
        expr: DATE_TRUNC('MONTH', QUERY_START_TIME)
        data_type: DATE

      - name: ACCESS_DAY_OF_WEEK
        description: "Day of week when access occurred (1=Sunday, 7=Saturday)"
        expr: DAYOFWEEK(QUERY_START_TIME)
        data_type: NUMBER

      - name: ACCESS_HOUR
        description: "Hour of day when access occurred (0-23)"
        expr: HOUR(QUERY_START_TIME)
        data_type: NUMBER

      - name: IS_BUSINESS_HOURS
        description: "Flag indicating if access occurred during business hours (M-F, 9AM-5PM)"
        expr: >
          CASE
            WHEN DAYOFWEEK(QUERY_START_TIME) BETWEEN 2 AND 6
            AND HOUR(QUERY_START_TIME) BETWEEN 9 AND 16
            THEN TRUE
            ELSE FALSE
          END
        data_type: BOOLEAN

    dimensions:
      - name: QUERY_ID
        description: >
          A unique identifier for the query. This value is also mentioned in
          the QUERY_HISTORY view and can be used to join the tables.
        expr: QUERY_ID
        data_type: TEXT
        unique: true

      - name: USER_NAME
        description: >
          The name of the user who issued the query that accessed the data.
        synonyms:
          - "username"
          - "user"
        expr: USER_NAME
        data_type: TEXT

      - name: PARENT_QUERY_ID
        description: >
          The unique identifier of the parent job or NULL if the job does not have a parent.
          This allows tracking of query hierarchies.
        expr: PARENT_QUERY_ID
        data_type: TEXT

      - name: ROOT_QUERY_ID
        description: >
          The unique identifier of the top most job in the chain or NULL if the job does not
          have a parent. Useful for tracking query hierarchies.
        expr: ROOT_QUERY_ID
        data_type: TEXT

      - name: DIRECT_OBJECTS_ACCESSED
        description: >
          Raw JSON array of data objects directly accessed in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: DIRECT_OBJECTS_ACCESSED
        data_type: VARIANT

      - name: BASE_OBJECTS_ACCESSED
        description: >
          Raw JSON array of all base data objects accessed to execute the query,
          including the underlying tables for views, UDFs, and stored procedures.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: BASE_OBJECTS_ACCESSED
        data_type: VARIANT

      - name: OBJECTS_MODIFIED
        description: >
          Raw JSON array specifying the objects that were modified in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of modified columns with source information

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: OBJECTS_MODIFIED
        data_type: VARIANT

      - name: OBJECT_MODIFIED_BY_DDL
        description: >
          Raw JSON object specifying the DDL operation on database objects.

          STRUCTURE:
          This is an object with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Object identifier
          - operationType: SQL operation (CREATE, ALTER, DROP, etc.)
          - properties: Array of object properties

          NOTE: To analyze this data in detail, you need to use JSON path extraction
          functions in a subsequent query, as demonstrated in the verified queries section.
        expr: OBJECT_MODIFIED_BY_DDL
        data_type: VARIANT

      - name: POLICIES_REFERENCED
        description: >
          Raw JSON array specifying information about enforced/referenced masking and row access policies.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the protected object
          - objectId: Object identifier
          - columns: Array of columns with masking policies
          - policies: Array of row access policies

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: POLICIES_REFERENCED
        data_type: VARIANT

      - name: HAS_DIRECT_OBJECT_ACCESS
        description: "Flag indicating if the query directly accessed any objects"
        expr: DIRECT_OBJECTS_ACCESSED IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_BASE_OBJECT_ACCESS
        description: "Flag indicating if the query accessed any base objects"
        expr: BASE_OBJECTS_ACCESSED IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_OBJECT_MODIFICATIONS
        description: "Flag indicating if the query modified any objects"
        expr: OBJECTS_MODIFIED IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_DDL_OPERATIONS
        description: "Flag indicating if the query performed DDL operations"
        expr: OBJECT_MODIFIED_BY_DDL IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_POLICY_REFERENCES
        description: "Flag indicating if the query involved any data policies"
        expr: POLICIES_REFERENCED IS NOT NULL
        data_type: BOOLEAN

      - name: DIRECT_OBJECT_COUNT
        description: "Number of direct objects accessed in the query"
        expr: ARRAY_SIZE(DIRECT_OBJECTS_ACCESSED)
        data_type: NUMBER

      - name: BASE_OBJECT_COUNT
        description: "Number of base objects accessed in the query"
        expr: ARRAY_SIZE(BASE_OBJECTS_ACCESSED)
        data_type: NUMBER

      - name: MODIFIED_OBJECT_COUNT
        description: "Number of objects modified in the query"
        expr: ARRAY_SIZE(OBJECTS_MODIFIED)
        data_type: NUMBER

      - name: POLICY_REFERENCE_COUNT
        description: "Number of policy references in the query"
        expr: ARRAY_SIZE(POLICIES_REFERENCED)
        data_type: NUMBER

      - name: DDL_OPERATION_TYPE
        description: "The DDL operation type if this was a DDL query (CREATE, ALTER, DROP, etc.)"
        expr: GET_PATH(OBJECT_MODIFIED_BY_DDL, 'operationType')::STRING
        data_type: TEXT

      - name: DDL_OBJECT_DOMAIN
        description: "The type of object affected by the DDL operation"
        expr: GET_PATH(OBJECT_MODIFIED_BY_DDL, 'objectDomain')::STRING
        data_type: TEXT
        is_enum: true
        sample_values:
          - "Table"
          - "View"
          - "Materialized view"
          - "Procedure"
          - "Function"
          - "Stage"

      - name: DDL_OBJECT_NAME
        description: "The fully qualified name (e.g. db.schema.table for a table) of the object affected by the DDL operation"
        expr: GET_PATH(OBJECT_MODIFIED_BY_DDL, 'objectName')::STRING
        data_type: TEXT

    filters:
      - name: BUSINESS_HOURS_ONLY
        description: "Filter to include only operations during business hours (M-F, 9AM-5PM)"
        expr: >
          DAYOFWEEK(QUERY_START_TIME) BETWEEN 2 AND 6 AND
          HOUR(QUERY_START_TIME) BETWEEN 9 AND 16

      - name: NON_BUSINESS_HOURS_ONLY
        description: "Filter to include only operations outside business hours"
        expr: >
          NOT (DAYOFWEEK(QUERY_START_TIME) BETWEEN 2 AND 6 AND
          HOUR(QUERY_START_TIME) BETWEEN 9 AND 16)

      - name: LAST_24_HOURS
        description: "Filter to include only operations in the last 24 hours"
        expr: QUERY_START_TIME >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())

      - name: LAST_7_DAYS
        description: "Filter to include only operations in the last 7 days"
        expr: QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())

      - name: LAST_30_DAYS
        description: "Filter to include only operations in the last 30 days"
        expr: QUERY_START_TIME >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())


  # Category 2: Tags, Policies, Sensitivity and Classifications

  - name: AGGREGATION_POLICIES
    description: Account Usage view that provides information about aggregation policies in your account.
      Each row represents a different aggregation policy that controls data access constraints.
      Has a latency of up to 120 minutes and shows only objects accessible to the current role.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: AGGREGATION_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the aggregation policy was created
        synonyms : ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time when the aggregation policy was last modified
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the aggregation policy was dropped
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated identifier for the aggregation policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: Name of the aggregation policy
        synonyms: ["POLICY NAME", "NAME", "AGGREGATION POLICY NAME"]
        data_type: VARCHAR

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal/system-generated identifier for the schema containing the policy
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID", "AGGREGATION POLICY SCHEMA ID", "AGGREGATION_POLICY PARENT SCHEMA ID", "POLICY PARENT SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Schema that contains the aggregation policy
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME", "AGGREGATION_POLICY SCHEMA NAME", "AGGREGATION_POLICY PARENT SCHEMA NAME", "POLICY PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal/system-generated identifier for the database containing the policy
        synonyms: ["CATALOG ID", "DATABASE ID", "POLICY PARENT CATALOG ID", "AGGREGATION_POLICY PARENT CATALOG ID", "POLICY PARENT DATABASE ID", "AGGREGATION_POLICY PARENT DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Database to which the aggregation policy belongs
        synonyms: ["CATALOG NAME", "DATABASE NAME", "POLICY PARENT CATALOG NAME", "AGGREGATION_POLICY PARENT CATALOG NAME", "POLICY PARENT DATABASE NAME", "AGGREGATION_POLICY PARENT DATABASE NAME"]
        data_type: VARCHAR

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the aggregation policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "AGGREGATION POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature of the aggregation policy's arguments
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: VARCHAR

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: Return value data type of the aggregation policy
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        data_type: VARCHAR
        is_enum: true

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: Aggregation policy definition containing the implementation logic
        synonyms: ["BODY", "DEFINITION", "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC"]
        data_type: VARCHAR

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: User-provided comments for the aggregation policy
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:  The type of role that owns the object. Returns 'ROLE' for standard roles,
          'APPLICATION' for Snowflake Native Apps, or NULL for deleted objects
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: VARCHAR
        sample_values:
          - ROLE
          - APPLICATION
        is_enum: true

    filters:
      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) aggregation policies"
        expr: DELETED IS NULL

      - name: has_min_group_size
        synonyms:
          - "group size policies"
        description: "Filter to show policies with minimum group size constraints"
        expr: POLICY_BODY LIKE '%MIN_GROUP_SIZE%'

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: PROJECTION_POLICIES
    description: This Account Usage view provides information about projection policies in your Snowflake account.
      Each row represents a different projection policy with its configuration details, ownership, and lifecycle timestamps.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: PROJECTION_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: The timestamp when the projection policy was initially created
        synonyms : ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description:   Date and time the policy was last modified by DDL operations, DML operations,
          or background metadata maintenance
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: The timestamp when the projection policy was dropped/deleted, if applicable
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal system-generated unique identifier for the projection policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: User-defined name of the projection policy
        synonyms: ["POLICY NAME", "NAME", "PROJECTION POLICY NAME"]
        data_type: VARCHAR

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal system-generated identifier for the schema containing the policy
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID", "PROJECTION_POLICY SCHEMA ID", "PROJECTION_POLICY PARENT SCHEMA ID", "POLICY PARENT SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Name of the schema that contains the projection policy
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME", "PROJECTION_POLICY SCHEMA NAME", "PROJECTION_POLICY PARENT SCHEMA NAME", "POLICY PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal system-generated identifier for the database containing the policy
        synonyms: ["CATALOG ID", "DATABASE ID", "POLICY PARENT CATALOG ID", "PROJECTION_POLICY PARENT CATALOG ID", "POLICY PARENT DATABASE ID", "PROJECTION POLICY PARENT DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Name of the database that contains the projection policy
        synonyms: ["CATALOG NAME", "DATABASE NAME", "POLICY PARENT CATALOG NAME", "MASKING POLICY PARENT CATALOG NAME", "POLICY PARENT DATABASE NAME", "MASKING POLICY PARENT DATABASE NAME"]
        data_type: VARCHAR

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the projection policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "MASKING POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature defining the arguments accepted by the projection policy
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: VARCHAR

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: The data type returned by the projection policy
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        sample_values:
          - PROJECTION_CONSTRAINT
        data_type: VARCHAR

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: The actual implementation/definition of the projection policy
        synonyms: ["POLICY BODY", "BODY", "DEFINITION", "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC"]
        data_type: VARCHAR

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: User-provided comments or documentation for the projection policy
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: TEXT

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:     Indicates the type of role that owns the policy. Values can be 'ROLE' for standard
          Snowflake roles or 'APPLICATION' for Snowflake Native Apps. Returns NULL for deleted objects.
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: VARCHAR
        is_enum: true

    filters:
      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) projection policies"
        expr: DELETED IS NULL

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: ROW_ACCESS_POLICIES
    description: Account Usage view that displays information about all row access policies defined in your account.
      Each row corresponds to a different row access policy.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: ROW_ACCESS_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the row access policy was created
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT"]


      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the object was last altered by a DML, DDL, or background metadata operation
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]


      - name: DELETED
        expr: DELETED
        description: Date and time when the row access policy was dropped
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]

    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated identifier for the row access policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: Name of the row access policy
        synonyms: ["POLICY NAME", "NAME", "ROW ACCESS POLICY NAME", "ROW FILTER POLICY NAME",  "ROW SECURITY POLICY NAME", "ROW_ACCESS_POLICY NAME", "ROW_FILTER_POLICY NAME", "ROW_SECURITY_POLICY NAME"]
        data_type: TEXT

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal/system-generated identifier for the schema in which the policy resides
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID", "ROW_ACCESS_POLICY SCHEMA ID", "ROW_ACCESS_POLICY PARENT SCHEMA ID", "POLICY PARENT SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Schema to which the row access policy belongs
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME", "ROW_ACCESS_POLICY SCHEMA NAME", "ROW_ACCESS_POLICY PARENT SCHEMA NAME", "POLICY PARENT SCHEMA NAME"]
        data_type: TEXT

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal/system-generated identifier for the database in which the policy resides
        synonyms: ["CATALOG ID", "DATABASE ID", "POLICY PARENT CATALOG ID", "ROW_ACCESS_POLICY PARENT CATALOG ID", "POLICY PARENT DATABASE ID", "ROW ACCESS POLICY PARENT DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Database to which the row access policy belongs
        synonyms: ["CATALOG NAME", "DATABASE NAME", "POLICY PARENT CATALOG NAME", "ROW ACCESS POLICY PARENT CATALOG NAME", "POLICY PARENT DATABASE NAME", "ROW ACCESS POLICY PARENT DATABASE NAME"]
        data_type: TEXT

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the row access policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "MASKING POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: TEXT

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature of the row access policy's arguments
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: TEXT

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: Return value data type
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        data_type: TEXT

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: Row access policy definition
        synonyms: ["POLICY BODY", "BODY", "DEFINITION",  "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC"]
        data_type: TEXT

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: Comments entered for the row access policy (if any)
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: TEXT

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:     The type of role that owns the object, for example ROLE. If a Snowflake Native App owns the object,
          the value is APPLICATION. Snowflake returns NULL if you delete the object because a deleted object
          does not have an owner role.
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: TEXT
        is_enum: true


      - name: OPTIONS
        expr: OPTIONS
        description: 'The value for the EXEMPT_OTHER_POLICIES property in the policy. If set to TRUE, the column returns
          {{ "EXEMPT_OTHER_POLICIES: "TRUE" }}. If the property is set to FALSE or not set at all, the column returns NULL.'
        synonyms: ["POLICY OPTIONS", "CONFIGURATION", "EXEMPT_OTHER_POLICIES OPTIONS"]
        data_type: VARIANT

    filters:
      - name: app_owned_policies
        description: Filter for policies owned by Snowflake Native Apps
        expr: OWNER_ROLE_TYPE = 'APPLICATION'

      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) row access policies"
        expr: DELETED IS NULL

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: MASKING_POLICIES
    description: This Account Usage view provides information about masking policies in your Snowflake account.
      Each row represents a different masking policy with its configuration details, ownership, and lifecycle timestamps.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: MASKING_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the masking policy was created
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT"]

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description:     Date and time the policy was last modified by DDL operations, DML operations,
          or background metadata maintenance
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]


      - name: DELETED
        expr: DELETED
        description: Date and time when the masking policy was dropped
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]


    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated unique identifier for the masking policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: Name of the masking policy
        synonyms: ["POLICY NAME", "NAME", "MASKING POLICY NAME", "COLUMN MASKING POLICY NAME",  "COLUMN_MASKING_POLICY NAME", "TOKENIZATION POLICY NAME", "COLUMN SECURITY POLICY NAME", "COLUMN_SECURITY POLICY NAME"]
        data_type: TEXT

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal/system-generated identifier for the schema containing the policy
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID", "MASKING_POLICY SCHEMA ID", "MASKING_POLICY PARENT SCHEMA ID", "POLICY PARENT SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Schema to which the masking policy belongs
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME", "MASKING_POLICY SCHEMA NAME", "MASKING_POLICY PARENT SCHEMA NAME", "POLICY PARENT SCHEMA NAME"]
        data_type: TEXT

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal/system-generated identifier for the database containing the policy
        synonyms: ["CATALOG ID", "DATABASE ID", "POLICY PARENT CATALOG ID", "MASKING_POLICY PARENT CATALOG ID", "POLICY PARENT DATABASE ID", "MASKING POLICY PARENT DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Database to which the masking policy belongs
        synonyms: ["CATALOG NAME", "DATABASE NAME", "POLICY PARENT CATALOG NAME", "MASKING POLICY PARENT CATALOG NAME", "POLICY PARENT DATABASE NAME", "MASKING POLICY PARENT DATABASE NAME"]
        data_type: TEXT

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the masking policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "MASKING POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: TEXT

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature of the masking policy's arguments in JSON format
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: TEXT

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: Return value data type of the masking policy in JSON format
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        data_type: TEXT

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: The SQL definition of the masking policy that specifies how data should be masked
        synonyms: ["POLICY BODY", "BODY", "DEFINITION", "MASK DEFINITION", "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC", "MASKING DEFINITION", "MASKING EXPRESSION", "MASKING POLICY EXPRESSION"]
        data_type: TEXT

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: User-provided comments or documentation for the masking policy
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: TEXT

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:     The type of role that owns the object. Returns 'ROLE' for standard roles,
          'APPLICATION' for Snowflake Native Apps, or NULL for deleted objects
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: TEXT
        is_enum: true

      - name: OPTIONS
        expr: OPTIONS
        description: 'Contains policy options like EXEMPT_OTHER_POLICIES. Returns JSON object with
          "EXEMPT_OTHER_POLICIES: TRUE" if set, NULL otherwise'
        synonyms: ["POLICY OPTIONS", "CONFIGURATION", "EXEMPT_OTHER_POLICIES OPTIONS"]
        data_type: VARIANT

    filters:
      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) masking policies"
        expr: DELETED IS NULL

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: TAGS
    description: Contains detailed information about tags defined in the Snowflake account, including metadata, ownership, and lifecycle information.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: TAGS

    primary_key:
      columns:
        - TAG_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the tag was created
        synonyms : ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time when the tag was last modified by DML/DDL statements or background operations
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the tag or its parent objects were dropped
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TAG_ID
        expr: TAG_ID
        description: Unique local identifier for the tag
        synonyms: ["TAG ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: TAG_NAME
        expr: TAG_NAME
        description: Name of the tag
        synonyms: ["TAG NAME", "NAME"]
        data_type: VARCHAR

      - name: TAG_SCHEMA_ID
        expr: TAG_SCHEMA_ID
        description: Local identifier of the schema containing the tag
        synonyms: ["TAG SCHEMA ID", "SCHEMA ID",  "TAG PARENT SCHEMA ID"]
        data_type: NUMBER

      - name: TAG_SCHEMA
        expr: TAG_SCHEMA
        description: Name of the schema containing the tag
        synonyms: ["TAG SCHEMA NAME", "SCHEMA NAME", "TAG PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: TAG_DATABASE_ID
        expr: TAG_DATABASE_ID
        description: Local identifier of the database containing the tag
        synonyms: ["CATALOG ID", "DATABASE ID", "TAG PARENT CATALOG ID", "TAG PARENT DATABASE ID"]
        data_type: NUMBER

      - name: TAG_DATABASE
        expr: TAG_DATABASE
        description: Name of the database containing the tag
        synonyms: ["CATALOG NAME", "DATABASE NAME", "TAG CATALOG NAME", "TAG PARENT DATABASE NAME"]
        data_type: VARCHAR

      - name: TAG_COMMENT
        expr: TAG_COMMENT
        description: User-provided comments or description for the tag
        synonyms: ["TAG COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

      - name: TAG_OWNER
        expr: TAG_OWNER
        description: The name of the role that owns the tag.
        synonyms: ["TAG OWNER", "OWNER ROLE"]
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: The type of the owner role
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: VARCHAR
        sample_values:
          - ROLE
          - APPLICATION
        is_enum: true

      - name: ALLOWED_VALUES
        expr: ALLOWED_VALUES
        description: The allowed values specified for this tag
        synonyms: ["RESTRICTED VALUES"]
        data_type: ARRAY

      - name: PROPAGATE
        expr: PROPAGATE
        description: Specified propagated value for the tags
        synonyms: ["PROPAGATION"]
        data_type: VARCHAR
        is_enum: true
        sample_values:
          - ON_DEPENDENCY
          - ON_DATA_MOVEMENT
          - ON_DEPENDENCY_AND_DATA_MOVEMENT

      - name: ON_CONFLICT
        expr: ON_CONFLICT
        description: If the tag is configured for automatic propagation, indicates what happens when the value of the tag being propagated conflicts with the value that was specified when the tag was manually applied to the same object
        synonyms: ["CONFLICTED VALUE"]
        data_type: VARCHAR

    filters:
      - name: active_tags_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) tags"
        expr: DELETED IS NULL

      - name: tags_created_this_year
        description: "Filter to show tags created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented tags", "with description"]
        description: "Filter to show tags with documentation comments"
        expr: TAG_COMMENT IS NOT NULL

      - name: propagated_tags
        synonyms: ["propagation enabled tags"]
        description: "Filter to show tags whose propagation is not null"
        expr: PROPAGATE IS NOT NULL

  - name: COLUMNS
    description: Account Usage view that displays information about columns defined in each table in the account.
      Contains column metadata, data types, and schema evolution records.
      Has a latency of up to 90 minutes and shows only objects accessible to the current role.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: COLUMNS

    primary_key:
      columns:
        - COLUMN_NAME
        - TABLE_NAME
        - TABLE_SCHEMA
        - TABLE_CATALOG

    time_dimensions:
      - name: DELETED
        expr: DELETED
        description: Date and time when the column was deleted
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "COLUMN DELETION TIME"]

    dimensions:
      - name: COLUMN_ID
        expr: COLUMN_ID
        description: Internal/system-generated identifier for the column
        synonyms: ["COLUMN ID", "Column Identifier"]
        data_type: NUMBER

      - name: COLUMN_NAME
        expr: COLUMN_NAME
        description: Name of the column
        synonyms: ["COLUMN NAME", "NAME"]
        data_type: VARCHAR

      - name: TABLE_ID
        expr: TABLE_ID
        description: Internal/system-generated identifier for the table or view for the column
        synonyms: ["TABLE ID", "PARENT TABLE ID", "PARENT VIEW ID"]
        data_type: NUMBER

      - name: TABLE_NAME
        expr: TABLE_NAME
        description: Table or view that the column belongs to
        synonyms: ["TABLE NAME", "PARENT TABLE NAME", "PARENT VIEW NAME"]
        data_type: VARCHAR

      - name: TABLE_SCHEMA_ID
        expr: TABLE_SCHEMA_ID
        description: Internal/system-generated identifier for the schema of the table or view for the column
        synonyms: ["TABLE SCHEMA ID", "COLUMN PARENT SCHEMA ID", "PARENT SCHEMA ID"]
        data_type: NUMBER

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Schema that the table or view belongs to
        synonyms: ["TABLE SCHEMA", "COLUMN PARENT SCHEMA", "COLUMN PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: TABLE_CATALOG_ID
        expr: TABLE_CATALOG_ID
        description: Internal/system-generated identifier for the database of the table or view for the column
        synonyms: ["TABLE CATALOG ID", "COLUMN PARENT DATABASE ID", "COLUMN PARENT CATALOG ID"]
        data_type: NUMBER

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Database that the table or view belongs to
        synonyms: ["TABLE CATALOG NAME", "COLUMN PARENT DATABASE NAME", "COLUMN PARENT CATALOG NAME"]
        data_type: VARCHAR

      - name: COLUMN_DEFAULT
        expr: COLUMN_DEFAULT
        description: Default value of the column
        synonyms: ["COLUMN DEFAULT VALUE", "DEFAULT VALUE"]
        data_type: VARCHAR

      - name: IS_NULLABLE
        expr: IS_NULLABLE
        description: Whether the column allows NULL values
        synonyms: ["IS NULLABLE", "NULLABLE", "ALLOW NULL"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: DATA_TYPE
        expr: DATA_TYPE
        description: Data type of the column
        synonyms: ["COLUMN DATA TYPE", "DATA TYPE"]
        sample_values:
          - FLOAT
          - DATE
          - VECTOR
          - TEXT
          - OBJECT
          - UNKNOWN
          - TIME
          - TIMESTAMP_TZ
          - TIMESTAMP_NTZ
          - TIMESTAMP_LTZ
          - NUMBER
          - BINARY
          - GEOGRAPHY
          - ARRAY
          - BOOLEAN
          - VARIANT
          - GEOMETRY
          - MAP
        data_type: VARCHAR
        is_enum: true

      - name: INTERVAL_TYPE
        expr: INTERVAL_TYPE
        description: Interval type of the column (not applicable for Snowflake)
        synonyms: ["INTERVAL TYPE", "Interval Data Type"]
        data_type: VARCHAR

      - name: IS_IDENTITY
        expr: IS_IDENTITY
        description: Whether the column is an identity column
        synonyms: ["IS IDENTITY", "IDENTITY COLUMN", "AUTO-INCREMENT COLUMN"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: IDENTITY_ORDERED
        expr: IDENTITY_ORDERED
        description: If YES, the column is an identity column and has the ORDER property. If NO, the column is an identity column and has the NOORDER property.
        synonyms: ["IDENTITY ORDERED", "Identity Column Order"]
        data_type: VARCHAR

      - name: SCHEMA_EVOLUTION_RECORD
        expr: SCHEMA_EVOLUTION_RECORD
        description: Records information about the latest triggered schema evolution for a given table column
        synonyms: ["SCHEMA EVOLUTION RECORD", "SCHEMA EVOLUTION HISTORY", "COLUMN INGESTION RECORD"]
        data_type: VARCHAR

      - name: COMMENT
        expr: COMMENT
        description: Comment for the column
        synonyms: ["COLUMN COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

    facts:
      - name: ORDINAL_POSITION
        expr: ORDINAL_POSITION
        description: Ordinal position of the column in the table/view
        synonyms: ["ORDINAL POSITION", "ORDINAL"]
        data_type: NUMBER

      - name: CHARACTER_MAXIMUM_LENGTH
        expr: CHARACTER_MAXIMUM_LENGTH
        description: Maximum length in characters of string columns
        synonyms: ["CHARACTER MAXIMUM LENGTH", "MAX LENGTH", "STRING LENGTH"]
        data_type: NUMBER
        default_aggregation: sum

      - name: CHARACTER_OCTET_LENGTH
        expr: CHARACTER_OCTET_LENGTH
        description: Maximum length in bytes of string columns
        synonyms: ["CHARACTER OCTET LENGTH", "MAX BYTES", "STRING BYTES"]
        data_type: NUMBER
        default_aggregation: sum

      - name: NUMERIC_PRECISION
        expr: NUMERIC_PRECISION
        description: Numeric precision of numeric columns
        synonyms: ["PRECISION", "NUMERIC PRECISION"]
        data_type: NUMBER

      - name: NUMERIC_PRECISION_RADIX
        expr: NUMERIC_PRECISION_RADIX
        description: Radix of precision of numeric columns
        synonyms: ["NUMERIC PRECISION RADIX", "Numeric Radix"]
        data_type: NUMBER

      - name: NUMERIC_SCALE
        expr: NUMERIC_SCALE
        description: Scale of numeric columns
        synonyms: ["SCALE", "NUMERIC SCALE"]
        data_type: NUMBER

    filters:
      - name: is_active
        synonyms:
          - "is not deleted"
          - "is active"
          - "current"
        description: "Filter to restrict only currently active records"
        expr: DELETED IS NULL

      - name: is_identity_column
        synonyms:
          - "auto increment columns"
          - "identity columns"
        description: "Filter to show only identity columns"
        expr: IS_IDENTITY = 'YES'

      - name: is_required
        synonyms:
          - "non-nullable"
          - "required fields"
        description: "Filter to show columns that don't allow NULL values"
        expr: IS_NULLABLE = 'NO'

      - name: has_default
        synonyms:
          - "default value exists"
          - "has default value"
        description: "Filter to show columns with default values"
        expr: COLUMN_DEFAULT IS NOT NULL

      - name: large_strings
        synonyms:
          - "long text fields"
          - "large text columns"
        description: "Filter to show string columns with large maximum lengths"
        expr: DATA_TYPE IN ('TEXT', 'VARCHAR', 'CHAR') AND CHARACTER_MAXIMUM_LENGTH > 1000

  - name: DATABASES
    description: 'Account Usage view that displays information about all databases defined in your account.
      Contains details about database creation, ownership, configuration, and lifecycle.
      Has a latency of up to 180 minutes and shows all databases regardless of access privileges.'

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: DATABASES

    primary_key:
      columns:
        - DATABASE_ID
        - DATABASE_NAME

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the database was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: 'Date and time when the database was last modified by:
          - DDL operations
          - DML operations (for tables only)
          - Background metadata maintenance'
        synonyms:  ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the database was dropped
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "DATABASE DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: DATABASE_ID
        expr: DATABASE_ID
        description: Internal/system-generated identifier for the database
        synonyms: ["DATABASE ID", "ID", "IDENTIFIER",  "CATALOG ID"]
        data_type: NUMBER

      - name: DATABASE_NAME
        expr: DATABASE_NAME
        description: Name of the database
        synonyms: ["DATABASE NAME", "NAME", "DB NAME", "CATALOG NAME"]
        data_type: VARCHAR

      - name: DATABASE_OWNER
        expr: DATABASE_OWNER
        description: Name of the role that owns the database
        synonyms: ["OWNER", "OWNER ROLE", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: IS_TRANSIENT
        expr: IS_TRANSIENT
        description: Indicates if the database is transient (no fail-safe period and reduced Time Travel)
        synonyms: ["IS TRANSIENT", "TRANSIENT DATABASE", "TRANSIENT FLAG"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: COMMENT
        expr: COMMENT
        description: User-provided comment or description for the database
        synonyms: ["DATABASE COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

      - name: TYPE
        expr: TYPE
        description: "Specifies the type of database:
          - STANDARD: Normal user-created database
          - APPLICATION: Application object
          - APPLICATION_PACKAGE: Application package
          - IMPORTED DATABASE: Database created from a share"
        synonyms: ["DATABASE TYPE", "DB TYPE", "CATALOG TYPE"]
        sample_values:
          - STANDARD
          - APPLICATION
          - APPLICATION_PACKAGE
          - IMPORTED DATABASE
        data_type: VARCHAR
        is_enum: true

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: 'Type of role that owns the database:
          - ROLE: Standard Snowflake role
          - APPLICATION: Snowflake Native App
          - NULL: Deleted database'
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE", "OWNER TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

    facts:
      - name: RETENTION_TIME
        expr: RETENTION_TIME
        description: Number of days that historical data is retained for Time Travel
        synonyms: ["TIME TRAVEL TIME", "RETENTION PERIOD", "HISTORICAL DATA TIME"]
        data_type: NUMBER
        default_aggregation: sum

    filters:
      - name: is_active
        synonyms:
          - "not deleted"
        description: "Filter to show only non-deleted databases"
        expr: DELETED IS NULL

      - name: is_standard
        synonyms:
          - "standard databases"
          - "normal databases"
        description: "Filter to show only standard user-created databases"
        expr: TYPE = 'STANDARD'

      - name: is_shared
        synonyms:
          - "imported databases"
          - "shared databases"
        description: "Filter to show only databases created from shares"
        expr: TYPE = 'IMPORTED DATABASE'

      - name: has_time_travel
        synonyms:
          - "historical data enabled"
          - "time travel enabled"
        description: "Filter to show databases with Time Travel enabled"
        expr: RETENTION_TIME > 0

  - name: DATA_CLASSIFICATION_LATEST
    description: >
      This view shows the most recent classification result for each classified table in Snowflake.
      Each row corresponds to a different table that has been classified. The RESULT column contains
      a complex JSON structure with classification details for each column in the classified table.

      This model provides dimensions that extract key information from the JSON structure without
      requiring complex JSON parsing functions in your queries.
    synonyms:
      - "data classification"
      - "column classifications"
      - "sensitive data classification"
      - "PII classification"

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: DATA_CLASSIFICATION_LATEST

    primary_key:
      columns:
        - TABLE_ID

    dimensions:
      - name: TABLE_ID
        description: "Internal/system-generated identifier for the table that was classified."
        expr: TABLE_ID
        data_type: NUMBER
        unique: true

      - name: TABLE_NAME
        description: "Name of the table that was classified."
        synonyms:
          - "classified table"
          - "table"
        expr: TABLE_NAME
        data_type: VARCHAR

      - name: SCHEMA_ID
        description: "Internal/system-generated identifier for the schema that contains the table."
        expr: SCHEMA_ID
        data_type: NUMBER

      - name: SCHEMA_NAME
        description: "Name of the schema that contains the table."
        synonyms:
          - "schema"
        expr: SCHEMA_NAME
        data_type: VARCHAR

      - name: DATABASE_ID
        description: "Internal/system-generated identifier for the database that contains the table."
        expr: DATABASE_ID
        data_type: NUMBER

      - name: DATABASE_NAME
        description: "Name of the database that contains the table."
        synonyms:
          - "database"
        expr: DATABASE_NAME
        data_type: VARCHAR

      - name: FULLY_QUALIFIED_NAME
        description: "Fully qualified name of the classified table."
        expr: DATABASE_NAME || '.' || SCHEMA_NAME || '.' || TABLE_NAME
        data_type: VARCHAR

      - name: STATUS
        description: "Classification status. One of the following: CLASSIFIED or REVIEWED."
        expr: STATUS
        data_type: VARCHAR

      - name: TRIGGER_TYPE
        description: "Mode of the classification trigger: MANUAL."
        expr: TRIGGER_TYPE
        data_type: VARCHAR

      - name: RESULT
        description: >
          Latest classification result as a VARIANT data type. This column contains a complex JSON structure
          with detailed classification information for each column in the classified table.

          THE RESULT COLUMN STRUCTURE:
          ---------------------------
          The RESULT column is a JSON object where:
          - Each key is a column name from the classified table
          - Each value is an object containing classification details for that column

          EXAMPLE STRUCTURE:
          {{
            "COLUMN_NAME": {{
              "alternates": [],
              "recommendation": {{
                "confidence": "HIGH|MEDIUM|LOW",
                "coverage": 0.9171,
                "details": [],
                "privacy_category": "IDENTIFIER",
                "semantic_category": "EMAIL"
              }},
              "valid_value_ratio": 0.9171
            }},
            "ANOTHER_COLUMN": {{
              ...
            }}
          }}

          HOW TO ACCESS THIS DATA:
          -----------------------
          1. To extract information for a specific column:
             SELECT GET_PATH(RESULT, 'COLUMN_NAME') as column_classification
             FROM DATA_CLASSIFICATION_LATEST

          2. To extract a specific property for a column:
             SELECT GET_PATH(RESULT, 'COLUMN_NAME:recommendation:semantic_category')::STRING
             FROM DATA_CLASSIFICATION_LATEST

          Note: This is the raw JSON variant column. Advanced JSON parsing with functions like
          LATERAL FLATTEN cannot be used directly as column expressions in the semantic model.
          Instead, these operations need to be performed in subsequent queries.
        expr: RESULT
        data_type: VARIANT

      - name: RESULT_JSON
        description: "JSON string representation of the RESULT column for easier processing."
        expr: TO_JSON(RESULT)
        data_type: VARCHAR

      - name: HAS_PII_DATA
        description: >
          Flag indicating if the table contains any personally identifiable information.
          This is determined by checking if the RESULT column contains any PII classifications.
        expr: CASE WHEN RESULT IS NOT NULL THEN TRUE ELSE FALSE END
        data_type: BOOLEAN

      - name: CLASSIFICATION_QUALITY
        description: >
          Descriptive quality of the classification based on the status.
          Values include 'High Quality', 'Medium Quality', 'Low Quality'.

          - 'High Quality' indicates the classification has been reviewed
          - 'Medium Quality' indicates the classification has been performed but not reviewed
          - 'Low Quality' indicates any other status
        expr: >
          CASE
            WHEN STATUS = 'REVIEWED' THEN 'High Quality'
            WHEN STATUS = 'CLASSIFIED' THEN 'Medium Quality'
            ELSE 'Low Quality'
          END
        data_type: VARCHAR

      - name: FULL_TABLE_PATH
        description: "Fully qualified path to the classified table."
        expr: DATABASE_NAME || '.' || SCHEMA_NAME || '.' || TABLE_NAME
        data_type: VARCHAR

    time_dimensions:
      - name: LAST_CLASSIFIED_ON
        description: "Time when the table was classified."
        synonyms:
          - "classification date"
          - "classification time"
        expr: LAST_CLASSIFIED_ON
        data_type: TIMESTAMP_LTZ

      - name: DAYS_SINCE_CLASSIFICATION
        description: "Number of days since the table was last classified."
        expr: DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP())
        data_type: NUMBER

      - name: CLASSIFICATION_MONTH
        description: "Month when the table was classified."
        expr: DATE_TRUNC('MONTH', LAST_CLASSIFIED_ON)
        data_type: TIMESTAMP_LTZ

      - name: CLASSIFICATION_AGE_CATEGORY
        description: >
          Categorizes tables by how recently they were classified:
          - Recent: Less than 30 days ago
          - Medium: 30-90 days ago
          - Old: More than 90 days ago
        expr: >
          CASE
            WHEN DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) <= 30 THEN 'Recent'
            WHEN DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) <= 90 THEN 'Medium'
            ELSE 'Old'
          END
        data_type: VARCHAR

    filters:
      - name: REVIEWED_TABLES_ONLY
        description: "Filter to include only tables that have been reviewed."
        expr: STATUS = 'REVIEWED'

      - name: RECENTLY_CLASSIFIED
        description: "Filter to tables classified within the last 30 days."
        expr: DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) <= 30

      - name: SPECIFIC_DATABASE
        description: "Filter tables from a specific database."
        expr: DATABASE_NAME = ?

      - name: SPECIFIC_SCHEMA
        description: "Filter tables from a specific schema."
        expr: SCHEMA_NAME = ?

      - name: CLASSIFICATION_NEEDS_REVIEW
        description: "Filter to tables that are classified but not yet reviewed."
        expr: STATUS = 'CLASSIFIED'

      - name: CLASSIFICATION_OUTDATED
        description: "Filter to tables that haven't been classified in over 90 days."
        expr: DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) > 90

  - name: GRANTS_TO_ROLES
    description: This Account Usage view provides information about access control privileges that have been granted to roles.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: GRANTS_TO_ROLES
    primary_key:
      columns:
        - GRANTEE_NAME
        - PRIVILEGE
        - GRANTED_ON
        - NAME
    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Date and time (in the UTC time zone) when the privilege was granted to the role
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: MODIFIED_ON
        expr: MODIFIED_ON
        description: Date and time (in the UTC time zone) when the privilege was last updated
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Date and time (in the UTC time zone) when the privilege was revoked
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: PRIVILEGE
        expr: PRIVILEGE
        description: Name of the privilege or permission that was granted to the role
        synonyms:
          - "privilege"
          - "access"
          - "grants"
          - "access type"
          - "permission"
        sample_values:
          - USAGE
          - SELECT
          - OWNERSHIP
          - MONITOR
          - APPLYBUDGET
          - MODIFY
          - OPERATE
          - CREATE TASK
          - CREATE COMPUTE POOL
          - CREATE TABLE
          - CREATE NETWORK RULE
          - CREATE STREAMLIT
          - CREATE VIEW
          - CREATE STAGE
          - EXECUTE TASK
          - CREATE SECRET
          - CREATE STREAM
          - CREATE ALERT
          - CREATE FILE FORMAT
          - CREATE SERVICE
          - ADD SEARCH OPTIMIZATION
          - CREATE MATERIALIZED VIEW
          - CREATE IMAGE REPOSITORY
          - CREATE PACKAGES POLICY
          - CREATE EVENT TABLE
          - CREATE PROJECTION POLICY
          - CREATE GIT REPOSITORY
          - CREATE SERVICE CLASS
          - CREATE PROCEDURE
          - CREATE NOTEBOOK
          - CREATE AUTHENTICATION POLICY
          - CREATE DYNAMIC TABLE
          - CREATE AGGREGATION POLICY
          - CREATE STORAGE LIFECYCLE POLICY
          - CREATE SEQUENCE
          - CREATE PASSWORD POLICY
          - CREATE EXTERNAL TABLE
          - CREATE ROW ACCESS POLICY
          - CREATE PIPE
          - CREATE DATASET
          - CREATE ICEBERG TABLE
          - CREATE CLASS
          - CREATE SEMANTIC VIEW
          - CREATE TAG
          - CREATE DATA METRIC FUNCTION
          - CREATE MASKING POLICY
          - CREATE RESOURCE GROUP
          - CREATE TEMPORARY TABLE
          - CREATE MODEL MONITOR
          - CREATE SNAPSHOT
          - CREATE SESSION POLICY
          - CREATE FUNCTION
          - CREATE MODEL
          - CREATE CONTACT
          - CREATE PRIVACY POLICY
          - CREATE CORTEX SEARCH SERVICE
          - READ
          - CREATE SCHEMA
          - EXECUTE MANAGED TASK
          - CREATE WAREHOUSE
          - CREATE ARTIFACT REPOSITORY
          - BIND SERVICE ENDPOINT
          - INSERT
          - UPDATE
          - CREATE JOIN POLICY
          - DELETE
          - CREATE DATABASE ROLE
          - REBUILD
          - EVOLVE SCHEMA
          - TRUNCATE
          - REFERENCES
          - CREATE SNOWFLAKE.ML.FORECAST
          - CREATE SNOWFLAKE.CORE.BUDGET
          - VIEW LINEAGE
          - CREATE DATABASE
          - CREATE SNOWFLAKE.ML.ANOMALY_DETECTION
          - CREATE SNOWFLAKE.ZIM_TEST.DOCUMENT_INTELLIGENCE
          - CREATE INTEGRATION
          - WRITE
          - MANAGE RELEASES
        data_type: VARCHAR

      - name: GRANTED_ON
        expr: GRANTED_ON
        description: Type of Snowflake object on which the privilege is granted (e.g., TABLE, DATABASE, VIEW)
        synonyms:
          - "granted on"
          - "object kind"
          - "object type"
          - "resource type"
          - "object domain"
        sample_values:
          - ACCOUNT
          - SCHEMA
          - VIEW
          - DATABASE
          - TABLE
          - DATABASE_ROLE
          - STAGE
          - PROCEDURE
          - FUNCTION
          - SEQUENCE
          - WAREHOUSE
          - SHARE
          - USER
          - ROLE
          - ACCOUNT
          - INTEGRATION
          - FILE FORMAT
          - TASK
          - INSTANCE_ROLE
          - MATERIALIZED VIEW
          - STREAM
          - RESOURCE MONITOR
          - PIPE
          - MANAGED ACCOUNT
          - EXTERNAL TABLE
          - NETWORK POLICY
          - NOTIFICATION SUBSCRIPTION
        data_type: VARCHAR
        is_enum: true

      - name: NAME
        expr: NAME
        description: Fully qualified name of the specific object instance on which the privilege is granted
        synonyms:
          - "name"
          - "object name"
          - "resource name"
        data_type: VARCHAR

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Database name that contains the object or stores the instance of a class
        synonyms:
          - "table catalog"
          - "table database"
          - "catalog"
          - "database"
          - "parent database"
        data_type: VARCHAR

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Schema name that contains the object or stores the instance of a class
        synonyms:
          - "table schema"
          - "schema"
          - "parent schema"
        data_type: VARCHAR

      - name: GRANTED_TO
        expr: GRANTED_TO
        description: Type of role receiving the grant (ROLE, DATABASE_ROLE, INSTANCE_ROLE, APPLICATION_ROLE, or APPLICATION)
        synonyms:
          - "granted to"
          - "role type"
          - "recipient type"
        sample_values:
          - ROLE
          - APPLICATION_ROLE
          - DATABASE_ROLE
          - INSTANCE_ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: GRANTEE_NAME
        expr: GRANTEE_NAME
        description: Name of the role or Snowflake Native App object receiving the privilege grant.
          This identifies the recipient role, not a user.
        synonyms:
          - "GRANTEE NAME"
          - "GRANTEE ROLE"
          - "recipient role"
          - "recipient"
        data_type: VARCHAR

      - name: GRANT_OPTION
        expr: GRANT_OPTION
        description: Indicates whether the recipient role can grant this privilege to other roles (TRUE)
          or not (FALSE) using the WITH GRANT OPTION clause
        synonyms:
          - "GRANT OPTION"
          - "Is Transferable"
          - "can grant"
          - "transferable"
        sample_values:
          - true
          - false
        data_type: BOOLEAN

      - name: GRANTED_BY
        expr: GRANTED_BY
        description: Role that authorized the privilege grant (grantor). Empty if privilege is granted by
          the SNOWFLAKE system role. For grants made with MANAGE GRANTS privilege, shows the
          object owner rather than the role with MANAGE GRANTS.
        synonyms:
          - "GRANTED BY"
          - "grantor"
          - "authorizing role"
        data_type: VARCHAR

      - name: GRANTED_BY_ROLE_TYPE
        expr: GRANTED_BY_ROLE_TYPE
        description: Type of role that granted the privilege (APPLICATION, ROLE or DATABASE_ROLE)
        synonyms:
          - "GRANTED BY ROLE TYPE"
          - "grantor role type"
          - "grantor type"
        sample_values:
          - ROLE
          - APPLICATION
          - DATABASE_ROLE
        data_type: VARCHAR
        is_enum: true

      - name: OBJECT_INSTANCE
        expr: OBJECT_INSTANCE
        description: Fully-qualified name of the object containing the instance role for a class,
          formatted as database.schema.class
        synonyms:
          - "OBJECT INSTANCE"
          - "instance path"
          - "qualified name"
        data_type: VARCHAR

    filters:
      - name: active_grants
        description: "Show only currently active grants that haven't been revoked"
        expr: DELETED_ON IS NULL

      - name: system_grants
        description: "Show only grants made by the SNOWFLAKE system role"
        expr: GRANTED_BY IS NULL

  - name: GRANTS_TO_USERS
    description: This Account Usage view tracks the roles that have been granted to users, including
      both current grants, historical grants as well as revoked grants. The view shows one row per unique
      role-user grant combination, with DELETED_ON indicating if the grant is currently active.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: GRANTS_TO_USERS
    primary_key:
      columns:
        - ROLE
        - GRANTEE_NAME
        - CREATED_ON
    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Time and date (in UTC) when the role was initially granted to the user.
          Each unique grant creates a new timestamp.
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Time and date (in UTC) when the role was revoked from the user.
          NULL indicates an active grant. When a role is revoked and granted again,
          a new row is created with a new CREATED_ON timestamp.
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: ROLE
        expr: ROLE
        description: The name or identifier of the role that was granted to the user
        synonyms:
          - "ROLE"
          - "granted role"
          - "assigned role"
          - "role name"
        data_type: VARCHAR

      - name: GRANTEE_NAME
        expr: GRANTEE_NAME
        description: The username or identifier of the user receiving the role grant
        synonyms:
          - "GRANTEE NAME"
          - "GRANTEE"
          - "user"
          - "user name"
          - "recipient"
          - "recipient name"
        data_type: VARCHAR

      - name: GRANTED_BY
        expr: GRANTED_BY
        description: The role that executed the GRANT command to assign the role to the user
        synonyms:
          - "GRANTED BY"
          - "granting role"
          - "authorizing role"
        data_type: VARCHAR

    filters:
      - name: active_grants
        description: "Show only currently active role grants that haven't been revoked"
        expr: DELETED_ON IS NULL

      - name: revoked_grants
        description: "Show only revoked role grants (deleted ones)"
        expr: DELETED_ON IS NOT NULL

      - name: historical_grants
        description: "Show only previously revoked role grants"
        expr: DELETED_ON IS NOT NULL

  - name: OBJECT_DEPENDENCIES
    description: 'Object Dependencies. It tracks when one object (the referencing object)
      references another object (the referenced object) without materializing or copying data. For example, when creating
      a view from a table, the view depends on the table and this dependency is recorded. The view has a latency of up to
      3 hours and was backfilled with historical data from January 22, 2022.

      Usage information:
      - Dependencies are tracked for Snowflake objects only, not external objects like S3 buckets
      - Data movement operations (CTAS, INSERT, MERGE) do not create dependencies
      - Session parameters in object definitions may cause inaccurate dependency tracking
      - Dependencies through function calls or nested objects may not be captured
      - BY_NAME_AND_ID dependencies may not be recorded after CREATE OR REPLACE operations

      Contains detailed information about object dependencies in Snowflake, tracking both the referenced (source)
      and referencing (dependent) objects. Each row represents a single dependency relationship.'

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: OBJECT_DEPENDENCIES

    dimensions:
      - name: REFERENCED_DATABASE
        description: The parent database containing the source object being referenced
        expr: REFERENCED_DATABASE
        data_type: VARCHAR
        synonyms: ["SOURCE DATABASE", "REFERENCED DB"]

      - name: REFERENCED_SCHEMA
        description: The parent schema containing the source object being referenced
        expr: REFERENCED_SCHEMA
        data_type: VARCHAR
        synonyms: ["SOURCE SCHEMA", "REFERENCED SCHEMA"]

      - name: REFERENCED_OBJECT_NAME
        description: The name of the source object being referenced
        expr: REFERENCED_OBJECT_NAME
        data_type: VARCHAR
        synonyms: ["SOURCE OBJECT", "REFERENCED OBJECT"]

      - name: REFERENCED_OBJECT_ID
        description: 'The unique identifier of the referenced object. Note: This will be NULL for shared objects in consumer accounts
          to prevent discovery of source object IDs.'
        expr: REFERENCED_OBJECT_ID
        data_type: NUMBER
        synonyms: ["SOURCE OBJECT ID"]

      - name: REFERENCED_OBJECT_DOMAIN
        description:     The type/domain of the referenced object (e.g. TABLE, VIEW, etc.). For shared objects in consumer accounts,
          this will always show as TABLE for table-like objects.
        expr: REFERENCED_OBJECT_DOMAIN
        data_type: VARCHAR
        synonyms: ["SOURCE OBJECT TYPE"]
        sample_values:
          - TABLE
          - VIEW
          - EXTERNAL TABLE
          - MATERIALIZED VIEW
          - TASK
          - STAGE
          - STREAM
          - FUNCTION
          - INTEGRATION

      - name: REFERENCING_DATABASE
        description: The parent database containing the dependent object that references the source
        expr: REFERENCING_DATABASE
        data_type: VARCHAR
        synonyms: ["DEPENDENT DATABASE"]

      - name: REFERENCING_SCHEMA
        description: The parent schema containing the dependent object that references the source
        expr: REFERENCING_SCHEMA
        data_type: VARCHAR
        synonyms: ["DEPENDENT SCHEMA"]

      - name: REFERENCING_OBJECT_NAME
        description: The name of the dependent object that references the source
        expr: REFERENCING_OBJECT_NAME
        data_type: VARCHAR
        synonyms: ["DEPENDENT OBJECT"]

      - name: REFERENCING_OBJECT_ID
        description: The unique identifier of the dependent object
        expr: REFERENCING_OBJECT_ID
        data_type: NUMBER
        synonyms: ["DEPENDENT OBJECT ID"]

      - name: REFERENCING_OBJECT_DOMAIN
        description: The type/domain of the dependent object (e.g. VIEW, MATERIALIZED VIEW, etc.)
        expr: REFERENCING_OBJECT_DOMAIN
        data_type: VARCHAR
        synonyms: ["DEPENDENT OBJECT TYPE"]
        sample_values:
          - VIEW
          - EXTERNAL TABLE
          - TASK
          - FUNCTION
          - STREAM
          - STAGE
          - MATERIALIZED VIEW

      - name: DEPENDENCY_TYPE
        description: 'The type of dependency relationship:
          - BY_NAME: Object references another by name (e.g. view referencing table)
          - BY_ID: Object stores ID of another object (e.g. stage referencing storage integration)
          - BY_NAME_AND_ID: Object depends on both name and ID (e.g. materialized views)'
        expr: DEPENDENCY_TYPE
        data_type: VARCHAR
        synonyms: ["REFERENCE TYPE"]
        sample_values:
          - BY_NAME
          - BY_ID
          - BY_NAME_AND_ID

    primary_key:
      columns:
        - REFERENCED_DATABASE
        - REFERENCED_SCHEMA
        - REFERENCED_OBJECT_NAME
        - REFERENCED_OBJECT_ID
        - REFERENCING_DATABASE
        - REFERENCING_SCHEMA
        - REFERENCING_OBJECT_NAME
        - REFERENCING_OBJECT_ID

  - name: POLICY_REFERENCES
    description: This Account Usage view lists policy objects and their references in your account.
      It supports aggregation, masking, projection, and row access policies.
      The view has a latency of up to 120 minutes and only shows objects accessible to the current role.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: POLICY_REFERENCES
    primary_key:
      columns:
        - REF_ENTITY_NAME
        - REF_DATABASE_NAME
        - REF_SCHEMA_NAME
        - REF_COLUMN_NAME
        - POLICY_ID
    dimensions:
      - name: POLICY_DB
        expr: POLICY_DB
        description: The database in which the policy is set
        synonyms: ["POLICY DATABASE", "POLICY DB", "POLICY PARENT DATABASE", "POLICY PARENT CATALOG", "POLICY DATABASE NAME"]
        data_type: VARCHAR

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: The schema in which the policy is set
        synonyms: ["POLICY SCHEMA", "POLICY PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated identifier for the policy
        synonyms: ["POLICY IDENTIFIER", "POLICY ID"]
        data_type: NUMBER

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: The name of the policy as defined in Snowflake
        synonyms: ["POLICY NAME", "POLICY"]
        data_type: VARCHAR

      - name: POLICY_KIND
        expr: POLICY_KIND
        description: The type of policy being applied
        synonyms: ["POLICY TYPE", "POLICY CATEGORY"]
        sample_values:
          - AGGREGATION_POLICY
          - PROJECTION_POLICY
          - MASKING_POLICY
          - ROW_ACCESS_POLICY
        data_type: VARCHAR(17)
        is_enum: true

      - name: REF_DATABASE_NAME
        expr: REF_DATABASE_NAME
        description: The name of the database containing the referenced object
        synonyms: ["REFERENCED DATABASE", "REFERENCED OBJECT DATABASE", "REFERENCE OBJECT CATALOG", "REFERENCE OBJECT DB", "REFERENCE OBJECT PARENT DB", "REFERENCED DATABASE NAME"]
        data_type: VARCHAR

      - name: REF_SCHEMA_NAME
        expr: REF_SCHEMA_NAME
        description: The name of the schema containing the referenced object
        synonyms: ["REFERENCED SCHEMA", "REFERENCED OBJECT SCHEMA", "REFERENCED OBJECT PARENT SCHEMA", "REFERENCED SCHEMA NAME"]
        data_type: VARCHAR

      - name: REF_ENTITY_NAME
        expr: REF_ENTITY_NAME
        description: The name of the object (table, view, external table) on which the policy is set
        synonyms: ["Referenced Entity", "Target Object"]
        data_type: VARCHAR

      - name: REF_ENTITY_DOMAIN
        expr: REF_ENTITY_DOMAIN
        description: The type of object on which the policy is set
        synonyms: ["ENTITY TYPE", "OBJECT TYPE", "OBJECT DOMAIN"]
        sample_values:
          - VIEW
          - TABLE
          - TAG
          - EXTERNAL TABLE
          - ICEBERG TABLE
          - MATERIALIZED VIEW
          - DYNAMIC TABLE
        data_type: VARCHAR
        is_enum: true

      - name: REF_COLUMN_NAME
        expr: REF_COLUMN_NAME
        description: The column name on which the policy is set (for column-level policies)
        synonyms: ["Referenced Column", "Target Column"]
        data_type: VARCHAR

      - name: REF_ARG_COLUMN_NAMES
        expr: REF_ARG_COLUMN_NAMES
        description: Array of column names used as arguments in the policy, returns NULL for Column-level Security masking policies
        synonyms: ["REFERENCED ARGUMENT COLUMNS", "REFERENCED ARGUMENT COLUMN NAMES"]
        data_type: VARCHAR

      - name: TAG_DATABASE
        expr: TAG_DATABASE
        description: The database containing the tag with an assigned policy (NULL if no tag policy)
        synonyms: ["TAG DATABASE", "TAG DB", "ATTACHED TAG PARENT DB", "ATTACHED TAG PARENT DATABASE", "TAG PARENT DATABASE"]
        data_type: VARCHAR

      - name: TAG_SCHEMA
        expr: TAG_SCHEMA
        description: The schema containing the tag with an assigned policy (NULL if no tag policy)
        synonyms: ["TAG SCHEMA", "ATTACHED TAG PARENT SCHEMA", "TAG PARENT SCHEMA"]
        data_type: VARCHAR

      - name: TAG_NAME
        expr: TAG_NAME
        description: The name of the tag with an assigned policy (NULL if no tag policy)
        synonyms: ["TAG NAME", "POLICY TAG", "POLICY TAG NAME"]
        data_type: VARCHAR

      - name: POLICY_STATUS
        expr: POLICY_STATUS
        description: 'Current status of the policy application:
          ACTIVE - Column has single policy via tag
          MULTIPLE_MASKING_POLICY_ASSIGNED_TO_THE_COLUMN - Multiple masking policies on same column
          COLUMN_IS_MISSING_FOR_SECONDARY_ARG - Conditional masking policy missing required column
          COLUMN_DATATYPE_MISMATCH_FOR_SECONDARY_ARG - Conditional masking policy column type mismatch'
        synonyms: ["TAG-BASED POLICY STATE", "TAG BASED POLICY STATUS"]
        data_type: VARCHAR
        is_enum: true
        sample_values:
          - ACTIVE
          - MULTIPLE_MASKING_POLICY_ASSIGNED_TO_THE_COLUMN
          - COLUMN_IS_MISSING_FOR_SECONDARY_ARG
          - COLUMN_DATATYPE_MISMATCH_FOR_SECONDARY_ARG

    filters:
      - name: active_policies
        description: Show only active policies
        expr: POLICY_STATUS = 'ACTIVE'

      - name: masking_policies
        description: Show only masking policies
        expr: POLICY_KIND = 'MASKING_POLICY'

      - name: tagged_policies
        description: Show only policies applied via tags
        expr: TAG_NAME IS NOT NULL

  - name: QUERY_HISTORY
    description: "Contains detailed information about query execution history including user types, reader accounts, and service execution details. Data available for last 365 days with up to 45 minute latency."

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: QUERY_HISTORY

    primary_key:
      columns:
        - QUERY_ID

    time_dimensions:
      - name: START_TIME
        expr: START_TIME
        description: "Query execution start timestamp"
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: END_TIME
        expr: END_TIME
        description: "Query execution end timestamp"
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: QUERY_ID
        expr: QUERY_ID
        description: "Unique identifier for the query execution"
        synonyms: ["QUERY ID"]
        data_type: VARCHAR

      - name: QUERY_TEXT
        expr: QUERY_TEXT
        description: "Full SQL text of the query (truncated at 100K characters)"
        synonyms: ["QUERY TEXT", "SQL"]
        data_type: VARCHAR

      - name: DATABASE_ID
        expr: DATABASE_ID
        description: "Internal identifier of the database context"
        synonyms: ["DATABASE ID"]
        data_type: NUMBER

      - name: DATABASE_NAME
        expr: DATABASE_NAME
        description: "Name of the database context"
        synonyms: ["DATABASE NAME"]
        data_type: VARCHAR

      - name: SCHEMA_ID
        expr: SCHEMA_ID
        description: "Internal identifier of the schema context"
        synonyms: ["SCHEMA ID"]
        data_type: NUMBER

      - name: SCHEMA_NAME
        expr: SCHEMA_NAME
        description: "Name of the schema context"
        synonyms: ["SCHEMA NAME"]
        data_type: VARCHAR

      - name: QUERY_TYPE
        expr: QUERY_TYPE
        description: "Type of SQL statement executed"
        synonyms: ["QUERY TYPE"]
        sample_values:
          - SELECT
          - USE
          - INSERT
          - SHOW
          - CALL
          - DESCRIBE
          - PUT_FILES
          - COPY
          - ALTER_SESSION
          - COMMIT
          - ROLLBACK
          - EXTERNAL_TABLE_REFRESH
          - UPDATE
          - REMOVE_FILES
          - CREATE
          - MERGE
          - CREATE_TABLE_AS_SELECT
          - GRANT
          - LIST_FILES
          - REFRESH_DYNAMIC_TABLE_AT_REFRESH_VERSION
          - CREATE_TABLE
          - SET
          - BEGIN_TRANSACTION
          - DROP
          - GET_FILES
          - DELETE
          - UNKNOWN
          - RECLUSTER
          - CREATE_VIEW
          - ALTER
          - CREATE_SESSION_POLICY
          - ALTER_SET_TAG
          - ALTER_TABLE_MODIFY_COLUMN
          - COMPACT_KEY_VALUE_TABLE
          - TRUNCATE_TABLE
          - EXECUTE_TASK
          - CREATE_TASK
          - REFRESH_REPLICATION_GROUP
          - ALTER_TABLE
          - EXPLAIN
          - MULTI_STATEMENT
          - FILE_DEFRAGMENTATION
          - DROP_TASK
          - DESCRIBE_QUERY
          - UNLOAD
          - REFRESH_GLOBAL_DATABASE
          - EXECUTE_STREAMLIT
          - RENAME_TABLE
          - EXECUTE_ON
          - ALTER_AUTO_RECLUSTER
          - PULL_MATERIALIZED_VIEW
          - MIXED_FILE_MIGRATION
          - PULL_SEARCH_INDEX
          - ALTER_TABLE_DMLPATCH
          - DIRECTORY_TABLE_REFRESH
          - ALTER_TABLE_MANAGE_CONTACT
          - REVOKE
          - ALTER_PIPE
          - ALTER_VIEW_MODIFY_COLUMN_MANAGE_POLICY
          - ALTER_TABLE_ADD_COLUMN
          - CREATE_STREAM
          - CREATE_MASKING_POLICY
          - CREATE_SEQUENCE
          - CREATE_EXTERNAL_TABLE
          - ALTER_TABLE_MANAGE_ROW_ACCESS_POLICY
          - COPY_FILES
          - ALTER_DYNAMIC_TABLE_LIFECYCLE
          - EXECUTE_JOB_SERVICE
          - DROP_SERVICE
          - ALTER_USER
          - COMPACT_MATERIALIZED_VIEW
          - INGEST
          - ALTER_WAREHOUSE_RESUME
          - ALTER_SECRET
          - ALTER_POLICY
          - CASCADE_MANUAL_REFRESH_DYNAMIC_TABLE
          - CREATE_CONSTRAINT
          - COMPACT_SEARCH_INDEX
          - ALTER_TABLE_MANAGE_STORAGE_LIFECYCLE_POLICY
          - ALTER_TABLE_DROP_COLUMN
          - RENAME_COLUMN
          - ALTER_SERVICE_SUSPEND
          - CREATE_ROW_ACCESS_POLICY
          - ALTER_SERVICE_RESUME
          - CREATE_IMAGE_REPOSITORY
          - ALTER_NETWORK_POLICY
          - RENAME
          - CREATE_SERVICE
          - DROP_ROW_ACCESS_POLICY
          - EXECUTE_ALERT
          - ALTER_SERVICE_UPGRADE_FROM_SPEC
          - DROP_STREAM
          - CREATE_STORAGE_LIFECYCLE_POLICY
          - RENAME_VIEW
          - CREATE_ICEBERG_TABLE
          - CREATE_SECRET
          - ALTER_VIEW_MODIFY_SECURITY
          - CREATE_ROLE
          - ALTER_VIEW_MODIFY_COLUMN
          - DROP_COMPUTE_POOL
          - ALTER_COMPUTE_POOL_STOP_ALL
          - CREATE_COMPUTE_POOL
          - UNSET
          - ALTER_ACCOUNT
          - RESTORE
          - CREATE_USER
          - ALTER_UNSET_TAG
          - RENAME_ROLE
          - ALTER_SERVICE_SET_PROPERTIES
          - DROP_CONSTRAINT
          - ALTER_TABLE_MANAGE_AGGREGATION_POLICY
          - RENAME_FILE_FORMAT
          - RENAME_STAGE
          - ALTER_WAREHOUSE_SUSPEND
          - DROP_STORAGE_LIFECYCLE_POLICY
        data_type: VARCHAR

      - name: SESSION_ID
        expr: SESSION_ID
        description: "Unique identifier for the session"
        synonyms: ["SESSION ID"]
        data_type: NUMBER

      - name: USER_NAME
        expr: USER_NAME
        description: "Name of the user executing the query"
        synonyms: ["USER NAME"]
        data_type: VARCHAR

      - name: ROLE_NAME
        expr: ROLE_NAME
        description: "Active role when query was executed"
        synonyms: ["ROLE NAME"]
        data_type: VARCHAR

      - name: WAREHOUSE_ID
        expr: WAREHOUSE_ID
        description: "Internal identifier of the warehouse used"
        synonyms: ["WAREHOUSE ID"]
        data_type: NUMBER

      - name: WAREHOUSE_NAME
        expr: WAREHOUSE_NAME
        description: "Name of the warehouse used"
        synonyms: ["WAREHOUSE NAME"]
        data_type: VARCHAR

      - name: WAREHOUSE_SIZE
        expr: WAREHOUSE_SIZE
        description: "Size of the warehouse when query executed"
        synonyms: ["WAREHOUSE SIZE"]
        sample_values:
          - X-Small
          - Small
          - Medium
          - Large
          - X-Large
          - 2X-Large
          - 3X-Large
          - 4X-Large
          - 5X-Large
          - ADAPTIVE
        data_type: VARCHAR
        is_enum: true

      - name: WAREHOUSE_TYPE
        expr: WAREHOUSE_TYPE
        description: "Type of warehouse used"
        synonyms: ["WAREHOUSE TYPE"]
        sample_values:
          - STANDARD
          - SNOWPARK-OPTIMIZED
        data_type: VARCHAR
        is_enum: true

      - name: USER_TYPE
        expr: USER_TYPE
        description: "Type of user executing the query"
        synonyms: ["USER TYPE"]
        sample_values:
          - SNOWFLAKE_SERVICE
        is_enum: true
        data_type: VARCHAR

      - name: USER_DATABASE_NAME
        expr: USER_DATABASE_NAME
        description: "Database name for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER DATABASE NAME"]
        data_type: VARCHAR

      - name: USER_DATABASE_ID
        expr: USER_DATABASE_ID
        description: "Internal database ID for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER DATABASE ID"]
        data_type: VARCHAR

      - name: USER_SCHEMA_NAME
        expr: USER_SCHEMA_NAME
        description: "Schema name for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER SCHEMA NAME"]
        data_type: VARCHAR

      - name: USER_SCHEMA_ID
        expr: USER_SCHEMA_ID
        description: "Internal schema ID for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER SCHEMA ID"]
        data_type: VARCHAR
      - name: QUERY_TAG
        expr: QUERY_TAG
        description: "User-specified query tag from session parameters"
        synonyms: ["QUERY TAG"]
        data_type: VARCHAR

      - name: EXECUTION_STATUS
        expr: EXECUTION_STATUS
        description: "Final execution status of the query"
        synonyms: ["EXECUTION STATUS"]
        sample_values:
          - SUCCESS
          - FAIL
          - INCIDENT
        data_type: VARCHAR

      - name: ERROR_CODE
        expr: ERROR_CODE
        description: "Error code if query failed"
        synonyms: ["ERROR CODE"]
        data_type: VARCHAR

      - name: ERROR_MESSAGE
        expr: ERROR_MESSAGE
        description: "Detailed error message if query failed"
        synonyms: ["ERROR MESSAGE"]
        data_type: VARCHAR

    facts:
      - name: TOTAL_ELAPSED_TIME
        expr: TOTAL_ELAPSED_TIME
        description: "Total time taken to execute the query in milliseconds"
        synonyms: ["ELAPSED TIME"]
        data_type: NUMBER
        default_aggregation: sum

      - name: BYTES_SCANNED
        expr: BYTES_SCANNED
        description: "Amount of data scanned by the query in bytes"
        synonyms: ["DATA SCANNED"]
        data_type: NUMBER
        default_aggregation: sum

      - name: PERCENTAGE_SCANNED_FROM_CACHE
        expr: PERCENTAGE_SCANNED_FROM_CACHE
        description: "Percentage of data read from cache (0.0 to 1.0)"
        data_type: FLOAT
        default_aggregation: avg

      - name: COMPILATION_TIME
        expr: COMPILATION_TIME
        description: "Time spent compiling the query in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: EXECUTION_TIME
        expr: EXECUTION_TIME
        description: "Time spent executing the query in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUEUED_PROVISIONING_TIME
        expr: QUEUED_PROVISIONING_TIME
        description: "Time spent waiting for warehouse provisioning in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUEUED_REPAIR_TIME
        expr: QUEUED_REPAIR_TIME
        description: "Time spent waiting for warehouse repair in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUEUED_OVERLOAD_TIME
        expr: QUEUED_OVERLOAD_TIME
        description: "Time spent waiting due to warehouse overload in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: TRANSACTION_BLOCKED_TIME
        expr: TRANSACTION_BLOCKED_TIME
        description: "Time spent blocked by concurrent DML in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_PRODUCED
        expr: ROWS_PRODUCED
        description: "Number of rows produced by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_INSERTED
        expr: ROWS_INSERTED
        description: "Number of rows inserted by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_UPDATED
        expr: ROWS_UPDATED
        description: "Number of rows updated by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_DELETED
        expr: ROWS_DELETED
        description: "Number of rows deleted by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: CREDITS_USED_CLOUD_SERVICES
        expr: CREDITS_USED_CLOUD_SERVICES
        description: "Number of credits used for cloud services"
        data_type: FLOAT
        default_aggregation: sum

      - name: QUERY_LOAD_PERCENT
        expr: QUERY_LOAD_PERCENT
        description: "Percentage of warehouse resources used by the query"
        data_type: NUMBER
        default_aggregation: avg

      - name: BYTES_WRITTEN_TO_RESULT
        expr: BYTES_WRITTEN_TO_RESULT
        description: "Size of the query result in bytes"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUERY_RETRY_TIME
        expr: QUERY_RETRY_TIME
        description: "Time spent on query retries in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: FAULT_HANDLING_TIME
        expr: FAULT_HANDLING_TIME
        description: "Time spent handling non-actionable errors in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

  - name: ROLES
    description: Account Usage view that displays information about all roles defined in the account.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: ROLES

    primary_key:
      columns:
        - NAME


    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Date and time when the role was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Date and time  when the role was dropped
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: ROLE_ID
        expr: ROLE_ID
        description: Internal/system-generated identifier for the role
        synonyms: ["ROLE ID", "IDENTIFIER", "ID"]
        data_type: NUMBER

      - name: NAME
        expr: NAME
        description: Name of the role
        synonyms: ["ROLE NAME", "ROLE"]
        data_type: VARCHAR

      - name: OWNER
        expr: OWNER
        description: Role with the OWNERSHIP privilege on the object
        synonyms: ["OWNER ROLE", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: ROLE_TYPE
        expr: ROLE_TYPE
        description: Type of the role
        synonyms: ["ROLE TYPE"]
        sample_values:
          - ROLE
          - DATABASE_ROLE
          - INSTANCE_ROLE
          - APPLICATION_ROLE
        data_type: TEXT
        is_enum: true

      - name: ROLE_DATABASE_NAME
        expr: ROLE_DATABASE_NAME
        description: Name of the database that contains the database role if the role is a database role
        synonyms: ["ROLE DATABASE NAME", "DATABASE ROLE PARENT DATABASE NAME", "DATABASE ROLE CATALOG NAME"]
        data_type: TEXT

      - name: ROLE_INSTANCE_ID
        expr: ROLE_INSTANCE_ID
        description: Internal/system-generated identifier for the class instance that the role belongs to
        synonyms: ["ROLE INSTANCE ID", "ROLE INSTANCE IDENTIFIER"]
        data_type: NUMBER

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: 'Type of role that owns the role:
          - ROLE: Standard Snowflake role
          - APPLICATION: Snowflake Native App/Application
          - NULL: Deleted role'
        synonyms: ["OWNER ROLE TYPE", "OWNER TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: COMMENT
        expr: COMMENT
        description: User-provided comment or description for the role
        synonyms: ["ROLE COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

    filters:
      - name: active_roles
        description: Filter for non-deleted roles
        expr: DELETED_ON IS NULL

      - name: database_roles
        description: Filter for database roles
        expr: ROLE_TYPE = 'DATABASE_ROLE'

      - name: instance_roles
        description: Filter for instance roles
        expr: ROLE_TYPE = 'INSTANCE_ROLE'

  - name: SCHEMATA
    description: Account Usage view that displays information about all schemas in the account,
      except the ACCOUNT_USAGE, READER_ACCOUNT_USAGE, and INFORMATION_SCHEMA schemas.

    synonyms:
        - SCHEMA
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: SCHEMATA
    primary_key:
      columns:
        - SCHEMA_ID
        - SCHEMA_NAME
        - CATALOG_NAME
    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the schema was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the object was last altered by a DML, DDL, or background metadata operation
        synonyms:  ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the schema was dropped
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "SCHEMA DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: SCHEMA_ID
        expr: SCHEMA_ID
        description: Internal/system-generated identifier for the schema
        synonyms: ["SCHEMA ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: SCHEMA_NAME
        expr: SCHEMA_NAME
        description: Name of the schema
        synonyms: ["SCHEMA NAME", "NAME"]
        data_type: VARCHAR

      - name: CATALOG_ID
        expr: CATALOG_ID
        description: Internal/system-generated identifier for the database of the schema
        synonyms: ["CATALOG ID", "DATABASE ID", "PARENT DATABASE ID", "PARENT CATALOG ID"]
        data_type: NUMBER

      - name: CATALOG_NAME
        expr: CATALOG_NAME
        description: Database that the schema belongs to
        synonyms: ["CATALOG NAME", "DATABASE NAME", "PARENT DATABASE NAME", "PARENT CATALOG NAME"]
        data_type: VARCHAR

      - name: SCHEMA_OWNER
        expr: SCHEMA_OWNER
        description: Name of the role that owns the schema
        synonyms: ["SCHEMA OWNER", "OWNER", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: IS_TRANSIENT
        expr: IS_TRANSIENT
        description: Whether the schema is transient
        synonyms: ["IS TRANSIENT", "TRANSIENT DATABASE", "TRANSIENT FLAG"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: IS_MANAGED_ACCESS
        expr: IS_MANAGED_ACCESS
        description: Whether the schema is a managed access schema
        synonyms: ["IS MANAGED ACCESS", "MANAGED ACCESS SCHEMA"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: SCHEMA_TYPE
        expr: SCHEMA_TYPE
        description: Type of schema
        synonyms: ["SCHEMA TYPE", "SCHEMA KIND"]
        sample_values:
          - STANDARD
          - VERSIONED
        data_type: VARCHAR
        is_enum: true

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: The type of role that owns the object (ROLE for regular roles, APPLICATION for Snowflake Native Apps)
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: VERSION_NAME
        expr: VERSION_NAME
        description: Name of the schema if it is a versioned schema, NULL otherwise
        synonyms: ["VERSION NAME", "VERSION"]
        data_type: VARCHAR

      - name: VERSIONED_SCHEMA_ID
        expr: VERSIONED_SCHEMA_ID
        description: Internal/system-generated identifier if the schema is a versioned schema, NULL otherwise
        synonyms: ["VERSIONED SCHEMA ID", "VERSIONED SCHEMA IDENTIFIER", "VERSIONED IDENTIFIER"]
        data_type: NUMBER

      - name: COMMENT
        expr: COMMENT
        description: Comment for the schema
        synonyms: ["SCHEMA COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

    facts:
      - name: RETENTION_TIME
        expr: RETENTION_TIME
        description: Number of days that historical data is retained for Time Travel
        synonyms: ["TIME TRAVEL TIME", "RETENTION PERIOD", "HISTORICAL DATA TIME"]
        data_type: NUMBER
        default_aggregation: sum

    filters:
      - name: standard_schemas
        description: Filter for standard (non-versioned) schemas
        expr: SCHEMA_TYPE = 'STANDARD'

      - name: versioned_schemas
        description: Filter for versioned schemas
        expr: SCHEMA_TYPE = 'VERSIONED'

      - name: non_transient_schemas
        description: Filter for non-transient schemas
        expr: IS_TRANSIENT = 'NO'

      - name: is_active
        synonyms:
          - "not deleted"
        description: "Filter to show only non-deleted databases"
        expr: DELETED IS NULL

      - name: has_time_travel
        synonyms:
          - "historical data enabled"
          - "time travel enabled"
        description: "Filter to show databases with Time Travel enabled"
        expr: RETENTION_TIME > 0

  - name: TABLES
    description: Account Usage view that displays information about all tables and views in the account.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: TABLES

    primary_key:
      columns:
        - TABLE_ID
        - TABLE_NAME
        - TABLE_SCHEMA
        - TABLE_CATALOG

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the table was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the object was last altered by a DML, DDL, or background metadata operation
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_DDL
        expr: LAST_DDL
        description: Timestamp of the last DDL operation performed on the table or view
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the table was dropped
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "TABLE DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TABLE_ID
        expr: TABLE_ID
        description: Internal, Snowflake-generated identifier for the table
        synonyms: ["VIEW ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: TABLE_NAME
        expr: TABLE_NAME
        description: Name of the table
        synonyms: ["TABLE NAME", "NAME"]
        data_type: VARCHAR

      - name: TABLE_SCHEMA_ID
        expr: TABLE_SCHEMA_ID
        description: Internal, Snowflake-generated identifier of the schema for the table
        synonyms: ["TABLE SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Schema that the table belongs to
        synonyms: ["TABLE SCHEMA", "SCHEMA NAME", "PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: TABLE_CATALOG_ID
        expr: TABLE_CATALOG_ID
        description: Internal, Snowflake-generated identifier of the database for the table
        synonyms: ["TABLE CATALOG ID", "DATABASE ID", "DATABASE IDENTIFIER"]
        data_type: NUMBER

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Database that the table belongs to
        synonyms: ["TABLE CATALOG", "DATABASE NAME", "CATALOG NAME", "PARENT DATABASE NAME"]
        data_type: VARCHAR

      - name: TABLE_OWNER
        expr: TABLE_OWNER
        description: Name of the role that owns the table
        synonyms: ["TABLE OWNER", "OWNER", "OWNING ROLE"]
        data_type: VARCHAR

      - name: TABLE_TYPE
        expr: TABLE_TYPE
        description: Indicates the table type
        synonyms: ["TABLE TYPE", "TABLE KIND"]
        sample_values:
          - BASE TABLE
          - TEMPORARY TABLE
          - EXTERNAL TABLE
          - EVENT TABLE
          - VIEW
          - MATERIALIZED VIEW
        data_type: VARCHAR
        is_enum: true

      - name: IS_TRANSIENT
        expr: IS_TRANSIENT
        description: Indicates whether the table is transient
        synonyms: ["IS TRANSIENT"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: CLUSTERING_KEY
        expr: CLUSTERING_KEY
        description: Column(s) and/or expression(s) that comprise the clustering key for the table
        synonyms: ["CLUSTERING KEY"]
        data_type: VARCHAR

      - name: LAST_DDL_BY
        expr: LAST_DDL_BY
        description: The current username for the user who executed the last DDL operation
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: The type of role that owns the object
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE"]
        data_type: VARCHAR
        sample_values:
          - ROLE
          - APPLICATION

      - name: INSTANCE_ID
        expr: INSTANCE_ID
        description: Internal/system-generated identifier for the instance
        data_type: NUMBER

      - name: IS_ICEBERG
        expr: IS_ICEBERG
        description: Indicates whether the table is an Iceberg table
        data_type: VARCHAR
        is_enum: true
        sample_values: ["YES", "NO"]

      - name: IS_DYNAMIC
        expr: IS_DYNAMIC
        description: Indicates whether the table is a dynamic table
        data_type: VARCHAR
        is_enum: true
        sample_values: ["YES", "NO"]

      - name: IS_HYBRID
        expr: IS_HYBRID
        description: Indicates whether the table is a hybrid table
        data_type: VARCHAR
        is_enum: true
        sample_values: ["YES", "NO"]

      - name: AUTO_CLUSTERING_ON
        expr: AUTO_CLUSTERING_ON
        description: Status of Automatic Clustering for a table
        synonyms: ["AUTO CLUSTERING ON"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: COMMENT
        expr: COMMENT
        description: Comment for the table
        synonyms: ["COMMENT"]
        data_type: VARCHAR

    facts:
      - name: ROW_COUNT
        expr: ROW_COUNT
        description: Number of rows in the table
        synonyms: ["ROW COUNT"]
        data_type: NUMBER
        default_aggregation: sum

      - name: BYTES
        expr: BYTES
        description: Number of bytes accessed by a scan of the table
        synonyms: ["BYTES"]
        data_type: NUMBER
        default_aggregation: sum

      - name: RETENTION_TIME
        expr: RETENTION_TIME
        description: Number of days that historical data is retained for Time Travel
        synonyms: ["RETENTION TIME"]
        data_type: NUMBER
        default_aggregation: sum

    filters:
      - name: active_views_only
        description: Show only non-deleted tables
        expr: DELETED IS NULL

      - name: iceberg_tables_only
        description: Show only iceberg tables
        expr: IS_ICEBERG = 'YES'

      - name: hybrid_tables_only
        description: Show only hybrid tables
        expr: IS_HYBRID = 'YES'

      - name: dynamic_tables_only
        description: Show only dynamic tables
        expr: IS_DYNAMIC = 'YES'

      - name: is_a_table
        description: Show only tables
        expr: TABLE_TYPE IN ('BASE TABLE', 'TEMPORARY TABLE', 'EXTERNAL TABLE', 'EVENT TABLE')

      - name: is_a_view
        description: Show only views
        expr: TABLE_TYPE IN ('VIEW', 'MATERIALIZED VIEW')


  - name: TAG_REFERENCES
    description: Account Usage view that identifies associations between objects and tags in Snowflake.
      Only records direct relationships between objects and tags (tag lineage not included).

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: TAG_REFERENCES

    primary_key:
      columns:
        - TAG_ID
        - OBJECT_ID
        - COLUMN_ID
        - OBJECT_DATABASE
        - OBJECT_SCHEMA
        - DOMAIN

    time_dimensions:
      - name: OBJECT_DELETED
        expr: OBJECT_DELETED
        description: 'Date and time when the associated object or its parent object was dropped.
          Note: Does not include timestamp for deleted columns that had tags.'
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TAG_DATABASE
        expr: TAG_DATABASE
        description: The database in which the tag is set
        synonyms: ["TAG DATABASE", "TAG DATABASE NAME", "TAG DB", "TAG CATALOG", "TAG PARENT DATABASE"]
        data_type: VARCHAR

      - name: TAG_SCHEMA
        expr: TAG_SCHEMA
        description: The schema in which the tag is set
        synonyms: ["TAG SCHEMA", "TAG SCHEMA NAME",  "TAG PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: TAG_ID
        expr: TAG_ID
        description: Internal/system-generated identifier for the tag (NULL for system tags)
        synonyms: ["TAG ID", "TAG IDENTIFIER"]
        data_type: NUMBER

      - name: TAG_NAME
        expr: TAG_NAME
        description: The name of the tag (key in the key = 'value' pair)
        synonyms: ["TAG NAME", "TAG", "ASSOCIATED TAG NAME", "ASSIGNED TAG NAME"]
        data_type: VARCHAR

      - name: TAG_VALUE
        expr: TAG_VALUE
        description: The value of the tag (value in the key = 'value' pair)
        synonyms: ["TAG VALUE", "ASSOCIATED TAG VALUE", "ASSIGNED TAG VALUE"]
        data_type: VARCHAR

      - name: OBJECT_DATABASE
        expr: OBJECT_DATABASE
        description:     Database name of the referenced object for database and schema objects.
          Empty if object is not a database or schema object.
        synonyms: ["OBJECT DATABASE NAME", "TAGGED OBJECT DATABASE", "REFERENCED OBJECT CATALOG", "REFERENCE OBJECT PARENT DATABASE"]
        data_type: VARCHAR

      - name: OBJECT_SCHEMA
        expr: OBJECT_SCHEMA
        description:     Schema name of the referenced object for schema objects.
          Empty if object is not a schema object (e.g. warehouse).
        synonyms: ["OBJECT SCHEMA NAME", "TAGGED OBJECT SCHEMA", "REFERENCED OBJECT SCHEMA", "REFERENCED OBJECT PARENT SCHEMA"]
        data_type: VARCHAR

      - name: OBJECT_ID
        expr: OBJECT_ID
        description: Internal identifier of the referenced object
        synonyms: ["OBJECT ID", "TAGGED OBJECT ID", "REFERENCED OBJECT ID", "OBJECT IDENTIFIER"]
        data_type: NUMBER

      - name: OBJECT_NAME
        expr: OBJECT_NAME
        description:     Name of the referenced object if tag is on the object.
          Parent table name if tag is on a column.
        synonyms: ["OBJECT NAME", "TAGGED OBJECT NAME", "REFERENCED OBJECT NAME"]
        data_type: VARCHAR

      - name: DOMAIN
        expr: DOMAIN
        description:     Domain of the reference object (e.g. TABLE, VIEW) for object tags.
          'COLUMN' for column-level tags.
        synonyms: ["DOMAIN", "OBJECT TYPE"]
        data_type: VARCHAR
        is_enum: true
        sample_values:
          - TABLE
          - COLUMN
          - WAREHOUSE
          - DATABASE ROLE
          - DATABASE
          - ROLE
          - SCHEMA
          - USER

      - name: COLUMN_ID
        expr: COLUMN_ID
        description: Local identifier of the referenced column (NULL if tag is not on a column)
        synonyms: ["COLUMN ID", "TAGGED COLUMN ID", "REFERENCED COLUMN ID"]
        data_type: NUMBER

      - name: COLUMN_NAME
        expr: COLUMN_NAME
        description: Name of the referenced column (NULL if tag is not on a column)
        synonyms: ["COLUMN NAME", "TAGGED COLUMN NAME", "REFERENCED COLUMN NAME"]
        data_type: VARCHAR

      - name: APPLY_METHOD
        expr: APPLY_METHOD
        description: Specifies how the tag got assigned to the object (NULL is legacy method)
        is_enum: true
        data_type: VARCHAR
        sample_values:
          - CLASSIFIED
          - INHERITED
          - MANUAL
          - PROPAGATED

    filters:
      - name: active_objects_only
        description: Show only tag references for non-deleted objects
        expr: OBJECT_DELETED IS NULL

      - name: column_tags_only
        description: Show tags assigned to columns
        expr: DOMAIN = 'COLUMN'

      - name: financial_identifiers
        description: "Show columns containing financial account or payment information"
        synonyms: ["financial data", "payment info", "banking data"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('BANK_ACCOUNT', 'PAYMENT_CARD', 'IBAN', 'TAX_IDENTIFIER')

      - name: government_ids
        description: "Show columns containing government-issued identification"
        synonyms: ["official ids", "identity documents"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('DRIVERS_LICENSE', 'MEDICARE_NUMBER', 'NATIONAL_IDENTIFIER', 'PASSPORT')

      - name: contact_information
        description: "Show columns containing contact details"
        synonyms: ["contact details", "contact info"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('EMAIL', 'PHONE_NUMBER', 'STREET_ADDRESS')

      - name: digital_identifiers
        description: "Show columns containing digital/electronic identifiers"
        synonyms: ["digital ids", "electronic identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('IP_ADDRESS', 'URL', 'IMEI', 'VIN')

      - name: location_data
        description: "Show columns containing geographic location information"
        synonyms: ["geographic data", "address data"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('ADMINISTRATIVE_AREA_1', 'ADMINISTRATIVE_AREA_2', 'CITY', 'POSTAL_CODE',
                          'COUNTRY', 'LAT_LONG', 'LATITUDE', 'LONGITUDE')

      - name: demographic_data
        description: "Show columns containing demographic information"
        synonyms: ["personal characteristics", "population attributes"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('AGE', 'GENDER', 'ETHNICITY', 'MARITAL_STATUS', 'OCCUPATION', 'YEAR_OF_BIRTH')

      - name: temporal_personal_data
        description: "Show columns containing time-based personal information"
        synonyms: ["time-based personal info", "date attributes"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('DATE_OF_BIRTH', 'YEAR_OF_BIRTH')

      - name: financial_sensitive_data
        description: "Show columns containing sensitive financial information"
        synonyms: ["sensitive financial info", "compensation data"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE = 'SALARY'

      - name: all_direct_identifiers
        description: "Show all columns classified as direct identifiers"
        synonyms: ["direct PII", "primary identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'PRIVACY_CATEGORY'
          AND TAG_VALUE = 'IDENTIFIER'

      - name: all_quasi_identifiers
        description: "Show all columns classified as quasi-identifiers"
        synonyms: ["indirect PII", "secondary identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'PRIVACY_CATEGORY'
          AND TAG_VALUE = 'QUASI_IDENTIFIER'

      - name: high_risk_identifiers
        description: "Show columns with highest risk for personal identification"
        synonyms: ["critical PII", "sensitive identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('NATIONAL_IDENTIFIER', 'PASSPORT', 'DRIVERS_LICENSE', 'MEDICARE_NUMBER', 'TAX_IDENTIFIER')

      - name: personal_names
        description: "Show columns containing personal names"
        synonyms: ["name fields", "person names"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE = 'NAME'

      - name: organization_identifiers
        description: "Show columns containing organization identifiers"
        synonyms: ["company ids", "business identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE = 'ORGANIZATION_IDENTIFIER'

  - name: USERS
    description: Account Usage view containing information about all users in the Snowflake account.
      Provides details about user authentication, security settings, defaults, and account status.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: USERS

    primary_key:
      columns:
        - NAME

    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Date and time (UTC) when the user was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Date and time (UTC) when the user was deleted
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: BYPASS_MFA_UNTIL
        expr: BYPASS_MFA_UNTIL
        description: Timestamp until which MFA is temporarily bypassed for the user
        synonyms: ["MFA_DISABLE_DURATION"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_SUCCESS_LOGIN
        expr: LAST_SUCCESS_LOGIN
        description: Date and time (UTC) of user's last successful login to Snowflake
        synonyms: ["LAST_LOGIN", "LOGIN_SUCCESS", "SUCCESSFUL LOGIN TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: EXPIRES_AT
        expr: EXPIRES_AT
        description: Date and time when user's status will be set to EXPIRED, preventing further logins
        synonyms: ["LOGIN_UNTIL_TIME", "EXPIRE TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LOCKED_UNTIL_TIME
        expr: LOCKED_UNTIL_TIME
        description: Timestamp until which the temporary lock on user login remains active
        synonyms: ["LOCK EXPIRES AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: PASSWORD_LAST_SET_TIME
        expr: PASSWORD_LAST_SET_TIME
        description: Timestamp when the last non-null password was set for the user
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: USER_ID
        expr: USER_ID
        description: Internal/system-generated unique identifier for the user
        synonyms: ["USER ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: NAME
        expr: NAME
        description: Unique identifier for the user
        synonyms: ["USER", "USER NAME"]
        data_type: VARCHAR
        unique: true

      - name: LOGIN_NAME
        expr: LOGIN_NAME
        description: Name that the user enters to log into the system
        synonyms: ["LOGIN NAME", "SIGN IN NAME"]
        data_type: VARCHAR

      - name: DISPLAY_NAME
        expr: DISPLAY_NAME
        description: Name displayed for the user in the Snowflake web interface
        synonyms: ["DISPLAY NAME", "USER FRIENDLY NAME"]
        data_type: VARCHAR

      - name: FIRST_NAME
        expr: FIRST_NAME
        description: First name of the user
        synonyms: ["FIRST NAME", "GIVEN NAME"]
        data_type: VARCHAR

      - name: LAST_NAME
        expr: LAST_NAME
        description: Last name of the user
        synonyms: ["LAST NAME", "SURNAME", "FAMILY NAME"]
        data_type: VARCHAR

      - name: EMAIL
        expr: EMAIL
        description: Email address for the user
        synonyms: ["EMAIL", "EMAIL ADDRESS"]
        data_type: VARCHAR

      - name: MUST_CHANGE_PASSWORD
        expr: MUST_CHANGE_PASSWORD
        description: Indicates if user must change password at next login
        synonyms: ["MUST CHANGE PASSWORD", "FORCE PASSWORD CHANGE"]
        data_type: BOOLEAN
        is_enum: true

      - name: HAS_PASSWORD
        expr: HAS_PASSWORD
        description: Indicates if a password has been created for the user
        synonyms: ["HAS PASSWORD", "PASSWORD SET"]
        data_type: BOOLEAN
        is_enum: true

      - name: DISABLED
        expr: DISABLED
        description: Indicates if user account is disabled, preventing login and query execution
        synonyms: ["DISABLED", "ACCOUNT DISABLED"]
        data_type: VARIANT
        is_enum: true

      - name: SNOWFLAKE_LOCK
        expr: SNOWFLAKE_LOCK
        description: Indicates if a temporary lock is placed on the user's account
        synonyms: ["SNOWFLAKE LOCK", "TEMPORARY LOCK", "TEMPORARY DISABLED"]
        data_type: VARIANT
        is_enum: true

      - name: DEFAULT_WAREHOUSE
        expr: DEFAULT_WAREHOUSE
        description: Virtual warehouse active by default for user's session upon login
        synonyms: ["DEFAULT WAREHOUSE", "PRIMARY WAREHOUSE"]
        data_type: VARCHAR

      - name: DEFAULT_NAMESPACE
        expr: DEFAULT_NAMESPACE
        description: Default namespace (database/schema) for user's session upon login
        synonyms: ["DEFAULT NAMESPACE", "DEFAULT DATABASE/SCHEMA"]
        data_type: VARCHAR

      - name: DEFAULT_ROLE
        expr: DEFAULT_ROLE
        description: Role that is active by default for user's session upon login
        synonyms: ["DEFAULT ROLE", "PRIMARY ROLE"]
        data_type: VARCHAR

      - name: DEFAULT_SECONDARY_ROLE
        expr: DEFAULT_SECONDARY_ROLE
        description: Default secondary role for the user (ALL or NULL if not set)
        synonyms: ["DEFAULT SECONDARY ROLE", "SECONDARY ROLE"]
        data_type: VARCHAR

      - name: EXT_AUTHN_DUO
        expr: EXT_AUTHN_DUO
        description: Indicates if Duo Security MFA is enabled for the user
        synonyms: ["DUO SECURITY", "DUO MFA"]
        data_type: VARIANT
        is_enum: true

      - name: EXT_AUTHN_UID
        expr: EXT_AUTHN_UID
        description: Authorization ID used for Duo Security
        synonyms: ["DUO AUTH ID", "EXTERNAL AUTH ID"]
        data_type: VARCHAR

      - name: HAS_MFA
        expr: HAS_MFA
        description: Indicates if user is enrolled for multi-factor authentication
        synonyms: ["HAS MFA", "MFA ENABLED"]
        data_type: BOOLEAN
        is_enum: true

      - name: HAS_RSA_PUBLIC_KEY
        expr: HAS_RSA_PUBLIC_KEY
        description: Indicates if RSA public key is set up for key pair authentication
        synonyms: ["HAS RSA KEY", "RSA AUTH ENABLED"]
        data_type: BOOLEAN
        is_enum: true

      - name: OWNER
        expr: OWNER
        description: Role with OWNERSHIP privilege on the user object
        synonyms: ["OWNER", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: TYPE
        expr: TYPE
        description: Type of user
        synonyms: ["USER TYPE", "USER ACCOUNT TYPE"]
        data_type: VARCHAR

      - name: DATABASE_NAME
        expr: DATABASE_NAME
        description: Service's database name (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE DATABASE", "DATABASE"]
        data_type: VARCHAR

      - name: DATABASE_ID
        expr: DATABASE_ID
        description: Internal identifier for service's database (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE DATABASE ID"]
        data_type: VARCHAR

      - name: SCHEMA_NAME
        expr: SCHEMA_NAME
        description: Service's schema name (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE SCHEMA", "SCHEMA"]
        data_type: VARCHAR

      - name: SCHEMA_ID
        expr: SCHEMA_ID
        description: Internal identifier for service's schema (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE SCHEMA ID"]
        data_type: VARCHAR

    filters:
      - name: active_users_only
        description: Show only non-deleted users
        expr: DELETED_ON IS NULL

      - name: mfa_users_only
        description: Show only users with MFA enabled
        expr: HAS_MFA = TRUE

      - name: non_disabled_users
        description: Show only enabled user accounts
        expr: DISABLED = FALSE

      - name: disabled_users
        description: Show only disable user accounts
        expr: DISABLED = TRUE

  - name: VIEWS
    description: Contains metadata about database views including their definitions, ownership, security settings,
      and timestamps for creation, modification and deletion.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: VIEWS

    primary_key:
      columns:
        - TABLE_ID
        - TABLE_NAME
        - TABLE_SCHEMA
        - TABLE_CATALOG

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the view was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the view was last altered by a DML, DDL, or background metadata operation
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_DDL
        expr: LAST_DDL
        description: Timestamp of the last DDL operation (CREATE/ALTER/DROP) performed on the view
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the view was deleted
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "VIEW DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TABLE_ID
        expr: TABLE_ID
        description: Internal/system-generated unique identifier for the view
        synonyms: ["VIEW ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: TABLE_NAME
        expr: TABLE_NAME
        description: Name of the view
        synonyms: ["VIEW NAME", "NAME"]
        data_type: VARCHAR

      - name: TABLE_SCHEMA_ID
        expr: TABLE_SCHEMA_ID
        description: Internal/system-generated identifier for the schema that contains the view
        synonyms: ["VIEW SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Name of the schema that contains the view
        synonyms: ["VIEW SCHEMA", "SCHEMA NAME", "PARENT SCHEMA NAME"]
        data_type: VARCHAR

      - name: TABLE_CATALOG_ID
        expr: TABLE_CATALOG_ID
        description: Internal/system-generated identifier for the database that contains the view
        synonyms: ["VIEW CATALOG ID", "DATABASE ID", "DATABASE IDENTIFIER"]
        data_type: NUMBER

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Name of the database that contains the view
        synonyms: ["VIEW CATALOG", "DATABASE NAME", "CATALOG NAME", "PARENT DATABASE NAME"]
        data_type: VARCHAR

      - name: TABLE_OWNER
        expr: TABLE_OWNER
        description: Name of the role that owns the view
        synonyms: ["VIEW OWNER", "OWNER", "OWNING ROLE"]
        data_type: VARCHAR

      - name: VIEW_DEFINITION
        expr: VIEW_DEFINITION
        description: Complete SQL query expression that defines the view
        synonyms: ["VIEW DEFINITION", "VIEW SQL", "SQL DEFINITION", "VIEW EXPRESSION"]
        data_type: VARCHAR

      - name: IS_SECURE
        expr: IS_SECURE
        description: Indicates if the view is secure (secure views hide the underlying SQL)
        synonyms: ["IS SECURE", "SECURE VIEW"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: LAST_DDL_BY
        expr: LAST_DDL_BY
        description: Username who executed the last DDL operation on the view
        synonyms: ["LAST DDL BY", "LAST MODIFIED BY"]
        data_type: VARCHAR

      - name: COMMENT
        expr: COMMENT
        description: User-provided description or comment about the view
        synonyms: ["COMMENT", "DESCRIPTION"]
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: Type of role that owns the view (ROLE or APPLICATION)
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: INSTANCE_ID
        expr: INSTANCE_ID
        description: Internal/system-generated identifier for the instance
        data_type: NUMBER

    filters:
      - name: active_views_only
        description: Show only non-deleted views
        expr: DELETED IS NULL

      - name: secure_views_only
        description: Show only secure views
        expr: IS_SECURE = 'YES'


relationships:
  - name: classification_to_databases
    left_table: DATA_CLASSIFICATION_LATEST
    right_table: DATABASES
    relationship_columns:
      - left_column: DATABASE_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: classification_to_schemas
    left_table: DATA_CLASSIFICATION_LATEST
    right_table: SCHEMATA
    relationship_columns:
      - left_column: SCHEMA_ID
        right_column: SCHEMA_ID
    join_type: inner
    relationship_type: many_to_one

  - name: classification_to_tables
    left_table: DATA_CLASSIFICATION_LATEST
    right_table: TABLES
    relationship_columns:
      - left_column: TABLE_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_databases
    left_table: POLICY_REFERENCES
    right_table: DATABASES
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_schemas
    left_table: POLICY_REFERENCES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: CATALOG_NAME
      - left_column: REF_SCHEMA_NAME
        right_column: SCHEMA_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_tables
    left_table: POLICY_REFERENCES
    right_table: TABLES
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: TABLE_CATALOG
      - left_column: REF_SCHEMA_NAME
        right_column: TABLE_SCHEMA
      - left_column: REF_ENTITY_NAME
        right_column: TABLE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_views
    left_table: POLICY_REFERENCES
    right_table: VIEWS
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: TABLE_CATALOG
      - left_column: REF_SCHEMA_NAME
        right_column: TABLE_SCHEMA
      - left_column: REF_ENTITY_NAME
        right_column: TABLE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_columns
    left_table: POLICY_REFERENCES
    right_table: COLUMNS
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: TABLE_CATALOG
      - left_column: REF_SCHEMA_NAME
        right_column: TABLE_SCHEMA
      - left_column: REF_ENTITY_NAME
        right_column: TABLE_NAME
      - left_column: REF_COLUMN_NAME
        right_column: COLUMN_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_masking
    left_table: POLICY_REFERENCES
    right_table: MASKING_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_agg_policy
    left_table: POLICY_REFERENCES
    right_table: AGGREGATION_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_proj_policy
    left_table: POLICY_REFERENCES
    right_table: PROJECTION_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_row_access
    left_table: POLICY_REFERENCES
    right_table: ROW_ACCESS_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: query_history_to_access_history
    left_table: ACCESS_HISTORY
    right_table: QUERY_HISTORY
    relationship_columns:
      - left_column: QUERY_ID
        right_column: QUERY_ID
    join_type: inner
    relationship_type: one_to_one

  - name: columns_to_databases
    left_table: COLUMNS
    right_table: DATABASES
    relationship_columns:
      - left_column: TABLE_CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: tables_to_databases
    left_table: TABLES
    right_table: DATABASES
    relationship_columns:
      - left_column: TABLE_CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: schemata_to_databases
    left_table: SCHEMATA
    right_table: DATABASES
    relationship_columns:
      - left_column: CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: databases_to_tables
    left_table: DATABASES
    right_table: TABLES
    relationship_columns:
      - left_column: DATABASE_ID
        right_column: TABLE_CATALOG_ID
    join_type: left_outer
    relationship_type: many_to_one

  - name: tables_to_schemata
    left_table: TABLES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: TABLE_SCHEMA_ID
        right_column: SCHEMA_ID
      - left_column: TABLE_CATALOG_ID
        right_column: CATALOG_ID
    join_type: inner
    relationship_type: many_to_one

  - name: roles_grants_to_roles
    left_table: GRANTS_TO_ROLES
    right_table: ROLES
    relationship_columns:
      - left_column: GRANTEE_NAME
        right_column: NAME
    join_type: inner
    relationship_type: many_to_one

  - name: users_grants_to_role_grants
    left_table: GRANTS_TO_USERS
    right_table: GRANTS_TO_ROLES
    relationship_columns:
      - left_column: ROLE
        right_column: GRANTEE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: users_grants_to_user
    left_table: GRANTS_TO_USERS
    right_table: USERS
    relationship_columns:
      - left_column: GRANTEE_NAME
        right_column: NAME
    join_type: inner
    relationship_type: many_to_one

  - name: users_grants_to_roles
    left_table: GRANTS_TO_USERS
    right_table: ROLES
    relationship_columns:
      - left_column: ROLE
        right_column: NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_databases
    left_table: TAG_REFERENCES
    right_table: DATABASES
    relationship_columns:
      - left_column: OBJECT_DATABASE
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_schemata
    left_table: TAG_REFERENCES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: OBJECT_SCHEMA
        right_column: SCHEMA_NAME
      - left_column: OBJECT_DATABASE
        right_column: CATALOG_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_tables
    left_table: TAG_REFERENCES
    right_table: TABLES
    relationship_columns:
      - left_column: OBJECT_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_columns
    left_table: TAG_REFERENCES
    right_table: COLUMNS
    relationship_columns:
      - left_column: COLUMN_NAME
        right_column: COLUMN_NAME
      - left_column: OBJECT_NAME
        right_column: TABLE_NAME
      - left_column: OBJECT_SCHEMA
        right_column: TABLE_SCHEMA
      - left_column: OBJECT_DATABASE
        right_column: TABLE_CATALOG
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_tags
    left_table: TAG_REFERENCES
    right_table: TAGS
    relationship_columns:
      - left_column: TAG_ID
        right_column: TAG_ID
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referenced_databases
    left_table: OBJECT_DEPENDENCIES
    right_table: DATABASES
    relationship_columns:
      - left_column: REFERENCED_DATABASE
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tobj_dep_to_referenced_schemata
    left_table: OBJECT_DEPENDENCIES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: REFERENCED_SCHEMA
        right_column: SCHEMA_NAME
      - left_column: REFERENCED_DATABASE
        right_column: CATALOG_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referenced_tables
    left_table: OBJECT_DEPENDENCIES
    right_table: TABLES
    relationship_columns:
      - left_column: REFERENCED_OBJECT_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referencing_databases
    left_table: OBJECT_DEPENDENCIES
    right_table: DATABASES
    relationship_columns:
      - left_column: REFERENCING_DATABASE
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tobj_dep_to_referencing_schemata
    left_table: OBJECT_DEPENDENCIES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: REFERENCING_SCHEMA
        right_column: SCHEMA_NAME
      - left_column: REFERENCING_DATABASE
        right_column: CATALOG_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referencing_tables
    left_table: OBJECT_DEPENDENCIES
    right_table: TABLES
    relationship_columns:
      - left_column: REFERENCING_OBJECT_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: aggregation_policy_to_schema
    left_table: AGGREGATION_POLICIES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: POLICY_SCHEMA_ID
        right_column: SCHEMA_ID
    join_type: inner
    relationship_type: many_to_one

  - name: aggregation_policy_to_catalog
    left_table: AGGREGATION_POLICIES
    right_table: DATABASES
    relationship_columns:
      - left_column: POLICY_CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: columns_to_tables
    left_table: COLUMNS
    right_table: TABLES
    relationship_columns:
      - left_column: TABLE_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

verified_queries:
# start of VQRs for snowflake public documentation questions
  - name: Show sensitive objects without data access policies
    question: "Which of my most popular objects are sensitive but not protected by a data access policy?"
    sql: |
      WITH recent_accesses AS (
        SELECT
          oa.value:objectName as object_name,
          count(*) as access_count
        FROM __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => direct_objects_accessed) oa
        WHERE
          ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP)
          AND oa.value:objectDomain IN ('Table', 'View')
          AND oa.value:objectId is not NULL
        GROUP BY object_name
        ORDER BY access_count DESC
        LIMIT 10
      ),
      sensitive_tables AS (
        SELECT DATABASE_NAME || '.' || SCHEMA_NAME || '.' || TABLE_NAME as object_name
      FROM __DATA_CLASSIFICATION_LATEST,
      LATERAL FLATTEN(INPUT => RESULT) AS r
      WHERE r.value:recommendation IS NOT NULL
      ),
      policy_protected_objects AS (
        SELECT DISTINCT REF_DATABASE_NAME || '.' || REF_SCHEMA_NAME || '.' || REF_ENTITY_NAME as object_name
        FROM __POLICY_REFERENCES
        WHERE REF_ENTITY_DOMAIN IN ('TABLE', 'VIEW')
      )
      SELECT
        ra.object_name
      FROM recent_accesses ra
      JOIN sensitive_tables so
        ON ra.object_name = so.object_name
      LEFT JOIN policy_protected_objects ppo
        ON ra.object_name = ppo.object_name
      WHERE ppo.object_name IS NULL
      ORDER BY ra.access_count DESC;
    use_as_onboarding_question: false

  - name: Percentage of objects classified as sensitive
    question: "What percentage of my objects are classified as sensitive?"
    sql: |
      WITH total_tables AS (
        SELECT COUNT(*) AS total
        FROM __TABLES
        WHERE DELETED IS NULL
      ),
      sensitive_tables AS (
        SELECT COUNT(DISTINCT table_id) AS sensitive
        FROM __DATA_CLASSIFICATION_LATEST,
        LATERAL FLATTEN(INPUT => RESULT) AS r
        WHERE r.value:recommendation IS NOT NULL
      )
      SELECT
        sensitive_tables.sensitive,
        total_tables.total,
        ROUND(100.0 * sensitive_tables.sensitive / total_tables.total, 2) AS percent_sensitive
      FROM sensitive_tables, total_tables;
    use_as_onboarding_question: false

  - name: Databases with tag-based masking policies
    question: "Which databases have tag-based masking policies?"
    sql: |
      SELECT DISTINCT
        tr.object_name AS database_name
      FROM __TAG_REFERENCES tr
      JOIN __POLICY_REFERENCES pr
        ON tr.tag_name = pr.tag_name
        AND tr.tag_schema = pr.tag_schema
        AND tr.tag_database = pr.tag_database
      WHERE
        tr.domain = 'DATABASE'
        AND pr.policy_kind = 'MASKING_POLICY'
        AND tr.object_deleted IS NULL;
    use_as_onboarding_question: false

  - name: Roles with privileges on table
    question: "What roles have privileges on table emp?"
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          grantee_name AS role_name,
          name AS object_name
        FROM __GRANTS_TO_ROLES gtr
        WHERE
          name = UPPER('emp')
          AND granted_on = 'TABLE'

        UNION ALL

        SELECT
          gtr.grantee_name AS role_name,
          rh.object_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
          ON gtr.name = rh.role_name
      )
      SELECT
        rh.role_name,
        gtr.privilege,
        gtr.name AS object_name,
        gtr.grant_option
      FROM role_hierarchy rh
      JOIN __grants_to_roles gtr
        ON rh.role_name = gtr.grantee_name
      WHERE
        gtr.granted_on = 'TABLE'
        AND gtr.name = UPPER('emp')
      ORDER BY role_name;
    use_as_onboarding_question: false

  - name: What objects can role access with select statements
    question: "Which objects classified as sensitive can the role DEX_ADMIN access with a SELECT statement?"
    sql: |
      WITH sensitive_tables AS (
        SELECT DISTINCT
          database_name,
          schema_name,
          table_name
        FROM __data_classification_latest,
        LATERAL FLATTEN(input => result) r
        WHERE r.value:recommendation IS NOT NULL
      ),
      role_hierarchy AS (
        SELECT
          gtr.grantee_name as role,
          gtr.table_catalog || '.' || gtr.table_schema || '.' || gtr.name as name
        FROM __GRANTS_TO_ROLES gtr
        JOIN sensitive_tables st
        ON gtr.table_catalog = st.database_name
        AND gtr.table_schema = st.schema_name
        AND gtr.name = st.table_name
        WHERE privilege in ('SELECT', 'OWNERSHIP')
        AND granted_on = 'TABLE'
        UNION ALL
        SELECT
          g.grantee_name,
          g.name
        FROM __GRANTS_TO_ROLES g
        JOIN role_hierarchy rh ON g.name = rh.role
      )
      select role, name from role_hierarchy
      WHERE ROLE = UPPER('DEX_ADMIN');
    use_as_onboarding_question: false

  - name: What roles are granted to user
    question: "Show me the roles, including secondary roles, currently granted to user RFEHRMANN."
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          role as role_name,
          grantee_name AS user_name
        FROM __GRANTS_TO_USERS
        WHERE
          grantee_name = UPPER('RFEHRMANN')
          AND deleted_on IS NULL
        UNION ALL
        SELECT
          gtr.grantee_name AS role_name,
          rh.user_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
          ON gtr.name = rh.role_name
        WHERE gtr.deleted_on IS NULL
      )
      SELECT DISTINCT role_name
      FROM role_hierarchy
      ORDER BY role_name;
    use_as_onboarding_question: false

  - name: Show top 10 most popular tables in schema
    question: "What are the top 10 most popular tables in schema DEMO based on the number of queries?"
    sql: |
      SELECT
        oa.value:objectName as object_name,
        count(*) as access_count
      FROM __ACCESS_HISTORY ah,
      LATERAL FLATTEN(input => ah.direct_objects_accessed) oa
      WHERE
        oa.value:objectDomain = 'Table'
        AND oa.value:objectName LIKE '%.DEMO.%'
        AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP)
      GROUP BY object_name
      ORDER BY access_count DESC
      LIMIT 10;
    use_as_onboarding_question: false

  - name: Show schema changes made to table
    question: "List all schema changes made to the table my_table5 in the past 7 days."
    sql: |
      SELECT
        qh.start_time,
        qh.query_text
      FROM __ACCESS_HISTORY ah
      JOIN __QUERY_HISTORY qh
        on ah.query_id = qh.query_id
      WHERE
        ah.object_modified_by_ddl:operationType = 'ALTER'
        AND ah.object_modified_by_ddl:objectDomain = 'Table'
        AND ah.object_modified_by_ddl:objectName LIKE '%.MY_TABLE5'
        AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP)
        AND (
          qh.query_text ILIKE '%ADD COLUMN%' OR
          qh.query_text ILIKE '%DROP COLUMN%' OR
          qh.query_text ILIKE '%RENAME COLUMN%' OR
          qh.query_text ILIKE '%SET DATA TYPE%'
        )
      LIMIT 10;
    use_as_onboarding_question: false
# end of VQRs for snowflake public documentation questions


# start of VQRs for quick start guide questions
  - name: Show tables updated in the past 24 hours under schema
    question: "List the tables updated in the past 24 hours in schema SCH1."
    sql: |
      SELECT table_name, table_schema
      FROM __TABLES
      WHERE table_schema = UPPER('SCH1')
        AND last_altered >= DATEADD(hour, -24, CURRENT_TIMESTAMP())
        AND DELETED IS NULL;
    use_as_onboarding_question: false

  - name: Show views under database
    question: "List all views defined in database KDD_DB."
    sql: |
      SELECT
        table_catalog AS database_name,
        table_schema AS schema_name,
        table_name AS view_name,
      FROM __VIEWS
      WHERE table_catalog = UPPER('KDD_DB')
        AND DELETED IS NULL
      ORDER BY
        database_name, schema_name, table_name;
    use_as_onboarding_question: false

  - name: Show most frequently queried tables under database
    question: "What are the most frequently queried tables in the last 7 days in database YYAN_TEST?"
    sql: |
      SELECT
        o_flattened.value:objectName as table_name,
        COUNT(*) AS query_count
      FROM
        __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened
      WHERE o_flattened.value:objectDomain = 'Table'
      AND o_flattened.value:objectName ILIKE 'YYAN_TEST.%'
      AND ah.QUERY_START_TIME >= DATEADD(day, -7, CURRENT_TIMESTAMP())
      GROUP BY
        o_flattened.value:objectName
      ORDER BY
        query_count DESC
      LIMIT 1;
    use_as_onboarding_question: false

  - name: Show tables not queried under database
    question: "Show the list of tables in database YLI that have not been queried in the past 7 days."
    sql: |
      WITH queried_tables AS (
        SELECT
          DISTINCT oa.value:objectName::string AS table_name
        FROM
          __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) oa
        WHERE
        oa.value:objectName::string ILIKE 'YLI.%'
        AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
        AND oa.value:objectDomain::string = 'Table'
      ),
      all_tables AS (
        SELECT
          table_catalog || '.' || table_schema || '.' || table_name AS table_name
        FROM __TABLES
        WHERE
        table_catalog = UPPER('YLI')
        AND deleted IS NULL
      )
      SELECT
        at.table_name
      FROM
        all_tables at
      LEFT JOIN
        queried_tables qt
      ON at.table_name = qt.table_name
      WHERE qt.table_name IS NULL
      ORDER BY at.table_name;
    use_as_onboarding_question: false

  - name: Top users querying columns with tag
    question: "Who are the top users querying columns tagged with tag PRIVACY_CATEGORY in database DEX_DB?"
    sql: |
      WITH tagged_tables AS (
        SELECT
          tag_name,tag_database,domain,
          object_database || '.' || object_schema || '.' || object_name AS table_name
        FROM __TAG_REFERENCES
        WHERE
          tag_name = 'PRIVACY_CATEGORY'
          AND object_database = 'DEX_DB'
          AND domain = 'COLUMN'
          AND object_deleted is null
      ),
      user_queries AS (
        SELECT
          ah.user_name,
          COUNT(*) AS query_count
        FROM __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) oa
        JOIN tagged_tables tt
          ON oa.value:objectName::string = tt.table_name
        WHERE oa.value:objectDomain::string = 'Table'
          AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
        GROUP BY 1
      )
      SELECT
        user_name,
        query_count
      FROM user_queries
      ORDER BY query_count DESC
      LIMIT 5;
    use_as_onboarding_question: false

  - name: Most used masking policy
    question: "Which masking policy was used the most in the past 7 days?"
    sql: |
      SELECT
        p.value:policyName::STRING AS masking_policy_name,
        COUNT(*) AS usage_count
      FROM
        __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => POLICIES_REFERENCED) AS obj,
        LATERAL FLATTEN(input => obj.value:columns) AS col,
        LATERAL FLATTEN(input => col.value:policies) AS p
      WHERE
         ah.query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
         AND p.value:policyKind::STRING = 'MASKING_POLICY'
      GROUP BY masking_policy_name
      ORDER BY usage_count DESC
      LIMIT 1;
    use_as_onboarding_question: false

  - name: Users granted to role
    question: "Which users have been granted access to role DEMO_USER?"
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT name as role_name
        FROM __ROLES
        WHERE name = UPPER('DEMO_USER')
          AND deleted_on IS NULL
        UNION ALL

        SELECT grantee_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
        ON gtr.name = rh.role_name
        WHERE
          gtr.privilege IN ('USAGE', 'OWNERSHIP')
          AND gtr.granted_on = 'ROLE'
          AND gtr.deleted_on IS NULL)
      SELECT DISTINCT gu.grantee_name as user_name
      FROM __GRANTS_TO_USERS gu
      JOIN role_hierarchy rh
      ON gu.role = rh.role_name
      where gu.deleted_on is null
      ORDER BY user_name;
    use_as_onboarding_question: false

  - name: Users with access to table
    question: "Show all the users who have access to table EMPLOYEE_DETAIL_PURCHASING both directly and indirectly."
    sql: |
      WITH RECURSIVE role_tree AS (
        SELECT grantee_name AS role_name
        FROM __GRANTS_TO_ROLES
        WHERE privilege = 'SELECT'
        AND granted_on = 'TABLE'
        AND name = UPPER('EMPLOYEE_DETAIL_PURCHASING')
        AND deleted_on IS NULL

        UNION ALL

        SELECT gtr.grantee_name AS role_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_tree rt ON gtr.name = rt.role_name
        WHERE gtr.privilege = 'USAGE'
        AND gtr.granted_on = 'ROLE'
        AND gtr.deleted_on IS NULL
      )
      SELECT DISTINCT gtu.grantee_name AS user_name
      FROM __GRANTS_TO_USERS gtu
      JOIN role_tree rt ON gtu.role = rt.role_name
      WHERE gtu.deleted_on IS NULL;
    use_as_onboarding_question: false

  - name: Users with access to table but did not access in last 3 months
    question: "Show the users that have access to table EMPLOYEE_DETAIL_PURCHASING but not used in the last 3 months."
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          gtr.grantee_name AS granted_role,
        FROM __GRANTS_TO_ROLES gtr
        WHERE gtr.privilege IN ('SELECT', 'OWNERSHIP')
        AND gtr.granted_on = 'TABLE'
        AND gtr.name = UPPER('EMPLOYEE_DETAIL_PURCHASING')
        AND gtr.deleted_on IS NULL

        UNION ALL

        SELECT
          gtr.grantee_name AS granted_role
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
        ON gtr.name = rh.granted_role
        WHERE gtr.granted_on = 'ROLE'
        AND gtr.privilege = 'USAGE'
        AND gtr.deleted_on IS NULL
      ),
      table_access AS (
        SELECT DISTINCT
          ah.user_name
        FROM __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) oa
        WHERE
          oa.value:objectName::string ilike '%.EMPLOYEE_DETAIL_PURCHASING'
          AND oa.value:objectDomain::string = 'Table'
          AND ah.query_start_time >= DATEADD(month, -3, CURRENT_TIMESTAMP())
      ),
      users_with_access AS (
        SELECT DISTINCT
          gu.grantee_name as user_name
        FROM __GRANTS_TO_USERS gu
        JOIN role_hierarchy rh
        ON gu.role = rh.granted_role
        WHERE gu.deleted_on IS NULL
      )
      SELECT
        uwa.user_name
      FROM users_with_access uwa
      LEFT JOIN table_access ta
      ON uwa.user_name = ta.user_name
      WHERE ta.user_name IS NULL
      ORDER BY uwa.user_name;
    use_as_onboarding_question: false

  - name: Users with access to objects tagged with tag
    question: "Show the list of users who have access to objects tagged with tag COSTCENTER"
    sql: |
      WITH RECURSIVE tagged_objects AS (
        SELECT
          tr.object_database AS database_name,
          tr.object_schema AS schema_name,
          tr.object_name
        FROM __TAG_REFERENCES tr
        WHERE
          tr.tag_name = UPPER('COSTCENTER')
          AND tr.object_deleted is null
      ),
      role_hierarchy as (
        SELECT
          gtr.grantee_name AS granted_role
        FROM __GRANTS_TO_ROLES gtr
        JOIN tagged_objects tobj
        ON gtr.table_catalog = tobj.database_name
          AND gtr.table_schema = tobj.schema_name
          AND gtr.name = tobj.object_name
        WHERE
          gtr.privilege IN ('SELECT', 'OWNERSHIP')
          AND gtr.deleted_on IS NULL

        UNION ALL

        SELECT
          gtr.grantee_name AS granted_role
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
        ON gtr.name = rh.granted_role
        WHERE gtr.granted_on = 'ROLE'
          AND gtr.privilege = 'USAGE'
          AND gtr.deleted_on IS NULL
      )
        SELECT DISTINCT
          gu.grantee_name as user_name
        FROM __GRANTS_TO_USERS gu
        JOIN role_hierarchy rh
        ON gu.role = rh.granted_role
        WHERE gu.deleted_on IS NULL;
    use_as_onboarding_question: false

  - name: Tagged columns without masking policy
    question: "Which columns are tagged with tag DG_TAG but don't have a masking policy?"
    sql: |
      WITH tagged_columns AS (
        SELECT
          object_database,
          object_schema,
          object_name,
          column_name
        FROM __TAG_REFERENCES
        WHERE tag_name = UPPER('DG_TAG')
        AND domain = 'COLUMN'
        AND object_deleted IS NULL
      ),
      masked_columns AS (
        SELECT
          ref_database_name AS object_database,
          ref_schema_name AS object_schema,
          ref_entity_name AS object_name,
          ref_column_name AS column_name
        FROM __POLICY_REFERENCES
        WHERE policy_kind = 'MASKING_POLICY'
        AND ref_column_name IS NOT NULL
      )
      SELECT
        t.object_database,
        t.object_schema,
        t.object_name,
        t.column_name
      FROM tagged_columns t
      LEFT JOIN masked_columns m
        ON t.object_database = m.object_database
        AND t.object_schema = m.object_schema
        AND t.object_name = m.object_name
        AND t.column_name = m.column_name
      WHERE m.column_name IS NULL
      ORDER BY t.object_database, t.object_schema, t.object_name, t.column_name;
    use_as_onboarding_question: false

  - name: Percentage of objects classified as sensitive by Snowflake Data Classification
    question: "What percentage of my objects are classified as sensitive by Snowflake Data Classification?"
    sql: |
      WITH total_tables AS (
        SELECT COUNT(*) AS total
        FROM __TABLES
        WHERE DELETED IS NULL
      ),
      sensitive_tables AS (
        SELECT COUNT(DISTINCT table_id) AS sensitive
        FROM __DATA_CLASSIFICATION_LATEST,
        LATERAL FLATTEN(INPUT => RESULT) AS r
        WHERE r.value:recommendation IS NOT NULL
      )
      SELECT
        sensitive_tables.sensitive,
        total_tables.total,
        ROUND(100.0 * sensitive_tables.sensitive / total_tables.total, 2) AS percent_sensitive
      FROM sensitive_tables, total_tables;
    use_as_onboarding_question: false

  - name: Sensitive tables accessible by role
    question: "Which tables are classified as sensitive, but accessible by the DEX_ADMIN role?"
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          r.name AS role_name,
        FROM __ROLES r
        WHERE r.name = UPPER('DEX_ADMIN')
          AND r.deleted_on IS NULL
        UNION ALL
        SELECT
          gtr.grantee_name AS role_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh ON gtr.name = rh.role_name
        WHERE gtr.granted_on = 'ROLE'
          AND gtr.privilege = 'USAGE'
          AND gtr.deleted_on IS NULL
      )
      , sensitive_tables AS (
        SELECT
          dcl.database_name,
          dcl.schema_name,
          dcl.table_name
        FROM __DATA_CLASSIFICATION_LATEST dcl,
        LATERAL FLATTEN(input => dcl.RESULT) f
        WHERE f.value:recommendation IS NOT NULL
        GROUP BY dcl.database_name, dcl.schema_name, dcl.table_name
      )
      , grants_to_role AS (
        SELECT
          gtr.table_catalog AS database_name,
          gtr.table_schema AS schema_name,
          gtr.name AS table_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh ON gtr.grantee_name = rh.role_name
        WHERE gtr.privilege IN ('SELECT','OWNERSHIP')
          AND gtr.granted_on = 'TABLE'
          AND gtr.deleted_on IS NULL
      )
      SELECT
        st.database_name,
        st.schema_name,
        st.table_name
      FROM sensitive_tables st
      INNER JOIN grants_to_role gtp
      ON st.database_name = gtp.database_name
        AND st.schema_name = gtp.schema_name
        AND st.table_name = gtp.table_name
      ORDER BY st.database_name, st.schema_name, st.table_name;
    use_as_onboarding_question: false

# end of VQRs for quick start guide questions

# start of VQRs for tags and policies dashboard questions
  - name: Policy References for tags and policies dashboard
    question: "What are the active policy references in the Snowflake account, including policy details and referenced entity information?"
    sql: |
      select policy_db, policy_schema, policy_name, policy_kind, ref_database_name, ref_schema_name, ref_entity_name, ref_entity_domain,  ref_column_name, tag_database, tag_schema, tag_name, policy_status
      from __POLICY_REFERENCES p_ref
      where policy_status='ACTIVE' ;
    use_as_onboarding_question: false

  - name: Tags References for tags and policies dashboard
    question: "What are the tag references for all objects in the Snowflake account, including tag names, values, and associated object metadata?"
    sql: |
      select  tag_database, tag_schema, tag_name, tag_value, object_database, object_schema, object_name, domain, column_name, apply_method
      from __TAG_REFERENCES
      where object_deleted is null;
    use_as_onboarding_question: false

  - name: Most used tags on a tables for tags and policies dashboard
    question: "show me the count of each tag associated with tables"
    sql: |
      select tag_id, tag_name, tag_database, tag_schema, count(*) from __TAG_REFERENCES where object_deleted is null and domain='TABLE' group by tag_id, tag_name, tag_database, tag_schema order by count(*) desc;
    use_as_onboarding_question: false

  - name: Most used row access policies on a tables for tags and policies dashboard
    question: "What are the most frequently used row access policies?"
    sql: |
      select policy_id, policy_name, policy_db, policy_schema, count(*)
      from __POLICY_REFERENCES
      where policy_status = 'ACTIVE'
        and policy_kind='ROW_ACCESS_POLICY'
      group by policy_id, policy_name, policy_db, policy_schema
      order by count(*) desc;
    use_as_onboarding_question: false

  - name: Most used tags on columns
    question: "what are the most frequently used column tags?"
    sql: |
      select tag_id, tag_name, tag_database, tag_schema, count(*)
      from __TAG_REFERENCES
      where
        object_deleted is null
        and domain='COLUMN'
      group by tag_id, tag_name, tag_database, tag_schema order by count(*) desc;
    use_as_onboarding_question: false

  - name: Most used masking policies on columns for tags and policies dashboard
    question: "what are the most frequently used masking policies?"
    sql: |
      select policy_id, policy_name, policy_db, policy_schema, policy_kind, tag_database, tag_schema, tag_name, count(*) from __POLICY_REFERENCES where policy_status = 'ACTIVE' and policy_kind='MASKING_POLICY' group by policy_id, policy_name, policy_db, policy_schema, policy_kind, tag_database, tag_schema, tag_name order by count(*);
    use_as_onboarding_question: false

# end of VQRs for tags and policies dashboard questions

  - name: Most Schemas in one database
    question: "What database contains the most schemas?"
    sql: |
      SELECT catalog_name as database_name, count(1) as schema_count
      FROM  __SCHEMATA
      WHERE
        deleted is null
      group by all
      order by 2 desc
      limit 1;
    use_as_onboarding_question: false

  - name: Role Owner
    question: "Who owns the role APP_USER?"
    sql: select OWNER from __ROLES where name = UPPER('APP_USER');
    use_as_onboarding_question: false

  - name: Get Aggregation Policy Counts
    question: "What is the number of aggregation policies in the account?"
    sql: SELECT COUNT(POLICY_ID) AS policy_count FROM __AGGREGATION_POLICIES WHERE DELETED IS NULL;
    use_as_onboarding_question: false

  - name: Get Aggregation Policy Owners
    question: "Who are the owners of the aggregation policies in the account?"
    sql: SELECT POLICY_OWNER AS owner FROM __AGGREGATION_POLICIES  WHERE DELETED IS NULL GROUP BY owner;
    use_as_onboarding_question: false

  - name: Get Aggregation Policy Schemas
    question: "What are the schemas of the aggregation policies in the account?"
    sql: SELECT POLICY_SCHEMA AS schema FROM __AGGREGATION_POLICIES WHERE DELETED IS NULL GROUP BY schema;
    use_as_onboarding_question: false

  - name: Get Aggregation Policy Catalogs
    question: "What are the catalogs of the aggregation policies in the account?"
    sql: SELECT POLICY_CATALOG AS catalog FROM __AGGREGATION_POLICIES WHERE DELETED IS NULL GROUP BY catalog;
    use_as_onboarding_question: false

  - name: get a policy definition
    question: "what is the definition for test_rap policy?"
    sql: |
      SELECT
            policy_body,
            'Aggregation Policy' AS policy_type
          FROM
            __aggregation_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL
          UNION ALL
          SELECT
            policy_body,
            'Masking Policy' AS policy_type
          FROM
            __masking_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL
          UNION ALL
          SELECT
            policy_body,
            'Projection Policy' AS policy_type
          FROM
            __projection_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL
          UNION ALL
          SELECT
            policy_body,
            'Row Access Policy' AS policy_type
          FROM
            __row_access_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL;
    use_as_onboarding_question: false

  - name: "Business Hours vs. Non-Business Hours Activity"
    question: "How does query activity compare between business and non-business hours?"
    sql: |
      SELECT
        CASE
          WHEN DAYOFWEEK(query_start_time) BETWEEN 2 AND 6 AND HOUR(query_start_time) BETWEEN 9 AND 16
          THEN 'Business Hours'
          ELSE 'Non-Business Hours'
        END as time_category,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY time_category
      ORDER BY time_category;

  - name: "Role Usage by Query Count"
    question: "Which roles are being used most frequently for queries?"
    sql: |
      SELECT
        role_name,
        COUNT(DISTINCT query_id) as query_count
      FROM __QUERY_HISTORY
      WHERE start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY role_name
      ORDER BY query_count DESC
      LIMIT 10;

  - name: "Query Complexity Distribution"
    question: "What is the distribution of query complexity based on object count?"
    sql: |
      SELECT
        CASE
          WHEN ARRAY_SIZE(direct_objects_accessed) = 0 THEN 'No Objects'
          WHEN ARRAY_SIZE(direct_objects_accessed) = 1 THEN 'Simple'
          WHEN ARRAY_SIZE(direct_objects_accessed) BETWEEN 2 AND 5 THEN 'Moderate'
          ELSE 'Complex'
        END as complexity,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY complexity
      ORDER BY query_count DESC;

  - name: "Daily Query Trend"
    question: "What is the daily trend of query activity over the past 30 days?"
    sql: |
      SELECT
        access_date as access_date,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
      GROUP BY access_date
      ORDER BY access_date;

  - name: "Weekend vs. Weekday Activity"
    question: "How does query activity compare between weekends and weekdays?"
    sql: |
      SELECT
        CASE
          WHEN DAYOFWEEK(query_start_time) IN (1, 7) THEN 'Weekend'
          ELSE 'Weekday'
        END as day_category,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY day_category
      ORDER BY day_category;

  - name: "Query Category Distribution"
    question: "What is the distribution of read, write, and DDL operations?"
    sql: |
      SELECT
        CASE
          WHEN QUERY_TYPE = 'SELECT' THEN 'Read'
          WHEN QUERY_TYPE IN ('INSERT', 'UPDATE', 'DELETE', 'MERGE') THEN 'Write'
          WHEN QUERY_TYPE IN ('CREATE', 'ALTER', 'DROP') THEN 'DDL'
          ELSE 'Other'
        END as query_category,
        COUNT(DISTINCT query_id) as query_count
      FROM __QUERY_HISTORY
      WHERE start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY query_category
      ORDER BY query_count DESC;

  - name: "Modification Operations by User"
    question: "Which users are performing the most data modification operations?"
    sql: |
      SELECT
        user_name,
        COUNT(DISTINCT query_id) as modification_count
      FROM __QUERY_HISTORY
      WHERE query_type IN ('INSERT', 'UPDATE', 'DELETE', 'MERGE')
      AND start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY user_name
      ORDER BY modification_count DESC
      LIMIT 10;

  - name: "Count Tables by Classification Status"
    question: "How many tables have been classified by status?"
    sql: |
      SELECT
        STATUS,
        COUNT(DISTINCT TABLE_ID) as TABLE_COUNT
      FROM __DATA_CLASSIFICATION_LATEST
      GROUP BY STATUS
      ORDER BY TABLE_COUNT DESC;

  - name: "Recently Classified Tables"
    question: "What tables were classified in the last 30 days?"
    sql: >
      SELECT
        DATABASE_NAME,
        SCHEMA_NAME,
        TABLE_NAME,
        LAST_CLASSIFIED_ON
      FROM __DATA_CLASSIFICATION_LATEST
      WHERE DAYS_SINCE_CLASSIFICATION <= 30
      ORDER BY LAST_CLASSIFIED_ON DESC;

  - name: "Database with Most Classified Tables"
    question: "Which database has the most classified tables?"
    sql: >
      SELECT
        DATABASE_NAME,
        COUNT(DISTINCT TABLE_ID) as TABLE_COUNT
      FROM __DATA_CLASSIFICATION_LATEST
      GROUP BY DATABASE_NAME
      ORDER BY TABLE_COUNT DESC
      LIMIT 10;

  - name: "Average Days Since Classification by Database"
    question: "What is the average age of classification results by database?"
    sql: >
      SELECT
        DATABASE_NAME,
        AVG(DAYS_SINCE_CLASSIFICATION) as AVG_DAYS_SINCE_CLASSIFICATION
      FROM __DATA_CLASSIFICATION_LATEST
      GROUP BY DATABASE_NAME
      ORDER BY AVG_DAYS_SINCE_CLASSIFICATION;

  - name: "Tables with Full Path"
    question: "List all classified tables with their full path"
    sql: >
      SELECT
        DATABASE_NAME || '.' || SCHEMA_NAME || '.' || TABLE_NAME as FULL_TABLE_PATH,
        LAST_CLASSIFIED_ON,
        STATUS
      FROM __DATA_CLASSIFICATION_LATEST
      ORDER BY LAST_CLASSIFIED_ON DESC;

  - name: "Classification Status over Time"
    question: "How many tables were classified each month?"
    sql: >
      SELECT
        CLASSIFICATION_MONTH,
        COUNT(DISTINCT TABLE_ID) as TABLE_COUNT
      FROM __DATA_CLASSIFICATION_LATEST
      GROUP BY CLASSIFICATION_MONTH
      ORDER BY CLASSIFICATION_MONTH DESC;

  - name: "Tables that Need Re-classification"
    question: "Which tables were classified more than 90 days ago?"
    sql: >
      SELECT
        DATABASE_NAME,
        SCHEMA_NAME,
        TABLE_NAME,
        LAST_CLASSIFIED_ON,
        DAYS_SINCE_CLASSIFICATION
      FROM __DATA_CLASSIFICATION_LATEST
      WHERE DAYS_SINCE_CLASSIFICATION > 90
      ORDER BY DAYS_SINCE_CLASSIFICATION DESC;

  - name: "Classification Quality Distribution"
    question: "What is the distribution of classification quality across tables?"
    sql: >
      SELECT
        CLASSIFICATION_QUALITY,
        COUNT(DISTINCT TABLE_ID) as TABLE_COUNT
      FROM __DATA_CLASSIFICATION_LATEST
      GROUP BY CLASSIFICATION_QUALITY
      ORDER BY TABLE_COUNT DESC;

  - name: "Extract and Count Semantic Categories"
    question: "What semantic categories have been identified in our data?"
    sql: >
      WITH base_classification AS (
        SELECT
          DATABASE_NAME,
          SCHEMA_NAME,
          TABLE_NAME,
          RESULT
        FROM __DATA_CLASSIFICATION_LATEST
      ),
      column_categories AS (
        SELECT
          f.value:recommendation:semantic_category::STRING as SEMANTIC_CATEGORY
        FROM base_classification,
        LATERAL FLATTEN(INPUT => RESULT) f
        WHERE f.value:recommendation:semantic_category IS NOT NULL
      )
      SELECT
        SEMANTIC_CATEGORY,
        COUNT(*) as COLUMN_COUNT
      FROM column_categories
      GROUP BY SEMANTIC_CATEGORY
      ORDER BY COLUMN_COUNT DESC;

  - name: "Extract Columns with High Confidence Classifications"
    question: "Which columns have been classified with high confidence?"
    sql: >
      WITH base_classification AS (
        SELECT
          DATABASE_NAME,
          SCHEMA_NAME,
          TABLE_NAME,
          RESULT
        FROM __DATA_CLASSIFICATION_LATEST
      )
      SELECT
        DATABASE_NAME,
        SCHEMA_NAME,
        TABLE_NAME,
        f.KEY as COLUMN_NAME,
        f.VALUE:recommendation:semantic_category::STRING as SEMANTIC_CATEGORY,
        f.VALUE:recommendation:privacy_category::STRING as PRIVACY_CATEGORY
      FROM base_classification,
      LATERAL FLATTEN(INPUT => RESULT) f
      WHERE f.VALUE:recommendation:confidence::STRING = 'HIGH'
      ORDER BY DATABASE_NAME, SCHEMA_NAME, TABLE_NAME, COLUMN_NAME;

  - name: "Query Activity by Hour of Day"
    question: "What is the distribution of query activity by hour of day?"
    sql: |
      SELECT
        HOUR(QUERY_START_TIME) as HOUR_OF_DAY,
        COUNT(DISTINCT QUERY_ID) as QUERY_COUNT
      FROM __ACCESS_HISTORY
      WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY HOUR_OF_DAY
      ORDER BY HOUR_OF_DAY;

  - name: "Top Users by Query Count"
    question: "Who are the top 10 most active users based on query count?"
    sql: |
      SELECT
        USER_NAME,
        COUNT(DISTINCT QUERY_ID) as QUERY_COUNT
      FROM __ACCESS_HISTORY
      WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY USER_NAME
      ORDER BY QUERY_COUNT DESC
      LIMIT 10;

  - name: "Query Type Distribution"
    question: "What is the distribution of different query types?"
    sql: |
      SELECT
        QUERY_TYPE,
        COUNT(DISTINCT QUERY_ID) as QUERY_COUNT
      FROM __QUERY_HISTORY
      WHERE START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY QUERY_TYPE
      ORDER BY QUERY_COUNT DESC;

  - name: "Most Accessed Tables"
    question: "Which tables are accessed most frequently over the last 30 days?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          DIRECT_OBJECTS_ACCESSED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
      )
      SELECT
        o_flattened.value:objectName::STRING AS OBJECT_NAME,
        o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
        COUNT(DISTINCT QUERY_ID) as ACCESS_COUNT
      FROM base_access,
      LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened
      WHERE o_flattened.value:objectDomain::STRING = 'Table'
      GROUP BY OBJECT_NAME, OBJECT_DOMAIN
      ORDER BY ACCESS_COUNT DESC
      LIMIT 10;

  - name: "Column-Level Access Analysis"
    question: "Which specific columns are being accessed most frequently?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          USER_NAME,
          DIRECT_OBJECTS_ACCESSED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      )
      SELECT
        o_flattened.value:objectName::STRING AS OBJECT_NAME,
        c_flattened.value:columnName::STRING AS COLUMN_NAME,
        COUNT(DISTINCT QUERY_ID) as ACCESS_COUNT
      FROM base_access,
      LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened,
      LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE o_flattened.value:objectDomain::STRING = 'Table'
      AND c_flattened.value:columnName IS NOT NULL
      GROUP BY OBJECT_NAME, COLUMN_NAME
      ORDER BY ACCESS_COUNT DESC
      LIMIT 10;

  - name: "Policy Usage Analysis"
    question: "Which data masking and row access policies are being applied most frequently?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          POLICIES_REFERENCED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
        AND POLICIES_REFERENCED IS NOT NULL
      )
      SELECT
        p.value:policyName::STRING AS POLICY_NAME,
        p.value:policyKind::STRING AS POLICY_KIND,
        COUNT(DISTINCT QUERY_ID) as USAGE_COUNT
      FROM base_access,
      LATERAL FLATTEN(input => POLICIES_REFERENCED) r,
      LATERAL FLATTEN(input => r.value:policies) p
      GROUP BY POLICY_NAME, POLICY_KIND
      ORDER BY USAGE_COUNT DESC
      LIMIT 10;

  - name: "Column Masking Policy Analysis"
    question: "Which columns have masking policies applied to them?"
    sql: |
      SELECT
        ref_database_name AS database_name,
        ref_schema_name AS schema_name,
        ref_entity_name AS table_name,
        ref_column_name AS column_name,
        policy_name
      FROM
        __policy_references
      WHERE
        policy_kind = 'MASKING_POLICY'
        AND NOT ref_column_name IS NULL;

  - name: "DDL Operations Analysis"
    question: "What DDL operations are being performed most frequently?"
    sql: |
      SELECT
        GET_PATH(OBJECT_MODIFIED_BY_DDL, 'operationType')::STRING AS OPERATION_TYPE,
        GET_PATH(OBJECT_MODIFIED_BY_DDL, 'objectDomain')::STRING AS OBJECT_DOMAIN,
        COUNT(*) as OPERATION_COUNT
      FROM __ACCESS_HISTORY
      WHERE OBJECT_MODIFIED_BY_DDL IS NOT NULL
      AND QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY OPERATION_TYPE, OBJECT_DOMAIN
      ORDER BY OPERATION_COUNT DESC;

  - name: "Data Lineage: Modified Columns and Their Sources"
    question: "What is the lineage of data modifications showing source and target columns?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          USER_NAME,
          QUERY_START_TIME,
          OBJECTS_MODIFIED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
        AND OBJECTS_MODIFIED IS NOT NULL
      ), base_history AS (
        SELECT
          QUERY_ID,
          QUERY_TYPE
        FROM __QUERY_HISTORY
        WHERE START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      )
      SELECT
        QUERY_ID,
        QUERY_TYPE,
        USER_NAME,
        QUERY_START_TIME,
        o_flattened.value:objectName::STRING AS TARGET_OBJECT,
        c_flattened.value:columnName::STRING AS TARGET_COLUMN,
        ds.value:objectName::STRING AS SOURCE_OBJECT,
        ds.value:columnName::STRING AS SOURCE_COLUMN,
        'Direct Source' as SOURCE_TYPE
      FROM base_access JOIN base_history USING (QUERY_ID),
      LATERAL FLATTEN(input => OBJECTS_MODIFIED) o_flattened,
      LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened,
      LATERAL FLATTEN(input => c_flattened.value:directSources) ds
      WHERE c_flattened.value:directSources IS NOT NULL
      ORDER BY QUERY_START_TIME DESC
      LIMIT 100;

  - name: "Access History Flattened View"
    question: "How can I view a flattened view of access history for easier analysis?"
    sql: |
      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'direct_objects' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          __ACCESS_HISTORY,
          LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE
          query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())

      UNION ALL

      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'base_objects' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          __ACCESS_HISTORY,
          LATERAL FLATTEN(input => BASE_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE
          query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())

      UNION ALL

      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'objects_modified' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          __ACCESS_HISTORY,
          LATERAL FLATTEN(input => OBJECTS_MODIFIED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE
          query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP());

  - name: tables not accessed recently
    question: "show me tables not accessed in last 28 days"
    sql: |
      WITH direct_accessed_tables AS (
        SELECT
          DISTINCT CAST(
            GET_PATH(o_flattened.value, 'objectName') AS TEXT
          ) AS object_name
        FROM
          __access_history,
          LATERAL FLATTEN(input => direct_objects_accessed) AS o_flattened(SEQ, KEY, PATH, INDEX, VALUE, THIS)
        WHERE
          query_start_time >= DATEADD(DAY, -28, CURRENT_TIMESTAMP())
          AND CAST(
            GET_PATH(o_flattened.value, 'objectDomain') AS TEXT
          ) = 'Table'
      ),
      base_accessed_tables AS (
        SELECT
          DISTINCT CAST(
            GET_PATH(o_flattened.value, 'objectName') AS TEXT
          ) AS object_name
        FROM
          __access_history,
          LATERAL FLATTEN(input => base_objects_accessed) AS o_flattened(SEQ, KEY, PATH, INDEX, VALUE, THIS)
        WHERE
          query_start_time >= DATEADD(DAY, -28, CURRENT_TIMESTAMP())
          AND CAST(
            GET_PATH(o_flattened.value, 'objectDomain') AS TEXT
          ) = 'Table'
      ),
      accessed_tables AS (
          SELECT
          DISTINCT object_name as object_name FROM (
             SELECT * from direct_accessed_tables
             UNION ALL SELECT * from base_accessed_tables )
      ),
      all_tables AS (
        SELECT
          DISTINCT t.table_catalog || '.' || t.table_schema || '.' || t.table_name AS full_table_name
        FROM
          __tables AS t
        WHERE
          t.deleted IS NULL
      )
      SELECT
        a.full_table_name
      FROM
        all_tables AS a
        LEFT JOIN accessed_tables AS b ON a.full_table_name = b.object_name
      WHERE
        b.object_name IS NOT NULL
      ORDER BY
        a.full_table_name;

  - name: users enabled MFA
    question: "Do users MDOHERTY and HRANJAN have MFA enabled?"
    sql: |
      SELECT
        name AS user_name,
        has_mfa AS mfa_enabled
        FROM
        __USERS
        WHERE
        name IN ('MDOHERTY', 'HRANJAN')
        AND deleted_on IS NULL
        AND disabled = 'false';

  - name: users access to a given role
    question: "Are users RFEHRMANN and SACHARYA granted to BB_TEST role?"
    sql: |
      SELECT
        gtu.grantee_name AS user_name,
        gtu.role,
        CASE
          WHEN gtu.deleted_on IS NULL THEN 'Active'
          ELSE 'Revoked'
        END AS grant_status
      FROM
         __GRANTS_TO_USERS AS gtu
      WHERE  gtu.grantee_name IN ('RFEHRMANN', 'SACHARYA')
        AND gtu.role = 'BB_TEST';

  - name: role access to a given schema
    question: "Does PARTITIONED_LAB_USER role have access to PARTITIONED_SCHEMA schema in database PARTITIONED_DATABASE?"
    sql: |
      SELECT
        g.privilege
      FROM
        __grants_to_roles AS g
      WHERE
        g.grantee_name = 'PARTITIONED_LAB_USER'
        AND g.granted_on = 'SCHEMA'
        AND g.name = 'PARTITIONED_SCHEMA'
        AND g.table_catalog = 'PARTITIONED_DATABASE'
        AND g.deleted_on IS NULL;

  - name: show databases
    question: "show databases"
    sql: SELECT database_name, database_owner, is_transient, type, created FROM  __databases WHERE  deleted IS NULL;

  - name: show schemas
    question: "show schemas"
    sql:  SELECT CATALOG_NAME, SCHEMA_NAME, SCHEMA_OWNER, CREATED FROM __SCHEMATA WHERE deleted IS NULL;

  - name: show roles
    question: "show roles"
    sql: SELECT name, role_type, owner, created_on FROM __roles WHERE deleted_on IS NULL;

  - name: show masking policies
    question: "show masking policies"
    sql: SELECT policy_name, policy_schema, policy_catalog, policy_owner, policy_signature, policy_return_type, policy_body, policy_comment, created FROM __masking_policies WHERE deleted IS NULL;

  - name: show proj policies
    question: "show projection policies"
    sql: SELECT policy_name, policy_schema, policy_catalog, policy_owner, policy_signature, policy_return_type, policy_body, policy_comment, created FROM __projection_policies WHERE deleted IS NULL;

  - name: show agg policies
    question: "show aggregation policies"
    sql: SELECT policy_name, policy_schema, policy_catalog, policy_owner, policy_signature, policy_return_type, policy_body, policy_comment, created FROM __aggregation_policies WHERE deleted IS NULL;

  - name: show raps
    question: "show row access policies"
    sql: SELECT policy_name, policy_schema, policy_catalog, policy_owner, policy_signature, policy_return_type, policy_body, policy_comment, created FROM __row_access_policies WHERE deleted IS NULL;

  - name: show tags
    question: "show tags"
    sql: SELECT tag_name, tag_database, tag_schema, tag_owner, allowed_values, propagate, on_conflict, created FROM __tags WHERE deleted IS NULL;

  - name: show grant to role
    question: "show grants to role Accountadmin"
    sql: SELECT GRANTEE_NAME, GRANTED_BY, privilege, name, TABLE_CATALOG, TABLE_SCHEMA, grant_option, granted_on FROM __grants_to_roles WHERE grantee_name = UPPER('Accountadmin') AND deleted_on IS NULL;

  - name: show grants to user
    question: "show grants to user HRANJAN"
    sql: SELECT GRANTEE_NAME, GRANTED_BY, Role, CREATED_ON  FROM __grants_to_users WHERE grantee_name = UPPER('HRANJAN') AND deleted_on IS NULL;

  - name: show users
    question: "show users"
    sql: SELECT name, login_name, display_name, first_name, last_name, email, default_warehouse, default_role, has_mfa, created_on FROM __users WHERE deleted_on IS NULL AND disabled = 'false';

  - name: show tables
    question: "show tables"
    sql: SELECT table_catalog AS database_name, table_schema AS schema_name, table_name AS view_name, table_type as type, table_owner as owner, created  FROM __tables WHERE table_type like '%TABLE%' AND deleted IS NULL;

  - name: show tables in db
    question: "show tables in database SNOWFLAKE_DEMO_DB"
    sql: SELECT table_catalog AS database_name, table_schema AS schema_name, table_name AS view_name, table_type as type, table_owner as owner, created  FROM __tables WHERE table_type like '%TABLE%' AND table_catalog = UPPER('SNOWFLAKE_DEMO_DB') AND deleted IS NULL;

  - name: show views
    question: "show views"
    sql: SELECT table_catalog AS database_name, table_schema AS schema_name, table_name AS view_name, table_owner as owner, created  FROM __views WHERE deleted IS NULL;

  - name: show materialized views
    question: "show materialized views"
    sql: SELECT table_catalog AS database_name, table_schema AS schema_name, table_name AS view_name, table_type as type, table_owner as owner, created  FROM __tables WHERE table_type = 'MATERIALIZED VIEW' AND deleted IS NULL;

  - name: desc databases
    question: "desc databases KDD_DB"
    sql: SELECT database_name, database_owner, is_transient, type, created FROM  __databases WHERE database_name = UPPER('KDD_DB') AND deleted IS NULL;

  - name: desc schemas
    question: "desc schemas KDD_DB.public"
    sql:  SELECT CATALOG_NAME, SCHEMA_NAME, SCHEMA_OWNER, CREATED FROM __SCHEMATA WHERE SCHEMA_NAME = UPPER('public') AND CATALOG_NAME = UPPER('KDD_DB') AND deleted IS NULL;

  - name: desc user
    question: "desc user HRANJAN"
    sql: SELECT name, login_name, display_name, first_name, last_name, email, default_warehouse, default_role, has_mfa, created_on FROM __users WHERE name = UPPER('HRANJAN') AND deleted_on IS NULL AND disabled = 'false';

  - name: desc roles
    question: "desc roles ACCOUNTADMIN"
    sql: SELECT name, role_type, owner, created_on FROM __roles WHERE name = UPPER('ACCOUNTADMIN') AND deleted_on IS NULL;

  - name: desc tables
    question: "desc tables DBT_HISTORY"
    sql: SELECT table_catalog AS database_name, table_schema AS schema_name, table_name AS view_name, table_type as type, table_owner as owner, created  FROM __tables WHERE table_type like '%TABLE%' AND table_name = UPPER('DBT_HISTORY') AND deleted IS NULL;

  - name: desc views
    question: "desc views VW_MV_SUMMARY_HISTORY"
    sql: SELECT table_catalog AS database_name, table_schema AS schema_name, table_name AS view_name, table_owner as owner, created  FROM __views WHERE table_name = UPPER('VW_MV_SUMMARY_HISTORY') AND deleted IS NULL;

  - name: desc materialized views
    question: "desc materialized views MATERIALIZED_VIEW_REFRESH_HISTORY"
    sql: SELECT table_catalog AS database_name, table_schema AS schema_name, table_name AS view_name, table_type as type, table_owner as owner, created  FROM __tables WHERE table_type = 'MATERIALIZED VIEW'  AND table_name = UPPER('MATERIALIZED_VIEW_REFRESH_HISTORY') AND deleted IS NULL;

  - name: desc tags
    question: "desc tags ADDL_TAG"
    sql: SELECT tag_name, tag_database, tag_schema, tag_owner, allowed_values, propagate, on_conflict, created FROM __tags WHERE tag_name = UPPER('ADDL_TAG') AND deleted IS NULL;

  - name: explain tag
    question: "explain tag ADDL_TAG"
    sql: SELECT tag_name, tag_database, tag_schema, tag_owner, allowed_values, propagate, on_conflict, created FROM __tags WHERE tag_name = UPPER('ADDL_TAG') AND deleted IS NULL;


  - name: show only the name of databases
    question: "show the name of databases"
    sql: |
      SELECT
        database_name
      FROM
        __databases
      WHERE
        deleted IS NULL;

  - name: show only the name of databases including deleted
    question: "show database names, including deleted"
    sql: |
      SELECT
        database_name
      FROM
        __databases
      WHERE
        deleted IS NULL;

  - name: Columns starting with specific prefix
    question: "Which columns have names starting with 'fault_' or 'test_'?"
    sql: |
      SELECT
        TABLE_CATALOG,
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME
      FROM
        __columns
      WHERE
        (COLUMN_NAME ilike 'test_%' OR COLUMN_NAME ilike 'fault_%' )
        AND deleted is null
      ORDER BY 1, 2, 3, 4;

  - name: schemas with no tables
    question: "Which schemas have only views and no tables?"
    sql: |
      WITH db_objects AS (
        SELECT
          t.table_catalog,
          t.table_schema,
          t.table_type,
          COUNT(*) AS obj_count
        FROM
          __tables AS t
        WHERE
          t.deleted IS NULL
        GROUP BY
          t.table_catalog,
          t.table_schema,
          t.table_type
        ),
      db_with_tables AS (
        SELECT
          table_catalog,
          table_schema
        FROM
          db_objects
        WHERE
          table_type IN (
            'BASE TABLE',
            'TEMPORARY TABLE',
            'EXTERNAL TABLE',
            'EVENT TABLE'
          )
        GROUP BY table_catalog, table_schema
        ),
      db_with_views AS (
        SELECT
          table_catalog,
          table_schema,
          sum(obj_count) as number_of_views
        FROM
          db_objects
        WHERE
          table_type IN ('VIEW', 'MATERIALIZED VIEW')
        GROUP BY table_catalog,  table_schema
      )
      SELECT
        v.table_catalog as database_name,
        v.table_schema AS schema_name,
        v.number_of_views
      FROM
        db_with_views AS v
      LEFT JOIN db_with_tables  AS tab
      ON tab.table_catalog = v.table_catalog AND
          tab.table_schema = v.table_schema
      WHERE
        tab.table_catalog is NULL
      ORDER BY  1, 2;

  - name: dynamic tables
    question: "What are the dynamic tables created in my account?"
    sql: |
      SELECT table_catalog || '.' || table_schema || '.' || table_name AS full_table_name
      FROM __tables
      WHERE is_dynamic = 'YES'
        AND deleted IS NULL;

  - name: not changed initial password
    question: "Can I identify users who have never changed their initial password?"
    sql: |
      SELECT
        u.name AS username,
        u.login_name,
        u.created_on,
        u.password_last_set_time
      FROM
        __users AS u
      WHERE
        u.deleted_on IS NULL
        AND u.has_password = TRUE
        AND (u.password_last_set_time IS NULL OR u.password_last_set_time < DATEADD(SECOND, 1, u.created_on))
      ORDER BY
        u.created_on DESC NULLS LAST;

  - name: tables with more than 1 MP
    question: "Can you show me which tables have at least 2 masking policies?"
    sql: |
      WITH policy_counts AS (
        SELECT
          pr.ref_database_name,
          pr.ref_schema_name,
          pr.ref_entity_name,
          COUNT(DISTINCT pr.policy_id) AS masking_policy_count
        FROM
          __policy_references AS pr
        WHERE
          pr.policy_kind = 'MASKING_POLICY'
        GROUP BY
          pr.ref_database_name,
          pr.ref_schema_name,
          pr.ref_entity_name
        )
      SELECT
        ref_database_name AS database_name,
        ref_schema_name AS schema_name,
        ref_entity_name AS table_name,
        masking_policy_count
      FROM
        policy_counts
      WHERE
        masking_policy_count >= 2
      ORDER BY
        masking_policy_count DESC NULLS LAST;

  - name: columns with masking policy
    question: "how many columns with a masking policy do I have?"
    sql: |
      SELECT
        COUNT(
        DISTINCT CASE
          WHEN pr.policy_kind = 'MASKING_POLICY' THEN CONCAT(
          pr.ref_database_name,
          '.',
          pr.ref_schema_name,
          '.',
          pr.ref_entity_name,
          '.',
          pr.ref_column_name
          )
        END
        ) AS columns_with_masking_policy
      FROM
        __policy_references AS pr
      WHERE
        pr.policy_kind = 'MASKING_POLICY'
        AND pr.policy_status = 'ACTIVE';

  - name: tables I own
    question: "I have a table named DBT_HISTORY, show me the schema and database name for it."
    sql: |
      SELECT
        table_schema AS schema_name,
        table_catalog AS database_name,
        table_owner
      FROM
        __tables
      WHERE
        table_name = 'DBT_HISTORY'
        AND table_owner == current_role()
        AND deleted IS NULL;

  - name: policy body for unknown policy type
    question: "What is the policy body for policy rap?"
    sql: |
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'MASKING POLICY' as policy_type
      FROM
        __masking_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL

      union all
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'PROJECTION POLICY' as policy_type
      FROM
        __projection_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL

      union all
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'AGGREGATION POLICY' as policy_type
      FROM
        __aggregation_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL

      union all
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'ROW ACCESS POLICY' as policy_type
      FROM
        __row_access_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL;

  - name: what tags on tables
    question: "What tags are applied to my tables?"
    sql: |
      SELECT
        tr.tag_database || '.' || tr.tag_schema || '.' || tr.tag_name AS tag_path,
        tr.tag_value,
        tr.object_database || '.' || tr.object_schema || '.' || tr.object_name AS object_path
      FROM __tag_references AS tr
      WHERE tr.object_deleted IS NULL
        AND tr.domain = 'TABLE'
      ORDER BY tr.tag_database, tr.tag_schema, tr.tag_name, tr.object_database, tr.object_schema, tr.object_name;

  - name: second most use policy
    question: "What is the second most used policy for tables?"
    sql: |
      WITH policy_counts AS (
        SELECT pr.policy_name, COUNT(DISTINCT pr.policy_id) AS policy_count
        FROM __policy_references AS pr
        WHERE pr.policy_status = 'ACTIVE'
          AND pr.ref_entity_domain = 'TABLE'
        GROUP BY pr.policy_name
      ),
      ranked_policies AS (
        SELECT policy_name, policy_count,
        RANK() OVER (ORDER BY policy_count DESC NULLS LAST) AS rnk
        FROM policy_counts
      )
      SELECT policy_name, policy_count
      FROM ranked_policies
      WHERE rnk = 2;

  - name: variant column with masking policy
    question: "list text columns that are protected by a masking policy."
    sql: |
      SELECT
        pr.ref_database_name AS database_name,
        pr.ref_schema_name AS schema_name,
        pr.ref_entity_name AS table_name,
        pr.ref_column_name AS column_name,
        pr.policy_name
      FROM __policy_references AS pr
      JOIN __columns AS c
        ON pr.ref_database_name = c.table_catalog
        AND pr.ref_schema_name = c.table_schema
        AND pr.ref_entity_name = c.table_name
        AND pr.ref_column_name = c.column_name
      WHERE pr.policy_kind = 'MASKING_POLICY'
        AND c.data_type = 'TEXT'
        AND NOT pr.ref_column_name IS NULL
        AND c.deleted IS NULL;

  - name: most assigned masking policy with string(text) return type
    question: "which masking policy with String datatype assigned to table most?"
    sql: |
      WITH table_policy_counts AS (
        SELECT
          mp.policy_name,
          mp.policy_return_type,
          COUNT(DISTINCT CONCAT(pr.ref_database_name, '.', pr.ref_schema_name, '.', pr.ref_entity_name)) AS table_count
        FROM __policy_references AS pr
        JOIN __masking_policies AS mp ON pr.policy_id = mp.policy_id
        WHERE pr.policy_kind = 'MASKING_POLICY'
        AND mp.policy_return_type like '%TEXT%'
        GROUP BY mp.policy_name, mp.policy_return_type
      )
      SELECT policy_name, table_count
      FROM table_policy_counts
      ORDER BY table_count DESC NULLS LAST
      LIMIT 1;

  - name: tagged columns of a table
    question: "what are the columns in the table Staff that has TAG_WITH_MASKING_POLICY tag?"
    sql: |
      SELECT
         tr.object_name,
         tr.object_database,
         tr.object_schema,
         tr.column_name,
         tr.tag_name
      FROM __tag_references AS tr
      WHERE
         tr.domain = 'COLUMN'
         AND tr.object_name = UPPER('Staff')
         AND tr.tag_name = UPPER('TAG_WITH_MASKING_POLICY')
         AND tr.object_deleted IS NULL;

  - name: Directly dependent objects.
    question: "What views directly depend on kmcg_sc_cat.lddw_core.bod_itm?"
    sql: |
      SELECT
        REFERENCING_DATABASE,
        REFERENCING_SCHEMA,
        REFERENCING_OBJECT_NAME,
        REFERENCING_OBJECT_DOMAIN,
        DEPENDENCY_TYPE
      FROM
        __OBJECT_DEPENDENCIES
      WHERE
        REFERENCED_OBJECT_NAME = UPPER('bod_itm')
        AND REFERENCED_SCHEMA = UPPER('lddw_core')
        AND REFERENCED_DATABASE = UPPER('kmcg_sc_cat')
        AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
        ORDER BY
          REFERENCING_OBJECT_DOMAIN, REFERENCING_OBJECT_NAME
        ;
    use_as_onboarding_question: false

  - name: All indirect dependencies.
    question: "What views indirectly depend on kmcg_sc_cat.lddw_core.acct_mst?"
    sql: |
      WITH RECURSIVE downstream_dependencies AS (
        -- Anchor member: Start with the initial referenced object (e.g., a base table)
        SELECT
            REFERENCED_DATABASE AS base_db,
            REFERENCED_SCHEMA AS base_schema,
            REFERENCED_OBJECT_NAME AS base_object_name,
            REFERENCED_OBJECT_DOMAIN AS base_object_domain,
            REFERENCING_DATABASE AS current_db,
            REFERENCING_SCHEMA AS current_schema,
            REFERENCING_OBJECT_NAME AS current_object_name,
            REFERENCING_OBJECT_DOMAIN AS current_object_domain,
            REFERENCING_OBJECT_ID AS current_object_id,
            1 AS dependency_level,
            ARRAY_CONSTRUCT(REFERENCED_OBJECT_NAME, REFERENCING_OBJECT_NAME) AS dependency_path
        FROM
            __OBJECT_DEPENDENCIES
        WHERE
            REFERENCED_OBJECT_NAME = 'ACCT_MST'
            AND REFERENCED_SCHEMA = 'LDDW_CORE'
            AND REFERENCED_DATABASE = 'KMCG_SC_CAT'
            AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')

        UNION ALL

        -- Recursive member: Find objects that depend on the 'current_object_name' from the previous iteration
        SELECT
            dd.base_db,
            dd.base_schema,
            dd.base_object_name,
            dd.base_object_domain,
            od.REFERENCING_DATABASE,
            od.REFERENCING_SCHEMA,
            od.REFERENCING_OBJECT_NAME,
            od.REFERENCING_OBJECT_DOMAIN,
            od.REFERENCING_OBJECT_ID,
            dd.dependency_level + 1,
            ARRAY_APPEND(dd.dependency_path, od.REFERENCING_OBJECT_NAME)
        FROM
            __OBJECT_DEPENDENCIES od
        INNER JOIN
            downstream_dependencies dd ON
                od.REFERENCED_OBJECT_ID = dd.current_object_id
                AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
      )
      SELECT DISTINCT
          base_db,
          base_schema,
          base_object_name,
          base_object_domain,
          current_db,
          current_schema,
          current_object_name,
          current_object_domain,
          dependency_level,
          ARRAY_TO_STRING(dependency_path, ' -> ') AS full_dependency_chain
      FROM
          downstream_dependencies
      WHERE dependency_level > 1
      ORDER BY
          dependency_level, current_object_name;
    use_as_onboarding_question: false

  - name: All dependent objects.
    question: "What views depend on kmcg_sc_cat.lddw_core.acct_mst?"
    sql: |
      WITH RECURSIVE downstream_dependencies AS (
        -- Anchor member: Start with the initial referenced object (e.g., a base table)
        SELECT
            REFERENCED_DATABASE AS base_db,
            REFERENCED_SCHEMA AS base_schema,
            REFERENCED_OBJECT_NAME AS base_object_name,
            REFERENCED_OBJECT_DOMAIN AS base_object_domain,
            REFERENCING_DATABASE AS current_db,
            REFERENCING_SCHEMA AS current_schema,
            REFERENCING_OBJECT_NAME AS current_object_name,
            REFERENCING_OBJECT_DOMAIN AS current_object_domain,
            REFERENCING_OBJECT_ID AS current_object_id,
            1 AS dependency_level,
            ARRAY_CONSTRUCT(REFERENCED_OBJECT_NAME, REFERENCING_OBJECT_NAME) AS dependency_path
        FROM
            __OBJECT_DEPENDENCIES
        WHERE
            REFERENCED_OBJECT_NAME = 'ACCT_MST'
            AND REFERENCED_SCHEMA = 'LDDW_CORE'
            AND REFERENCED_DATABASE = 'KMCG_SC_CAT'
            AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')

        UNION ALL

        -- Recursive member: Find objects that depend on the 'current_object_name' from the previous iteration
        SELECT
            dd.base_db,
            dd.base_schema,
            dd.base_object_name,
            dd.base_object_domain,
            od.REFERENCING_DATABASE,
            od.REFERENCING_SCHEMA,
            od.REFERENCING_OBJECT_NAME,
            od.REFERENCING_OBJECT_DOMAIN,
            od.REFERENCING_OBJECT_ID,
            dd.dependency_level + 1,
            ARRAY_APPEND(dd.dependency_path, od.REFERENCING_OBJECT_NAME)
        FROM
            __OBJECT_DEPENDENCIES od
        INNER JOIN
            downstream_dependencies dd ON
                od.REFERENCED_OBJECT_ID = dd.current_object_id
                AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
      )
      SELECT DISTINCT
          base_db,
          base_schema,
          base_object_name,
          base_object_domain,
          current_db,
          current_schema,
          current_object_name,
          current_object_domain,
          dependency_level,
          ARRAY_TO_STRING(dependency_path, ' -> ') AS full_dependency_chain
      FROM
          downstream_dependencies
      ORDER BY
          dependency_level, current_object_name;
    use_as_onboarding_question: false

  - name: Find all sources for an object.
    question: "What are all of the table sources for the view kmcg_sc_cat.ld_scdm_bi_sl.xd_ship_info_v?"
    sql: |
      WITH RECURSIVE upstream_lineage AS (
        -- Anchor member: Start with the initial referencing object
        SELECT
            REFERENCING_DATABASE AS target_db,
            REFERENCING_SCHEMA AS target_schema,
            REFERENCING_OBJECT_NAME AS target_object_name,
            REFERENCING_OBJECT_DOMAIN AS target_object_domain,
            REFERENCED_DATABASE AS current_db,
            REFERENCED_SCHEMA AS current_schema,
            REFERENCED_OBJECT_NAME AS current_object_name,
            REFERENCED_OBJECT_DOMAIN AS current_object_domain,
            REFERENCED_OBJECT_ID AS current_object_id,
            1 AS lineage_level,
            ARRAY_CONSTRUCT(REFERENCING_OBJECT_NAME, REFERENCED_OBJECT_NAME) AS lineage_path
        FROM
            __OBJECT_DEPENDENCIES
        WHERE
            REFERENCING_OBJECT_NAME = 'XD_SHIP_INFO_V'
            AND REFERENCING_SCHEMA = 'LD_SCDM_BI_SL'
            AND REFERENCING_DATABASE = 'KMCG_SC_CAT'

        UNION ALL

        -- Recursive member: Find objects that the 'current_object_name' depends on from the previous iteration
        SELECT
            ul.target_db,
            ul.target_schema,
            ul.target_object_name,
            ul.target_object_domain,
            od.REFERENCED_DATABASE,
            od.REFERENCED_SCHEMA,
            od.REFERENCED_OBJECT_NAME,
            od.REFERENCED_OBJECT_DOMAIN,
            od.REFERENCED_OBJECT_ID,
            ul.lineage_level + 1,
            ARRAY_APPEND(ul.lineage_path, od.REFERENCED_OBJECT_NAME)
        FROM
            __OBJECT_DEPENDENCIES od
        INNER JOIN
            upstream_lineage ul ON
                od.REFERENCING_OBJECT_ID = ul.current_object_id
                AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
                AND od.REFERENCED_OBJECT_DOMAIN IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
      )
      SELECT DISTINCT
          current_db as database_name,
          current_schema as schema_name,
          current_object_name as table_name,
          ARRAY_TO_STRING(lineage_path, ' <- ') AS full_lineage_chain
      FROM
          upstream_lineage
      WHERE current_object_domain = 'TABLE'
      ORDER BY
          current_object_name;
    use_as_onboarding_question: false

  - name: Views dependent on table with no recent access
    question: "Identify views that are directly or indirectly dependent on table kmcg_sc_cat.lddw_bval.plng_vers_sch_brd_hdr and have not been queried in the last 90 days."
    sql: |
      WITH RECURSIVE
          -- Step 1: Find all views (and intermediate objects) that depend on the specified table.
          -- This CTE traces the downstream lineage from the base table to all views built upon it,
          -- directly or indirectly.
          downstream_views AS (
              -- Anchor member: Start with the initial referenced object (the base table)
              -- Replace the WHERE clause values with your specific table database, schema, and name
              SELECT
                  REFERENCING_OBJECT_ID AS view_id,
                  REFERENCING_DATABASE AS view_db,
                  REFERENCING_SCHEMA AS view_schema,
                  REFERENCING_OBJECT_NAME AS view_name,
                  REFERENCING_OBJECT_DOMAIN AS view_domain,
                  REFERENCED_DATABASE AS base_table_db,
                  REFERENCED_SCHEMA AS base_table_schema,
                  REFERENCED_OBJECT_NAME AS base_table_name,
                  1 AS dependency_level
              FROM
                  __OBJECT_DEPENDENCIES
              WHERE
                  REFERENCED_DATABASE = 'KMCG_SC_CAT'
                  AND REFERENCED_SCHEMA = 'LDDW_BVAL'
                  AND REFERENCED_OBJECT_NAME = 'PLNG_VERS_SCH_BRD_HDR'
                  AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')

              UNION ALL

              -- Recursive member: Find objects that depend on the 'current_object' from the previous iteration.
              -- Continue only if the referencing object is a view or materialized view.
              SELECT
                  od.REFERENCING_OBJECT_ID,
                  od.REFERENCING_DATABASE,
                  od.REFERENCING_SCHEMA,
                  od.REFERENCING_OBJECT_NAME,
                  od.REFERENCING_OBJECT_DOMAIN,
                  dv.base_table_db,
                  dv.base_table_schema,
                  dv.base_table_name,
                  dv.dependency_level + 1
              FROM
                  __OBJECT_DEPENDENCIES od
              INNER JOIN
                  downstream_views dv
                  ON od.REFERENCED_OBJECT_ID = dv.view_id
                  AND od.REFERENCED_OBJECT_DOMAIN = dv.view_domain
              WHERE
                  od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
          ),
          -- Step 2: Identify views that have been accessed recently using ACCESS_HISTORY.
          -- This CTE flattens the DIRECT_OBJECTS_ACCESSED array to identify individual accessed objects.
          recently_accessed_views AS (
              SELECT DISTINCT
                  accessed_obj.VALUE:objectId::NUMBER AS accessed_view_id,
                  accessed_obj.VALUE:objectName::VARCHAR AS accessed_view_name,
                  accessed_obj.VALUE:objectDomain::VARCHAR AS accessed_view_domain
              FROM
                  __ACCESS_HISTORY ah,
                  LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED) accessed_obj
              WHERE
                  ah.QUERY_START_TIME >= DATEADD(day, -90, CURRENT_TIMESTAMP())
                  AND accessed_obj.VALUE:objectDomain::VARCHAR IN ('View', 'Materialized view')
          )
      -- Final Step: Select views from the dependency lineage that are NOT in the recently_accessed_views list.
      SELECT
          dv.view_db,
          dv.view_schema,
          dv.view_name,
          dv.view_domain,
          dv.dependency_level
      FROM
          downstream_views dv
      LEFT JOIN
          recently_accessed_views rav
          ON dv.view_id = rav.accessed_view_id
      WHERE
          rav.accessed_view_id IS NULL -- This condition identifies views that have NO recent access
      ORDER BY
          dv.dependency_level, dv.view_db, dv.view_schema, dv.view_name;
    use_as_onboarding_question: false

  - name: tables not recently queried directly/indirectly
    question: "Identify all tables that have not been queried directly or indirectly in the last 180 days."
    sql: |
      WITH RECURSIVE
          -- Step 1: Get all active tables and views in the account.
          all_active_objects AS (
              SELECT
                  TABLE_ID AS object_id,
                  TABLE_CATALOG AS object_db,
                  TABLE_SCHEMA AS object_schema,
                  TABLE_NAME AS object_name,
                  TABLE_TYPE AS object_domain,
                  CREATED AS created_on,
                  LAST_ALTERED AS last_altered_on,
                  TABLE_OWNER AS object_owner
              FROM
                  __TABLES
              WHERE
                  DELETED IS NULL

              UNION ALL

              SELECT
                  TABLE_ID AS object_id,
                  TABLE_CATALOG AS object_db,
                  TABLE_SCHEMA AS object_schema,
                  TABLE_NAME AS object_name,
                  'VIEW' AS object_domain,
                  CREATED AS created_on,
                  LAST_ALTERED AS last_altered_on,
                  TABLE_OWNER AS object_owner
              FROM
                  __VIEWS
              WHERE
                  DELETED IS NULL
          ),
          -- Step 2: Identify all objects that have been accessed (directly) in the last 180 days using ACCESS_HISTORY.
          recently_accessed_objects AS (
              SELECT DISTINCT
                  aao.object_id,
                  aao.object_domain
              FROM
                  __ACCESS_HISTORY ah,
                  LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED) AS b_obj
              INNER JOIN
                  all_active_objects aao
                  ON aao.object_name = b_obj.value:objectName::STRING
                  AND aao.object_domain = b_obj.value:objectDomain::STRING
              WHERE
                  ah.QUERY_START_TIME >= DATEADD(day, -180, CURRENT_TIMESTAMP())
          ),
          -- Step 3: Recursive CTE to find all objects that are referenced by the current objects.
          recursive_downstream_path (object_id, object_domain) AS (
              -- Anchor member: Start with the recently accessed objects
              SELECT
                  object_id,
                  object_domain
              FROM
                  recently_accessed_objects

              UNION ALL

              -- Recursive member: Find objects that the current set (rdp.object_id is the referencing object) depends on.
              -- We select the REFERENCED_OBJECT_ID as the new object_id for the next iteration.
              SELECT
                  od.REFERENCED_OBJECT_ID AS object_id,
                  od.REFERENCED_OBJECT_DOMAIN AS object_domain
              FROM
                  __OBJECT_DEPENDENCIES od
              INNER JOIN
                  recursive_downstream_path rdp ON od.REFERENCING_OBJECT_ID = rdp.object_id
                                                AND od.REFERENCING_OBJECT_DOMAIN = rdp.object_domain
          ),
          -- Step 4: Combine all directly and indirectly queried/dependent object IDs from all paths.
          all_queried_and_dependent_ids_combined AS (
              SELECT object_id, object_domain FROM recursive_downstream_path
              UNION DISTINCT
              SELECT object_id, object_domain FROM recently_accessed_objects
          )
      -- Final Step: Select active objects from our initial list that are NOT found
      -- in the combined set of directly or indirectly queried objects.
      SELECT
          aao.object_db,
          aao.object_schema,
          aao.object_name,
          aao.object_domain,
          aao.object_owner,
          aao.created_on,
          aao.last_altered_on
      FROM
          all_active_objects aao
      LEFT JOIN
          all_queried_and_dependent_ids_combined aqdic
          ON aao.object_id = aqdic.object_id
          AND aao.object_domain = aqdic.object_domain
      WHERE
          aqdic.object_id IS NULL -- This condition filters for objects that were NOT found in the 'queried or dependent' set
          AND aao.object_domain ILIKE '%TABLE%'
      ORDER BY
          aao.object_db, aao.object_schema, aao.object_name;
    use_as_onboarding_question: false

  - name: sensitive views
    question: "Identify the 10 most frequently accessed views that are built upon tables containing system tags related to sensitive data."
    sql: |
      WITH
          -- Step 1: Identify tables that have columns classified with sensitive data tags.
          -- Snowflake's automatic classification applies 'SEMANTIC_CATEGORY' and 'PRIVACY_CATEGORY' tags to columns.
          -- The TAG_REFERENCES view records these assignments. When a tag is on a column,
          -- the OBJECT_NAME and OBJECT_ID in TAG_REFERENCES refer to the parent table.
          SensitiveTaggedTables AS (
              SELECT DISTINCT
                  tr.OBJECT_DATABASE AS sensitive_table_db,
                  tr.OBJECT_SCHEMA AS sensitive_table_schema,
                  tr.OBJECT_NAME AS sensitive_table_name,
                  tr.OBJECT_ID AS sensitive_table_id,
                  tr.TAG_NAME AS sensitive_tag_name,
                  tr.TAG_VALUE AS sensitive_tag_value
              FROM
                  __TAG_REFERENCES tr
              WHERE
                  tr.DOMAIN = 'COLUMN' -- System classification tags are applied to columns.
                  AND tr.TAG_NAME IN ('SEMANTIC_CATEGORY', 'PRIVACY_CATEGORY') -- These are the system tags for sensitive data.
                  AND tr.TAG_VALUE <> 'NONE'
                  AND tr.OBJECT_DELETED IS NULL
          ),
          -- Step 2: Find views that directly depend on these sensitive-tagged tables.
          SensitiveViews AS (
              SELECT DISTINCT
                  od.REFERENCING_DATABASE AS view_database,
                  od.REFERENCING_SCHEMA AS view_schema,
                  od.REFERENCING_OBJECT_NAME AS view_name,
                  od.REFERENCING_OBJECT_DOMAIN AS view_type,
                  od.REFERENCING_OBJECT_ID AS view_id,
                  stt.sensitive_table_db,
                  stt.sensitive_table_schema,
                  stt.sensitive_table_name,
                  stt.sensitive_tag_name,
                  stt.sensitive_tag_value
              FROM
                  __OBJECT_DEPENDENCIES od
              JOIN
                  SensitiveTaggedTables stt
                  ON od.REFERENCED_OBJECT_ID = stt.sensitive_table_id
              WHERE
                  od.REFERENCED_OBJECT_DOMAIN = 'TABLE'
                  AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
          ),
          -- Step 3: Calculate access frequency for these sensitive views over the last 30 days.
          ViewAccessFrequency AS (
              SELECT
                  accessed_obj.VALUE:objectId::NUMBER AS view_id,
                  accessed_obj.VALUE:objectName::VARCHAR AS view_name,
                  COUNT(DISTINCT ah.QUERY_ID) AS access_count
              FROM
                  __ACCESS_HISTORY ah,
                  LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED) accessed_obj
              WHERE
                  ah.QUERY_START_TIME >= DATEADD(day, -7, CURRENT_TIMESTAMP())
                  AND accessed_obj.VALUE:objectDomain::VARCHAR IN ('View', 'Materialized view')
              GROUP BY
                  accessed_obj.VALUE:objectId::NUMBER,
                  accessed_obj.VALUE:objectName::VARCHAR
          )
      -- Final Step: Join sensitive views with their access frequency and return top 10 most accessed.
      SELECT
          sv.view_database,
          sv.view_schema,
          sv.view_name,
          sv.view_type,
          COALESCE(vaf.access_count, 0) AS access_count_last_7_days,
          sv.sensitive_table_db,
          sv.sensitive_table_schema,
          sv.sensitive_table_name,
          sv.sensitive_tag_name,
          sv.sensitive_tag_value
      FROM
          SensitiveViews sv
      JOIN
          ViewAccessFrequency vaf
          ON sv.view_id = vaf.view_id
      ORDER BY
          access_count_last_7_days DESC, sv.view_database, sv.view_schema, sv.view_name
      LIMIT 10;
    use_as_onboarding_question: false

  - name: views with inheritied policy
    question: "Identify all tables or views that directly or indirectly depend on objects where the CONFIDENTIALITY_TYPE_DESC_POLICY row access policy is applied."
    sql: |
      WITH RECURSIVE
          -- Step 1: Find all tables with the specified projection policy.
          -- The POLICY_REFERENCES view lists objects (tables/views/columns) that have policies set on them.
          PolicyAppliedObjects AS (
              SELECT DISTINCT
                  pr.REF_ENTITY_NAME AS object_name,
                  pr.REF_ENTITY_DOMAIN AS object_domain,
                  pr.REF_DATABASE_NAME AS object_db,
                  pr.REF_SCHEMA_NAME AS object_schema,
                  policy_kind,
                  policy_name
              FROM
                  __POLICY_REFERENCES pr
              LEFT JOIN
                  __TABLES t
                  ON pr.REF_DATABASE_NAME = t.TABLE_CATALOG
                  AND pr.REF_SCHEMA_NAME = t.TABLE_SCHEMA
                  AND pr.REF_ENTITY_NAME = t.TABLE_NAME
                  AND pr.REF_ENTITY_DOMAIN ILIKE '%TABLE%'
                  AND t.DELETED IS NULL
              LEFT JOIN
                  __VIEWS v
                  ON pr.REF_DATABASE_NAME = v.TABLE_CATALOG
                  AND pr.REF_SCHEMA_NAME = v.TABLE_SCHEMA
                  AND pr.REF_ENTITY_NAME = v.TABLE_NAME
                  AND pr.REF_ENTITY_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
                  AND v.DELETED IS NULL
              WHERE
                  pr.POLICY_NAME = 'CONFIDENTIALITY_TYPE_DESC_POLICY'
                  AND pr.POLICY_KIND = 'ROW_ACCESS_POLICY'
          ),
          -- Step 2: Trace all tables and views that depend on the objects identified in Step 1.
          -- This CTE finds all downstream objects from the policy-applied tables/views.
          ImpactedObjects AS (
              -- Anchor member: Start with objects directly referencing the policy-applied objects.
              SELECT
                  od.REFERENCING_DATABASE AS object_db,
                  od.REFERENCING_SCHEMA AS object_schema,
                  od.REFERENCING_OBJECT_NAME AS object_name,
                  od.REFERENCING_OBJECT_DOMAIN AS object_domain,
                  od.REFERENCING_OBJECT_ID AS object_id,
                  pao.object_db AS policy_applied_object_db,
                  pao.object_schema AS policy_applied_object_schema,
                  pao.object_name AS policy_applied_object_name,
                  pao.object_domain AS policy_applied_object_type,
                  pao.policy_kind,
                  pao.policy_name,
                  1 AS dependency_level
              FROM
                  __OBJECT_DEPENDENCIES od
              JOIN
                  PolicyAppliedObjects pao
                  ON od.REFERENCED_DATABASE = pao.object_db
                  AND od.REFERENCED_SCHEMA = pao.object_schema
                  AND od.REFERENCED_OBJECT_NAME = pao.object_name
                  AND od.REFERENCED_OBJECT_DOMAIN = pao.object_domain
                  AND od.REFERENCED_OBJECT_DOMAIN = pao.object_domain
              WHERE
                  od.REFERENCING_OBJECT_DOMAIN IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
              UNION ALL

              -- Recursive member: Find objects that depend on the 'current_object' from the previous iteration.
              SELECT
                  od.REFERENCING_DATABASE,
                  od.REFERENCING_SCHEMA,
                  od.REFERENCING_OBJECT_NAME,
                  od.REFERENCING_OBJECT_DOMAIN,
                  od.REFERENCING_OBJECT_ID,
                  io.policy_applied_object_db,
                  io.policy_applied_object_schema,
                  io.policy_applied_object_name,
                  io.policy_applied_object_type,
                  io.policy_kind,
                  io.policy_name,
                  io.dependency_level + 1
              FROM
                  __OBJECT_DEPENDENCIES od
              INNER JOIN
                  ImpactedObjects io
                  ON od.REFERENCED_DATABASE = io.object_db
                  AND od.REFERENCED_SCHEMA = io.object_schema
                  AND od.REFERENCED_OBJECT_NAME = io.object_name
                  AND od.REFERENCED_OBJECT_DOMAIN = io.object_domain
              WHERE
                  od.REFERENCING_OBJECT_DOMAIN IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
          )
      -- Final Step: Select distinct impacted objects and their source policy-applied objects.
      SELECT DISTINCT
          io.object_db,
          io.object_schema,
          io.object_name,
          io.object_domain,
          io.dependency_level,
          io.policy_applied_object_db,
          io.policy_applied_object_schema,
          io.policy_applied_object_name,
          io.policy_applied_object_type,
      FROM
          ImpactedObjects io
      ORDER BY
          io.dependency_level, io.object_db, io.object_schema, io.object_name;
    use_as_onboarding_question: false

  - name: user schemas
    question: "Show the schemas I own"
    sql: |
      SELECT
        CATALOG_NAME,
        SCHEMA_NAME,
        SCHEMA_OWNER,
        CREATED
      FROM SCHEMATA
      WHERE
        SCHEMA_OWNER = CURRENT_ROLE()
        AND DELETED IS NULL;

  - name: user databases
    question: "List my databases for me"
    sql: |
      SELECT
        database_name,
        database_owner,
        is_transient,
        type,
        created
      FROM databases
      WHERE
        database_owner = CURRENT_ROLE()
        AND deleted IS NULL;

  - name: user row access policies
    question: "What row access policies I have created in last 30 days"
    sql: |
      SELECT
        policy_name,
        policy_schema,
        policy_catalog,
        policy_owner,
        policy_signature,
        policy_return_type,
        policy_body,
        policy_comment,
        created
      FROM row_access_policies
      WHERE
        policy_owner = CURRENT_ROLE()
        AND deleted IS NULL
        AND created >= DATEADD(DAY, -30, CURRENT_TIMESTAMP());

  - name: user masking policies
    question: list all masking policies I have created so far
    sql: |
      SELECT
        policy_name,
        policy_schema,
        policy_catalog,
        policy_owner,
        policy_signature,
        policy_return_type,
        policy_body,
        policy_comment,
        created
      FROM masking_policies
      WHERE
        policy_owner = CURRENT_ROLE()
        AND deleted IS NULL;

  - name: users having access to a given table
    question: Show all users that have access to database TICKETS_DB
    sql: |
      WITH RECURSIVE role_tree AS (
        SELECT grantee_name AS role_name
        FROM __grants_to_roles
        WHERE
          privilege IN ('USAGE', 'OWNERSHIP')
          AND granted_on = 'DATABASE'
          AND name = UPPER('DKUMAR')
          AND deleted_on IS NULL
        UNION ALL
        SELECT gtr.grantee_name AS role_name
        FROM __grants_to_roles AS gtr
        JOIN role_tree AS rt
        ON gtr.name = rt.role_name
        WHERE
          gtr.privilege = 'USAGE'
          AND gtr.granted_on = 'ROLE'
          AND gtr.deleted_on IS NULL
      )
      SELECT DISTINCT
      u.name,
      u.login_name,
      u.display_name,
      u.email
      FROM __users AS u
      JOIN __grants_to_users AS gtu ON u.name = gtu.grantee_name
      JOIN role_tree AS rt  ON gtu.role = rt.role_name
      WHERE
        u.deleted_on IS NULL
        AND gtu.deleted_on IS NULL;

  - name: users with select privilege on a table
    question: Who has SELECT privilege on table AVJOSHI_DEMOS.PUBLIC.CUSTOMERS?
    sql: |
      WITH RECURSIVE role_tree AS (
        SELECT
        grantee_name AS role_name,
        name AS object_name
        FROM __grants_to_roles AS gtr
        WHERE
          TABLE_CATALOG = 'AVJOSHI_DEMOS'
          AND TABLE_SCHEMA = 'PUBLIC'
          AND name = 'CUSTOMERS'
          AND granted_on = 'TABLE'
          AND gtr.privilege IN ('SELECT', 'OWNERSHIP')
        UNION ALL

        SELECT gtr.grantee_name AS role_name, rh.object_name
        FROM __grants_to_roles AS gtr
        JOIN role_tree AS rh ON gtr.name = rh.role_name
        WHERE
          gtr.privilege = 'USAGE'
          AND gtr.granted_on = 'ROLE'
          AND gtr.deleted_on IS NULL
      )
      SELECT DISTINCT
        u.name,
        u.login_name,
        u.display_name,
        u.email
      FROM __users AS u
      JOIN __grants_to_users AS gtu ON u.name = gtu.grantee_name
      JOIN role_tree AS rt  ON gtu.role = rt.role_name
      WHERE u.deleted_on IS NULL AND gtu.deleted_on IS NULL

  - name: why missing access
    question: What are the privileges required to allow role DEMO_USER to create new tables under TICKETS_DB
    sql: |
      WITH RECURSIVE required_roles AS (
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          gtr.name AS object_name
        FROM __grants_to_roles AS gtr
        WHERE
          gtr.granted_on = 'DATABASE'
          AND gtr.name = UPPER('TICKETS_DB')
          AND gtr.deleted_on is NULL
          AND gtr.privilege IN ('CREATE TABLE', 'OWNERSHIP')

      UNION ALL
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          rh.object_name
        FROM __grants_to_roles AS gtr
        JOIN required_roles AS rh
        ON gtr.name = rh.role_name
        WHERE
          gtr.granted_on = 'ROLE'
          AND gtr.deleted_on is NULL
      ), existing_roles AS (
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          gtr.name AS object_name
        FROM __grants_to_roles AS gtr
        WHERE
          gtr.granted_on = 'DATABASE'
          AND gtr.name = UPPER('TICKETS_DB')
          AND gtr.grantee_name = UPPER('DEMO_USER')
          AND gtr.privilege IN ('CREATE TABLE', 'OWNERSHIP')
          AND gtr.deleted_on is NULL
        UNION ALL
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          rh.object_name
        FROM __grants_to_roles AS gtr
        JOIN required_roles AS rh
        ON gtr.name = rh.role_name
        WHERE
          gtr.granted_on = 'ROLE'
          AND gtr.deleted_on is NULL
      )
      SELECT DISTINCT
        rr.role_name roles_with_access,
        IFF(er.role_name IS NULL, 'No', 'Yes') already_have_access
      FROM required_roles rr
      left join existing_roles er
      on rr.role_name = er.role_name;

  - name: given users manage access
    question: Can DGibbar manage access to any object in my account?
    sql: |
      WITH RECURSIVE ROLE_TREE AS
      (
        SELECT role as role_name
        FROM __grants_to_users
        WHERE grantee_name = UPPER('DGibbar')
          AND DELETED_ON is NULL

        UNION ALL

        SELECT gtr.NAME as role_name
        FROM __grants_to_roles gtr
        INNER JOIN ROLE_TREE rt ON gtr.grantee_name = rt.role_name
        WHERE
          gtr.privilege = 'USAGE' AND
          gtr.GRANTED_ON = 'ROLE' AND
          gtr.DELETED_ON is NULL
      )
      select
        gtr.privilege,
        gtr.name,
        gtr.table_catalog,
        gtr.table_schema,
        gtr.granted_on
      from ROLE_TREE all_roles
      INNER JOIN __grants_to_roles AS gtr
      ON gtr.grantee_name = all_roles.role_name
      WHERE
        gtr.privilege LIKE '%GRANT%'
        OR gtr.privilege = 'OWNERSHIP'
        OR gtr.privilege = 'MANAGE GRANTS'
      ;

  - name: overlapping roles
    question: Are there roles with overlapping privileges that could be consolidated?
    sql: |
      WITH role_privileges AS (
        SELECT
          grantee_name,
          granted_on,
          name,
          COALESCE(table_catalog, '') AS table_catalog,
          COALESCE(table_schema, '') AS table_schema,
          privilege
        FROM __grants_to_roles
        WHERE deleted_on IS NULL
        GROUP BY
          grantee_name,
          granted_on,
          name,
          table_catalog,
          table_schema,
          privilege
      ), overlapping_roles AS (
        SELECT
          r1.grantee_name AS role1,
          r2.grantee_name AS role2,
          r1.granted_on,
          r1.name AS object_name,
          r1.privilege,
          r1.table_catalog,
          r1.table_schema
        FROM role_privileges AS r1
        JOIN role_privileges AS r2
        ON r1.granted_on = r2.granted_on
          AND r1.name = r2.name
          AND r1.table_catalog = r2.table_catalog
          AND r1.table_schema = r2.table_schema
          AND r1.privilege = r2.privilege
          AND r1.grantee_name < r2.grantee_name
      )
      SELECT
        role1,
        role2,
        COUNT(
        DISTINCT CONCAT(granted_on, ':', table_catalog, '.', table_schema, '.', object_name, ':', privilege)
        ) AS shared_privileges,
        ARRAY_AGG(DISTINCT CONCAT(granted_on, ' ', privilege, ' ON ', object_name)) AS common_privileges
      FROM overlapping_roles
      GROUP BY role1, role2
      HAVING COUNT(DISTINCT CONCAT(granted_on, ':', object_name, ':', privilege)) > 1
      ORDER BY shared_privileges DESC NULLS LAST;
