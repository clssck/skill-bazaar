---
name: semantic-view
description: "Use for ALL requests that mention: create, build, debug, fix, troubleshoot, optimize, improve, analyze, or evaluate a semantic view — AND for requests about VQR suggestions, verified queries, verified query representations, seeding/generating queries, suggesting metrics, suggesting filters, recommending metrics/filters/facts, importing Tableau (.twb/.twbx/.tds/.tdsx) or Power BI (.pbit/.pbix) files, or enriching a semantic view. Also use for: evaluate semantic view, analyst evaluation, sql correctness evaluation, test my semantic view, run evaluation on semantic view, measure SQL generation accuracy, sql_correctness metric, verified query evaluation. This is the entry point - even if the request seems simple. DO NOT attempt to create, debug, or generate suggestions for semantic views manually - always invoke this skill first. This skill guides users through creation, setup, auditing, VQR suggestion generation, filter & metric suggestions, Tableau/Power BI imports, SQL generation debugging, and native Analyst Evaluations (sql_correctness) workflows for semantic views with Cortex Analyst."
---

# Semantic View Skill

## When to Use

When a user wants to create, debug, optimize semantic views, generate VQR (verified query) suggestions, or get filter & metric suggestions for Cortex Analyst. This is the entry point for all semantic view workflows including VQR and filter/metric suggestion generation.

## Prerequisites

- Fully qualified semantic view name (DATABASE.SCHEMA.VIEW_NAME)
- Snowflake access configured
- Python dependencies: `tomli`, `urllib3`, `requests`, `pyyaml`, `snowflake-connector-python`
  - Install via: `uv pip install tomli urllib3 requests pyyaml snowflake-connector-python`

## ⚠️ MANDATORY INITIALIZATION (Required Before ANY Workflow)

**Before creating, auditing, or debugging semantic views, you MUST complete initialization:**

### Step 1: Complete Setup ✋ BLOCKING

**Load**: [setup/SKILL.md](setup/SKILL.md)

**This will:**

- Get BASE_WORKING_DIR from user (where to create files)
- Create session directory WORKING_DIR (timestamped)

**After setup completes, you will have these variables:**

- `SKILL_BASE_DIR` - Script location
- `BASE_WORKING_DIR` - User's chosen base directory
- `WORKING_DIR` - Session directory: `{BASE_WORKING_DIR}/semantic_view_{TIMESTAMP}`

**DO NOT PROCEED until setup is complete.**

### Step 2: Workflow Routing and Available Skills ✋

**After setup completes**, you will be routed to the appropriate workflow based on whether you're working with a NEW or EXISTING semantic view.

#### Workflow Decision Tree

```
Setup/SKILL.md Part 2: Workflow Routing
    ↓
Determine: NEW, IMPORT, EXISTING, VQR SUGGESTIONS, or FILTER & METRIC SUGGESTIONS?
    ↓
┌────┴────┬──────────┬──────────┬──────────┐
↓         ↓          ↓          ↓          ↓
NEW     IMPORT    EXISTING   VQR       FILTERS &
↓         ↓          ↓      SUGGEST.   METRICS
Load    Load        Continue   ↓          ↓
creation/ import_     to     Load       Load
SKILL.md  tableau/  Part 3   vqr_       filters_and_
       OR import_           suggestions/ metrics_suggestions/
       powerbi/             SKILL.md    SKILL.md
       SKILL.md
    ↓        ↓          ↓
Create   Import     Create
creation/ Tableau   optimization/
subdir   or PBI     subdir
         file
    ↓        ↓          ↓
Generate Generate   Download
semantic semantic   existing
model    model      model
                       ↓
                   Present mode
                   selection
                       ↓
                   ┌───┴───┐
                   ↓       ↓
               AUDIT    DEBUG
                MODE     MODE
```

#### Supporting Skills Available

Throughout any workflow, you can load these supporting skills as needed:

**Validation**:

