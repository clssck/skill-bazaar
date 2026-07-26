---
name: Inconsistencies Detection
description: Detection rules and methodology for identifying conflicting definitions, logical errors, and orphaned references across the semantic view
parent_skill: best-practices-audit
---

# Inconsistencies Detection

## Purpose

Identify conflicting definitions, logical errors, and structural inconsistencies across the semantic view that could lead to incorrect query results or model confusion.

## Detection Methodology

### Step 1: Build Cross-Reference Map

Create a comprehensive map of all components:

1. **Column Registry**
   - Map all columns by name across all tables
   - Track descriptions, data types and classifications

2. **Relationship Registry**
   - Map all relationships between tables
   - Track foreign keys and join conditions

3. **Metric Registry**
   - Map all measures and aggregations
   - Track calculation methods

### Step 2: Execute Detection Rules

Run all inconsistency checks:

#### 1. Column Inconsistencies

- **[PRIORITIZE THIS] Conflicting descriptions for same column**
  - Example: `order_date` has different descriptions across tables
  - Severity: MEDIUM (causes confusion)

- **Same column name with different data types**
  - Example: `customer_id` is NUMBER in one table, VARCHAR in another
  - Severity: CRITICAL (joins will fail)

- **Mixed dimension/measure classification**
  - Example: Column classified as both dimension and measure
  - Severity: HIGH (ambiguous usage)

#### 2. Relationship Inconsistencies

- **Orphaned relationships** (references non-existent tables/columns)
  - Severity: CRITICAL (will cause query failures)

- **Circular dependencies**
  - Example: Table A joins to B, B joins to C, C joins back to A
  - Severity: HIGH (can cause infinite loops)

- **Conflicting join conditions**
  - Example: Same relationship defined differently in multiple places
  - Severity: HIGH (unpredictable behavior)

#### 3. Type Inconsistencies

- **Dimension used as measure elsewhere**
  - Example: `product_category` defined as dimension but also used with COUNT aggregation
  - Severity: HIGH (ambiguous usage)

- **Measure used as dimension elsewhere**
  - Severity: HIGH (incorrect classification)

- **Time dimension type mismatches**
  - Example: Date column not marked as time dimension
  - Severity: MEDIUM (missed optimization opportunities)

#### 4. Aggregation Inconsistencies

- **Same measure with different aggregation functions**
  - Example: `revenue` uses SUM in one place, AVG in another
  - Severity: HIGH (conflicting logic)

- **Conflicting aggregation logic**
  - Severity: HIGH (wrong results)

#### 5. Filter Inconsistencies

- **Contradictory filter conditions**
  - Example: Filter requires both `status = 'active'` AND `status = 'inactive'`
  - Severity: CRITICAL (impossible conditions)

- **Overlapping filters with conflicts**
  - Severity: MEDIUM (unexpected behavior)

### Step 3: Categorize by Severity

Group findings by severity and type:

- **CRITICAL**: Will cause query failures or wrong results
- **HIGH**: Likely to cause confusion or unexpected behavior
- **MEDIUM**: May cause issues in specific scenarios
- **LOW**: Stylistic inconsistencies

## Output Format

For each inconsistency detected, report:

1. **Severity Level**: CRITICAL/HIGH/MEDIUM/LOW
2. **Detection Rule**: Which check detected it
3. **Issue Description**: What the inconsistency is
4. **Locations**: Where the conflicts occur
5. **Impact**: How this affects query results
6. **Resolution**: How to fix the issue
