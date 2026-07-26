# Overfitting Detection & Generalization Guide

**Purpose:** How to identify instruction patterns too specific to evaluation questions, and how to generalize them for production.
**Used by:** Phase 5 (overfitting detection) and Phase 6 (generalization & validation).

---

## Detecting Overfitting

Read through updated instructions carefully and reason about production impact for each pattern.

### What to Look For

- Specific years, dates, or time periods from eval questions
- Specific company/account names used as examples
- Hardcoded numeric thresholds that only work for eval data scale
- Fixed result counts (e.g., "show top 10") without context
- Absolute value ranges specific to eval data
- Any patterns that seem too specific to the evaluation set

### How to Reason About Each Issue

**❌ Don't:** Just pattern-match for years/names
```
"Found '2025' in instructions - that's overfitting"
```

**✅ Do:** Reason about production impact
```
"Line 107 says 'First half of 2025' = Jan 1 - June 30, 2025. 

This is problematic because in production:
- Users will ask about 2026, 2027, etc.
- The instruction only defines 2025 specifically
- Next year, 'first half' won't be interpreted correctly

We should generalize to: 'First half' = Jan 1 - June 30 of *specified year*"
```

---

## Example Overfitting Analysis

```
I found 4 critical overfitting issues:

1. **Line 107: "First half of 2025" = Jan 1 - June 30, 2025**
   
   Why problematic: This hard-codes year 2025 from your evaluation questions.
   Production risk: In 2026, if a user asks "first half", the agent won't 
   know it means Jan-Jun 2026.
   Generalization needed: Define "first half" as Jan 1 - June 30 of 
   *specified year*, not a fixed 2025 date.

2. **Line 117: "AMD might match AMDOCS, AMD Holdings, etc."**
   
   Why problematic: "AMD" is a specific company name from Q7 in your eval set.
   Production risk: Users might search for other short names (IBM, HP, SAP, 
   GE) and won't have this warning.
   Generalization needed: Explain that short names may match unrelated 
   companies, give AMD as ONE example among others.

3. **Line 145: "Daily credits typically: SIS (10-1000), Total (10K-1M+)"**
   
   Why problematic: These absolute ranges came from your evaluation data scale.
   Production risk: A very large enterprise customer might have 10M daily 
   credits, or a small trial might have 5 credits.
   Generalization needed: Use relative comparisons instead of absolute ranges.

4. **Line 122: "Filter out accounts with <1000 total credits"**
   
   Why problematic: The 1000 threshold came from your eval data distribution.
   Production risk: For different question types or data scales, 1000 might 
   filter out important results or not filter enough.
   Generalization needed: Make filtering context-dependent.
```

### Prioritization

| Priority | Criteria |
|----------|----------|
| **Critical** | Will definitely cause production failures |
| **Medium** | Might cause issues in some scenarios |
| **Low** | Minor improvements |

---

## Generalization Patterns

### Time Periods

**BEFORE (overfit):**
```
"First half of 2025" = Jan 1 - June 30, 2025
"Last couple of months ending mid-October" = Aug 1 - Oct 15
```

**AFTER (generalized):**
```
**For time-based questions:**
- Standard period definitions:
  - "First half" or "H1" = January 1 - June 30 of specified year
  - "Second half" or "H2" = July 1 - December 31 of specified year
  - "Q1" = Jan-Mar, "Q2" = Apr-Jun, "Q3" = Jul-Sep, "Q4" = Oct-Dec
  - "Last/past [N] months" = N months before reference date
  - "Last/past [N] days/weeks" = N days/weeks before reference date
- Interpret relative terms based on context and current date
- When time period is ambiguous, ask for clarification
- Always specify exact date ranges in your tool queries
```

### Company/Entity Names

**BEFORE (overfit):** "AMD might match AMDOCS, AMD Holdings, etc."

**AFTER (generalized):** "Short company names (2-4 chars like AMD, IBM, HP) may match unrelated companies. For short names, ask user to confirm the exact entity or use more specific identifiers."

### Numeric Thresholds

**BEFORE (overfit):** "Daily credits typically: SIS (10-1000), Total (10K-1M+)"

**AFTER (generalized):** "SIS credits are typically 100-1000x smaller than total Snowflake credits. Use relative comparisons rather than absolute ranges, which vary by customer size."

### Result Counts

**BEFORE (overfit):** "Show top 10-20 results"

**AFTER (generalized):** Vary based on question type:
- "which account has highest X" → show 3-5
- "accounts with high X" → show 10-20
- "all accounts doing X" → show complete list with count

---

## Validation After Generalization

1. **Create new version folder** with generalized instructions
2. **Update agent** with generalized instructions
3. **Run final evaluation** — same method used throughout
4. **Three-way comparison:**

```
Optimization Journey:

Baseline:        4/13 (31%)    4,067 characters
Updated:        10/13 (77%)   12,637 characters (+210%)
Generalized:    13/13 (100%)  14,420 characters (+14% vs updated)

Question-by-Question:
Q#  Baseline  Updated  Generalized  Journey
Q1     ✗        ✓          ✓        Fixed in update, maintained
Q2     ✗        ✗          ✓        Fixed in generalization
...
```

**Key check:** Generalization should NOT regress any previously-fixed questions. If it does, the generalization was too aggressive and needs refinement.
