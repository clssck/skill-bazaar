# Insight Quality Guardrails

Statistical validation rules for agent observability insights.

## Sample Size Thresholds

| Sample Size | Confidence Level | Action |
|-------------|------------------|--------|
| n < 10 | None | Suppress insight, note in `data_limitations` |
| n = 10-29 | Low | Report with warning: "Low confidence (n=X)" |
| n = 30-99 | Moderate | Report normally with sample size |
| n >= 100 | High | Report with full confidence |

## Feedback-Specific Rules

### Satisfaction Claims

| Feedback Count | Coverage | Action |
|----------------|----------|--------|
| < 10 responses | Any | Do NOT claim satisfaction rate |
| 10-29 responses | < 5% | Low confidence + coverage warning |
| 30+ responses | >= 5% | Report satisfaction normally |

### Required Context

Always include in feedback insights:
- Sample size (n)
- Coverage % (feedback / requests)
- Confidence level
- Time period

**Example:**
```
Satisfaction: 78% (n=45 responses, 3.2% coverage, moderate confidence)
```

## Language Rules

### Allowed Language

- "X is associated with Y"
- "Requests with X tend to have Y"
- "X correlates with Y"
- "X rate is Z% (above/below baseline)"
- "Data suggests X"

### Forbidden Language

- "X causes Y"
- "X leads to Y"
- "X results in Y"
- "Because of X, Y happens"
- Definitive causal claims without controlled experiments

## Baseline Comparisons

When making comparative claims, require:

1. **Explicit baseline stated**
   - "Error rate 5.2% (account average: 3.1%)"
   - "P90 latency 4.2s (target SLA: 3.0s)"

2. **Statistical significance considered**
   - For rates: require n >= 30 to claim difference
   - For percentiles: require n >= 100

3. **Time period alignment**
   - Compare same time periods (7d vs 7d)
   - Note if comparing different durations

## Trend Claims

### Short-term Trends (< 7 days)
- Do NOT claim trends with < 5 data points
- Label as "recent pattern" not "trend"

### Medium-term Trends (7-30 days)
- Require >= 7 data points
- Can use "trend" terminology

### Long-term Trends (> 30 days)
- Require >= 14 data points
- Full trend analysis appropriate

## Anomaly Detection

### Spike/Drop Claims
- Require 2+ standard deviations from mean
- OR 50%+ change from previous period
- Always provide context (baseline, expected range)

### Pattern Claims
- Require pattern to repeat 3+ times
- Note confidence in repeatability

## Output Requirements

### Every Insight Must Include

```json
{
  "insight": "string - the claim",
  "category": "usage|performance|quality|feedback|tool|conversation",
  "confidence": "low|moderate|high",
  "sample_size": "number",
  "baseline_comparison": "string|null",
  "time_period": "string",
  "warning": "string|null"
}
```

### Data Limitations Section

Always populate `data_limitations` with:
- Missing data categories
- Low sample size warnings
- Coverage gaps
- Time period constraints
- Schema differences encountered

## Validation Checklist

Before finalizing insights:

- [ ] Sample size meets threshold for claim type
- [ ] Confidence level assigned correctly
- [ ] No causal language used
- [ ] Baseline stated for comparative claims
- [ ] Time period explicitly noted
- [ ] Coverage calculated for feedback claims
- [ ] Data limitations documented
