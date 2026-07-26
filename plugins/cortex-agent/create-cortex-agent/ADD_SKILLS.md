# Adding Skills to a Cortex Agent

This document provides instructions for adding or modifying skills on a Cortex Agent. Skills allow you to load custom skills from a Snowflake stage into the agent, providing specialized instructions and knowledge that extend the agent's capabilities.

## Prerequisites

- Skills must be accessible from a Snowflake stage (either a Git repository stage or a named stage)
- The role used for agent creation/modification must have access to the stage containing the skills
- For Git integration: privileges to CREATE API INTEGRATION (or use an existing one) and CREATE GIT REPOSITORY

---

## Part 1: Setting Up Git Integration for Skills

If your skills are stored in a Git repository, you can integrate the repository directly with Snowflake. This allows you to reference skills by branch, tag, or commit hash.

### Step 1: Determine Git Repository Details

Ask the user for the following information:

```
Git Repository Setup:
- Repository URL: [e.g., https://github.com/your-org/skills-repo.git]
- Is this a public or private repository?
- Do you have an existing API integration for Git, or should we create one?
```

### Step 2: Create or Use an API Integration

#### For Public Repositories (No Authentication)

```sql
-- Create API integration for Git HTTPS access (public repos)
CREATE OR REPLACE API INTEGRATION git_api_integration
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/your-org/')  -- Adjust to your Git host/org
  ENABLED = TRUE;
```

#### For Private/Internal Repositories (With Authentication)

When using private repositories, include `ALLOWED_AUTHENTICATION_SECRETS`:

```sql
-- Create API integration for Git HTTPS access (private repos)
CREATE OR REPLACE API INTEGRATION git_api_integration
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/your-org/')  -- Adjust to your Git host/org
  ALLOWED_AUTHENTICATION_SECRETS = ALL  -- Or specify specific secrets: (my_secret1, my_secret2)
  ENABLED = TRUE;
```

**Notes on API_ALLOWED_PREFIXES:**
- Use the base URL of your Git organization or repository
- For GitHub: `'https://github.com/your-org/'`
- For GitLab: `'https://gitlab.com/your-org/'`
- For Bitbucket: `'https://bitbucket.org/your-org/'`
- For Azure DevOps: `'https://dev.azure.com/your-org/'`
- Multiple prefixes can be specified as a comma-separated list

**If using an existing API integration:**
```sql
-- Verify the integration exists and is enabled
SHOW API INTEGRATIONS LIKE 'git_api_integration';
```

### Step 3: Create the Git Repository

#### For Public Repositories (No Authentication)

```sql
CREATE OR REPLACE GIT REPOSITORY <DATABASE>.<SCHEMA>.skills_repo
  API_INTEGRATION = git_api_integration
  ORIGIN = 'https://github.com/your-org/skills-repo.git';
```

#### For Private/Internal Repositories (With Authentication)

**Step 3a: Create a Secret with Credentials**

> **Workflow Note:** When helping a user integrate a private repository, ask the user to create the secret themselves (since it contains sensitive credentials like PATs). Provide them with the SQL template below, and once they confirm the secret name and location, proceed with the remaining steps (API integration, Git repository creation, etc.).

Create a secret containing your Git credentials. Use a Personal Access Token (PAT) instead of your password:

```sql
-- Create secret for Git authentication
CREATE OR REPLACE SECRET <DATABASE>.<SCHEMA>.git_secret
  TYPE = PASSWORD
  USERNAME = 'your-username'
  PASSWORD = 'your-personal-access-token'
  COMMENT = 'Git credentials for private repository access';
```

**Provider-specific username requirements:**

| Git Provider | USERNAME Value | Notes |
|--------------|----------------|-------|
| GitHub | Your GitHub username | Use a PAT with `repo` scope |
| GitLab | Your GitLab username | Use a PAT with `read_repository` scope |
| Bitbucket | `x-token-auth` | Use App Password or Repository Access Token |
| Azure DevOps | Your email or username | Use a PAT with Code (Read) permission |

**How to create a Personal Access Token (PAT):**
- **GitHub**: Settings > Developer settings > Personal access tokens > Generate new token
  - **Classic PAT**: Select `repo` scope for full repository access
  - **Fine-grained PAT**: Select the specific repository and grant "Contents" read access
- **GitLab**: Settings > Access Tokens > Create personal access token (select `read_repository` scope)
- **Bitbucket**: Settings > App passwords > Create app password (select Repository Read)
- **Azure DevOps**: User settings > Personal access tokens > New Token (select Code Read)

