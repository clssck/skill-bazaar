---
name: Duplicates Detection
description: Detection rules and methodology for identifying duplicate instructions between custom instructions and core semantic model elements
parent_skill: best-practices-audit
---

# Duplicates Detection

## Purpose

Identify duplicate instructions between `module_custom_instructions`/`custom_instructions` fields and core semantic model elements (descriptions, synonyms, sample values). This helps eliminate redundancy, improve maintainability, and prevent conflicting guidance.

## Detection Methodology

### Step 1: Extract Custom Instructions

Extract all custom instructions from the semantic view:

1. **Module Custom Instructions** (recommended approach)
   - sql_generation instructions
   - question_categorization instructions
   - Other module-specific instructions

2. **Custom Instructions** (legacy field)
   - General instructions for SQL generation

### Step 2: Extract Core Semantic Model Elements

Extract all core semantic model elements:

1. **Descriptions**
   - Table descriptions
   - Column descriptions (dimensions, facts, time dimensions)
   - Metric descriptions
   - Filter descriptions

2. **Synonyms**
   - Table synonyms
   - Column synonyms

3. **Sample Values**
   - Column sample values

4. **Metrics**
   - Metric definitions and calculation logic
   - Aggregation functions and expressions

5. **Filters**
   - Filter definitions and conditions
   - Filter logic and predicates

**⚠️ EXCLUSION**: Do NOT compare custom instructions against VQRs (Verified Query Repository entries). VQRs serve a different purpose (providing example question-SQL pairs) and should not be considered duplicates of custom instructions.

### Step 3: Detect Duplicate Instructions

Compare custom instructions against core model elements:

#### 1. Instruction Text Extraction
   - Parse all instruction text from module_custom_instructions
   - Parse all instruction text from custom_instructions

#### 2. Semantic Model Content Extraction
   - Collect all descriptions
   - Collect all synonyms
   - Collect all sample values
   - Collect all metric definitions and logic
   - Collect all filter definitions and conditions

#### 3. Duplicate Detection

- **Check if instruction text repeats information from descriptions**
  - Example: Instruction says "customer_id is the unique identifier" while column description already states this
  - Similarity: Exact match or high similarity (>85%)

- **Check if instruction text repeats information from synonyms**
  - Example: Instruction mentions "'revenue' can be called 'sales'" while synonyms already define this
  - Similarity: Exact match or high similarity (>85%)

- **Check if instruction text repeats information from sample values**
  - Example: Instruction lists valid status values that are already in sample_values
  - Similarity: Exact match or high similarity (>85%)

- **Check if instruction text repeats metric logic**
  - Example: Instruction describes "Total revenue is calculated as SUM(order_amount)" while metric already defines this calculation
  - Similarity: Exact match or high similarity (>85%)

- **Check if instruction text repeats filter logic**
  - Example: Instruction states "Active customers have status = 'ACTIVE'" while filter already defines this condition
  - Similarity: Exact match or high similarity (>85%)

#### 4. Categorize Findings

- **Exact duplicates**: Instruction repeats model element verbatim (100% match)
- **High similarity**: Instruction conveys same information in different words (>85% similarity)
- **Partial overlap**: Instruction partially repeats model information (50-85% similarity)

## Output Format

For each duplicate detected, report:

1. **Type**: Description/Synonym/Sample Value/Metric/Filter duplication
2. **Instruction Location**: module_custom_instructions.{module} OR custom_instructions
3. **Instruction Text**: The duplicated instruction text
4. **Already in Model**: Where this information already exists in the core model
5. **Similarity Score**: Percentage match (if applicable)
6. **Impact**: Why duplication is problematic
7. **Resolution**: Recommendation to remove from instructions

## Resolution Strategy

Duplicated information should be **removed from custom instructions** and kept only in the core semantic model elements because:

1. **Single Source of Truth**: Prevents conflicting information between instructions and model definitions
2. **Easier Maintenance**: Update metric logic, filter conditions, descriptions, etc. in one place only
3. **Better Organization**: Information lives in its natural location (metrics in metrics section, filters in filters section, etc.)
4. **Clearer Instructions**: Custom instructions focus on unique guidance not already defined in the model elements

## Important Constraints

**⚠️ DO NOT recommend migrating custom_instructions to module_custom_instructions**

- Both custom_instructions and module_custom_instructions are valid fields
- DO NOT flag the use of custom_instructions as a duplicate issue
- DO NOT recommend converting custom_instructions to module_custom_instructions
- Focus ONLY on identifying duplicate content between instructions and model elements (descriptions, synonyms, sample values)
