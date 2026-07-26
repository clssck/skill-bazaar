# Best Practices for AI Assistants

**Purpose:** Guidelines for effective agent optimization — analyzing failures, generating improvements, detecting overfitting, and communicating with users.
**Used by:** All phases of the optimization workflow.

---

## Analyzing Failures

**❌ Don't:** Use predefined failure categories
```
"This is a tool selection error" [forcing into predetermined bucket]
```

**✅ Do:** Discover actual patterns
```
"Looking at these 3 failures, they all asked for percentages but got absolute 
numbers. The common issue is the agent isn't computing the division. This is 
a calculation pattern issue, not covered by current instructions."

"Q7 and Q12 both routed to the wrong semantic model. Q7 used 'Streamlit in 
Snowflake' tool when the question asked about 'Streamlit Open Source'. Q12 
queried all AI/ML products when the question specifically asked for 'ML Platform' 
only. This is a tool routing and product disambiguation issue."
```

---

## Generating Improvements

**❌ Don't:** Provide generic template instructions
```
"Add: When user asks for X, do Y"
```

**✅ Do:** Create specific, actionable instructions
```
"Add this section:

## Proportion/Percentage Calculations

**For 'what percent' questions:**
- Calculate: (numerator / NULLIF(denominator, 0)) * 100
- Return: '67.4% (1.2M out of 1.8M total credits)'

**For 'highest proportion' questions:**
- Sort by percentage DESC (not absolute values)
- Return top N with percentages and raw numbers

This handles Q4 (what percent of credits...) and Q9 (highest proportion of spend...)"
```

---

## Detecting Overfitting

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

## Communicating with User

**Be specific about what you're doing:**
```
✅ "I'm going to query Snowflake for all agents in TEMP.NVYTLA schema"
✅ "Let me analyze Q4 - it asked for percentage but got absolute number"
✅ "I found 3 questions with the same pattern - percentage calculation issues"
```

**Ask for validation at key decision points:**
```
✅ "Does this failure categorization make sense to you?"
✅ "Would this instruction fix the issue?"
✅ "Should we prioritize fixing percentages or account matching first?"
```

**Show your reasoning:**
```
✅ "This pattern is overfit because [explanation + production risk]"
✅ "I categorized these together because [common root cause]"
✅ "This generalization handles [list of scenarios]"
```

---

## Common Pitfalls to Avoid

### 1. Accepting First Draft
```
❌ User approves first improvement suggestion → immediately update agent
✅ User approves → iterate on wording → show how it handles failed question → then update
```

### 2. Writing Eval-Specific Instructions
```
❌ "For 'first half of 2025' questions, use Jan 1 - June 30, 2025"
✅ Catch this yourself: "Wait, this is too specific to 2025. Let me generalize..."
```

### 3. Forcing Predefined Categories
```
❌ "Categorizing into: Tool Selection, Metric Confusion, Calculation, Data Quality"
✅ "Analyzing patterns... I see 3 distinct issues: percentage calculations, 
    account pattern matching, and time period interpretation"
```

### 4. Skipping Overfitting Check
```
❌ 77% accuracy → "Great improvement! Ready for production"
✅ 77% accuracy → "Good improvement! Let me check for overfitting before we deploy..."
```

### 5. Not Explaining Reasoning
```
❌ "This is overfit" [no explanation]
✅ "This is overfit because it hard-codes 2025. In production, users will ask 
    about other years and the agent won't know how to handle them."
```

---

## When to Escalate to User

**Ask user for input when:**
- **Ambiguous requirements:** "Should we prioritize accuracy or speed?"
- **Domain knowledge needed:** "What should the expected answer be for this question?"
- **Trade-off decisions:** "This instruction improves Q4 but might affect Q7. Which is more important?"
- **Validation needed:** "Does this failure categorization make sense?"
- **Approval required:** "Ready to update the agent with these changes?"

**Don't ask user for:**
- **Technical execution:** Just run the scripts
- **Obvious issues:** "I found an overfitting issue" (explain it, don't ask if it's an issue)
- **Analysis:** Do the analysis yourself, then present findings
