# View Quota Shared Resources

View which resource domains and targets are configured on a quota.

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/shared-resources.md`

---

## How to View Shared Resources

### GET_QUOTA_SCOPE

Returns the full scope JSON including shared resources (when `ENABLE_QUOTA_WITH_SHARED_RESOURCE` is enabled for the account).

```sql
CALL {quota_fqn}!GET_QUOTA_SCOPE();
```

**Returns** a VARIANT with structure:
```json
{
  "user_tags": { ... },
  "shared_resources": [
    {
      "domain": "AI FUNCTION",
      "target": null
    },
    {
      "domain": "WAREHOUSE",
      "target": "MY_WAREHOUSE"
    }
  ]
}
```

- `domain`: The resource domain (e.g., `'AI FUNCTION'`, `'WAREHOUSE'`, `'CORTEX AGENT'`, `'SNOWFLAKE INTELLIGENCE'`, `'CORTEX_CODE'`)
- `target`: The specific target within the domain, or `null` if all targets in the domain are included

> **Note**: The `shared_resources` field is only present when the `ENABLE_QUOTA_WITH_SHARED_RESOURCE` account parameter is enabled. If the field is absent, shared resources are not configured or the feature is not enabled.

---

## Presenting Results

Show the user a table of configured shared resources:

```
| Domain              | Target         |
|---------------------|----------------|
| AI FUNCTION         | (all)          |
| WAREHOUSE           | MY_WAREHOUSE   |
```
