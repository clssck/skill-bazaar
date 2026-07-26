---
name: declarative-sharing
description: "**[REQUIRED]** Use for **ALL** declarative sharing and application packages with TYPE=DATA, (i.e data apps). Share data products across Snowflake accounts with versioning. Default choice when user wants to share data with another account. Also use when converting an existing data share to declarative sharing, or when a consumer wants to migrate from a data share to a declarative app. Triggers: declarative, data product, native app, data app, data application, share, sharing, another account, cross account, cross region, application package, manifest, marketplace, listing, publish, share a table, share data, manifest from share, share to manifest, generate manifest from share, inspect share, share to yaml, introspect share, convert share, migrate share, existing share, secure share to declarative, upgrade share, future-proof share, multiple shares, combine shares, merge shares, multiple data shares, consumer migration, migrate from share, upgrade share to app, replace share with app, share to app migration, drop-in replacement, switch from share to app"
---

# Declarative Sharing (Data Apps)

Share data products with versioning, bundling, and app roles - without the complexity of full native apps.

**"Data app" = declarative share.** When a user says "data app", "data application", "bundle into an app", or "create an app they can install", they mean a declarative share (`TYPE = DATA` application package) — NOT a full native app. Only use the full native app framework if the user explicitly needs a setup script, consumer-side data access, or Snowpark Container Services.

## Intent Detection

Detect user intent and route to the appropriate workflow:

| User Intent | Route |
|-------------|-------|
| **Create/share data from scratch** — share objects, create a data app, build a package, create a listing (no existing data share) | Default workflow (Steps 1-6 below) |
| **Convert or create declarative share from one or more existing data shares** — provider has one or more traditional data shares (secure shares) and wants to migrate or combine them into declarative sharing, or use them as the starting point for a new declarative share | **Load** `workflows/manifest-from-share.md`, then continue with Steps 4-6 below |
| **Consumer migrating from data share to declarative app** — consumer has a database from a traditional data share and the provider has published a new declarative app (listing or package). Consumer wants to switch with zero downtime and no query changes | **Load** `workflows/consumer-share-migration.md` (standalone workflow, does NOT continue with Steps below) |

**Route to `workflows/manifest-from-share.md`** when the user mentions an existing data share (or multiple data shares) they want to convert or base the declarative share on. Common motivations:
- Migrating from traditional sharing to declarative sharing
- Combining multiple data shares into a single declarative share spanning multiple databases
- Adding new capabilities (notebooks, agents, semantic views) to an existing share
- Future-proofing a data share with versioning and app roles
- Getting versioning support for an existing share

After `workflows/manifest-from-share.md` produces the manifest, return here at **Step 4** to create and release the application package.

**Route to `workflows/consumer-share-migration.md`** when the user is a **consumer** (not provider) who already has a database from a traditional data share and wants to switch to a new declarative app. Key signals:
- User mentions having a shared database they want to replace/upgrade
- User mentions a listing name or app package from their provider
- User asks about migrating grants, renaming databases, or zero-downtime share migration
- User is on the **consumer** side (they received a share, not created one)

## When to Use This Skill

**Choose Declarative Sharing when cross-account sharing:**
- Sharing data with **another account** (recommend declarative sharing by default)
- Sharing **multiple related objects** (tables + views + agents + semantic views)
- Need **versioning** with automatic consumer updates
- Want **app roles** for granular access control within the share
- Sharing **Cortex Agents** or **semantic views**
- Even sharing a **single table** — declarative sharing provides versioning and a better upgrade path

**Use Traditional Data Sharing ONLY when:**
- User **explicitly** asks for a traditional data share (not an application package)
- Sharing a **single table or view** with **no future need** for bundling, versioning, or AI features
- No versioning or bundling needed and user confirms they don't want it

**Use Full Native Apps instead when:**
- Need a **setup script** to create objects in consumer account
- App must **access consumer's data** (with their permission)
- Require **Snowpark Container Services** or custom containers
- Building **Streamlit apps** → Use `apps/deploy-to-spcs` or `apps/build-react-app` skills

