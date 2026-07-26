---
name: find-skill-and-plugin
description: >-
  Find, add, check, or update Cortex Code catalog skills and plugins in CoCo
  Desktop before using them. Use when the user asks to search "the catalog"
  (even without specifying skill or plugin), discover available skills or
  plugins, install a catalog skill or plugin, make an uninstalled `/skill` or
  `$skill` usable, or browse the skill or plugin marketplace/catalog. Uses the
  native Agent Settings catalog browse and import UI through the desktop's
  active Snowflake connection — not the cortex CLI. Do not use this for public
  Snowflake Marketplace datasets or apps; use marketplace-search for
  third-party data/product listings.
---

# Find Skill and Plugin (Desktop)

Use this skill to discover Cortex Code skills and plugins from the catalog and
install them locally through CoCo Desktop's native **Agent Settings** UI, which
runs through the desktop's active Snowflake connection (not the CLI connection).

CoCo Desktop has no `cortex skill find` / `cortex plugin find` search command.
Discovery happens by **browsing the catalog** — either from the native import
dialog's "Browse Catalog" button, or by giving the user a direct link to the
Skills & Plugins catalog page in Snowsight (see
[Give the user a direct catalog link](#give-the-user-a-direct-catalog-link)
below). Because there is no in-app search, providing the direct link and telling
the user to search for the skill/plugin there is the recommended way to help
them find something by keyword. Installation happens through the native
**catalog import**.

## Workflow

**Before doing anything**, read the user's request and pick exactly one path:

| What the user said | Path to follow |
|--------------------|----------------|
| Mentions "skill" (e.g. "find a skill", "install skill") | **Skill Workflow** only |
| Mentions "plugin" (e.g. "find a plugin", "add plugin") | **Plugin Workflow** only |
| Neither "skill" nor "plugin" | **Both** — offer skill browse and plugin browse |

If the user already has a `snow://skill_catalog/<DB>.<SCHEMA>.<NAME>` URI or an
FQN in hand, skip discovery and go straight to the import step below

---

### Skill Workflow

1. **Discover** — help the user find a skill in one of two ways:
   - **Recommended (direct link):** because there is no in-app search, build a
     direct link to the catalog page and tell the user to search for the skill
     there. See
     [Give the user a direct catalog link](#give-the-user-a-direct-catalog-link).
   - **Native browse dialog:**
     1. Open **Agent Settings** — click the profile or settings icon in the
        top-right corner of the chat panel (or use the menu).
     2. Navigate to the **Skills** tab.
     3. Click the **+** button to open the add-skill dropdown.
     4. Select **"Add from Skills Catalog"**.
     5. In the **"Import from Skills Catalog"** dialog, click **"Browse Skills
        Catalog"** to open the catalog in the browser and find a skill. Copy its
        `snow://skill_catalog/<DB>.<SCHEMA>.<NAME>` URI.

2. **Import** — back in the **"Import from Skills Catalog"** dialog:
   1. Paste the URI (`snow://skill_catalog/<DB>.<SCHEMA>.<NAME>`; any
      `/versions/version$N` suffix is optional — the base URI resolves to the
      latest version).
   2. Click **Import**.
   3. On the consent screen (**"Install this skill from the catalog?"**), click
      **OK**.
   4. Wait for the success toast: **`"Imported skill(s): <name>"`**.

3. **Confirm** — the skill appears under the **Skills** tab in Agent Settings.
   Use the installed skill's real name for future `$skill` or `/skill`
   references. A running agent may not auto-load a skill installed mid-turn, so
   do not assume `$skill` or `/skill` will resolve until a later turn.

For full documentation, see
[Import a skill from the catalog](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-desktop/skills#import-a-skill-from-the-catalog).

---

### Plugin Workflow

1. **Discover** — help the user find a plugin in one of two ways:
   - **Recommended (direct link):** because there is no in-app search, build a
     direct link to the catalog page and tell the user to search for the plugin
     there. See
     [Give the user a direct catalog link](#give-the-user-a-direct-catalog-link).
     (Skills and plugins share the same catalog page.)
   - **Native browse dialog:**
     1. Open **Agent Settings** — click the profile or settings icon in the
        top-right corner of the chat panel (or use the menu).
     2. Navigate to the **Plugins** tab.
     3. Click the **+** button to open the add-plugin dropdown.
     4. Select **"Add from Plugins Catalog"**.
     5. In the **"Import from Plugins Catalog"** dialog, click **"Browse Plugins
        Catalog"** to open the catalog in the browser and find a plugin. Copy its
        `snow://skill_catalog/<DB>.<SCHEMA>.<NAME>` URI.

2. **Import** — back in the **"Import from Plugins Catalog"** dialog:
   1. Paste the URI (version suffix optional).
   2. Click **Import**.
   3. On the consent screen (**"Install this plugin from the catalog?"**), click
      **OK**.
   4. Wait for the success toast:
      **`"Plugin '<name>' imported from the Plugins Catalog."`**.

3. **Confirm** — the plugin appears as a card with a **CATALOG** badge in the
   **Plugins** tab of Agent Settings.

For full documentation, see
[Import a plugin from the catalog](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-desktop/plugins#import-a-plugin-from-the-catalog).

---

### Both (default)

Only use this path when the user's request mentions neither "skill" nor
"plugin". Explain that skills and plugins live in separate catalog tabs, and ask
which they want to browse first (or offer both). Then follow the appropriate
Skill Workflow or Plugin Workflow above.

---

## Give the user a direct catalog link

Since CoCo Desktop has no search command, the most helpful way to let the user
find a skill or plugin by keyword is to give them a direct link to the Skills &
Plugins catalog page in Snowsight and tell them to search there. Skills and
plugins live on the **same** catalog page.

1. Resolve the account's Snowsight host, org, and account names by running this
   SQL through the active connection:

   ```sql
   SELECT CURRENT_ORGANIZATION_NAME() AS ORG,
          CURRENT_ACCOUNT_NAME()      AS ACCOUNT,
          SYSTEM$NA_SECURITY_URL('')  AS HOST_URL;
   ```

2. Build the catalog URL as:

   ```
   {host}/{org}/{account}/#/skills
   ```

   - `{host}` is the origin (`<scheme>://<host>`, no path) of `HOST_URL`. If
     `HOST_URL` is empty or unparseable, fall back to `https://app.snowflake.com`.
   - `{org}` and `{account}` are the `ORG` and `ACCOUNT` values, URL-encoded.
   - Example: `https://app.snowflake.com/MYORG/MYACCT/#/skills`

3. Present the link to the user and tell them to browse or search the catalog
   there for the skill/plugin they want, then copy its
   `snow://skill_catalog/<DB>.<SCHEMA>.<NAME>` link to import (see the import
   steps above).

If the SQL fails (e.g. insufficient privileges) and you cannot resolve the org
and account, fall back to `https://app.snowflake.com` and tell the user to sign
in and open **Skills & Plugins** (the `#/skills` page) in Snowsight.

---

## Determining artifact type from a URI

If the user gives a URI or FQN but is unsure whether it is a skill or a plugin,
determine the type through the active connection before importing:

```sql
DESCRIBE CORTEX EXTENSION "DB"."SCHEMA"."NAME";
```

Read the `type` column:
- `SKILL` → follow the **Skill Workflow** import step.
- `PLUGIN` → follow the **Plugin Workflow** import step.

If `DESCRIBE` fails:
- **Object not found** — the URI may be wrong or the extension was dropped. Show
  the error and stop.
- **Insufficient privileges** — the current role lacks `READ` on this extension.
  Ask the user to confirm the correct role is active in the desktop and that the
  publisher has granted access.

---

## Guardrails

- Do not run `cortex skill find`, `cortex plugin find`, `cortex skill add`, or
  `cortex plugin add` CLI commands — these use the CLI connection, not the
  desktop's active connection. The native catalog import downloads and registers
  the artifact through the active connection.
- Do not write directly to `~/.snowflake/cortex/skills.json` or the stage cache;
  the native import computes the correct cache path and registers the entry.
- Always recommend the user visit the relevant documentation link when guiding
  them through the import — include it in your response, not just on failure.
- Do not tell the user to use an uninstalled catalog skill with `$skill` or
  `/skill`; install it first.
- Do not assume the catalog SQL object name equals the installed skill name; use
  the actual installed name shown under Agent Settings.
- Do not use this skill for public Snowflake Marketplace datasets, Native Apps,
  or connectors; use `marketplace-search`.
- When the user explicitly says "skill", use only the Skill Workflow; when they
  say "plugin", use only the Plugin Workflow.
