#!/usr/bin/env python3
"""
Integration test for upload_google_shared_drive_via_openflow_to_stage.py

Tests that the Google Drive to Stage CDC connector successfully syncs files
from a Google Shared Drive to a Snowflake stage.

Environment variables:
  - SNOWFLAKE_CONNECTION_NAME: Connection name from ~/.snowflake/connections.toml
  - SNOWFLAKE_PAT: Programmatic Access Token for Openflow API
  - TEST_WAREHOUSE: Warehouse to use for tests (optional, uses current if not set)
  - TEST_DATABASE: Database for tests (optional, uses current if not set)

Run with:
  SNOWFLAKE_PAT="your-pat" pytest tests/test_google_drive_to_stage.py -v -m integration
"""

import functools
import io
import json
import os
import sys
import time
import uuid

import pytest
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snowflake_utils import qualify_name  # noqa: E402
from upload_google_shared_drive_via_openflow_to_stage import (  # noqa: E402
    setup_google_drive_cdc,
    start_connector,
    get_pat_token,
    make_nifi_request,
)


# --- Google Drive API Utilities ---

def get_google_drive_service(service_account_json_path: str, delegation_user: str):
    """
    Create a Google Drive API service using service account credentials.
    
    Args:
        service_account_json_path: Path to service account JSON file
        delegation_user: Email of user to impersonate
    
    Returns:
        Google Drive API service object
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    credentials = service_account.Credentials.from_service_account_file(
        service_account_json_path,
        scopes=SCOPES,
        subject=delegation_user,
    )
    
    return build('drive', 'v3', credentials=credentials)


def find_folder_by_name(service, parent_id: str, folder_name: str) -> str | None:
    """
    Find a folder by name within a parent folder.
    
    Args:
        service: Google Drive API service
        parent_id: ID of the parent folder/drive
        folder_name: Name of the folder to find
    
    Returns:
        Folder ID if found, None otherwise
    """
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
    
    results = service.files().list(
        q=query,
        spaces='drive',
        corpora='drive',
        driveId=parent_id,
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields='files(id, name)',
    ).execute()
    
    files = results.get('files', [])
    if files:
        return files[0]['id']
    return None


def create_folder(service, parent_id: str, folder_name: str, drive_id: str) -> str:
    """
    Create a folder in Google Drive.
    
    Args:
        service: Google Drive API service
        parent_id: ID of the parent folder
        folder_name: Name for the new folder
        drive_id: ID of the shared drive
    
    Returns:
        ID of the created folder
    """
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    
    folder = service.files().create(
        body=file_metadata,
        supportsAllDrives=True,
        fields='id',
    ).execute()
    
    return folder.get('id')


def upload_test_file(service, parent_id: str, filename: str, content: bytes, mime_type: str = 'text/plain') -> str:
    """
    Upload a file to Google Drive.
    
    Args:
        service: Google Drive API service
        parent_id: ID of the parent folder
        filename: Name for the file
        content: File content as bytes
        mime_type: MIME type of the file
    
    Returns:
        ID of the uploaded file
    """
    from googleapiclient.http import MediaIoBaseUpload
    
    file_metadata = {
        'name': filename,
        'parents': [parent_id],
    }
    
    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype=mime_type,
        resumable=True,
    )
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        supportsAllDrives=True,
        fields='id',
    ).execute()
    
    return file.get('id')


def delete_file(service, file_id: str) -> bool:
    """
    Delete (trash) a file from Google Drive.
    
    Note: In shared drives, we can only trash files, not permanently delete them.
    The canDelete capability is usually False, but canTrash is True.
    
    Args:
        service: Google Drive API service
        file_id: ID of the file to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # In shared drives, we need to trash the file instead of deleting
        # The delete() method requires canDelete capability which is usually False
        service.files().update(
            fileId=file_id,
            body={'trashed': True},
            supportsAllDrives=True,
        ).execute()
        return True
    except Exception as e:
        print(f"Warning: Could not trash file {file_id}: {e}")
        return False


