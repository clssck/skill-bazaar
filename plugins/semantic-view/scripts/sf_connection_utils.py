#!/usr/bin/env python3
"""
Shared utilities for Snowflake connection management.

This module provides common functionality for connecting to Snowflake
and reading connection configurations from TOML files.
"""

import sys
import tomllib
from pathlib import Path
from typing import Any, cast

import snowflake.connector


def read_connection_config(connection_name: str | None = None) -> dict[str, Any]:
    """
    Read Snowflake connection configuration from TOML files.

    Priority:
    1. ~/.snowflake/connections.toml
    2. ~/.snowflake/config.toml

    Args:
        connection_name: Name of the connection to use. If None, uses default_connection_name.

    Returns:
        Dictionary with connection configuration

    Raises:
        SystemExit: If no configuration files found or connection not found
    """
    config_dir = Path.home() / ".snowflake"
    connections_path = config_dir / "connections.toml"
    config_path = config_dir / "config.toml"

    connections = {}
    default_connection_name = None

    # Try connections.toml first (priority 1)
    if connections_path.exists():
        try:
            with open(connections_path, "rb") as f:
                data = tomllib.load(f)
                default_connection_name = data.get("default_connection_name")
                # connections.toml has flat structure
                for key, value in data.items():
                    if key != "default_connection_name" and isinstance(value, dict):
                        connections[key] = value
        except Exception as e:
            print(f"❌ Error reading {connections_path}: {e}")
            sys.exit(1)

    # Try config.toml if connections.toml didn't have connections (priority 2)
    elif config_path.exists():
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
                default_connection_name = data.get("default_connection_name")
                # config.toml has [connections.name] structure
                connections = data.get("connections", {})
        except Exception as e:
            print(f"❌ Error reading {config_path}: {e}")
            sys.exit(1)

    if not connections:
        print("❌ No Snowflake configuration found")
        print(
            "   Please create ~/.snowflake/connections.toml or ~/.snowflake/config.toml"
        )
        sys.exit(1)

    # Determine which connection to use
    target_connection = connection_name or default_connection_name
    if not target_connection:
        # Use first available connection
        target_connection = next(iter(connections.keys()))
        print(
            f"ℹ️  No connection specified, using first available: {target_connection}"
        )

    if target_connection not in connections:
        print(f"❌ Connection '{target_connection}' not found")
        print(f"   Available connections: {', '.join(connections.keys())}")
        sys.exit(1)

    config = connections[target_connection]

    # Validate required fields (different scripts may have different requirements)
    if "account" not in config:
        print(f"❌ Connection '{target_connection}' missing required field: account")
        sys.exit(1)

    return config


def build_rest_url(config: dict[str, Any]) -> str:
    """
    Build the Snowflake REST API URL from connection config.

    Args:
        config: Connection configuration dictionary

    Returns:
        REST URL (without https:// prefix)
    """
    if "host" in config and config["host"]:
        host = cast(str, config["host"])
        if host.startswith("https://"):
            host = host[8:]
        # Normalize account portion: underscores → hyphens for DNS/SSL compatibility
        parts = host.split(".", 1)
        parts[0] = parts[0].replace("_", "-")
        return ".".join(parts)
    else:
        account = config["account"].lower().replace("_", "-")
        return f"{account}.snowflakecomputing.com"


class SnowflakeConnection:
    """Snowflake connection class that reads from Snowflake CLI config files.

    Follows Snowflake CLI priority rules:
    1. connections.toml (priority 1)
    2. config.toml (priority 2, only if connections.toml doesn't exist)
    """

    def __init__(self, connection_name: str):
        self.connection_name = connection_name
        self.session_connection = None
        self.conn_config: dict[str, str] = {}
        self._load_connection_config()

    def _load_connection_config(self) -> None:
        """Load connection configuration following Snowflake CLI priority rules.

        Priority order:
        1. connections.toml (used exclusively if present)
        2. config.toml (only if connections.toml doesn't exist)
        """
        try:
            config_dir = Path.home() / ".snowflake"
            connections_file = config_dir / "connections.toml"
            config_file = config_dir / "config.toml"

            # Priority 1: connections.toml (if it exists, use ONLY this file)
            if connections_file.exists():
                config_data = self._parse_connections_toml(connections_file)
                if self.connection_name not in config_data:
                    raise ValueError(
                        f"Connection '{self.connection_name}' not found in connections.toml. "
                        f"Available connections: {list(config_data.keys())}"
                    )
                self.conn_config = config_data[self.connection_name]
                print(
                    f"✅ Connection '{self.connection_name}' loaded from connections.toml"
                )
                return

            # Priority 2: config.toml (only if connections.toml doesn't exist)
            if config_file.exists():
                config_data = self._parse_config_toml(config_file)
                if self.connection_name not in config_data:
                    raise ValueError(
                        f"Connection '{self.connection_name}' not found in config.toml. "
                        f"Available connections: {list(config_data.keys())}"
                    )
                self.conn_config = config_data[self.connection_name]
                print(f"✅ Connection '{self.connection_name}' loaded from config.toml")
                return

            # No config files found
            raise FileNotFoundError(
                f"No Snowflake configuration files found. "
                f"Please create either {connections_file} or {config_file}"
            )

        except Exception as e:
            raise RuntimeError(
                f"Failed to load connection '{self.connection_name}': {e}"
            )

    def _parse_connections_toml(self, file_path: Path) -> dict[str, dict[str, str]]:
        """Parse connections.toml with flat structure [connection_name]."""
        with open(file_path, "rb") as f:
            toml_data = tomllib.load(f)

        # Extract connections - flat structure, excluding 'default_connection_name'
        config_data: dict[str, dict[str, str]] = {}
        for key, value in toml_data.items():
            if key != "default_connection_name" and isinstance(value, dict):
                config_data[key] = value

        return config_data

    def _parse_config_toml(self, file_path: Path) -> dict[str, dict[str, str]]:
        """Parse config.toml with [connections.name] structure."""
        with open(file_path, "rb") as f:
            toml_data = tomllib.load(f)

        # Extract connections from [connections.name] structure
        connections = toml_data.get("connections", {})
        return cast(dict[str, dict[str, str]], connections)

    def get_snowflake_session(self) -> Any:
        """Get a snowflake.connector connection."""
        if self.session_connection is None:
            # Create connection using config from toml
            self.session_connection = snowflake.connector.connect(
                account=self.conn_config.get("account"),
                user=self.conn_config.get("user"),
                password=self.conn_config.get("password"),
                database=self.conn_config.get("database"),
                schema=self.conn_config.get("schema"),
                warehouse=self.conn_config.get("warehouse"),
            )
        return self.session_connection

    def close(self) -> None:
        """Close the Snowflake connection."""
        if self.session_connection:
            self.session_connection.close()
            self.session_connection = None
