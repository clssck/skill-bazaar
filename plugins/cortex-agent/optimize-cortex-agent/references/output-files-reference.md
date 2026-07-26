# Output Files & Success Metrics Reference

**Purpose:** Workspace directory structure and success criteria for the optimization workflow.
**Used by:** All phases — workspace setup (Phase 1) and deployment summary (Phase 6).

---

## Workspace Directory Structure

```
<WORKSPACE_DIR>/
├── optimization_log.md                         # Running log (update continuously)
├── state.json                                  # Phase gate file (coordinator reads/writes)
├── versions/
│   ├── vYYYYMMDD-HHMM-baseline/                # Baseline version (Phase 1-3)
│   │   ├── agent_config.json                   # Original config
│   │   ├── instructions_orchestration.txt      # Original instructions
│   │   ├── tools_summary.txt                   # Tool inventory
│   │   └── evals/
│   │       └── eval_baseline/
│   │           ├── q01_response.json ... qNN_response.json
│   │           ├── evaluation_summary.json
│   │           └── analysis_notes.txt          # Your analysis
│   │
│   ├── vYYYYMMDD-HHMM-updated/                 # Updated version (Phase 4)
│   │   ├── instructions_orchestration.txt      # Updated instructions
│   │   ├── change_manifest.md                  # What changed
│   │   └── evals/
│   │       ├── eval_after_update/
│   │       │   ├── q01_response.json ... qNN_response.json
│   │       │   ├── evaluation_summary.json
│   │       │   └── comparison_vs_baseline.txt
│   │       └── eval_failed_retry/              # Optional: retry failed questions
│   │
│   └── vYYYYMMDD-HHMM-generalized/             # Generalized version (Phase 6)
│       ├── instructions_orchestration.txt      # Generalized instructions
│       ├── change_manifest.md                  # Generalization changes
│       └── evals/
│           ├── eval_generalized/
│           │   ├── q01_response.json ... qNN_response.json
│           │   ├── evaluation_summary.json
│           │   └── three_way_comparison.txt    # Baseline → Updated → Generalized
│           ├── eval_full/                      # Optional: full validation
│           ├── eval_edge/                      # Optional: edge cases only
│           └── eval_production_sample/         # Optional: production queries
│
└── DEPLOYMENT_SUMMARY.md                       # Final summary (optional, at workspace root)
```

---

## Measuring Success

Track these metrics throughout optimization:

| Metric | Baseline | Target | How to Measure |
|--------|----------|--------|----------------|
| **Accuracy** | Measure first | >80% | Evaluation results |
| **Instruction Size** | Measure first | <20KB | Character count |
| **Overfitting Issues** | N/A | 0 critical | Phase 5 analysis |
| **Regressions** | 0 | 0 | Evaluation comparison |

---

## Success Criteria

- ✅ >80% accuracy on evaluation set
- ✅ Zero critical overfitting issues
- ✅ Zero regressions from baseline to final
- ✅ Domain expert approval for production deployment

---

## Deployment Summary Template

```markdown
# Deployment Summary: [AGENT_NAME]

## Accuracy Improvement
- Baseline: X% (N/M)
- Final: Y% (N/M)
- Improvement: +Z percentage points

## Key Changes Made
1. [Change 1]
2. [Change 2]
...

## Instruction Size
- Baseline: X chars
- Final: Y chars (+Z%)

## Production Readiness
✅/❌ Evaluation accuracy target met
✅/❌ No critical overfitting issues
✅/❌ Generalized for production variations
✅/❌ Domain expert approved

## Monitoring Recommendations
- Collect production failures for next iteration
- Track accuracy on real user queries
- Update evaluation set with production edge cases
- Re-evaluate quarterly as data/tools change
```