**Documentation**: [Declarative Sharing](https://docs.snowflake.com/en/developer-guide/declarative-sharing/about)

## Prerequisites

- Snowflake account with `CREATE APPLICATION PACKAGE` privilege
- Objects to share already exist (or will be created)

**Pre-flight check** (optional, skip if user says to proceed):
```sql
SHOW GRANTS ON ACCOUNT
  ->> SELECT "privilege", "grantee_name" FROM $1
      WHERE "privilege" = 'CREATE APPLICATION PACKAGE'
        AND "grantee_name" = CURRENT_ROLE();
```
If no rows returned, the current role lacks the privilege — switch to a role that has it or ask an ACCOUNTADMIN to grant it.

## Workflow

### Step 1: Determine What to Share

Ask or infer from context:

1. **What existing objects** need to be shared? (tables, views, functions, procedures)
   - Views MUST be SECURE (`CREATE SECURE VIEW`) — non-secure views will not work
2. **What additional entities** would enhance the data product?
   - **Cortex Agents** — use `agent-optimization` skill to create/optimize agents

**⚠️ AGENT RULES — READ ALL THREE:**

**1. Syntax:** `CREATE AGENT` / `CREATE OR REPLACE AGENT` — NOT `CREATE CORTEX AGENT` (does not exist). Do not analogize from `CREATE CORTEX SEARCH SERVICE`.

**2. execution_environment:** ALL tool types except Cortex Search require this in `tool_resources`:
```yaml
execution_environment:
  type: warehouse
  warehouse: ""
```
The empty string is correct — it resolves to the consumer's default warehouse at install time. Without this: generic tools (UDF/procedure) FAIL HARD, Analyst tools silently return no results.

**3. Provider-side testing:** Agents with `warehouse: ""` will fail when invoked on the provider side. This is expected — test in the consumer account or UI after sharing.
     - Note: Cortex Search not officially supported yet
   - **Semantic views** — do NOT hallucinate the DDL syntax; use `cortex search docs` to retrieve it
     - Note: verified_queries not yet supported in declarative sharing; avoid AI Optimization
   - **Notebooks** (CoCo CLI only, do not proactively suggest) — Do NOT create notebooks from CoCo Web; the workspace `write` tool corrupts notebook JSON, producing unparseable files. If a user explicitly asks for a notebook on CoCo Web, explain this limitation. From CoCo CLI: every code cell MUST have `"metadata": {"language": "sql"}` or `"language": "python"`, and **NEVER** put `%%sql` or any Jupyter magic in cell source. Notebooks can ONLY access data within the same application package.
   - **UDFs/procedures** for data transformation
     - SQL body MUST use `SCHEMA.TABLE` (relative), **NEVER** `DB.SCHEMA.TABLE` (FQN) — the provider DB doesn't exist on the consumer

**🛑 STOP — BEFORE writing ANY SQL that creates objects (agents, UDFs, procedures, semantic views, notebooks):**
1. **Read `references/create-objects.sql` NOW.** Do not guess syntax from memory.
2. **Copy the exact DDL template** from that file. Do not modify the command keywords.
3. Only skip this if you are sharing exclusively pre-existing tables/views with zero new objects.

### Step 2: Organize Schema Layout

Create all objects in the **source database** (the one the user pointed you to, or a database you already created for this task). **⚠️ NEVER create a database with the same name as the application package** — databases and application packages share the same namespace in Snowflake. If a database `X` exists, `CREATE APPLICATION PACKAGE X TYPE = DATA` will fail.

**Simple case** (only tables, or only views): Use the existing schema where objects already live. Skip schema creation — go straight to Step 3.

**Mixed objects** (agents + data, or UDFs + tables): Create new schemas **in the source database** — shared-by-copy and shared-by-reference objects **cannot be in the same schema**. **⚠️ `RELEASE LIVE VERSION` will fail if you put an agent in the same schema as tables/views.**

| Category | Objects | Schema |
|----------|---------|--------|
| **Shared-by-copy** | Agents, UDFs, procedures | `SHARED_BY_COPY_SCHEMA` |
| **Shared-by-reference** | Tables, views, semantic views, Cortex Search services | `SHARED_BY_REFERENCE_SCHEMA` |

```
SOURCE_DATABASE/          ← the database containing source data (NOT the package name)
├── SHARED_BY_COPY_SCHEMA /
│   ├── my_agent
│   └── my_udf()
└── SHARED_BY_REFERENCE_SCHEMA/
    ├── my_table
    └── my_semantic_view
```

### Step 3: Create Manifest

**🛑 STOP — Read `references/manifest.yml` NOW before writing any manifest YAML.** The format is non-standard and differs from what you expect. Do not guess.

**Minimal example** (sharing one table from scratch — when coming from `manifest-from-share.md`, use the manifest it generated instead):
```yaml
roles:
  - app_user:
      comment: "Read-only access"

shared_content:
  databases:
    - MY_DATABASE:
        schemas:
          - MY_SCHEMA:
              roles: [app_user]
              tables:
                - MY_TABLE:
                    roles: [app_user]
```

**Critical format rules:**
- Do NOT include `manifest_version` — it is auto-added on release
- Do NOT use `app_roles:` — the correct key is `roles:`
- Do NOT use `artifacts:`, `setup_script:`, `privileges:`, or `references:` — those are for native apps, NOT declarative sharing
- Database and schema names are map keys (with colon), NOT `name:` fields
- Object types are: `tables`, `views`, `semantic_views`, `cortex_agents`, `functions`, `procedures`, `cortex_search_services`
- Per-object `roles` must be a subset of the parent schema's `roles`
- **`required_databases`**: Almost always OMIT this. Only needed when a shared view's expansion references tables in a *different* database that isn't already in `shared_content/databases` — this tells Snowflake to replicate that database in cross-region scenarios. If all your objects live in the same database, do NOT add `required_databases`. It is NOT a place to list the databases you're sharing — that's what `shared_content/databases` is for

### Step 4: Create and Release Package

**🛑 STOP — Read `references/package-release.sql` NOW before running any package commands.** Do not guess syntax.

**⚠️ NEVER do these:**
- `CREATE DATABASE <PACKAGE_NAME>` — databases and app packages share the same namespace; this blocks `CREATE APPLICATION PACKAGE` with that name
- `CREATE CORTEX AGENT` — WRONG; correct is `CREATE AGENT` (no "CORTEX" keyword)
- `CREATE APPLICATION PACKAGE <PKG> DATA = TRUE` — WRONG syntax; correct is `TYPE = DATA`
- `CREATE APPLICATION PACKAGE <PKG> TYPE=SHARE` — WRONG; `TYPE=DATA`, not `TYPE=SHARE`
- `CREATE OR REPLACE APPLICATION PACKAGE ...` — no `OR REPLACE` for APPLICATION PACKAGES
- `CREATE OR REPLACE APPLICATION ...` — no `OR REPLACE` for APPLICATIONS (use DROP + CREATE)
- `ALTER APPLICATION PACKAGE ... ADD LIVE VERSION` — LIVE version is auto-created
- `ALTER APPLICATION PACKAGE ... REGISTER VERSION` — REGISTER is for release channels, not LIVE
- `PUT 'snow://workspace/...'` — PUT only accepts local `file://` URLs; use `COPY FILES` instead
- `SELECT $1 FROM snow://...` — not supported for application packages
- `SET DEFAULT RELEASE DIRECTIVE` — wrong command for LIVE version
- `GRANT REFERENCE_USAGE ON DATABASE ...` — NOT needed; the manifest handles all access automatically
- `GRANT USAGE ON DATABASE/SCHEMA ... TO APPLICATION PACKAGE` — NOT needed for declarative sharing; this is traditional sharing syntax

**Note:** Snowflake uppercases unquoted identifiers. If you create `my_pkg`, it becomes `MY_PKG`. Use the uppercased name in `snow://` URLs: `snow://package/MY_PKG/versions/LIVE/`.

**Environment check** — your system prompt tells you which environment you're in. Use exactly one path below:
- `"You are in a Workspace"` → **CoCo Web (Workspaces)** — has `write`/`read`/`edit` tools
- `"You are NOT in a Workspace"` → **CoCo Web (Non-Workspaces)** — NO file tools, must use stage method
- CLI / terminal → **CoCo CLI** — has `write`/`read`/`edit` tools, local filesystem

**Step 4.1** — Create package (copy this verbatim — do NOT guess variations):
```sql
CREATE APPLICATION PACKAGE <PKG> TYPE = DATA;
```
If unsure about ANY step below, re-read `references/package-release.sql` NOW before proceeding.

**Step 4.2** — Write and upload `manifest.yml`. Follow your environment path:

**CoCo Web (Workspaces):**
1. Write `manifest.yml` via `write` tool. User can review/edit before upload.
2. Upload:
```sql
COPY FILES INTO snow://package/<PKG>/versions/LIVE/
  FROM 'snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/'
  FILES = ('manifest.yml');
```

**CoCo Web (Non-Workspaces):**
You do NOT have `write`/`read`/`edit` tools. Recommend the user open a Workspace for the best experience: *"For file management and easier editing, open a Workspace in Snowsight (Projects > Workspaces) and start a new CoCo chat there."*

If the user wants to proceed without Workspaces, use the stage method — write YAML directly to a stage using `$$` dollar-quoting and a passthrough file format:
```sql
CREATE OR REPLACE TEMPORARY STAGE manifest_stage;
COPY INTO @manifest_stage/manifest.yml FROM (
  SELECT $$<entire manifest YAML here>$$
)
FILE_FORMAT = (TYPE = CSV COMPRESSION = NONE FIELD_OPTIONALLY_ENCLOSED_BY = NONE ESCAPE = NONE ESCAPE_UNENCLOSED_FIELD = NONE)
SINGLE = TRUE OVERWRITE = TRUE;

COPY FILES INTO snow://package/<PKG>/versions/LIVE/
  FROM @manifest_stage
  FILES = ('manifest.yml');
```
Use `$$` dollar-quoting to avoid escaping issues in YAML. The four FILE_FORMAT params are all required — without them Snowflake adds compression, backslash escaping, or quoting that corrupt the YAML.

**CoCo CLI:**
1. Write `manifest.yml` via `write` tool. User can review/edit before upload.
2. Upload:
```sql
PUT file:///workspace/manifest.yml snow://package/<PKG>/versions/LIVE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

**Step 4.3** (optional, **CoCo CLI only**) — Write notebook `.ipynb` via `write` tool.
**⚠️ Do NOT create notebooks on CoCo Web (any tab).** The workspace `write` tool corrupts notebook JSON, and the stage method cannot produce valid notebook JSON. If the user asks for a notebook on CoCo Web, explain this limitation. Do not proactively suggest notebooks.

**Step 4.3a** — **Notebook sanitization** (CoCo CLI only — REQUIRED before uploading ANY `.ipynb`):
After writing the notebook, **re-read** it and verify:
- **No** `%%sql`, `%%sql -r dataframe_N`, or any `%%` magic prefix in any cell `"source"`
- **No** `"resultVariableName"` in cell `"metadata"`
- Every code cell has `"metadata": {"language": "sql"}` or `"metadata": {"language": "python"}`
If any magic is present, `edit` the file to strip it. Then add a second `PUT` for the `.ipynb` file.

**Step 4.4** — Verify upload before releasing:
```sql
LIST snow://package/<PKG>/versions/LIVE/;
```
**If 0 rows: do NOT release.** Debug the upload — the file path or environment may be wrong. Re-check Step 4.2.

**Step 4.5** — Release (MUST be LAST, ONLY after LIST confirms files are present):
```sql
ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION;
```

**⚠️ STOP**: Confirm package created and LIVE version released before proceeding.

### Step 4A: Modifying an Existing Package

Use this flow when the user wants to **modify** a package that already exists — e.g., update the manifest or add new files. Skip Steps 1-4 above; jump directly here.

**Step 4A.1** — List current files:
```sql
LIST snow://package/<PKG>/versions/LIVE/
```

**Step 4A.2** — Download files for editing:

**CoCo Web (Workspaces):**
```sql
COPY FILES INTO 'snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/'
  FROM snow://package/<PKG>/versions/LIVE/
  FILES = ('manifest.yml');
```
Then `read`/`edit` the file in the workspace.

**CoCo Web (Non-Workspaces):**
Recommend the user switch to Workspaces for easier editing. If they decline, download to a stage and read:
```sql
CREATE OR REPLACE STAGE download_stage;
COPY FILES INTO @download_stage/
  FROM snow://package/<PKG>/versions/LIVE/
  FILES = ('manifest.yml');

CREATE OR REPLACE FILE FORMAT raw_text_fmt
  TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = NONE
  COMPRESSION = NONE ESCAPE = NONE ESCAPE_UNENCLOSED_FIELD = NONE;

SELECT $1 AS content FROM @download_stage/manifest.yml (FILE_FORMAT => 'raw_text_fmt');
```
Edit the YAML, then re-upload using the stage method from Step 4.2.

**CoCo CLI:**
```sql
GET snow://package/<PKG>/versions/LIVE/manifest.yml file:///tmp/;
```
Ask the user where they want files downloaded — `/tmp/` is a safe default.

**Step 4A.3** — Read and edit files (Workspaces/CLI: via `read`/`edit` tools).

**Step 4A.4** — Upload modified files back to package (same upload commands as Step 4.2 for your environment). Verify with `LIST` before releasing.

**Step 4A.5** — Test or release the updated version:

To **iterate without releasing** (provider-side dev/test cycle):
```sql
-- Build to pick up the updated files:
ALTER APPLICATION PACKAGE <PKG> BUILD;

-- Install test app from LIVE version (first time only):
CREATE APPLICATION <APP> FROM APPLICATION PACKAGE <PKG> USING VERSION LIVE;

-- Upgrade test app to latest built LIVE version (subsequent iterations):
ALTER APPLICATION <APP> UPGRADE USING VERSION LIVE;
```

To **release** (MUST be LAST, after testing):
```sql
ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION;
```

If a released app already exists (provider or consumer), upgrade it after releasing:
```sql
ALTER APPLICATION <APP> UPGRADE;
```

### Step 5: Create Listing (Distribution)

> **Ready to share?** Would you like to:
> 1. **Create a private listing** (share with specific accounts)
> 2. **Use Provider Studio UI** (more options)
>
> For private listing, I'll need:
> - **Target account(s)**: `MYORG.MYACCOUNT` format
> - **Listing title**

**⚠️ MANDATORY**: Listing syntax is in `references/package-release.sql` (already loaded at Step 4). For advanced listing scenarios, invoke the `internal-marketplace-org-listing` skill.

To find organization name: `SELECT CURRENT_ORGANIZATION_NAME();`

**Cross-region sharing** — Ask the user: "Is the target account in a different region or cloud?" If yes:

**⚠️ NEVER run these for cross-region checks (all are hallucinated/wrong):**
- `SYSTEM$SHOW_ACTIVE_REGION_LIST()` — does NOT exist
- `SYSTEM$SHOW_ACTIVE_REGION_GROUP()` — does NOT exist
- `SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER(...)` — does NOT exist
- `SHOW ORGANIZATION ACCOUNTS` — wrong tool for this job
- `SHOW SHARES` to find consumer region — wrong tool for this job
- `SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS` — wrong tool for this job
- Do NOT try to programmatically discover the consumer's region — just ask the user

**The ONLY command needed** — check if auto-fulfillment is enabled for the provider account:
```sql
SELECT SYSTEM$IS_GLOBAL_DATA_SHARING_ENABLED_FOR_ACCOUNT('<PROVIDER_ACCOUNT_NAME>');
```
- Returns `TRUE` → proceed to create cross-region listing with `auto_fulfillment` in YAML
- Returns `FALSE` → tell user ORGADMIN must enable it first:
  ```sql
  SELECT SYSTEM$ENABLE_GLOBAL_DATA_SHARING_FOR_ACCOUNT('<PROVIDER_ACCOUNT_NAME>');
  ```
- These functions require `ORGADMIN` role. If the current role can't run them, tell the user to ask their ORGADMIN.

Then add `auto_fulfillment` to the listing YAML — see `references/package-release.sql` for the exact cross-region listing template.

### Step 6: Consumer-Side Verification

> **If you're a consumer**, skip directly to this step.

**⚠️ NEVER do these:**
- `CREATE OR REPLACE APPLICATION ...` — does NOT exist. Must `DROP APPLICATION IF EXISTS` first, then `CREATE APPLICATION`

**Install commands** (copy verbatim — do NOT guess):
```sql
-- Same-account install (from package):
CREATE APPLICATION <APP> FROM APPLICATION PACKAGE <PKG>;

-- Cross-account install (from listing):
CREATE APPLICATION <APP> FROM LISTING '<LISTING_ID>';

-- Reinstall (must drop first):
DROP APPLICATION IF EXISTS <APP>;
CREATE APPLICATION <APP> FROM APPLICATION PACKAGE <PKG>;

-- Upgrade existing app to latest released version (no reinstall needed):
ALTER APPLICATION <APP> UPGRADE;
```

**Test in UI first**: Snowflake Intelligence → select the agent.

**Troubleshooting**: See `references/troubleshooting.md`.

---

## Key Concepts

### Constraints & Limits

- **1,000 object limit** in `shared_content` per application package — plan schema layout accordingly
- **No wildcard/regex** for object names in the manifest — every object must be listed explicitly
- **Semantic view verified_queries**: Do NOT use FQN — use table alias only (e.g. `SELECT * FROM COMPANIES`), or you get INTERNAL_ERROR 370001
- **Notebooks can only access data within the same application package** — they cannot query external databases or the provider's source data directly
- **No REFERENCE_USAGE grants** — manifest handles access automatically
- **App name becomes the database** — `SELECT * FROM <app_name>.<schema>.<table>`

---

## Stopping Points

**Skip all stopping points when the user says to proceed end-to-end or skip confirmations.** Execute the full workflow without pausing.

When interactive:
- ✋ After Step 2: Confirm schema layout before creating manifest
- ✋ After Step 4 or 4A: Confirm package created/updated and version released
- ✋ After Step 5: Ask whether user wants a listing
- ✋ After Step 6: Confirm consumer can access data

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

**Iteration rule:** When user asks to redo or fix a step, skip confirmations for previously approved steps. Go directly to the step that needs fixing without re-asking about earlier decisions.

## Output

- Application package (`TYPE=DATA`) with manifest
- Consumer-installable data app
- Private listing (if requested)