**GitHub Organizations with SAML/SSO Enforcement**

If your repository is in a GitHub organization that uses SAML SSO (common for enterprise organizations like `snowflake-eng`), you must authorize your PAT for SSO access:

1. Go to https://github.com/settings/tokens
2. Find your PAT in the list
3. Click **Configure SSO** button next to the token
4. Click **Authorize** next to your organization name
5. Complete any SSO authentication prompts

Without SSO authorization, you'll get an error like:
```
"Resource protected by organization SAML enforcement. You must grant your Personal Access token access to this organization."
```

**Step 3b: Grant Access to the Secret (if needed)**

If other roles need to use this repository, grant them access to the secret:

```sql
-- Grant usage on the secret to other roles
GRANT USAGE ON SECRET <DATABASE>.<SCHEMA>.git_secret TO ROLE <role_name>;
```

**Step 3c: Create the Repository with Credentials**

```sql
CREATE OR REPLACE GIT REPOSITORY <DATABASE>.<SCHEMA>.skills_repo
  API_INTEGRATION = git_api_integration
  GIT_CREDENTIALS = <DATABASE>.<SCHEMA>.git_secret
  ORIGIN = 'https://github.com/your-org/private-skills-repo.git';
```

**Security Best Practices:**
- Store secrets in a dedicated schema with restricted access
- Use tokens with minimal required permissions (read-only for cloning)
- Rotate tokens periodically and update the secret
- Use `ALLOWED_AUTHENTICATION_SECRETS = (specific_secret)` instead of `ALL` when possible
- Never share PATs or include them in code/logs

### Step 4: Fetch and Verify Repository Contents

```sql
-- Fetch the latest from the remote repository
ALTER GIT REPOSITORY <DATABASE>.<SCHEMA>.skills_repo FETCH;

-- List available branches
SHOW GIT BRANCHES IN GIT REPOSITORY <DATABASE>.<SCHEMA>.skills_repo;

-- List available tags
SHOW GIT TAGS IN GIT REPOSITORY <DATABASE>.<SCHEMA>.skills_repo;

-- List skills in the repository (example: main branch)
LIST @<DATABASE>.<SCHEMA>.skills_repo/branches/main/skills;
```

### Step 5: Reference Skills from Git Repository

Skills in a Git repository can be referenced using the following path formats:

| Reference Type | Path Format | Example |
|----------------|-------------|---------|
| Branch | `@DB.SCHEMA.REPO/branches/<branch>/path` | `@MY_DB.PUBLIC.skills_repo/branches/main/skills/my_skill` |
| Tag | `@DB.SCHEMA.REPO/tags/<tag>/path` | `@MY_DB.PUBLIC.skills_repo/tags/v1.0/skills/my_skill` |
| Commit | `@DB.SCHEMA.REPO/commits/<hash>/path` | `@MY_DB.PUBLIC.skills_repo/commits/abc123/skills/my_skill` |

**Recommended patterns:**

- **Development**: Reference by branch or commit hash for iterative testing
  ```
  @MY_DB.PUBLIC.skills_repo_dev/branches/feature-branch/skills/my_skill
  ```

- **Production**: Reference by tag for stable, versioned releases
  ```
  @MY_DB.PUBLIC.skills_repo/tags/stable_v1/skills/my_skill
  ```

### Keeping Skills Updated

To sync the latest changes from the remote repository:

```sql
ALTER GIT REPOSITORY <DATABASE>.<SCHEMA>.skills_repo FETCH;
```

**Note:** After fetching, agents referencing branch paths (e.g., `/branches/main/`) will automatically use the updated files. Agents referencing tags or commits will remain on the specified version.

### Troubleshooting Git Repository Integration

#### Error: "Operation clone is not permitted by server"

This error typically indicates authentication failure. Debug steps:

1. **Test your PAT directly** using curl:
   ```bash
   curl -H "Authorization: token YOUR_PAT" https://api.github.com/repos/your-org/your-repo
   ```

2. **Expected responses:**
   - **Success**: Returns JSON with repository details (id, name, full_name, etc.)
   - **401 Bad credentials**: PAT is invalid, expired, or mistyped
   - **403 SAML enforcement**: PAT needs SSO authorization (see above)
   - **404 Not Found**: Repository doesn't exist or PAT doesn't have access

3. **Common fixes:**
   - Regenerate the PAT and update the Snowflake secret
   - Authorize the PAT for SSO (for enterprise GitHub organizations)
   - Verify the GitHub username in the secret is correct
   - Ensure the PAT has `repo` scope

#### Error: "Repository not found" when pushing locally