- **Load**: [validation/SKILL.md](validation/SKILL.md)
- **Purpose**: Validation procedures used by both audit and debug workflows
- **When to use**: To validate semantic models before applying changes

**Optimization Patterns**:

- **Load**: [optimization/SKILL.md](optimization/SKILL.md)
- **Purpose**: Library of optimization patterns for semantic view improvements (dimensions, metrics, filters, relationships, custom instructions)
- **When to use**: When you need guidance on specific optimization techniques for descriptions, synonyms, named filters, etc.

**Modeling Patterns** (advanced DDL/YAML constructs):

- **Load**: [patterns/SKILL.md](patterns/SKILL.md)
- **Purpose**: Catalog of 14 advanced Semantic View modeling patterns — each ships a tight DDL/YAML snippet for a specific modeling intent (period-over-period comparison, rolling/lag/YTD metrics, SCD2 / ASOF temporal joins, snapshot facts that must not sum across time, accumulating-snapshot funnels, multi-path metrics, role-playing dimensions, cross-entity derived metrics, multi-fact layouts, `PRIVATE` facts, computed-FK joins, AI metadata steering Cortex Analyst, and a six-scenario structural diagnostic).
- **When to use**: User wants to compare a metric to the same period last year/month (YoY, MoM, SPLY); build a rolling average, year-to-date total, or lag-N comparison; model a slowly-changing-dimension lookup (`valid_from`/`valid_to`, ASOF, "address active at order time"); track a snapshot fact that must not sum across time ("balance / inventory / headcount over time"); model a funnel across multiple milestone dates ("loan funnel", "applied → reviewed → decided → funded"); add a cross-entity derived metric (`% of total`, `net = gross − returns`); expose a `PRIVATE` fact only used inside the SV; join on a computed (non-physical) key; steer Cortex Analyst with verified queries / AI metadata; or diagnose a fan trap, "multi-path relationship not supported" error, or numbers that look inflated. Also when an audit / debug step identifies a structural issue that maps to one of these patterns.

**Upload**:

- **Load**: [upload/SKILL.md](upload/SKILL.md)
- **Purpose**: Upload optimized semantic view YAML to Snowflake
- **When to use**: Only when user explicitly requests deployment to Snowflake

**SVA verified-query SQL (reference)**:

- **Load**: [reference/sva_validate_verified_queries.md](reference/sva_validate_verified_queries.md) — compile-check VQR SQL (`validate_verified_queries`), bulk or inline
- **Load**: [reference/sva_expand_truncate_verified_query.md](reference/sva_expand_truncate_verified_query.md) — semantic ↔ physical SQL (`expand_verified_query` / `truncate_verified_query`)
- **When to use**: User asks to validate VQRs compile, expand/truncate verified query SQL, or you need SQL templates for `SYSTEM$CORTEX_ANALYST_SVA_TOOL` (use with a local YAML path from optimization setup or user-provided file)

**Time Tracking** (Optional):

- **Load**: [time_tracking/SKILL.md](time_tracking/SKILL.md)
- **Purpose**: Track execution time for tool calls and workflow steps
- **When to use**: Only if user explicitly requests time tracking

**⚠️ After setup, refer to Core Capabilities below for detailed information on each workflow.**

## Core Capabilities

**Routing note:** `setup/SKILL.md` Part 2 only chooses **Creation** vs **Optimization** (existing view → Part 3 download). **VQR Suggestions**, **Filters & Metrics Suggestions**, **Tableau Import**, and **Power BI Import** below are loaded **directly from this list** when the user’s intent matches — they **do not** require Part 3. For SVA SQL against a downloaded model, complete optimization setup first or use a user-supplied YAML path.

### Creation Mode

Create new semantic views from scratch with proper structure, relationships, and validation using table metadata and VQRs (SQL Queries).

**When to use**: User wants to CREATE a new semantic view (not optimize an existing one)

**Action**: Load [creation/SKILL.md](creation/SKILL.md)

