---
name: data-governance
description: "**[REQUIRED]** for all Snowflake data governance tasks. Routes to six sub-skills: (1) horizon-catalog — access history, users, roles, grants, permissions, query history, compliance, catalog; (2) data-policy — [REQUIRED] masking, row access, projection, aggregation, join, and tokenization policies, tag-based policies (masking, tokenization, row access, projection, aggregation, join), protect sensitive data, column/TIMESTAMP masking, the 2-stage UI create flow triggered by `/data-governance Create a new <policy type> policy for me`; (3) sensitive-data-classification — [REQUIRED for ALL classification] PII, classify, data classification, manual/automatic classification, Classification Profile, auto_tag, custom classifiers, regex, semantic/privacy category, IDENTIFIER, QUASI_IDENTIFIER, SENSITIVE, SYSTEM$CLASSIFY, DATA_CLASSIFICATION_LATEST, GDPR/CCPA/PCI; (4) governance-maturity-score — governance posture, maturity score, assessment, recommendations; (5) observability-maturity-score — data observability, DMF coverage, quality monitoring maturity, lineage usage, observability assessment; (6) object-contacts — [REQUIRED] assign data steward, create contact, object contact, contact report, who owns this table, SET CONTACT, data stewardship. MUST be used for classification or masking tasks — do not answer from general knowledge. horizon-catalog is the fallback. Triggers: governance, access history, permissions, grants, roles, audit, compliance, catalog, masking policy, row access policy, projection policy, aggregation policy, join policy, JOIN_REQUIRED, tokenization policy, tokenize at write time, external tokenization, FPE, PII, sensitive data, classification, run classification, SYSTEM$CLASSIFY, classifier, classification profile, DATA_CLASSIFICATION_LATEST, detect PII, GDPR, CCPA, PCI, tag sensitive columns, governance maturity score, governance posture, how well governed, data observability, observability maturity, DMF coverage, lineage usage, observability assessment, data steward, object contact, assign contact, who owns this table, contact report, SET CONTACT, /data-governance Create a new policy."
---

# Data Governance

Route general data-governance, catalog & audit queries, data policy work, sensitive data classification, governance maturity assessment, and object contact management to the right sub-skill.

> **Fast-path: UI policy slash-commands.** If the user's first message starts with one of the data-governance UI slash-commands below, load `workflows/data-policy.md` AND the matching workflow file together, and follow the 2-stage UI workflow exclusively. Do not load other layers. Do not ask the universal intake questions.
>
> - `/data-governance Create a new <policy type> policy for me` (any of: masking, row access, projection, aggregation, join, tokenization) → also load `workflows/data-policy/L4_workflow_create_2stage_ui.md`
> - `/data-governance Edit the <POLICY_KIND> POLICY named <POLICY_NAME> located at <DB>.<SCHEMA>.` → also load `workflows/data-policy/L4_workflow_edit_2stage_ui.md`

## When to Use

Activate this skill when the user asks about any of:

- **Policy keywords**: "masking policy", "row access policy", "projection policy", "aggregation policy", "join policy", "tokenization policy", "data policy", "audit policies", "create policy", "policy best practices", "tag-based masking", "tag-based tokenization", "tag-based row access", "tag-based projection", "tag-based aggregation", "tag-based join", "tag-based policies", "role-based access control for columns", "protect sensitive data", "column masking", "TIMESTAMP masking", "JOIN_REQUIRED", "JOIN_CONSTRAINT", "tokenize at write time", "external tokenization", "FPE", "format-preserving encryption", "/data-governance Create a new policy"
- **Classification keywords** *(always use this skill if the keywords matches— do not answer with general knowledge or the catalog workflow)*: "PII", "sensitive data", "classify", "classification", "data classification", "manual data classification", "run data classification", "run classification", "run manual classification", "automatic data classification", "set up automatic classification", "enable automatic classification", "SYSTEM$CLASSIFY", "auto-classification", "find sensitive data", "classify my table", "classification profile", "Data Privacy Classification Profile", "privacy profile", "custom classifier", "create classifier", "regex pattern", "value regex", "semantic category", "privacy category", "IDENTIFIER", "QUASI_IDENTIFIER", "SENSITIVE", "DATA_CLASSIFICATION_LATEST", "detect PII", "find PII", "scan for PII", "GDPR compliance", "CCPA compliance", "PCI data detection", "auto-tag columns", "tag sensitive columns", "tag PII columns", "minimum_object_age_for_classification_days", "maximum_classification_validity_days", "auto_tag", "unset classification profile", "internal ID classifier", "internal code detection"
- **Catalog & audit keywords**: "access history", "who has access", "who accessed", "permissions", "role hierarchy", "grants", "audit trail", "query history", "object dependencies", "compliance", "catalog", "users", "roles", "schema change", "column changed", "column definition", "DDL history", "has column changed", "when was this column changed", "what is the data type of", "column metadata"
- **Governance maturity keywords**: "governance maturity score", "governance posture", "governance assessment", "governance health", "governance recommendations", "governance checklist", "how well governed is my account"
- **Observability maturity keywords**: "data observability score", "observability maturity", "observability assessment", "DMF coverage", "quality monitoring maturity", "pipeline monitoring maturity", "dashboard data quality", "BI tool monitoring", "external lineage", "lineage for RCA", "impact analysis readiness"
- **Object contact keywords**: "data steward", "object contact", "assign contact", "create contact", "contact report", "who owns this table", "who is responsible for", "SET CONTACT", "STEWARD contact", "ACCESS_APPROVAL contact", "SUPPORT contact", "data stewardship", "contact inheritance", "GET_CONTACTS"