If you can't push to a private repository from your local machine:

1. **Check SSH vs HTTPS**: Your SSH key identity may differ from your PAT identity
2. **Verify remote URL**: `git remote -v`
3. **Test SSH connection**: `ssh -T git@github.com`
4. **Try HTTPS with PAT**: 
   ```bash
   git remote set-url origin https://username@github.com/org/repo.git
   # When prompted for password, use your PAT
   ```

#### Verifying Secret Configuration

```sql
-- Check secret details (password is not shown)
DESCRIBE SECRET <DATABASE>.<SCHEMA>.git_secret;

-- Verify the username is correct
-- The USERNAME should match your Git provider account
```

---

## Part 2: Adding Skills to a New Agent

### Step 1: Gather Skill Information

Ask the user for the following information about each skill:

```
For each skill you want to add, please provide:

1. Skill name: [a unique identifier, e.g., "customer_support_skill"]
2. Skill source type:
   - SYSTEM: A built-in system skill (no path needed)
   - STAGE: Skill stored in a Snowflake named stage
   - GIT_INTEGRATION: Skill stored in a Git repository stage
3. Skill path (for STAGE/GIT_INTEGRATION only):
   - Stage: @MY_DB.MY_SCHEMA.SKILLS_STAGE/my_skill
   - Git repo: @MY_DB.MY_SCHEMA.SKILLS_REPO/branches/main/skills/my_skill

You can specify multiple skills.
```

### Step 2: Validate Skills

For skills with `STAGE` or `GIT_INTEGRATION` source types, perform the following validations:

#### 2a. Verify the skill name matches the directory name

The skill `name` in the agent spec **must** match the last directory segment of the `path`. This is how the agent resolves which skill to load at runtime.

For example, if the path is `@MY_DB.MY_SCHEMA.SKILLS_STAGE/customer_support_skill`, the skill name must be `customer_support_skill`.

**Validation rule:** Extract the last path component from the `source.path` and confirm it matches the `name` field.

```
Path: @MY_DB.MY_SCHEMA.SKILLS_STAGE/customer_support_skill
                                     └── must match ──────> name: "customer_support_skill" ✅

Path: @MY_DB.MY_SCHEMA.skills_repo/branches/main/skills/analytics_skill
                                                         └── must match ──> name: "analytics_skill" ✅

Path: @MY_DB.MY_SCHEMA.SKILLS_STAGE/customer_support_skill
                                                            name: "my_custom_name" ❌ MISMATCH
```

If the name does not match the directory, the skill will fail to load at runtime. Ask the user to correct either the skill name or the path.

#### 2b. Verify a SKILL.md file exists in the skill directory

Each skill directory **must** contain a `SKILL.md` file. This file defines the skill's metadata (name, description) and instructions. Without it, the agent cannot load the skill.

Run the following SQL to verify:

```sql
-- Check for SKILL.md in the skill directory
LIST @<DATABASE>.<SCHEMA>.<STAGE_OR_REPO>/<path_to_skill>/ PATTERN='.*SKILL\.md';
```

**Examples:**

```sql
-- For a named stage skill
LIST @MY_DB.MY_SCHEMA.SKILLS_STAGE/customer_support_skill/ PATTERN='.*SKILL\.md';

-- For a Git repository skill
LIST @MY_DB.MY_SCHEMA.skills_repo/branches/main/skills/analytics_skill/ PATTERN='.*SKILL\.md';
```

If no `SKILL.md` file is found, the skill directory is not valid. Ask the user to ensure their skill directory contains a `SKILL.md` file at the root level of the skill folder.

#### 2c. Verify the stage paths are accessible

Confirm the stage paths exist and are accessible:

```sql
-- For Git repository stage
LIST @<DATABASE>.<SCHEMA>.<GIT_REPO>/branches/<branch>/skills;

-- For named stage
LIST @<DATABASE>.<SCHEMA>.<STAGE>;
```

### Step 3: Configure the Agent Spec

Skills are defined in the top-level `skills` array of the agent specification. Each skill entry requires a `name` and a `source` object.

**Add skills to the `skills` array:**

```json
"skills": [
  {
    "name": "my_skill_name",
    "source": {
      "type": "STAGE",
      "path": "@DB.SCHEMA.STAGE/skill_name"
    }
  }
]
```

**Supported source types:**

| Source Type | Description | Requires `path` |
|-------------|-------------|-----------------|
| `SYSTEM` | Built-in system skill | No |
| `STAGE` | Skill stored in a Snowflake named stage | Yes |
| `GIT_INTEGRATION` | Skill stored in a Git repository stage | Yes |