### VQR Suggestions

Generate verified query suggestions by mining Cortex Analyst usage and Snowflake query history. Runs both modes in parallel and merges results.

**When to use**: User wants to suggest, generate, seed, or populate VQRs for a semantic view — including right after creation

**Action**: Load [vqr_suggestions/SKILL.md](vqr_suggestions/SKILL.md)

### Filters & Metrics Suggestions

Suggest metrics, named filters, and computed facts for a semantic view by mining Snowflake query history via `SYSTEM$CORTEX_ANALYST_SVA_TOOL`.

**When to use**: User wants to suggest, recommend, or auto-generate metrics, filters, or facts for a semantic view

**Action**: Load [filters_and_metrics_suggestions/SKILL.md](filters_and_metrics_suggestions/SKILL.md)

### Tableau Import Mode

Import Tableau workbooks (.twb, .twbx) and datasources (.tds, .tdsx) into Snowflake Semantic Views. Handles published datasources, custom SQL, and provides flexible deployment options.

**When to use**: User wants to IMPORT or CONVERT a Tableau file to a semantic view

**Trigger keywords**: import Tableau, convert Tableau, Tableau to semantic view, migrate workbook, .twb, .twbx

**Action**: Load [import_tableau/SKILL.md](import_tableau/SKILL.md)

### Power BI Import Mode

Import Power BI templates (.pbit) and desktop files (.pbix) into Snowflake Semantic Views. Handles M-query table resolution, DAX measures (with non-transpilable measures dropped), and target DB/schema remapping.

**When to use**: User wants to IMPORT or CONVERT a Power BI file to a semantic view

**Trigger keywords**: import Power BI, convert Power BI, Power BI to semantic view, migrate dashboard, .pbit, .pbix

**Action**: Load [import_powerbi/SKILL.md](import_powerbi/SKILL.md)

### Evaluate Semantic View

Run native Snowflake Analyst Evaluations against a semantic view's verified queries (sql_correctness metric).

**When to use**: User wants to evaluate, benchmark, or measure SQL generation accuracy of a semantic view — including running `sql_correctness`, checking for regressions, or validating improvements

**Trigger keywords**: evaluate semantic view, analyst evaluation, sql correctness, verified query evaluation, measure accuracy, test my semantic view, regression check

**Action**: Load [evaluate/SKILL.md](evaluate/SKILL.md)

### Optimization, Audit, and Debug

For working with EXISTING semantic views.

**When to use**: User wants to optimize, audit, or debug an existing semantic view

**Action**: Continue in setup/SKILL.md (Part 3)

#### 1. Audit and Optimize Loop

Comprehensive audit system for semantic views including:

1. VQR testing (behavioral — CA without VQR hints)
2. Best Practices verification
3. Custom Criteria evaluation
4. SVA VQR compile check (`validate_verified_queries` — see [reference/sva_validate_verified_queries.md](reference/sva_validate_verified_queries.md))

**Load**: [audit/SKILL.md](audit/SKILL.md) when user chooses AUDIT MODE

#### 2. Debug Loop

Targeted problem-solving for specific issues with SQL generation from natural language queries.

**Load**: [debug/SKILL.md](debug/SKILL.md) when user chooses DEBUG MODE

## Supporting Skills

### Validation

**Load**: [validation/SKILL.md](validation/SKILL.md) - Validation procedures used by both audit and debug workflows

### Optimization Patterns

**Load**: [optimization/SKILL.md](optimization/SKILL.md) - Library of optimization patterns for semantic view improvements (descriptions, synonyms, named filters, relationships, custom instructions)

### Modeling Patterns