## Workflow Decision Tree

```
User request
  |
  v
Step 1: Identify intent
  |
  ├── Masking policy / row access policy / projection policy / aggregation policy /
  |   join policy / tokenization policy / audit policies / tag-based policies (any kind) /
  |   role-based column access / protect sensitive data /
  |   column masking / TIMESTAMP masking / clean room joins / tokenize at write time
  |         └──> Load workflows/data-policy.md
  |             (data-policy.md checks the category-seeded UI slash-command
  |              `/data-governance Create a data policy for categories <...> [source=classification-wizard]`
  |              FIRST — routing to its category-seeded create workflow only when the message
  |              starts with that exact prefix AND carries the `[source=classification-wizard]`
  |              sentinel (the workflow then asks which policy type; masking or projection) —
  |              then falls back to detecting
  |              `/data-governance Create a new <policy type> policy for me`
  |              and its 2-stage UI workflow if matched.)
  |
  ├── PII / sensitive data / classification / data classification / run classification /
  |   manual data classification / automatic data classification / SYSTEM$CLASSIFY /
  |   classifier / custom classifier / create classifier / regex pattern / value regex /
  |   semantic category / privacy category / IDENTIFIER / QUASI_IDENTIFIER / SENSITIVE /
  |   classification profile / Data Privacy Classification Profile / DATA_CLASSIFICATION_LATEST /
  |   detect PII / find PII / scan for PII / auto-classification / GDPR / CCPA / PCI /
  |   auto-tag columns / tag sensitive columns / unset classification profile /
  |   minimum_object_age_for_classification_days / maximum_classification_validity_days / auto_tag
  |         └──> Load workflows/sensitive-data-classification.md
  |
  ├── Governance maturity score / governance posture / governance assessment /
  |   governance health / governance recommendations / governance checklist /
  |   how well governed
  |         └──> Load workflows/governance-maturity-score.md
  |
  ├── Data observability score / observability maturity / DMF coverage /
  |   quality monitoring maturity / lineage usage / observability assessment
  |         └──> Load workflows/observability-maturity-score.md
  |
  ├── Data steward / object contact / assign contact / create contact /
  |   contact report / who owns this table / SET CONTACT / GET_CONTACTS /
  |   contact inheritance / stewardship
  |         └──> Load workflows/object-contacts.md
  |
  └── Everything else (catalog, access, users, grants, roles, object deps,
      query history, compliance, or any governance question not matched above)
            └──> Load workflows/horizon-catalog.md  ← also the fallback
```

## Workflow

### Step 1: Route to Sub-skill

Identify the user's intent and load the matching sub-skill:

| User Intent | Sub-skill to Load |
|---|---|
| Masking policy, row access policy, projection policy, aggregation policy, join policy, tokenization policy, create policy, audit policies, policy best practices, tag-based masking, tag-based tokenization, tag-based row access, tag-based projection, tag-based aggregation, tag-based join, role-based column access, protect sensitive data, column masking, TIMESTAMP masking, JOIN_REQUIRED, JOIN_CONSTRAINT, tokenize at write time, external tokenization, FPE, `/data-governance Create a new <policy type> policy for me`, `/data-governance Create a data policy for categories <...> [source=classification-wizard]` | **Load** `workflows/data-policy.md` (which routes to the category-seeded create workflow FIRST when the message starts with the `Create a data policy for categories` prefix AND carries the `[source=classification-wizard]` sentinel — that workflow asks which policy type to create, masking or projection — else to the 2-stage UI workflow if that slash-command pattern matches, else to the standard create / audit workflows) |
| PII, sensitive data, classify, classification, data classification, run classification, manual data classification, automatic data classification, set up automatic classification, enable automatic classification, SYSTEM$CLASSIFY, auto-classification, custom classifier, create classifier, regex pattern, value regex, semantic category, privacy category, IDENTIFIER, QUASI_IDENTIFIER, SENSITIVE, classification profile, Data Privacy Classification Profile, minimum_object_age_for_classification_days, maximum_classification_validity_days, auto_tag, unset classification profile, DATA_CLASSIFICATION_LATEST, detect PII, find PII, scan for PII, GDPR/CCPA/PCI compliance detection, auto-tag columns, tag PII columns | **Load** `workflows/sensitive-data-classification.md` |
| Governance maturity score, governance posture, governance assessment, governance health, governance recommendations, governance checklist, how well governed | **Load** `workflows/governance-maturity-score.md` |
| Data observability score, observability maturity, DMF coverage, quality monitoring maturity, lineage usage, observability assessment, BI tool monitoring, external lineage | **Load** `workflows/observability-maturity-score.md` |
| Data steward, object contact, assign contact, create contact, contact report, who owns this table, who is responsible for, SET CONTACT, GET_CONTACTS, STEWARD/SUPPORT/ACCESS_APPROVAL contact, contact inheritance, data stewardship | **Load** `workflows/object-contacts.md` |
| Catalog, access history, who has access, permissions, grants, roles, users, query history, object dependencies, compliance, or any other governance or catalog related questions | **Load** `workflows/horizon-catalog.md` |

