# Quota Notifications & Thresholds

Configure notification thresholds and admin notification channels for a quota.

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/notifications.md`

---

## Workflow

### Step 1: Identify the Quota

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` to find the target quota.

---

### Step 2: Add Notification Thresholds

Collect:
- **Threshold percentage** (e.g., 50, 75, 100)
- **Spend strategy**: `PROJECTED` (default) or `ACTUAL`
- **Notify user**: TRUE or FALSE (whether the user gets an email)

```
At what percentage of the per-user limit should a notification fire?
Should it trigger on projected spend (proactive, default) or actual spend (precise)?
Should the user themselves be notified?
```

Use `ADD_NOTIFICATION_THRESHOLD` from reference file `references/quota/notifications.md`.

Ask "Would you like to add another threshold?" and repeat until done.

To remove a threshold, use `REMOVE_NOTIFICATION_THRESHOLD` from reference file `references/quota/notifications.md`.

---

### Step 3: Configure Admin Summary Notifications (Optional)

Admin summary notifications send aggregated reports of users who breach thresholds. Delivered in real-time after each quota evaluation that detects new breaches.

> **Prerequisite**: Before adding a notification integration, the user must run `GRANT USAGE ON INTEGRATION {name} TO DATABASE SNOWFLAKE`. See reference file for details.

**Option A: Notification Integration**

Use `ADD_NOTIFICATION_INTEGRATION` from reference file `references/quota/notifications.md`.

**Option B: Admin Emails**

Use `SET_ADMIN_EMAILS` from reference file `references/quota/notifications.md`.

> If both the notification integration and email list are null, admin summary notifications are suppressed.

---

### Step 4: Verify

Use `GET_NOTIFICATION_THRESHOLDS` and `GET_NOTIFICATION_INTEGRATIONS` from reference file `references/quota/notifications.md`.

Present results to the user.