### Step 4: Create the Agent with Skills

Use the `CREATE AGENT` command with the `FROM SPECIFICATION` clause and JSON content.

> **Note:** Using JSON is recommended because `DESCRIBE AGENT` returns JSON. This makes the read-modify-update workflow seamless—you can parse the returned spec, modify it, and pass it back without format conversion.

```sql
-- Create a new agent with skills
CREATE OR REPLACE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>
FROM SPECIFICATION $$
{
  "models": {
    "orchestration": "auto"
  },
  "skills": [
    {
      "name": "my_skill_name",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@DATABASE.SCHEMA.REPO/branches/main/skills/my_skill_name"
      }
    },
    {
      "name": "another_skill",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@DATABASE.SCHEMA.REPO/branches/main/skills/another_skill"
      }
    }
  ]
}
$$;
```

**Verify the agent was created:**

```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
DESCRIBE AS RESOURCE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;  -- Shows full spec as JSON
```

---

## Modifying Skills on an Existing Agent

### Step 1: Get Current Agent Configuration

First, retrieve the current agent spec:

```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
```

This returns the current `agent_spec` JSON. Parse it to see the existing `skills` array.

### Step 2: Determine the Modification

Ask the user what they want to do:

```
How would you like to modify the skills?
1. Add new skills (keep existing skills)
2. Remove specific skills
3. Replace all skills with a new list
4. Remove all skills
```

### Step 3: Update the Agent Spec

Based on the user's choice, modify the agent spec:

**Option 1 - Add new skills:**
- Add the new skill entries to the existing `skills` array

**Option 2 - Remove specific skills:**
- Remove the specified entries from the `skills` array
- If the array becomes empty, remove the `skills` field entirely

**Option 3 - Replace all skills:**
- Replace the `skills` array with the new list

**Option 4 - Remove all skills:**
- Remove the `skills` field from the agent spec

### Step 4: Apply the Changes

Use `CREATE OR REPLACE AGENT` with the updated specification:

```sql
-- Replace the agent with updated skills
CREATE OR REPLACE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>
FROM SPECIFICATION $$
{
  "models": {
    "orchestration": "auto"
  },
  "skills": [
    {
      "name": "existing_skill",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@DATABASE.SCHEMA.REPO/branches/main/skills/existing_skill"
      }
    },
    {
      "name": "new_skill",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@DATABASE.SCHEMA.REPO/branches/main/skills/new_skill"
      }
    }
  ]
}
$$;
```

### Step 5: Verify the Changes

Confirm the agent was updated:

```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
DESCRIBE AS RESOURCE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;  -- Shows full spec as JSON
```

## Example Agent Specifications

### Agent with Skills from Git Repository (Recommended)

```sql
CREATE OR REPLACE AGENT MY_DATABASE.MY_SCHEMA.MY_AGENT
FROM SPECIFICATION $$
{
  "models": {
    "orchestration": "auto"
  },
  "skills": [
    {
      "name": "customer_support_skill",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@MY_DATABASE.MY_SCHEMA.skills_repo/tags/stable_v1/skills/customer_support_skill"
      }
    },
    {
      "name": "analytics_skill",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@MY_DATABASE.MY_SCHEMA.skills_repo/tags/stable_v1/skills/analytics_skill"
      }
    }
  ]
}
$$;
```

### Agent with Skills from Named Stage

```sql
CREATE OR REPLACE AGENT MY_DATABASE.MY_SCHEMA.MY_AGENT
FROM SPECIFICATION $$
{
  "models": {
    "orchestration": "auto"
  },
  "skills": [
    {
      "name": "customer_support_skill",
      "source": {
        "type": "STAGE",
        "path": "@MY_DATABASE.MY_SCHEMA.SKILLS_STAGE/customer_support_skill"
      }
    },
    {
      "name": "analytics_skill",
      "source": {
        "type": "STAGE",
        "path": "@MY_DATABASE.MY_SCHEMA.SKILLS_STAGE/analytics_skill"
      }
    }
  ]
}
$$;
```

### Agent with Skills and Other Tools

```sql
CREATE OR REPLACE AGENT MY_DATABASE.MY_SCHEMA.MY_AGENT
FROM SPECIFICATION $$
{
  "models": {
    "orchestration": "auto"
  },
  "skills": [
    {
      "name": "sales_expert_skill",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@MY_DATABASE.MY_SCHEMA.skills_repo/branches/main/skills/sales_expert_skill"
      }
    }
  ],
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "query_sales_data",
        "description": "Query sales data using natural language"
      }
    }
  ],
  "tool_resources": {
    "query_sales_data": {
      "semantic_view": "MY_DATABASE.MY_SCHEMA.SALES_SEMANTIC_VIEW"
    }
  }
}
$$;
```