If the intent spans multiple areas (e.g., "classify my data and set up a masking policy"), load both sub-skills sequentially, starting with classification.

If intent is ambiguous, ask:

```
Which area can I help you with?

1. Horizon Catalog — Access history, who has access, role/grant analysis, object dependencies, compliance queries, catalog exploration
2. Data Policies — Masking policies, row access policies, projection policies
3. Sensitive Data Classification — Detect PII, set up auto-classification, create classifiers
4. Governance Maturity Score — Assess governance posture, score (0–5), recommendations
5. Observability Maturity Score — Assess data observability (DMFs, BI coverage, lineage), score (0–5), recommendations
6. Object Contacts — Assign data stewards, create contacts, generate contact reports, manage stewardship
```

### Step 2: Execute Sub-skill

Follow the loaded sub-skill's workflow completely. Each sub-skill is self-contained with its own templates, references, and stopping points.

**Fallback rule:** If any sub-skill cannot fully answer the question, load `workflows/horizon-catalog.md` for supplemental catalog context.

## Sub-skills

| Sub-skill | File | Purpose |
|---|---|---|
| Horizon Catalog | `workflows/horizon-catalog.md` | Full ACCOUNT_USAGE catalog: access, users, roles, grants, permissions, object dependencies, query history. Default fallback. |
| Data Policy | `workflows/data-policy.md` | **[REQUIRED]** Masking, row access, projection, aggregation, join, and tokenization policy creation and auditing; protect sensitive data; column and TIMESTAMP masking; UI 2-stage create flow via `/data-governance Create a new <policy type> policy for me` |
| Sensitive Data Classification | `workflows/sensitive-data-classification.md` | **[REQUIRED]** PII detection, run/manual/automatic data classification, Data Privacy Classification Profiles, auto-classification setup, GDPR/CCPA/PCI, custom classifiers |
| Governance Maturity Score | `workflows/governance-maturity-score.md` | Assess governance posture across Know/Protect/Monitor pillars; produce maturity score (0–5) and actionable recommendations |
| Observability Maturity Score | `workflows/observability-maturity-score.md` | Assess data observability (Quality Monitoring, BI Coverage, External Lineage, Lineage Usage); score (0–5) and recommendations |
| Object Contacts | `workflows/object-contacts.md` | **[REQUIRED]** Assign data stewards, create contacts, manage contact inheritance, generate contact reports, find objects by contact |

## Critical Rules

**Role hierarchy traversal (applies to ALL access, grants, roles, or permissions questions):**

Snowflake privileges flow BOTTOM-UP through the role hierarchy — a child role's privileges are automatically inherited by all parent roles. For ANY "who has access", "what roles can access X", or "which users have privilege on Y" question:

- **NEVER** answer using only direct grants — that misses users who inherit access through a parent role
- **ALWAYS** use `WITH RECURSIVE` to walk the full grant tree:

```sql
WITH RECURSIVE role_hierarchy AS (
  -- Base: roles directly granted the privilege on the target object
  SELECT grantee_name AS role_name
  FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
  WHERE name = UPPER('<object_name>')
    AND granted_on = '<OBJECT_TYPE>'        -- e.g. 'TABLE'
    AND privilege IN ('SELECT', 'OWNERSHIP')
    AND deleted_on IS NULL
  UNION ALL
  -- Recursive step: roles that have been granted a qualifying child role
  SELECT gtr.grantee_name
  FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES gtr
  JOIN role_hierarchy rh ON gtr.name = rh.role_name
  WHERE gtr.granted_on = 'ROLE'
    AND gtr.privilege = 'USAGE'
    AND gtr.deleted_on IS NULL
)
SELECT DISTINCT gu.grantee_name AS user_name
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS gu
JOIN role_hierarchy rh ON gu.role = rh.role_name
WHERE gu.deleted_on IS NULL;
```

A flat `UNION` between two independent queries only traverses one level and will silently miss users who inherit access two or more hops up the role tree.

## Stopping Points

- ✋ **On ambiguous intent**: Present the 6-option menu and wait for user selection before loading any sub-skill
- ✋ **Sub-skill stopping points**: Each sub-skill has its own mandatory stopping points — honour them
