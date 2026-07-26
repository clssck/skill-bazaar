---
name: Missing Relationships Detection
description: Detect when relationship count is suspiciously low and check primary key prerequisites
parent_skill: best-practices-audit
---

# Missing Relationships Detection

## When to Flag

**Only flag when relationships are suspiciously low:**

| Tables | Expected Min Relationships | Flag If          |
| ------ | -------------------------- | ---------------- |
| 2-3    | 1                          | 0 relationships  |
| 4-6    | 2                          | ≤1 relationship  |
| 7+     | 3                          | ≤2 relationships |

**AND** at least one of:

- Multiple tables share FK-like columns (e.g., `ACCOUNT_ID` in 3+ tables)
- Dimension table exists (table with `*_ID` as likely PK) but no relationships point to it

## Detection Steps

1. **Count existing relationships** vs table count
2. **If below threshold**: Identify potential relationship candidates
3. **For each candidate, check if at least one table has a primary key** on join columns
4. **Report findings with PK status**

## Output Format

**⚠️ Audit only IDENTIFIES - does not modify the model.**

```
### 🔗 MISSING RELATIONSHIPS ({count})

Relationship count ({current}) is low for {table_count} tables.

| Table A | Table B | Join Columns | PK Status |
|---------|---------|--------------|-----------|
| ORDERS | CUSTOMERS | CUSTOMER_ID → CUSTOMER_ID | ✅ CUSTOMERS has PK |
| LOGS | ACCOUNTS | ACCOUNT_ID, DEPLOYMENT → ... | ❌ Neither has PK |

### ⚠️ PRIMARY KEY ISSUES ({count})

At least one table must have a PK on the join columns:

| Table | Suggested PK Columns | Action |
|-------|---------------------|--------|
| ACCOUNTS | ACCOUNT_ID, DEPLOYMENT, DS | Verify with infer_primary_keys.py |
| PRODUCTS | PRODUCT_ID | Verify with infer_primary_keys.py |

**Options for missing primary keys:**
1. Use `infer_primary_keys.py` to validate uniqueness (OPTIMIZATION MODE)
2. User provides known primary key columns
```

## Next Steps

To fix: Route to **OPTIMIZATION MODE** → `optimization/relationship_optimization.md`

**⚠️ Primary keys must be verified/added BEFORE relationships can be created.**
