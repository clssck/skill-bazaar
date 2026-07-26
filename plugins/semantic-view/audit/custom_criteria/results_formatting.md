---
name: Custom Criteria Results Formatting
description: Present custom criteria audit findings to user
parent_skill: custom-criteria-audit
---

# Custom Criteria Audit Results Formatting

## When to Load

Custom Criteria Audit Phase 6: Evaluation complete, need to present findings.

## Task

Present custom criteria validation results clearly with compliance rates, violations, and actionable recommendations.

## Present Summary

```
## Custom Criteria Audit Results

**Criteria Evaluated**: {total_criteria}
**Overall Compliance**: {overall_compliance}%

**Summary by Criterion**:
- ✅ Fully Compliant: {fully_compliant_count}
- ⚠️ Partially Compliant: {partially_compliant_count}
- ❌ Non-Compliant: {non_compliant_count}
```

## Present Each Criterion Result

### Fully Compliant (100%)
```
### ✅ CRITERION {n}: FULLY COMPLIANT

**Your Criterion**: "{original_user_input}"
**Interpretation**: {how_criterion_was_parsed}
**Scope**: Checked {total_checked} {component_type}(s)
**Result**: All components meet this criterion (100% compliance)
**Details**: {list passing components}
```

### Partially Compliant (1-99%)
```
### ⚠️ CRITERION {n}: PARTIALLY COMPLIANT ({compliance_rate}%)

**Your Criterion**: "{original_user_input}"
**Interpretation**: {how_criterion_was_parsed}
**Scope**: Checked {total_checked} {component_type}(s)
**Result**: ✅ Passing: {passing_count} | ❌ Failing: {failing_count} | Compliance: {compliance_rate}%

**Violations**:
1. {failing_component_1}
   - Issue: {specific_violation}
   - Expected: {expected_value} | Actual: {actual_value}
2. {failing_component_2}
   - Issue: {specific_violation}
   - Expected: {expected_value} | Actual: {actual_value}

**Recommendations**: {how_to_fix_violations}
```

### Non-Compliant (0%)
```
### ❌ CRITERION {n}: NON-COMPLIANT (0%)

**Your Criterion**: "{original_user_input}"
**Interpretation**: {how_criterion_was_parsed}
**Scope**: Checked {total_checked} {component_type}(s)
**Result**: No components meet this criterion (0% compliance)

**All Violations**: {list all failing components with issues}

**Recommendations**: {comprehensive_fix_strategy}
**Priority**: {HIGH/MEDIUM/LOW}
```

## Present Overall Compliance Score

```
## Overall Compliance Summary

**Compliance by Component Type**:
- Measures: {measure_compliance}%
- Dimensions: {dimension_compliance}%
- Tables: {table_compliance}%
- Relationships: {relationship_compliance}%

**Top Priority Actions**:
1. {highest_impact_fix}
2. {second_priority_fix}
3. {third_priority_fix}
```

## Compliance Thresholds & Priorities

- **✅ Fully Compliant**: 100%
- **⚠️ Partially Compliant**: 1-99%
- **❌ Non-Compliant**: 0%

**Priority Levels**:
- **HIGH**: Affects data integrity, query correctness, or breaks functionality
- **MEDIUM**: Affects usability, clarity, or consistency
- **LOW**: Stylistic or documentation improvements

## Next Action

Return to `custom_criteria/SKILL.md` Phase 7 for next steps prompt.