def delete_folder(service, folder_id: str) -> bool:
    """
    Delete (trash) a folder from Google Drive.
    
    Note: In shared drives, we can only trash folders, not permanently delete them.
    The canDelete capability is usually False, but canTrash is True.
    
    Args:
        service: Google Drive API service
        folder_id: ID of the folder to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # In shared drives, we need to trash the folder instead of deleting
        service.files().update(
            fileId=folder_id,
            body={'trashed': True},
            supportsAllDrives=True,
        ).execute()
        return True
    except Exception as e:
        print(f"Warning: Could not trash folder {folder_id}: {e}")
        return False


# --- Cleanup Utilities ---

def cleanup_openflow_process_group(base_url: str, pg_id: str, pat_token: str = None, max_retries: int = 5) -> bool:
    """
    Stop, disable services, empty queues, and delete a process group.
    
    This is a robust cleanup that handles various states the process group
    might be in. Returns True if cleanup succeeded, False otherwise.
    """
    if pat_token is None:
        try:
            pat_token = get_pat_token()
        except ValueError:
            print(f"  Warning: Cannot clean up process group {pg_id} - no PAT token")
            return False
    
    headers = {"Authorization": f"Bearer {pat_token}"}
    
    try:
        print(f"  Cleaning up process group: {pg_id}")
        
        # Step 1: Stop all processors
        print(f"    Stopping processors...")
        try:
            requests.put(
                f"{base_url}/flow/process-groups/{pg_id}",
                headers={**headers, "Content-Type": "application/json"},
                json={"id": pg_id, "state": "STOPPED", "disconnectedNodeAcknowledged": False},
                timeout=30,
            )
        except Exception as e:
            print(f"    Warning: Error stopping processors: {e}")
        
        time.sleep(3)
        
        # Step 2: Disable controller services (may need multiple attempts)
        print(f"    Disabling controller services...")
        for _ in range(3):
            try:
                requests.put(
                    f"{base_url}/flow/process-groups/{pg_id}/controller-services",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"id": pg_id, "state": "DISABLED", "disconnectedNodeAcknowledged": False},
                    timeout=30,
                )
                time.sleep(3)
            except Exception as e:
                print(f"    Warning: Error disabling services: {e}")
        
        # Step 3: Drop all flowfiles
        print(f"    Dropping flowfiles...")
        try:
            drop_response = requests.post(
                f"{base_url}/process-groups/{pg_id}/empty-all-connections-requests",
                headers={**headers, "Content-Type": "application/json"},
                json={},
                timeout=30,
            )
            if drop_response.status_code == 200:
                # Wait for drop to complete
                drop_request = drop_response.json().get("dropRequest", {})
                drop_id = drop_request.get("id")
                if drop_id:
                    for _ in range(30):
                        time.sleep(2)
                        try:
                            status_response = requests.get(
                                f"{base_url}/process-groups/{pg_id}/empty-all-connections-requests/{drop_id}",
                                headers=headers,
                                timeout=30,
                            )
                            if status_response.status_code == 200:
                                if status_response.json().get("dropRequest", {}).get("finished"):
                                    break
                        except Exception:
                            pass
        except Exception as e:
            print(f"    Warning: Error dropping flowfiles: {e}")
        
        time.sleep(5)
        
        # Step 4: Delete with retries
        print(f"    Deleting process group...")
        for attempt in range(max_retries):
            try:
                pg_response = requests.get(
                    f"{base_url}/process-groups/{pg_id}",
                    headers=headers,
                    timeout=30,
                )
                if pg_response.status_code == 404:
                    print(f"    ✓ Process group already deleted")
                    return True
                    
                if pg_response.status_code == 200:
                    version = pg_response.json().get("revision", {}).get("version", 0)
                    
                    delete_response = requests.delete(
                        f"{base_url}/process-groups/{pg_id}?version={version}&clientId=test-cleanup-{attempt}",
                        headers=headers,
                        timeout=30,
                    )
                    
                    if delete_response.status_code in (200, 204):
                        print(f"    ✓ Process group deleted successfully")
                        return True
                    elif delete_response.status_code == 404:
                        print(f"    ✓ Process group already deleted")
                        return True
                    elif delete_response.status_code == 409:
                        # Conflict - wait longer and retry
                        wait_time = (attempt + 1) * 5
                        print(f"    Conflict, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"    Warning: Delete returned {delete_response.status_code}")
            except Exception as e:
                print(f"    Warning: Error on attempt {attempt + 1}: {e}")
            
            time.sleep(5)
        
        print(f"    ⚠ Could not delete process group after {max_retries} attempts")
        return False
        
    except Exception as e:
        print(f"    Error during cleanup: {e}")
        return False


def cleanup_openflow_test_process_groups(base_url: str, name_prefix: str = "Google Drive CDC") -> int:
    """
    Clean up all process groups matching the given name prefix.
    
    Returns the number of process groups cleaned up.
    """
    try:
        pat_token = get_pat_token()
    except ValueError:
        print("Cannot clean up Openflow - no PAT token")
        return 0
    
    headers = {"Authorization": f"Bearer {pat_token}"}
    cleaned = 0
    
    try:
        # Get all process groups
        response = requests.get(
            f"{base_url}/flow/process-groups/root?uiOnly=true",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        
        process_groups = response.json().get("processGroupFlow", {}).get("flow", {}).get("processGroups", [])
        
        for pg in process_groups:
            name = pg.get("component", {}).get("name", "")
            pg_id = pg.get("id", "")
            
            if name.startswith(name_prefix):
                print(f"Found test process group: {name}")
                if cleanup_openflow_process_group(base_url, pg_id, pat_token):
                    cleaned += 1
        
        return cleaned
        
    except Exception as e:
        print(f"Error listing process groups: {e}")
        return cleaned

from .test_helpers import requires_snowflake  # noqa: E402


# --- Test Configuration (Hardcoded) ---

# Database/schema for tests (will be created if doesn't exist)
TEST_DATABASE = "OPENFLOW_TEST"
TEST_SCHEMA_PREFIX = "GDRIVE_CDC_TEST"

# Google Shared Drive configuration
GOOGLE_SHARED_DRIVE_ID = "0ADmOQBrQBWcWUk9PVA"  # The shared drive ID
GOOGLE_SHARED_DRIVE_URL = f"https://drive.google.com/drive/folders/{GOOGLE_SHARED_DRIVE_ID}"
GOOGLE_PARENT_FOLDER_NAME = "davidkurokawa"  # Parent folder for test subfolders
GOOGLE_DELEGATION_USER = "openflow-test-user@engsandbox.snowflake.com"

# Service account credentials (path only - never read contents)
SERVICE_ACCOUNT_JSON_PATH = os.path.expanduser("~/Downloads/google-drive-service-account.json")

# Openflow runtime
OPENFLOW_RUNTIME_URL = "https://of--sfengineering-openflow-dev-preprod8.awsuswest2preprod8.pp-snowflakecomputing.app/dkurokawa/nifi-api"

# Connector JSON path (the custom connector with configurable stage)
CONNECTOR_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "google-drive-to-stage-cdc-connector.json"
)

# How long to wait for files to sync (in seconds)
SYNC_WAIT_TIME = 120  # 2 minutes for initial sync
CDC_WAIT_TIME = 90  # 1.5 minutes for CDC changes (processor yields for 30 sec after no changes)
SYNC_CHECK_INTERVAL = 10  # Check every 10 seconds

# Test files to upload
TEST_FILES = [
    ("test_document_1.txt", b"This is test document 1 for Google Drive CDC integration test.\nIt contains some sample text.", "text/plain"),
    ("test_document_2.txt", b"This is test document 2.\nAnother file to verify the CDC sync works correctly.", "text/plain"),
    ("test_data.json", b'{"test": true, "message": "Sample JSON file for CDC test", "items": [1, 2, 3]}', "application/json"),
]


def requires_openflow_pat(func):
    """Decorator to skip tests if SNOWFLAKE_PAT is not set."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            get_pat_token()
        except ValueError:
            pytest.skip("SNOWFLAKE_PAT not set")
        return func(*args, **kwargs)
    return pytest.mark.integration(wrapper)


