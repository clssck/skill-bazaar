#!/usr/bin/env python3
"""
Set up a CDC (Change Data Capture) pipeline from Google Shared Drive to a Snowflake stage
using the Openflow connector.

This script:
1. Discovers and configures the Openflow Google Drive connector
2. Starts the connector to begin syncing files from Google Shared Drive

Supported Connectors:
--------------------

google-drive-no-cortex (recommended for stage output):
  - Writes raw files to an internal stage called @<DB>.<SCHEMA>.DOCUMENTS
  - Creates DOC_METADATA table to track file information
  - Supports file extensions: pdf, txt, docx, xlsx, pptx, html
  - Stage is created automatically with directory mode enabled

unstructured-google-drive-cdc (for Cortex Search):
  - Parses documents and chunks content for search
  - Writes chunks to DOCS_CHUNKS table
  - Creates a Cortex Search Service

Prerequisites:
- A Google Service Account with Domain-Wide Delegation
- A Google Shared Drive (Team Drive) that the service account can access
- An Openflow Runtime with the Google Drive connector available
- An External Access Integration configured with the required network rules:
  - oauth2.googleapis.com:443
  - www.googleapis.com:443
  - drive.googleapis.com:443
  - admin.googleapis.com:443
  - accounts.google.com:443
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests
import snowflake.connector

from snowflake_utils import (
    get_connection,
    qualify_name,
    setup_context,
)


# --- Constants ---

# Connector types - prefer no-cortex for stage output, fall back to cortex version
GOOGLE_DRIVE_CONNECTOR_PREFERENCES = [
    "google-drive-no-cortex",           # Writes raw files to stage
    "unstructured-google-drive-cdc",    # Writes chunks to table for Cortex Search
]

# Required network endpoints for External Access Integration
REQUIRED_NETWORK_ENDPOINTS = [
    "oauth2.googleapis.com:443",
    "www.googleapis.com:443",
    "drive.googleapis.com:443",
    "admin.googleapis.com:443",
    "accounts.google.com:443",
]


def get_pat_token() -> str:
    """Get the Snowflake PAT token from environment."""
    pat = os.environ.get("SNOWFLAKE_PAT")
    if not pat:
        raise ValueError(
            "SNOWFLAKE_PAT environment variable not set. "
            "Please set it to your Snowflake Programmatic Access Token."
        )
    return pat


def derive_runtime_key(runtime_name: str) -> str:
    """
    Derive the runtime key from the runtime name.
    
    Rules:
    - Lowercase the name
    - Replace spaces with dashes
    - Remove all other non-alphanumeric characters
    - Remove leading and trailing dashes
    - Collapse multiple consecutive dashes into a single dash
    """
    key = runtime_name.lower()
    key = key.replace(" ", "-")
    key = re.sub(r"[^a-z0-9-]", "", key)
    key = re.sub(r"-+", "-", key)
    key = key.strip("-")
    return key


def find_runtime_url(
    conn: snowflake.connector.SnowflakeConnection,
    runtime_name: str,
) -> str:
    """
    Find the Openflow runtime URL from Snowflake.
    
    Args:
        conn: Snowflake connection
        runtime_name: Name of the Openflow runtime
    
    Returns:
        The base URL for the runtime (e.g., https://host/runtime-key/nifi-api)
    """
    runtime_key = derive_runtime_key(runtime_name)
    
    with conn.cursor() as cur:
        # Get list of Openflow runtime integrations
        cur.execute("SHOW OPENFLOW RUNTIME INTEGRATIONS")
        integrations = cur.fetchall()
        
        # Get column indices
        columns = [desc[0] for desc in cur.description]
        name_idx = columns.index("name")
        
        for row in integrations:
            integration_name = row[name_idx]
            
            # Describe the integration to get the OAuth redirect URI
            cur.execute(f"DESCRIBE INTEGRATION {integration_name}")
            props = cur.fetchall()
            
            for prop in props:
                prop_name = prop[0]
                prop_value = prop[1]
                
                if prop_name == "OAUTH_REDIRECT_URI" and runtime_key in str(prop_value).lower():
                    # Extract the deployment host from the redirect URI
                    # URI format: https://{host}/{runtime-key}/login/...
                    parsed = urlparse(prop_value)
                    host = parsed.netloc
                    return f"https://{host}/{runtime_key}/nifi-api"
    
    raise ValueError(
        f"Could not find Openflow runtime URL for runtime: {runtime_name}. "
        "Make sure the runtime exists and you have access to it."
    )


def make_nifi_request(
    base_url: str,
    endpoint: str,
    method: str = "GET",
    data: dict | None = None,
    pat_token: str | None = None,
) -> dict:
    """
    Make a request to the NiFi REST API.
    
    Args:
        base_url: Base URL for the runtime (ending in /nifi-api)
        endpoint: API endpoint (e.g., /flow/registries)
        method: HTTP method
        data: Request body for POST/PUT
        pat_token: PAT token for authentication
    
    Returns:
        Response JSON
    """
    if pat_token is None:
        pat_token = get_pat_token()
    
    url = f"{base_url}{endpoint}"
    headers = {
        "Authorization": f"Bearer {pat_token}",
        "Content-Type": "application/json",
    }
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=data)
    elif method == "PUT":
        response = requests.put(url, headers=headers, json=data)
    elif method == "DELETE":
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")
    
    response.raise_for_status()
    
    if response.content:
        return response.json()
    return {}


def upload_asset(
    base_url: str,
    parameter_context_id: str,
    filename: str,
    content: bytes,
    pat_token: str | None = None,
) -> dict:
    """
    Upload an asset to a parameter context.
    
    Args:
        base_url: Base URL for the runtime
        parameter_context_id: ID of the parameter context
        filename: Name of the file being uploaded
        content: File content as bytes
        pat_token: PAT token for authentication
    
    Returns:
        Asset information including ID
    """
    if pat_token is None:
        pat_token = get_pat_token()
    
    url = f"{base_url}/parameter-contexts/{parameter_context_id}/assets"
    headers = {
        "Authorization": f"Bearer {pat_token}",
        "Content-Type": "application/octet-stream",
        "filename": filename,
    }
    
    response = requests.post(url, headers=headers, data=content)
    response.raise_for_status()
    return response.json()


def find_connector_registry(base_url: str) -> tuple[str, str]:
    """
    Find the connector registry client and bucket.
    
    Returns:
        Tuple of (registry_id, bucket_id)
    """
    # List registry clients
    registries = make_nifi_request(base_url, "/flow/registries")
    
    registry_id = None
    for registry in registries.get("registries", []):
        # Check both possible paths for the type
        reg_type = registry.get("component", {}).get("type", "")
        if not reg_type:
            reg_type = registry.get("registry", {}).get("type", "")
        
        if "ConnectorFlowRegistryClient" in reg_type:
            # Get ID from component or registry
            registry_id = registry.get("id")
            if not registry_id:
                registry_id = registry.get("component", {}).get("id")
            if not registry_id:
                registry_id = registry.get("registry", {}).get("id")
            break
    
    if not registry_id:
        raise ValueError("Could not find ConnectorFlowRegistryClient in the runtime")
    
    return registry_id, "connectors"


def list_available_connectors(base_url: str, registry_id: str) -> list[dict]:
    """
    List all available connectors in the registry.
    
    Returns:
        List of connector flow information (unwrapped from versionedFlow)
    """
    flows = make_nifi_request(
        base_url,
        f"/flow/registries/{registry_id}/buckets/connectors/flows",
    )
    # Unwrap the versionedFlow objects
    result = []
    for flow in flows.get("versionedFlows", []):
        if "versionedFlow" in flow:
            result.append(flow["versionedFlow"])
        else:
            result.append(flow)
    return result


def find_google_drive_connector(
    base_url: str,
    registry_id: str,
    connector_name: str | None = None,
) -> dict:
    """
    Find a Google Drive connector in the registry.
    
    Args:
        base_url: NiFi API base URL
        registry_id: Registry client ID
        connector_name: Specific connector name to use. If None, tries preferences in order.
    
    Returns:
        Connector flow information
    """
    flows = list_available_connectors(base_url, registry_id)
    
    # Build a lookup by flow ID
    flow_by_id = {flow.get("flowId", "").lower(): flow for flow in flows}
    
    # If specific connector requested, look for it
    if connector_name:
        for flow in flows:
            flow_id = flow.get("flowId", "")
            if connector_name.lower() in flow_id.lower() or flow_id.lower() in connector_name.lower():
                return flow
        raise ValueError(
            f"Could not find connector '{connector_name}' in the registry. "
            f"Available connectors: {[f.get('flowId') for f in flows]}"
        )
    
    # Try preferred connectors in order
    for preferred in GOOGLE_DRIVE_CONNECTOR_PREFERENCES:
        for flow in flows:
            flow_id = flow.get("flowId", "")
            if preferred.lower() in flow_id.lower():
                print(f"  Found connector: {flow_id}")
                return flow
    
    # Fall back to any Google Drive connector
    for flow in flows:
        flow_id = flow.get("flowId", "")
        if "google" in flow_id.lower() and "drive" in flow_id.lower():
            print(f"  Found connector: {flow_id}")
            return flow
    
    raise ValueError(
        "Could not find any Google Drive connector in the registry. "
        f"Available connectors: {[f.get('flowId') for f in flows]}"
    )


def get_latest_connector_version(
    base_url: str,
    registry_id: str,
    flow_id: str,
) -> str:
    """Get the latest version of a connector."""
    versions = make_nifi_request(
        base_url,
        f"/flow/registries/{registry_id}/buckets/connectors/flows/{flow_id}/versions",
    )
    
    version_list = versions.get("versionedFlowSnapshotMetadataSet", [])
    if not version_list:
        raise ValueError(f"No versions found for connector: {flow_id}")
    
    # Sort by version (assuming semver-like format) and get latest
    latest = max(version_list, key=lambda v: v.get("versionedFlowSnapshotMetadata", {}).get("version", "0"))
    return latest.get("versionedFlowSnapshotMetadata", {}).get("version", "")


def add_connector_to_runtime(
    base_url: str,
    registry_id: str,
    flow_id: str,
    version: str,
) -> dict:
    """
    Add the connector to the runtime as a Process Group from registry.
    
    Returns:
        Process Group information
    """
    payload = {
        "revision": {
            "clientId": "python-script-client",
            "version": 0,
        },
        "disconnectedNodeAcknowledged": False,
        "component": {
            "position": {
                "x": 0,
                "y": 0,
            },
            "versionControlInformation": {
                "registryId": registry_id,
                "bucketId": "connectors",
                "flowId": flow_id,
                "version": version,
            },
        },
    }
    
    return make_nifi_request(
        base_url,
        "/process-groups/root/process-groups?parameterContextHandlingStrategy=KEEP_EXISTING",
        method="POST",
        data=payload,
    )


def add_connector_from_json(
    base_url: str,
    flow_definition_path: str,
    group_name: str = "Custom Connector",
    pat_token: str | None = None,
) -> dict:
    """
    Add a connector to the runtime by uploading a flow definition JSON file.
    
    This allows deploying custom connectors that aren't in the registry.
    Uses NiFi's process-groups upload endpoint with multipart form data.
    
    Args:
        base_url: NiFi API base URL
        flow_definition_path: Path to the flow definition JSON file
        group_name: Name for the process group
        pat_token: PAT token for authentication
    
    Returns:
        Process Group information
    """
    if pat_token is None:
        pat_token = get_pat_token()
    
    url = f"{base_url}/process-groups/root/process-groups/upload"
    headers = {
        "Authorization": f"Bearer {pat_token}",
    }
    
    # Upload using multipart form data with required parameters
    with open(flow_definition_path, "rb") as f:
        files = {
            "file": (os.path.basename(flow_definition_path), f, "application/json"),
        }
        data = {
            "groupName": group_name,
            "positionX": "100",
            "positionY": "100",
            "clientId": "python-script-client",
        }
        
        response = requests.post(url, headers=headers, files=files, data=data)
    
    if response.status_code not in (200, 201):
        raise Exception(f"Failed to upload flow: {response.status_code} - {response.text[:500]}")
    
    return response.json()


def find_process_group_parameter_context(base_url: str, pg_id: str) -> str:
    """Find the parameter context ID for a process group."""
    pg_info = make_nifi_request(base_url, f"/process-groups/{pg_id}")
    param_context = pg_info.get("component", {}).get("parameterContext", {})
    return param_context.get("id", "")


def get_parameter_context(base_url: str, context_id: str) -> dict:
    """Get parameter context details."""
    return make_nifi_request(base_url, f"/parameter-contexts/{context_id}")


def update_parameters(
    base_url: str,
    context_id: str,
    parameters: list[dict],
    max_retries: int = 3,
) -> None:
    """
    Update parameters in a parameter context.
    
    Args:
        base_url: Base URL for the runtime
        context_id: Parameter context ID
        parameters: List of parameter updates
        max_retries: Maximum number of retries on conflict
    """
    for attempt in range(max_retries):
        try:
            # Get current context to get revision
            context = get_parameter_context(base_url, context_id)
            revision = context.get("revision", {"version": 0})
            
            payload = {
                "revision": revision,
                "id": context_id,
                "component": {
                    "id": context_id,
                    "parameters": parameters,
                },
            }
            
            # Start the update request
            result = make_nifi_request(
                base_url,
                f"/parameter-contexts/{context_id}/update-requests",
                method="POST",
                data=payload,
            )
            
            # Wait for the update to complete
            request_id = result.get("request", {}).get("requestId")
            if request_id:
                max_attempts = 30
                for _ in range(max_attempts):
                    status = make_nifi_request(
                        base_url,
                        f"/parameter-contexts/{context_id}/update-requests/{request_id}",
                    )
                    if status.get("request", {}).get("complete"):
                        # Delete the request
                        make_nifi_request(
                            base_url,
                            f"/parameter-contexts/{context_id}/update-requests/{request_id}",
                            method="DELETE",
                        )
                        return  # Success
                    time.sleep(1)
            return  # Success (no request_id means immediate completion)
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409 and attempt < max_retries - 1:
                # Conflict - wait and retry with fresh revision
                wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                print(f"    Parameter update conflict, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            raise


def get_available_parameters(base_url: str, context_id: str) -> list[str]:
    """Get the list of available parameter names in a context."""
    context = get_parameter_context(base_url, context_id)
    params = context.get("component", {}).get("parameters", [])
    return [p.get("parameter", {}).get("name", "") for p in params]


def configure_google_drive_no_cortex_connector(
    base_url: str,
    pg_id: str,
    service_account_json: str,
    google_drive_id: str,
    google_folder_name: str,
    delegation_user: str,
    google_domain: str,
    snowflake_role: str,
    destination_database: str,
    destination_schema: str,
    destination_stage: str,
    warehouse: str,
    file_extensions: str = "pdf,txt,docx,xlsx,pptx,html",
) -> None:
    """
    Configure the google-drive-no-cortex connector (or custom google-drive-to-stage-cdc).
    
    This connector writes raw files to an internal stage and maintains metadata
    in DOC_METADATA table.
    
    Parameters from the connector JSON definition:
    - Source: GCP Service Account JSON, Google Delegation User
    - Destination: Destination Database, Destination Schema, Destination Stage, Snowflake Role, etc.
    - Ingestion: Google Domain, Google Drive ID, Google Folder Name, File Extensions To Ingest
    
    Note: The custom google-drive-to-stage-cdc connector supports configurable stage names
    via the 'Destination Stage' parameter. The original google-drive-no-cortex uses
    hardcoded 'DOCUMENTS'.
    """
    # Get the parameter context for this process group
    context_id = find_process_group_parameter_context(base_url, pg_id)
    if not context_id:
        raise ValueError(f"Could not find parameter context for process group: {pg_id}")
    
    print(f"  Configuring parameter context: {context_id}")
    
    # Parameters based on the actual connector definition
    parameters = [
        # Source Parameters
        {
            "parameter": {
                "name": "GCP Service Account JSON",
                "value": service_account_json,
                "sensitive": True,
            }
        },
        {
            "parameter": {
                "name": "Google Delegation User",
                "value": delegation_user,
                "sensitive": False,
            }
        },
        # Destination Parameters
        {
            "parameter": {
                "name": "Destination Database",
                "value": destination_database,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Destination Schema",
                "value": destination_schema,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Authentication Strategy",
                "value": "SNOWFLAKE_SESSION_TOKEN",
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Role",
                "value": snowflake_role,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Warehouse",
                "value": warehouse,
                "sensitive": False,
            }
        },
        # Destination Stage (for custom connector with configurable stage)
        {
            "parameter": {
                "name": "Destination Stage",
                "value": destination_stage,
                "sensitive": False,
            }
        },
        # Ingestion Parameters
        {
            "parameter": {
                "name": "Google Domain",
                "value": google_domain,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Google Drive ID",
                "value": google_drive_id,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Google Folder Name",
                "value": google_folder_name,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "File Extensions To Ingest",
                "value": file_extensions,
                "sensitive": False,
            }
        },
    ]
    
    update_parameters(base_url, context_id, parameters)
    
    print(f"  ✓ Configured for stage output")
    print(f"    Files will be written to: @{destination_database}.{destination_schema}.{destination_stage}")
    print(f"    Metadata table: {destination_database}.{destination_schema}.DOC_METADATA")


def configure_google_drive_cortex_connector(
    base_url: str,
    pg_id: str,
    service_account_json: str,
    google_drive_id: str,
    google_folder_name: str,
    delegation_user: str,
    google_domain: str,
    snowflake_role: str,
    destination_database: str,
    destination_schema: str,
    warehouse: str,
    cortex_search_role: str | None = None,
) -> None:
    """
    Configure the unstructured-google-drive-cdc connector (Cortex Search version).
    
    This connector parses documents and writes chunks to DOCS_CHUNKS table
    for use with Cortex Search.
    """
    # Get the parameter context for this process group
    context_id = find_process_group_parameter_context(base_url, pg_id)
    if not context_id:
        raise ValueError(f"Could not find parameter context for process group: {pg_id}")
    
    print(f"  Configuring parameter context: {context_id}")
    
    # JSON escape the service account JSON
    escaped_json = json.dumps(service_account_json)
    
    parameters = [
        {
            "parameter": {
                "name": "Google Drive ID",
                "value": google_drive_id,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Google Folder Name",
                "value": google_folder_name,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Google Delegation User",
                "value": delegation_user,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Google Domain",
                "value": google_domain,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "GCP Service Account JSON",
                "value": escaped_json,
                "sensitive": True,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Authentication Strategy",
                "value": "SNOWFLAKE_SESSION_TOKEN",
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Role",
                "value": snowflake_role,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Destination Database",
                "value": destination_database,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Destination Schema",
                "value": destination_schema,
                "sensitive": False,
            }
        },
        {
            "parameter": {
                "name": "Snowflake Warehouse",
                "value": warehouse,
                "sensitive": False,
            }
        },
    ]
    
    if cortex_search_role:
        parameters.append({
            "parameter": {
                "name": "Snowflake Cortex Search Service User Role",
                "value": cortex_search_role,
                "sensitive": False,
            }
        })
    
    update_parameters(base_url, context_id, parameters)
    
    print(f"  ✓ Configured for Cortex Search")
    print(f"    Chunks will be written to: {destination_database}.{destination_schema}.DOCS_CHUNKS")


def configure_update_chunks_processor(base_url: str, pg_id: str) -> None:
    """
    Configure the 'Update Chunks Table' processor to use 8 concurrent tasks.
    
    Path: "Google Drive (Cortex Connect)" -> "Update Snowflake Cortex" -> "Update Chunks and Permissions"
    """
    print("  Configuring processor concurrent tasks...")
    
    def find_processor_in_group(group_id: str, processor_name_pattern: str) -> str | None:
        """Recursively find a processor matching the pattern."""
        # Get the process group details
        pg_flow = make_nifi_request(base_url, f"/flow/process-groups/{group_id}?uiOnly=true")
        
        # Check processors in this group
        for processor in pg_flow.get("processGroupFlow", {}).get("flow", {}).get("processors", []):
            name = processor.get("component", {}).get("name", "")
            if processor_name_pattern.lower() in name.lower():
                return processor.get("id")
        
        # Check nested process groups
        for nested_pg in pg_flow.get("processGroupFlow", {}).get("flow", {}).get("processGroups", []):
            result = find_processor_in_group(nested_pg.get("id"), processor_name_pattern)
            if result:
                return result
        
        return None
    
    processor_id = find_processor_in_group(pg_id, "Update Chunks Table")
    if not processor_id:
        print("  Warning: Could not find 'Update Chunks Table' processor")
        return
    
    # Get the processor details
    processor = make_nifi_request(base_url, f"/processors/{processor_id}")
    revision = processor.get("revision", {"version": 0})
    
    # Update concurrent tasks
    payload = {
        "revision": revision,
        "component": {
            "id": processor_id,
            "config": {
                "concurrentlySchedulableTaskCount": "8",
            },
        },
    }
    
    make_nifi_request(base_url, f"/processors/{processor_id}", method="PUT", data=payload)
    print("  Set 'Update Chunks Table' processor to 8 concurrent tasks")


def enable_controller_services(base_url: str, pg_id: str) -> None:
    """Enable all controller services in a process group."""
    print("  Enabling controller services...")
    
    payload = {
        "id": pg_id,
        "disconnectedNodeAcknowledged": False,
        "state": "ENABLED",
    }
    
    make_nifi_request(
        base_url,
        f"/flow/process-groups/{pg_id}/controller-services",
        method="PUT",
        data=payload,
    )
    
    # Wait a bit for services to enable
    time.sleep(5)


def start_process_group(base_url: str, pg_id: str) -> None:
    """Start a process group."""
    print("  Starting process group...")
    
    payload = {
        "id": pg_id,
        "disconnectedNodeAcknowledged": False,
        "state": "RUNNING",
    }
    
    make_nifi_request(
        base_url,
        f"/flow/process-groups/{pg_id}",
        method="PUT",
        data=payload,
    )


def check_bulletins(base_url: str, pg_id: str) -> list[dict]:
    """Check for bulletins (warnings/errors) in a process group."""
    pg_flow = make_nifi_request(base_url, f"/flow/process-groups/{pg_id}?uiOnly=true")
    
    bulletins = []
    for pg in pg_flow.get("processGroupFlow", {}).get("flow", {}).get("processGroups", []):
        if pg.get("id") == pg_id:
            bulletins.extend(pg.get("bulletins", []))
    
    return bulletins


def parse_google_drive_url(url: str) -> tuple[str, str]:
    """
    Parse a Google Drive URL to extract the drive ID and folder name.
    
    Example URL: https://drive.google.com/drive/folders/0ADmOQBrQBWcWUk9PVA
    
    Returns:
        Tuple of (drive_id, folder_name)
    """
    # Pattern for shared drive folder URLs
    folder_pattern = re.compile(r"drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)")
    
    match = folder_pattern.search(url)
    if match:
        folder_id = match.group(1)
        # The folder ID in the URL could be either the drive ID or a folder within a drive
        return folder_id, ""
    
    raise ValueError(f"Could not parse Google Drive URL: {url}")


def extract_domain_from_email(email: str) -> str:
    """Extract the domain from an email address."""
    if "@" in email:
        return email.split("@")[1]
    return email


def create_or_enable_stage(
    conn: snowflake.connector.SnowflakeConnection,
    stage_name: str,
) -> None:
    """
    Create a stage with directory mode enabled, or enable directory mode on existing stage.
    
    Args:
        conn: Snowflake connection
        stage_name: Fully qualified stage name
    """
    with conn.cursor() as cur:
        # Try to create the stage with directory mode
        try:
            cur.execute(f"""
                CREATE STAGE IF NOT EXISTS {stage_name}
                ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
                DIRECTORY = (ENABLE = TRUE, REFRESH_ON_CREATE = TRUE)
            """)
            print(f"  Created/verified stage with directory enabled: {stage_name}")
        except Exception as e:
            # Stage might exist without directory mode, try to enable it
            print(f"  Stage exists, enabling directory mode: {stage_name}")
            try:
                cur.execute(f"""
                    ALTER STAGE {stage_name} SET
                        DIRECTORY = (ENABLE = TRUE)
                """)
            except Exception as alter_e:
                print(f"  Warning: Could not enable directory mode: {alter_e}")
                raise


def setup_google_drive_cdc(
    conn: snowflake.connector.SnowflakeConnection,
    runtime_url: str,
    service_account_json_path: str,
    google_drive_folder: str,
    delegation_user: str,
    stage_name: str,
    snowflake_role: str,
    warehouse: str,
    connector_name: str | None = None,
    connector_json_path: str | None = None,
    cortex_search_role: str | None = None,
    folder_name: str | None = None,
) -> tuple[str, str]:
    """
    Set up the Google Drive CDC connector.
    
    Args:
        conn: Snowflake connection
        runtime_url: Openflow runtime base URL
        service_account_json_path: Path to Google service account JSON file
        google_drive_folder: Google Drive shared drive URL or ID
        delegation_user: Google delegation user email
        stage_name: Fully qualified Snowflake stage name
        snowflake_role: Snowflake role for the connector
        warehouse: Snowflake warehouse name
        connector_name: Specific connector to use from registry (e.g., 'google-drive-no-cortex')
        connector_json_path: Path to custom connector JSON definition file (takes precedence over connector_name)
        cortex_search_role: Role for Cortex Search Service access
        folder_name: Name of folder within the shared drive to sync (optional, syncs all if not specified)
    
    Returns:
        Tuple of (Process Group ID, connector_type)
    """
    print("\nSetting up Google Drive CDC connector...")
    
    # Read service account JSON
    with open(service_account_json_path) as f:
        service_account_json = f.read()
    
    # Parse the Google Drive folder URL/ID
    if google_drive_folder.startswith("http"):
        google_drive_id, parsed_folder_name = parse_google_drive_url(google_drive_folder)
    else:
        google_drive_id = google_drive_folder
        parsed_folder_name = ""
    
    # Use explicitly provided folder_name if given, otherwise use parsed value
    effective_folder_name = folder_name if folder_name is not None else parsed_folder_name
    
    # Extract domain from delegation user
    google_domain = extract_domain_from_email(delegation_user)
    
    # Extract database, schema, and stage name from fully qualified stage name
    stage_parts = stage_name.split(".")
    if len(stage_parts) >= 3:
        destination_database = stage_parts[0]
        destination_schema = stage_parts[1]
        destination_stage = stage_parts[2]  # The actual stage name (e.g., DOCUMENTS or custom)
    else:
        raise ValueError(
            f"Stage name must be fully qualified (DB.SCHEMA.STAGE): {stage_name}"
        )
    
    if cortex_search_role is None:
        cortex_search_role = snowflake_role
    
    # Add the connector to the runtime - either from JSON file or registry
    if connector_json_path:
        # Deploy from local JSON file
        print(f"  Deploying connector from JSON file: {connector_json_path}")
        # Generate a unique group name based on stage name
        group_name = f"Google Drive CDC - {destination_stage}"
        pg_result = add_connector_from_json(runtime_url, connector_json_path, group_name=group_name)
        pg_id = pg_result.get("id")
        
        # Try to determine connector type from the JSON file name or content
        connector_type = os.path.basename(connector_json_path).replace(".json", "")
        if "no-cortex" in connector_json_path.lower() or "no_cortex" in connector_json_path.lower():
            connector_type = "google-drive-no-cortex"
        
        print(f"  Connector deployed from JSON, type: {connector_type}")
    else:
        # Deploy from registry
        print("  Finding connector registry...")
        registry_id, _ = find_connector_registry(runtime_url)
        
        # Find the Google Drive connector (prefer no-cortex for stage output)
        print("  Finding Google Drive connector...")
        connector = find_google_drive_connector(runtime_url, registry_id, connector_name)
        flow_id = connector.get("flowId")
        connector_type = flow_id
        
        print(f"  Using connector: {connector_type}")
        
        # Get the latest version
        print("  Getting latest connector version...")
        version = get_latest_connector_version(runtime_url, registry_id, flow_id)
        print(f"  Using connector version: {version}")
        
        # Add the connector to the runtime
        print("  Adding connector to runtime...")
        pg_result = add_connector_to_runtime(runtime_url, registry_id, flow_id, version)
        pg_id = pg_result.get("id")
    
    print(f"  Connector added with Process Group ID: {pg_id}")
    
    # Configure the connector based on type
    print("  Configuring connector parameters...")
    # Detect if this is a "stage output" connector (writes to stage, not Cortex Search)
    # - "no-cortex" in name means google-drive-no-cortex
    # - "to-stage" in name means our custom google-drive-to-stage-cdc connector
    # - connector_json_path being provided also means custom stage connector
    is_stage_connector = (
        "no-cortex" in connector_type.lower() or
        "to-stage" in connector_type.lower() or
        connector_json_path is not None
    )
    
    if is_stage_connector:
        configure_google_drive_no_cortex_connector(
            base_url=runtime_url,
            pg_id=pg_id,
            service_account_json=service_account_json,
            google_drive_id=google_drive_id,
            google_folder_name=effective_folder_name,
            delegation_user=delegation_user,
            google_domain=google_domain,
            snowflake_role=snowflake_role,
            destination_database=destination_database,
            destination_schema=destination_schema,
            destination_stage=destination_stage,
            warehouse=warehouse,
        )
    else:
        configure_google_drive_cortex_connector(
            base_url=runtime_url,
            pg_id=pg_id,
            service_account_json=service_account_json,
            google_drive_id=google_drive_id,
            google_folder_name=effective_folder_name,
            delegation_user=delegation_user,
            google_domain=google_domain,
            snowflake_role=snowflake_role,
            destination_database=destination_database,
            destination_schema=destination_schema,
            warehouse=warehouse,
            cortex_search_role=cortex_search_role,
        )
        # Configure the Update Chunks processor for better performance (only for Cortex connector)
        configure_update_chunks_processor(runtime_url, pg_id)
    
    return pg_id, connector_type


def start_connector(runtime_url: str, pg_id: str) -> None:
    """Start the connector and check for errors."""
    print("\nStarting connector...")
    
    # Enable controller services
    enable_controller_services(runtime_url, pg_id)
    
    # Start the process group
    start_process_group(runtime_url, pg_id)
    
    print("  Connector started!")
    
    # Wait and check for bulletins
    print("  Waiting 10 seconds to check for errors...")
    time.sleep(10)
    
    bulletins = check_bulletins(runtime_url, pg_id)
    if bulletins:
        print("\n  Warnings/Errors detected:")
        for bulletin in bulletins:
            msg = bulletin.get("bulletin", {}).get("message", "Unknown")
            print(f"    - {msg}")
    else:
        print("  No errors detected!")


def main():
    parser = argparse.ArgumentParser(
        description="Set up CDC from Google Shared Drive to Snowflake stage via Openflow"
    )
    parser.add_argument(
        "--service-account-json",
        required=True,
        help="Path to Google service account JSON file",
    )
    parser.add_argument(
        "--google-drive-folder",
        required=True,
        help="Google Shared Drive folder URL or ID",
    )
    parser.add_argument(
        "--delegation-user",
        required=True,
        help="Google delegation user email (must have access to the Shared Drive)",
    )
    parser.add_argument(
        "--runtime",
        required=True,
        help="Openflow runtime name or URL",
    )
    parser.add_argument(
        "--external-access-integration",
        required=True,
        help="Name of the External Access Integration for Google APIs",
    )
    parser.add_argument(
        "--stage",
        required=True,
        help=(
            "Snowflake stage reference (e.g., DB.SCHEMA.MY_STAGE). "
            "For google-drive-no-cortex: used to derive database/schema (stage name is always DOCUMENTS). "
            "For unstructured-google-drive-cdc: used to derive database/schema for tables."
        ),
    )
    parser.add_argument(
        "--role",
        required=True,
        help="Snowflake role for the connector to use",
    )
    parser.add_argument(
        "--cortex-search-role",
        default=None,
        help="Snowflake role for Cortex Search Service access (defaults to --role)",
    )
    parser.add_argument(
        "--warehouse",
        required=True,
        help="Snowflake warehouse name",
    )
    parser.add_argument(
        "--connection",
        default=None,
        help="Snowflake connection name (defaults to SNOWFLAKE_CONNECTION_NAME env var)",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Database to use (if stage name is not fully qualified)",
    )
    parser.add_argument(
        "--schema",
        default="PUBLIC",
        help="Schema to use (default: PUBLIC)",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start the connector after configuration",
    )
    parser.add_argument(
        "--skip-stage-creation",
        action="store_true",
        help="Skip stage creation/configuration",
    )
    parser.add_argument(
        "--connector",
        default=None,
        help=(
            "Specific connector to use from registry. Options: 'google-drive-no-cortex' (writes to stage), "
            "'unstructured-google-drive-cdc' (writes to table for Cortex Search). "
            "If not specified, prefers 'google-drive-no-cortex' if available."
        ),
    )
    parser.add_argument(
        "--connector-json",
        default=None,
        help=(
            "Path to a custom connector JSON definition file. "
            "Use this to deploy your own connector instead of one from the registry. "
            "This takes precedence over --connector."
        ),
    )
    parser.add_argument(
        "--list-connectors",
        action="store_true",
        help="List available Google Drive connectors and exit",
    )

    args = parser.parse_args()

    # Validate service account JSON file exists
    if not os.path.exists(args.service_account_json):
        print(f"Error: Service account JSON file not found: {args.service_account_json}", file=sys.stderr)
        sys.exit(1)

    # Connect to Snowflake
    conn = get_connection(args.connection)

    try:
        # Set database/schema context
        db, schema = setup_context(conn, args.database, args.schema)

        # Determine fully qualified stage name
        stage_name = qualify_name(args.stage, db, schema)

        print("=" * 60)
        print("Google Shared Drive to Snowflake Stage CDC Setup")
        print("=" * 60)
        print(f"\nConfiguration:")
        print(f"  Service Account JSON: {args.service_account_json}")
        print(f"  Google Drive Folder: {args.google_drive_folder}")
        print(f"  Delegation User: {args.delegation_user}")
        print(f"  Runtime: {args.runtime}")
        print(f"  External Access Integration: {args.external_access_integration}")
        print(f"  Stage: {stage_name}")
        print(f"  Role: {args.role}")
        print(f"  Warehouse: {args.warehouse}")

        # Note: For google-drive-no-cortex, the connector creates its own DOCUMENTS stage
        # For other connectors, we can create/enable the user-specified stage
        if not args.skip_stage_creation and args.connector and "no-cortex" not in args.connector.lower():
            print(f"\nSetting up stage...")
            create_or_enable_stage(conn, stage_name)
        elif not args.skip_stage_creation:
            print(f"\nNote: google-drive-no-cortex connector will create its own DOCUMENTS stage")

        # Find or construct the runtime URL
        if args.runtime.startswith("http"):
            runtime_url = args.runtime
            if not runtime_url.endswith("/nifi-api"):
                runtime_url = runtime_url.rstrip("/") + "/nifi-api"
        else:
            print(f"\nFinding runtime URL for: {args.runtime}")
            runtime_url = find_runtime_url(conn, args.runtime)
        
        print(f"  Runtime URL: {runtime_url}")

        # Handle --list-connectors option
        if args.list_connectors:
            print("\nListing available connectors...")
            registry_id, _ = find_connector_registry(runtime_url)
            connectors = list_available_connectors(runtime_url, registry_id)
            
            print("\nAvailable connectors:")
            google_drive_connectors = []
            for c in connectors:
                flow_id = c.get("flowId", "")
                desc = c.get("description", "No description")
                if "google" in flow_id.lower() or "drive" in flow_id.lower():
                    google_drive_connectors.append((flow_id, desc))
                    print(f"  * {flow_id}")
                    print(f"      {desc[:80]}...")
            
            if not google_drive_connectors:
                print("  (No Google Drive connectors found)")
                print("\n  All connectors:")
                for c in connectors[:10]:
                    print(f"    - {c.get('flowId')}")
            
            conn.close()
            return

        # Remind about External Access Integration configuration
        print(f"\n⚠️  Important: Ensure your External Access Integration ({args.external_access_integration})")
        print("  includes network rules for the following endpoints:")
        for endpoint in REQUIRED_NETWORK_ENDPOINTS:
            print(f"    - {endpoint}")
        print("  And that the integration is added to your Openflow Runtime.")

        # Validate connector JSON file if provided
        if args.connector_json and not os.path.exists(args.connector_json):
            print(f"Error: Connector JSON file not found: {args.connector_json}", file=sys.stderr)
            sys.exit(1)

        # Set up the CDC connector
        pg_id, connector_type = setup_google_drive_cdc(
            conn=conn,
            runtime_url=runtime_url,
            service_account_json_path=args.service_account_json,
            google_drive_folder=args.google_drive_folder,
            delegation_user=args.delegation_user,
            stage_name=stage_name,
            snowflake_role=args.role,
            warehouse=args.warehouse,
            connector_name=args.connector,
            connector_json_path=args.connector_json,
            cortex_search_role=args.cortex_search_role,
        )

        # Start the connector if requested
        if args.start:
            start_connector(runtime_url, pg_id)

        print("\n" + "=" * 60)
        print("Setup Complete!")
        print("=" * 60)
        
        # Extract database.schema from stage name
        db_schema = stage_name.rsplit(".", 1)[0]
        
        print(f"\nConnector: {connector_type}")
        
        # Output based on connector type
        is_stage_connector = "no-cortex" in connector_type.lower()
        
        if is_stage_connector:
            # Use the stage name from the --stage argument
            print(f"\nWhat happens next:")
            print(f"  1. Files from the Shared Drive will be synced continuously")
            print(f"  2. Raw files will be written to stage: @{stage_name}")
            print(f"  3. Metadata tracked in: {db_schema}.DOC_METADATA")
            print(f"  4. You can use directory table for CDC to downstream tables")
            
            if not args.start:
                print(f"\nTo start the connector, either:")
                print(f"  1. Run this script again with --start")
                print(f"  2. Start the connector from the Openflow UI")
            
            print(f"\nTo list synced files:")
            print(f"  LIST @{stage_name};")
            print(f"\nTo query directory table:")
            print(f"  SELECT * FROM DIRECTORY(@{stage_name});")
            print(f"\nTo view file metadata:")
            print(f"  SELECT * FROM {db_schema}.DOC_METADATA;")
            print(f"\nFor downstream processing, create a stream on the directory table:")
            print(f"  CREATE STREAM my_stream ON DIRECTORY(@{stage_name});")
        else:
            print(f"\nWhat happens next:")
            print(f"  1. Files from the Shared Drive will be synced continuously")
            print(f"  2. Documents will be parsed and chunked")
            print(f"  3. Chunks will be written to: {db_schema}.DOCS_CHUNKS")
            print(f"  4. A Cortex Search Service will be created for natural language search")
            
            if not args.start:
                print(f"\nTo start the connector, either:")
                print(f"  1. Run this script again with --start")
                print(f"  2. Start the connector from the Openflow UI")
            
            print(f"\nTo check synced document chunks:")
            print(f"  SELECT * FROM {db_schema}.DOCS_CHUNKS LIMIT 10;")
            
            print(f"\nStage (also created for potential downstream use):")
            print(f"  LIST @{stage_name};")
            print(f"  SELECT * FROM DIRECTORY(@{stage_name});")

    finally:
        conn.close()


if __name__ == "__main__":
    main()