### Agent with System Skills

```sql
CREATE OR REPLACE AGENT MY_DATABASE.MY_SCHEMA.MY_AGENT
FROM SPECIFICATION $$
{
  "models": {
    "orchestration": "auto"
  },
  "skills": [
    {
      "name": "data_science_expertise",
      "source": {
        "type": "SYSTEM"
      }
    }
  ]
}
$$;
```

### Agent with Mixed Skill Sources

```sql
CREATE OR REPLACE AGENT MY_DATABASE.MY_SCHEMA.MY_AGENT
FROM SPECIFICATION $$
{
  "models": {
    "orchestration": "auto"
  },
  "skills": [
    {
      "name": "data_science_expertise",
      "source": {
        "type": "SYSTEM"
      }
    },
    {
      "name": "custom_analytics",
      "source": {
        "type": "STAGE",
        "path": "@MY_DATABASE.MY_SCHEMA.SKILLS_STAGE/custom_analytics"
      }
    },
    {
      "name": "report_generator",
      "source": {
        "type": "GIT_INTEGRATION",
        "path": "@MY_DATABASE.MY_SCHEMA.skills_repo/tags/v1.0/skills/report_generator"
      }
    }
  ]
}
$$;
```

---

## Technical Notes

### Skill Path Formats

Skills can be referenced from two types of stages:

| Stage Type | Path Format | Example |
|------------|-------------|---------|
| Git Repository (branch) | `@DB.SCHEMA.REPO/branches/<branch>/path` | `@MY_DB.PUBLIC.skills_repo/branches/main/skills/my_skill` |
| Git Repository (tag) | `@DB.SCHEMA.REPO/tags/<tag>/path` | `@MY_DB.PUBLIC.skills_repo/tags/v1.0/skills/my_skill` |
| Git Repository (commit) | `@DB.SCHEMA.REPO/commits/<hash>/path` | `@MY_DB.PUBLIC.skills_repo/commits/abc123/skills/my_skill` |
| Named Stage | `@DB.SCHEMA.STAGE/path` | `@MY_DB.PUBLIC.SKILLS_STAGE/my_skill` |

### Skill Source Types

| Source Type | Description | `path` Required | Example Use Case |
|-------------|-------------|-----------------|------------------|
| `SYSTEM` | Built-in system skill | No | System-provided capabilities (e.g., data science expertise) |
| `STAGE` | Skill in a Snowflake named stage | Yes | Custom skills uploaded to a stage |
| `GIT_INTEGRATION` | Skill in a Git repository stage | Yes | Skills managed in version control |

### Agent Spec Skill Schema

Each entry in the `skills` array follows this JSON structure:

```json
{
  "skills": [
    {
      "name": "<unique_skill_name>",
      "source": {
        "type": "SYSTEM | STAGE | GIT_INTEGRATION",
        "path": "<stage_path>"
      }
    }
  ]
}
```

- `name`: A unique identifier for the skill within the agent. Must be unique across all skills.
- `source.type`: One of `SYSTEM`, `STAGE`, or `GIT_INTEGRATION`.
- `source.path`: The stage path to the skill. Required for `STAGE` and `GIT_INTEGRATION` types. Not required for `SYSTEM` type.

### Required Privileges

| Action | Required Privilege |
|--------|-------------------|
| Create API Integration | CREATE INTEGRATION on ACCOUNT |
| Create Git Repository | CREATE GIT REPOSITORY on SCHEMA |
| Alter Git Repository (fetch) | OWNERSHIP on GIT REPOSITORY |
| Use existing Git Repository | USAGE on GIT REPOSITORY |
| Access skills from stage | USAGE on STAGE |

### Best Practices

1. **Use Git tags for production agents** - Tags provide immutable references to specific versions
2. **Use branches for development** - Allows rapid iteration without changing agent config
3. **Separate dev/prod repositories** - Consider `skills_repo_dev` and `skills_repo` for isolation
4. **Fetch before deployments** - Always run `ALTER GIT REPOSITORY ... FETCH` before updating agents to ensure latest code
5. **Use descriptive skill names** - Skill names should clearly indicate their purpose (e.g., `customer_support_skill` instead of `skill1`)
6. **Use `GIT_INTEGRATION` source type for Git-based skills** - This is more explicit than `STAGE` when referencing Git repository stages