@requires_snowflake
class TestGoogleDriveToStage:
    """Integration tests for Google Drive to Stage CDC."""
    
    # Track deployed process groups for cleanup
    _deployed_process_groups = []
    
    # Track Google Drive test folder for cleanup
    _gdrive_test_folder_id = None
    _gdrive_service = None

    @pytest.fixture(scope="class")
    def gdrive_test_folder(self):
        """
        Create a test folder in Google Drive with test files.
        
        Creates a subfolder with a UUID name inside davidkurokawa folder,
        uploads test files, and cleans up after tests.
        
        Yields:
            Tuple of (folder_name, folder_id)
        """
        print("\n--- Google Drive Setup ---")
        
        # Create the Drive service
        print(f"Connecting to Google Drive as {GOOGLE_DELEGATION_USER}...")
        service = get_google_drive_service(SERVICE_ACCOUNT_JSON_PATH, GOOGLE_DELEGATION_USER)
        TestGoogleDriveToStage._gdrive_service = service
        
        # Find the parent folder (davidkurokawa)
        print(f"Finding parent folder: {GOOGLE_PARENT_FOLDER_NAME}...")
        parent_folder_id = find_folder_by_name(service, GOOGLE_SHARED_DRIVE_ID, GOOGLE_PARENT_FOLDER_NAME)
        if not parent_folder_id:
            pytest.fail(f"Could not find parent folder '{GOOGLE_PARENT_FOLDER_NAME}' in shared drive")
        print(f"  Found parent folder: {parent_folder_id}")
        
        # Create a unique test folder
        unique_id = uuid.uuid4().hex[:8]
        test_folder_name = f"test_cdc_{unique_id}"
        print(f"Creating test folder: {test_folder_name}...")
        
        test_folder_id = create_folder(service, parent_folder_id, test_folder_name, GOOGLE_SHARED_DRIVE_ID)
        TestGoogleDriveToStage._gdrive_test_folder_id = test_folder_id
        print(f"  Created folder: {test_folder_id}")
        
        # Upload test files
        print(f"Uploading {len(TEST_FILES)} test files...")
        uploaded_files = []
        for filename, content, mime_type in TEST_FILES:
            file_id = upload_test_file(service, test_folder_id, filename, content, mime_type)
            uploaded_files.append((filename, file_id))
            print(f"  Uploaded: {filename} ({file_id})")
        
        print(f"✓ Test folder ready with {len(uploaded_files)} files")
        
        # The full folder path for the connector
        full_folder_path = f"{GOOGLE_PARENT_FOLDER_NAME}/{test_folder_name}"
        
        yield (full_folder_path, test_folder_id)
        
        # Cleanup: Delete the test folder
        print("\n--- Google Drive Cleanup ---")
        print(f"Deleting test folder: {test_folder_name} ({test_folder_id})...")
        if delete_folder(service, test_folder_id):
            print("✓ Test folder deleted")
            TestGoogleDriveToStage._gdrive_test_folder_id = None
        else:
            print("⚠ Could not delete test folder")

    @pytest.fixture(scope="class")
    def gdrive_test_database(self, snowflake_connection):
        """Ensure test database exists."""
        with snowflake_connection.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {TEST_DATABASE}")
            cur.execute(f"USE DATABASE {TEST_DATABASE}")
        return TEST_DATABASE

    @pytest.fixture(scope="class")
    def gdrive_test_schema(self, snowflake_connection, gdrive_test_database):
        """Create a unique test schema for this test session."""
        unique_id = uuid.uuid4().hex[:8].upper()
        schema_name = f"{TEST_SCHEMA_PREFIX}_{unique_id}"
        full_schema = f"{gdrive_test_database}.{schema_name}"
        
        with snowflake_connection.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {full_schema}")
            cur.execute(f"USE SCHEMA {full_schema}")
        
        yield schema_name
        
        # Cleanup: Drop the schema after tests
        print(f"\n--- Snowflake Cleanup ---")
        print(f"Dropping schema: {full_schema}")
        with snowflake_connection.cursor() as cur:
            try:
                cur.execute(f"DROP SCHEMA IF EXISTS {full_schema} CASCADE")
                print(f"✓ Schema dropped successfully")
            except Exception as e:
                print(f"⚠ Schema cleanup warning: {e}")

    @pytest.fixture(scope="class")
    def gdrive_test_warehouse(self, snowflake_connection):
        """Get the warehouse to use for tests."""
        with snowflake_connection.cursor() as cur:
            cur.execute("SELECT CURRENT_WAREHOUSE()")
            result = cur.fetchone()
            if result and result[0]:
                return result[0]
            else:
                pytest.skip("No warehouse available for tests")

    @pytest.fixture(scope="class")
    def gdrive_test_stage(self, snowflake_connection, gdrive_test_database, gdrive_test_schema):
        """
        Create a unique stage name for the Google Drive CDC test.
        
        Note: The connector creates the stage itself, so we just generate a name.
        """
        unique_id = uuid.uuid4().hex[:8].upper()
        stage_name = f"GDRIVE_STAGE_{unique_id}"
        full_stage_name = f"{gdrive_test_database}.{gdrive_test_schema}.{stage_name}"
        
        yield full_stage_name
        
        # Cleanup is handled by dropping the schema (CASCADE)
    
    @pytest.fixture(scope="class", autouse=True)
    def openflow_cleanup(self, request):
        """
        Cleanup fixture that runs after all tests in the class.
        
        Cleans up any Openflow process groups that were deployed during tests.
        """
        # Clear the list before tests
        TestGoogleDriveToStage._deployed_process_groups = []
        
        yield  # Run tests
        
        # Cleanup after tests
        print(f"\n--- Openflow Cleanup ---")
        
        if TestGoogleDriveToStage._deployed_process_groups:
            for pg_id in TestGoogleDriveToStage._deployed_process_groups:
                cleanup_openflow_process_group(OPENFLOW_RUNTIME_URL, pg_id)
        else:
            print("No process groups to clean up")
        
        # Also clean up any orphaned test process groups (from failed runs)
        print("\nChecking for orphaned test process groups...")
        cleaned = cleanup_openflow_test_process_groups(
            OPENFLOW_RUNTIME_URL, 
            name_prefix="Google Drive CDC -"
        )
        if cleaned > 0:
            print(f"Cleaned up {cleaned} orphaned process group(s)")

    def test_prerequisites_service_account_exists(self):
        """Verify the service account JSON file exists (without reading it)."""
        assert os.path.exists(SERVICE_ACCOUNT_JSON_PATH), (
            f"Service account JSON file not found: {SERVICE_ACCOUNT_JSON_PATH}\n"
            "Please ensure the file exists at this location."
        )

    def test_prerequisites_connector_json_exists(self):
        """Verify the custom connector JSON file exists."""
        assert os.path.exists(CONNECTOR_JSON_PATH), (
            f"Connector JSON file not found: {CONNECTOR_JSON_PATH}\n"
            "Run the script to generate it first."
        )

    def test_prerequisites_pat_available(self):
        """Verify SNOWFLAKE_PAT is set."""
        try:
            token = get_pat_token()
            assert token is not None and len(token) > 0
        except ValueError:
            pytest.skip("SNOWFLAKE_PAT environment variable not set")

    @requires_openflow_pat
    def test_prerequisites_runtime_accessible(self):
        """Verify the Openflow runtime is accessible."""
        try:
            result = make_nifi_request(
                OPENFLOW_RUNTIME_URL, 
                "/flow/process-groups/root?uiOnly=true"
            )
            assert "processGroupFlow" in result
        except Exception as e:
            pytest.fail(f"Failed to access Openflow runtime at {OPENFLOW_RUNTIME_URL}: {e}")

    @pytest.mark.integration
    @requires_openflow_pat
    def test_files_appear_in_stage(
        self,
        snowflake_connection,
        gdrive_test_folder,
        gdrive_test_stage,
        gdrive_test_warehouse,
    ):
        """
        Test that files from Google Drive appear in the Snowflake stage.
        
        This is the main integration test that:
        1. Creates a test folder in Google Drive with test files
        2. Deploys the custom connector from JSON
        3. Configures it to sync from the test folder
        4. Starts the connector
        5. Waits for files to sync
        6. Verifies files appear in the stage
        7. Cleans up the test folder
        """
        # Get the test folder path from the fixture
        test_folder_path, test_folder_id = gdrive_test_folder
        
        # Get role from current session
        with snowflake_connection.cursor() as cur:
            cur.execute("SELECT CURRENT_ROLE()")
            current_role = cur.fetchone()[0]

        print(f"\n{'='*60}")
        print("Google Drive to Stage CDC Integration Test")
        print(f"{'='*60}")
        print(f"Stage: {gdrive_test_stage}")
        print(f"Google Drive folder: {test_folder_path}")
        print(f"Expected files: {len(TEST_FILES)}")
        print(f"Delegation user: {GOOGLE_DELEGATION_USER}")
        print(f"Role: {current_role}")
        print(f"Warehouse: {gdrive_test_warehouse}")
        print(f"Runtime: {OPENFLOW_RUNTIME_URL}")

        # Deploy and configure the connector using our custom JSON
        # This allows us to use a configurable stage name
        pg_id, connector_type = setup_google_drive_cdc(
            conn=snowflake_connection,
            runtime_url=OPENFLOW_RUNTIME_URL,
            service_account_json_path=SERVICE_ACCOUNT_JSON_PATH,
            google_drive_folder=GOOGLE_SHARED_DRIVE_URL,
            delegation_user=GOOGLE_DELEGATION_USER,
            stage_name=gdrive_test_stage,
            snowflake_role=current_role,
            warehouse=gdrive_test_warehouse,
            connector_json_path=CONNECTOR_JSON_PATH,  # Use custom connector with configurable stage
            folder_name=test_folder_path,  # Dynamically created test folder
        )
        
        # Register for cleanup (even if test fails)
        TestGoogleDriveToStage._deployed_process_groups.append(pg_id)
        
        # With the custom connector, the stage name is from gdrive_test_stage
        actual_stage = gdrive_test_stage
        print(f"Files will be written to stage: {actual_stage}")

        print(f"\nConnector deployed: {connector_type}")
        print(f"Process Group ID: {pg_id}")

        # Start the connector
        try:
            start_connector(OPENFLOW_RUNTIME_URL, pg_id)
            print("Connector started!")
        except Exception as e:
            pytest.fail(f"Failed to start connector: {e}")

        # Wait for files to sync
        print(f"\nWaiting for files to sync (up to {SYNC_WAIT_TIME} seconds)...")
        
        files_found = False
        file_count = 0
        start_time = time.time()
        
        while time.time() - start_time < SYNC_WAIT_TIME:
            with snowflake_connection.cursor() as cur:
                try:
                    # First, refresh the directory table
                    cur.execute(f"ALTER STAGE {actual_stage} REFRESH")
                    
                    # Query the directory table
                    cur.execute(f"SELECT COUNT(*) FROM DIRECTORY(@{actual_stage})")
                    file_count = cur.fetchone()[0]
                    
                    elapsed = int(time.time() - start_time)
                    print(f"  [{elapsed}s] Files in stage: {file_count}")
                    
                    if file_count > 0:
                        files_found = True
                        break
                except Exception as e:
                    elapsed = int(time.time() - start_time)
                    print(f"  [{elapsed}s] Waiting for stage... ({type(e).__name__})")
            
            time.sleep(SYNC_CHECK_INTERVAL)

        # Assertions
        assert files_found, (
            f"No files appeared in stage {actual_stage} after {SYNC_WAIT_TIME} seconds.\n"
            "Check the connector logs in Openflow for errors:\n"
            f"  {OPENFLOW_RUNTIME_URL.replace('/nifi-api', '')}"
        )

        # List the files that were synced
        with snowflake_connection.cursor() as cur:
            cur.execute(f"""
                SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED 
                FROM DIRECTORY(@{actual_stage})
                ORDER BY LAST_MODIFIED DESC
                LIMIT 20
            """)
            files = cur.fetchall()
            initial_file_count = len(files)
            
            print(f"\n✓ Successfully synced {initial_file_count} file(s):")
            for f in files:
                print(f"  - {f[0]} ({f[1]} bytes)")

        # Check metadata table was also populated
        db_schema = actual_stage.rsplit(".", 1)[0]
        with snowflake_connection.cursor() as cur:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {db_schema}.DOC_METADATA")
                metadata_count = cur.fetchone()[0]
                print(f"\n✓ DOC_METADATA table has {metadata_count} record(s)")
            except Exception as e:
                print(f"\n⚠ Could not query DOC_METADATA: {e}")

        # --- Test CDC: Add a new file AND delete an existing file simultaneously ---
        print(f"\n{'='*60}")
        print("Testing CDC: Adding new file AND deleting existing file...")
        print(f"{'='*60}")
        
        service = TestGoogleDriveToStage._gdrive_service
        if service is None:
            print("⚠ Google Drive service not available, skipping CDC test")
        else:
            # Get the file ID of one of the original test files to delete
            # We uploaded test_document_1.txt, test_document_2.txt, and test_data.json
            # Let's find test_document_2.txt in the test folder
            file_to_delete_id = None
            file_to_delete_name = "test_document_2.txt"
            
            # List files in the test folder to get the ID
            file_query = f"'{test_folder_id}' in parents and name = '{file_to_delete_name}' and trashed = false"
            file_results = service.files().list(
                q=file_query,
                spaces='drive',
                corpora='drive',
                driveId=GOOGLE_SHARED_DRIVE_ID,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields='files(id, name)',
            ).execute()
            
            files = file_results.get('files', [])
            if files:
                file_to_delete_id = files[0]['id']
                print(f"  Found file to delete: {file_to_delete_name} ({file_to_delete_id})")
            
            # Upload a new file
            new_file_content = b"This is a NEW file added after initial sync to test CDC functionality."
            new_file_name = f"cdc_test_file_{uuid.uuid4().hex[:8]}.txt"
            new_file_id = upload_test_file(service, test_folder_id, new_file_name, new_file_content)
            print(f"  Added new file: {new_file_name} ({new_file_id})")
            
            # Delete (trash) one of the original files
            if file_to_delete_id:
                if delete_file(service, file_to_delete_id):
                    print(f"  Trashed existing file: {file_to_delete_name}")
                else:
                    print(f"  ⚠ Could not trash file {file_to_delete_id}")
                    file_to_delete_id = None  # Mark as failed
            
            # Give Google Drive API time to propagate both changes
            print("  Waiting 10s for changes to propagate in Google Drive...")
            time.sleep(10)
            
            # Wait for CDC to detect both changes
            # The count should stay the same (one added, one deleted), but the files should be different
            print(f"\nWaiting for CDC to sync changes (up to {CDC_WAIT_TIME} seconds)...")
            print(f"  Expected: new file appears, deleted file disappears (count stays at {initial_file_count})")
            
            cdc_complete = False
            new_file_exists = False
            deleted_file_gone = False
            start_time = time.time()
            
            while time.time() - start_time < CDC_WAIT_TIME:
                with snowflake_connection.cursor() as cur:
                    try:
                        cur.execute(f"ALTER STAGE {actual_stage} REFRESH")
                        
                        # Check if new file exists
                        cur.execute(f"""
                            SELECT COUNT(*) FROM DIRECTORY(@{actual_stage})
                            WHERE RELATIVE_PATH LIKE '%{new_file_name}%'
                        """)
                        new_file_exists = cur.fetchone()[0] > 0
                        
                        # Check if deleted file still exists (by looking for original file name pattern)
                        cur.execute(f"""
                            SELECT COUNT(*) FROM DIRECTORY(@{actual_stage})
                            WHERE RELATIVE_PATH LIKE '%{file_to_delete_name}%'
                        """)
                        deleted_file_gone = cur.fetchone()[0] == 0
                        
                        # Get total count
                        cur.execute(f"SELECT COUNT(*) FROM DIRECTORY(@{actual_stage})")
                        current_count = cur.fetchone()[0]
                        
                        elapsed = int(time.time() - start_time)
                        status = []
                        status.append("new:✓" if new_file_exists else "new:✗")
                        status.append("deleted:✓" if deleted_file_gone else "deleted:✗")
                        
                        print(f"  [{elapsed}s] Files: {current_count}, {', '.join(status)}")
                        
                        # CDC is complete when new file exists AND deleted file is gone
                        if new_file_exists and deleted_file_gone:
                            cdc_complete = True
                            break
                    except Exception as e:
                        elapsed = int(time.time() - start_time)
                        print(f"  [{elapsed}s] Error checking stage: {type(e).__name__}")
                
                time.sleep(SYNC_CHECK_INTERVAL)
            
            # Verify CDC worked for both add and delete
            assert cdc_complete, (
                f"CDC did not complete after {CDC_WAIT_TIME} seconds.\n"
                f"New file exists: {new_file_exists}, Deleted file gone: {deleted_file_gone}\n"
                "CDC add/delete may not be working correctly."
            )
            
            # List final files
            with snowflake_connection.cursor() as cur:
                cur.execute(f"""
                    SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED 
                    FROM DIRECTORY(@{actual_stage})
                    ORDER BY LAST_MODIFIED DESC
                    LIMIT 20
                """)
                final_files = cur.fetchall()
                
                print(f"\n✓ CDC working! Final state: {len(final_files)} file(s) in stage:")
                for f in final_files:
                    is_new = new_file_name in f[0]
                    marker = " (ADDED)" if is_new else ""
                    print(f"  - {f[0]} ({f[1]} bytes){marker}")

        print(f"\n{'='*60}")
        print("Test PASSED!")
        print(f"{'='*60}")