**Load**: [patterns/SKILL.md](patterns/SKILL.md) when the user wants to apply a specific advanced modeling intent: a period-over-period comparison (YoY / MoM / SPLY); a rolling, YTD/QTD/MTD, or lag-N metric; an SCD2 lookup with `valid_from`/`valid_to` or an ASOF event-time join; a snapshot fact that must not sum across time (balance / inventory / headcount); an accumulating funnel across multiple milestone dates; routing a metric through a specific FK when one fact has two FKs to the same dim (multi-path `USING`); reusing the same physical dim under multiple roles; a cross-entity derived metric (`% of total`, `net = gross − returns`); splitting shared dims across multiple fact tables; a `PRIVATE` fact used only inside the SV; a join on a key that doesn't exist as a physical column (computed FK); steering Cortex Analyst with verified queries / `AI_SQL_GENERATION` / `AI_QUESTION_CATEGORIZATION` metadata; or diagnosing a fan trap / "multi-path relationship not supported" error / numbers that look inflated. Each pattern ships a tight DDL/YAML snippet, gotchas grounded in upstream `queries.sql`, and verbatim docs links.

### Time Tracking (Optional)

**Load**: [time_tracking/SKILL.md](time_tracking/SKILL.md) - Track execution time for tool calls and workflow steps (only load if user explicitly requests time tracking)

### Upload

**Load**: [upload/SKILL.md](upload/SKILL.md) - Upload optimized semantic view YAML to Snowflake (only load when user wants to deploy/upload)

### SVA verified-query SQL (reference)

**Load**: [reference/sva_validate_verified_queries.md](reference/sva_validate_verified_queries.md), [reference/sva_expand_truncate_verified_query.md](reference/sva_expand_truncate_verified_query.md) — Snowflake Analyst VQR compile validation and semantic/physical SQL conversion

## Workflow Decision Tree

**Complete visual representation of the initialization and routing flow:**

```
Start Session
    ↓
Step 1: Load setup/SKILL.md ✋
    ├─ Part 1: Directory Initialization
    │   ├─ Capture SKILL_BASE_DIR
    │   ├─ Get BASE_WORKING_DIR (ask or infer)
    │   └─ Create WORKING_DIR (semantic_view_{TIMESTAMP})
    │
    ├─ Part 2: Workflow Routing
    │   └─ Determine: NEW, IMPORT, EXISTING, VQR SUGGESTIONS, or FILTER & METRIC SUGGESTIONS?
    │       ↓
    │   ┌───┴───┬─────┬──────────┬──────────┐
    │   ↓       ↓     ↓          ↓          ↓
    │  NEW   IMPORT EXISTING  VQR       FILTERS &
    │   ↓       ↓     ↓      SUGGEST.   METRICS
    │  Load   Load  Continue    ↓          ↓
    │ creation/ import_ Part 3 Load       Load
    │ SKILL.md tableau/       vqr_        filters_and_
    │       OR import_       suggestions/ metrics_suggestions/
    │       powerbi/         SKILL.md    SKILL.md
    │       SKILL.md
    │
    └─ Part 3: Optimization Setup (if EXISTING)
        ├─ Create {WORKING_DIR}/optimization/
        ├─ Download semantic model
        └─ Present mode selection
            ↓
        ┌───┴───┐
        ↓       ↓
    AUDIT    DEBUG
     MODE     MODE
```

**See above for supporting skills available throughout any workflow.**

## Key Principles

1. **Progressive Disclosure**: Load skills incrementally as needed
2. **Modularity**: Each skill is self-contained and reusable
3. **User Confirmation**: Stop at mandatory checkpoints for user input
4. **Validation First**: Always validate before applying changes

## Rules

1. **⚠️ Test Locally First**: By default, test with local YAML files using `semantic_model_file` parameter. Only upload to Snowflake when user explicitly requests deployment.
2. **⚠️ MANDATORY CHECKPOINT FOR ALL OPTIMIZATIONS**: Before any actual semantic view optimization:
   - Wait for explicit user approval (e.g., "approved", "looks good", "proceed")
   - NEVER chain separate optimization edits without user approval between them
3. **⚠️ Always use `uv run python` for scripts**. DO NOT use `python script.py` or `python3 script.py`.
