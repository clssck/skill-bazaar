# CLI Version Check

Confirm the Snowflake Apps command surface is available and the Snowflake CLI is current.

## Goal

Use `snow app` for all Snowflake Apps commands. Verify it works and warn the user if their CLI is outdated.

## Check command surface (required)

Use exactly these two commands: `snow app setup --help` to check the command surface, and `snow --version` to check the version. Do not combine them into other variations.

```bash
snow app setup --help
```

If it succeeds, use `snow app` for all Snowflake Apps commands.

If it fails, the Snowflake CLI is missing or too old to expose the `snow app` command surface. Stop and ask the user to install or upgrade Snowflake CLI (see the upgrade commands below) before continuing.

## Version check (informational)

Also run:

```bash
snow --version
```

If the version is earlier than 3.17, warn the user that their CLI is outdated and offer an upgrade command.

## Upgrade commands by install method

Detect the install method and use the first match:

| Detection | Update Command |
|-----------|----------------|
| `brew list snowflake-cli 2>/dev/null` | `brew update && brew upgrade snowflake-cli` |
| `pipx list 2>/dev/null \| grep snowflake-cli` | `pipx upgrade snowflake-cli` |
| `pip show snowflake-cli 2>/dev/null` | `pip install --upgrade snowflake-cli` |
| `snow --info` reports `"installation_source": "binary"` | Download the new installer from the [GitHub releases page](https://github.com/snowflakedb/snowflake-cli/releases) and run it |
| None of the above | `pip install --upgrade snowflake-cli` |