# --- Standalone test runner ---

def run_basic_test(cleanup: bool = True):
    """
    Run a basic test without pytest.
    
    This can be used for quick manual testing.
    
    Args:
        cleanup: If True, clean up Openflow and Snowflake artifacts after test.
    
    Requires:
      - SNOWFLAKE_CONNECTION_NAME environment variable
      - SNOWFLAKE_PAT environment variable
    """
    # Import here to avoid issues when running with pytest
    from snowflake_utils import get_connection
    
    print("=" * 60)
    print("Basic Google Drive to Stage Test")
    print("=" * 60)
    
    pg_id = None  # Track for cleanup
    conn = None
    test_schema = None
    
    try:
        # Check prerequisites
        print("\n1. Checking prerequisites...")
        
        if not os.path.exists(SERVICE_ACCOUNT_JSON_PATH):
            print(f"   ✗ Service account file not found: {SERVICE_ACCOUNT_JSON_PATH}")
            return False
        print(f"   ✓ Service account file exists")
        
        if not os.path.exists(CONNECTOR_JSON_PATH):
            print(f"   ✗ Connector JSON not found: {CONNECTOR_JSON_PATH}")
            return False
        print(f"   ✓ Connector JSON exists")
        
        try:
            get_pat_token()
            print("   ✓ SNOWFLAKE_PAT is set")
        except ValueError:
            print("   ✗ SNOWFLAKE_PAT not set")
            return False
        
        print(f"   ✓ Delegation user: {GOOGLE_DELEGATION_USER}")
        
        # Check runtime
        print("\n2. Checking Openflow runtime...")
        try:
            result = make_nifi_request(OPENFLOW_RUNTIME_URL, "/flow/process-groups/root?uiOnly=true")
            print("   ✓ Runtime is accessible")
        except Exception as e:
            print(f"   ✗ Runtime not accessible: {e}")
            return False
        
        # Connect to Snowflake
        print("\n3. Connecting to Snowflake...")
        try:
            conn = get_connection()
            print("   ✓ Connected to Snowflake")
        except Exception as e:
            print(f"   ✗ Failed to connect: {e}")
            return False
        
        # Get current context
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            db, schema, role, warehouse = cur.fetchone()
            print(f"   Database: {db}")
            print(f"   Schema: {schema}")
            print(f"   Role: {role}")
            print(f"   Warehouse: {warehouse}")
        
        if not warehouse:
            print("   ✗ No warehouse set")
            return False
        
        # Create a unique test schema
        unique_id = uuid.uuid4().hex[:8].upper()
        test_schema = f"{TEST_DATABASE}.GDRIVE_MANUAL_TEST_{unique_id}"
        
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {TEST_DATABASE}")
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {test_schema}")
            cur.execute(f"USE SCHEMA {test_schema}")
        
        test_stage_name = f"{test_schema}.GDRIVE_STAGE"
        
        print(f"\n4. Test configuration:")
        print(f"   Schema: {test_schema}")
        print(f"   Stage: {test_stage_name}")
        print(f"   Folder: {GOOGLE_FOLDER_NAME}")
        
        # Deploy connector
        print(f"\n5. Deploying connector...")
        try:
            pg_id, connector_type = setup_google_drive_cdc(
                conn=conn,
                runtime_url=OPENFLOW_RUNTIME_URL,
                service_account_json_path=SERVICE_ACCOUNT_JSON_PATH,
                google_drive_folder=GOOGLE_SHARED_DRIVE_URL,
                delegation_user=GOOGLE_DELEGATION_USER,
                stage_name=test_stage_name,
                snowflake_role=role,
                warehouse=warehouse,
                connector_json_path=CONNECTOR_JSON_PATH,
                folder_name=GOOGLE_FOLDER_NAME,
            )
            print(f"   ✓ Connector deployed: {connector_type}")
            print(f"   ✓ Process Group ID: {pg_id}")
        except Exception as e:
            print(f"   ✗ Failed to deploy connector: {e}")
            return False
        
        # Start connector
        print(f"\n6. Starting connector...")
        try:
            start_connector(OPENFLOW_RUNTIME_URL, pg_id)
            print("   ✓ Connector started")
        except Exception as e:
            print(f"   ✗ Failed to start connector: {e}")
            return False
        
        # Wait for files
        print(f"\n7. Waiting for files to sync (up to {SYNC_WAIT_TIME}s)...")
        files_found = False
        start_time = time.time()
        
        while time.time() - start_time < SYNC_WAIT_TIME:
            with conn.cursor() as cur:
                try:
                    cur.execute(f"ALTER STAGE {test_stage_name} REFRESH")
                    cur.execute(f"SELECT COUNT(*) FROM DIRECTORY(@{test_stage_name})")
                    count = cur.fetchone()[0]
                    elapsed = int(time.time() - start_time)
                    print(f"   [{elapsed}s] Files in stage: {count}")
                    
                    if count > 0:
                        files_found = True
                        break
                except Exception:
                    elapsed = int(time.time() - start_time)
                    print(f"   [{elapsed}s] Waiting for stage...")
            
            time.sleep(SYNC_CHECK_INTERVAL)
        
        if files_found:
            print(f"\n{'='*60}")
            print("✓ TEST PASSED - Files appeared in stage!")
            print(f"{'='*60}")
            print(f"\nStage: {test_stage_name}")
            print(f"To inspect: SELECT * FROM DIRECTORY(@{test_stage_name});")
            return True
        else:
            print(f"\n{'='*60}")
            print("✗ TEST FAILED - No files appeared in stage")
            print(f"{'='*60}")
            print(f"\nCheck the connector logs at:")
            print(f"  {OPENFLOW_RUNTIME_URL.replace('/nifi-api', '')}")
            return False
    
    finally:
        # Cleanup
        if cleanup:
            print(f"\n{'='*60}")
            print("Cleanup")
            print(f"{'='*60}")
            
            # Clean up Openflow process group
            if pg_id:
                print(f"\nCleaning up Openflow process group: {pg_id}")
                cleanup_openflow_process_group(OPENFLOW_RUNTIME_URL, pg_id)
            
            # Clean up Snowflake schema
            if conn and test_schema:
                print(f"\nDropping test schema: {test_schema}")
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE")
                    print("✓ Schema dropped")
                except Exception as e:
                    print(f"⚠ Schema cleanup warning: {e}")
            
            if conn:
                conn.close()
        else:
            print("\n⚠ Cleanup skipped (cleanup=False)")
            print(f"  - Openflow PG: {pg_id}")
            print(f"  - Snowflake schema: {test_schema}")
            if conn:
                conn.close()


if __name__ == "__main__":
    # When run directly, execute the basic test
    success = run_basic_test()
    sys.exit(0 if success else 1)
