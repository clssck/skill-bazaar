---
name: snowflake-apps-develop
description: "Local development, testing, and iteration for Snowflake Apps. Use when the user wants to run locally, test, add features, or iterate on an existing app."
---

# Develop Snowflake App

Local iteration on an existing Snowflake App. The template-specific mechanics — how to run it, what to verify, and framework-specific pitfalls — live in the project's own `README.md`.

## Run Locally

Run the app locally, reading the project's `README.md` for the framework-specific run command and smoke checks. Start any dev server in the background, since it's a long-running process. (Local development is not available in every environment — if it isn't supported where you are running, tell the user and route them to `../deploy/SKILL.md` instead.)

## Verify Before Declaring Success

Once it's running, confirm it renders without errors and is fetching **real** Snowflake data (not mock data). Run any additional smoke checks the README specifies. Diagnose any failures before telling the user the app is up.

## Secrets

For reading secrets, consult the project's `README.md`. Keep one platform-level guardrail in mind: declare each secret as a **top-level** `secrets:` block in `app.yml` (a sibling of `install:`/`run:`/`profile:`), **not** nested under `run:`, or the SPCS runtime ignores it.

## Next Steps

When the app is ready, validate it, then ask the user if they'd like to deploy — the router will load the `deploy` sub-skill.
