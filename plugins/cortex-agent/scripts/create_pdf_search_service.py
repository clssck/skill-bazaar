#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import snowflake.connector
from snowflake.connector import DictCursor


def __create_stage_if_not_exists(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    stage_name: str,
) -> None:
    create_stage_sql = f"""
    CREATE STAGE IF NOT EXISTS {database}.{schema}.{stage_name}
        DIRECTORY = (ENABLE = TRUE)
        ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    """
    with conn.cursor() as cur:
        cur.execute(create_stage_sql)


def __upload_pdfs_to_stage(
    conn: snowflake.connector.SnowflakeConnection,
    pdf_paths: List[str],
    database: str,
    schema: str,
    stage_name: str,
) -> List[str]:
    uploaded_files = []
    for pdf_path in pdf_paths:
        if not os.path.exists(pdf_path):
            print(f"Warning: File not found: {pdf_path}", file=sys.stderr)
            continue

        file_name = Path(pdf_path).name
        put_sql = f"PUT 'file://{pdf_path}' @{database}.{schema}.{stage_name}/ AUTO_COMPRESS=FALSE"

        with conn.cursor() as cur:
            cur.execute(put_sql)
            uploaded_files.append(file_name)
            print(f"Uploaded: {file_name}")

    return uploaded_files


def __parse_pdfs_and_create_chunks_table(
    conn: snowflake.connector.SnowflakeConnection,
    uploaded_files: List[str],
    database: str,
    schema: str,
    stage_name: str,
    table_name: str,
    chunk_mode: str,
    chunk_size: int,
    overlap: int,
) -> None:
    create_table_sql = f"""
    CREATE OR REPLACE TABLE {database}.{schema}.{table_name} (
        pdf_file VARCHAR,
        page_index INT,
        chunk_index INT,
        chunk_text VARCHAR,
        metadata VARIANT
    )
    """
    with conn.cursor() as cur:
        cur.execute(create_table_sql)
        print(f"Created table: {database}.{schema}.{table_name}")

    if chunk_mode == "page":
        for file_name in uploaded_files:
            insert_sql = f"""
            INSERT INTO {database}.{schema}.{table_name} (pdf_file, page_index, chunk_index, chunk_text, metadata)
            SELECT
                '{file_name}' AS pdf_file,
                page.value:index::INT AS page_index,
                0 AS chunk_index,
                page.value:content::VARCHAR AS chunk_text,
                OBJECT_CONSTRUCT(
                    'source', '{file_name}',
                    'page', page.value:index::INT
                ) AS metadata
            FROM (
                SELECT SNOWFLAKE.CORTEX.AI_PARSE_DOCUMENT(
                    TO_FILE('@{database}.{schema}.{stage_name}', '{file_name}'),
                    {{'mode': 'LAYOUT', 'page_split': true}}
                ) AS parsed_doc
            ),
            LATERAL FLATTEN(input => parsed_doc:pages) AS page
            """
            with conn.cursor() as cur:
                cur.execute(insert_sql)
                print(f"Processed {file_name} with page-level chunking")

    elif chunk_mode == "section":
        for file_name in uploaded_files:
            insert_sql = f"""
            INSERT INTO {database}.{schema}.{table_name} (pdf_file, page_index, chunk_index, chunk_text, metadata)
            SELECT
                '{file_name}' AS pdf_file,
                page.value:index::INT AS page_index,
                chunk_idx AS chunk_index,
                chunk.value::VARCHAR AS chunk_text,
                OBJECT_CONSTRUCT(
                    'source', '{file_name}',
                    'page', page.value:index::INT,
                    'chunk', chunk_idx
                ) AS metadata
            FROM (
                SELECT SNOWFLAKE.CORTEX.AI_PARSE_DOCUMENT(
                    TO_FILE('@{database}.{schema}.{stage_name}', '{file_name}'),
                    {{'mode': 'LAYOUT', 'page_split': true}}
                ) AS parsed_doc
            ),
            LATERAL FLATTEN(input => parsed_doc:pages) AS page,
            LATERAL FLATTEN(
                input => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(
                    page.value:content::VARCHAR,
                    'markdown',
                    {chunk_size},
                    {overlap}
                )
            ) AS chunk,
            LATERAL (SELECT ROW_NUMBER() OVER (ORDER BY 1) - 1 AS chunk_idx)
            """
            with conn.cursor() as cur:
                cur.execute(insert_sql)
                print(f"Processed {file_name} with section-level chunking")


def __create_cortex_search_service(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table_name: str,
    service_name: str,
    warehouse: str,
    target_lag: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {database}.{schema}.{table_name} SET CHANGE_TRACKING = TRUE")

    create_service_sql = f"""
    CREATE OR REPLACE CORTEX SEARCH SERVICE {database}.{schema}.{service_name}
        ON chunk_text
        ATTRIBUTES pdf_file, page_index, chunk_index
        WAREHOUSE = {warehouse}
        TARGET_LAG = '{target_lag}'
        AS (
            SELECT
                chunk_text,
                pdf_file,
                page_index,
                chunk_index,
                metadata
            FROM {database}.{schema}.{table_name}
        )
    """
    with conn.cursor() as cur:
        cur.execute(create_service_sql)
        print(f"Created Cortex Search Service: {database}.{schema}.{service_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Create a Cortex Search service from PDF documents"
    )
    parser.add_argument(
        "pdfs",
        nargs="+",
        help="Paths to PDF files to process",
    )
    parser.add_argument(
        "--warehouse",
        required=True,
        help="Warehouse to use for processing",
    )
    parser.add_argument(
        "--connection",
        default=None,
        help="Snowflake connection name (defaults to SNOWFLAKE_CONNECTION_NAME env var or 'default')",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Database to use (defaults to current database)",
    )
    parser.add_argument(
        "--schema",
        default="PUBLIC",
        help="Schema to use (default: PUBLIC)",
    )
    parser.add_argument(
        "--service-name",
        default="PDF_SEARCH_SERVICE",
        help="Name for the Cortex Search service (default: PDF_SEARCH_SERVICE)",
    )
    parser.add_argument(
        "--stage-name",
        default="PDF_STAGE",
        help="Name for the stage (default: PDF_STAGE)",
    )
    parser.add_argument(
        "--table-name",
        default="PDF_CHUNKS",
        help="Name for the chunks table (default: PDF_CHUNKS)",
    )
    parser.add_argument(
        "--chunk-mode",
        choices=["page", "section"],
        default="page",
        help="Chunking mode: 'page' for page-level (default), 'section' for section-level with overlap",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Chunk size in characters for section-level chunking (default: 512)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=50,
        help="Overlap in characters for section-level chunking (default: 50)",
    )
    parser.add_argument(
        "--target-lag",
        default="1 hour",
        help="Target lag for the search service (default: '1 hour')",
    )

    args = parser.parse_args()

    connection_name = (
        args.connection
        or os.getenv("SNOWFLAKE_CONNECTION_NAME")
        or "default"
    )

    print(f"Connecting to Snowflake using connection: {connection_name}")
    conn = snowflake.connector.connect(connection_name=connection_name)

    try:
        if args.database:
            with conn.cursor() as cur:
                cur.execute(f"USE DATABASE {args.database}")
            database = args.database
        else:
            with conn.cursor(DictCursor) as cur:
                cur.execute("SELECT CURRENT_DATABASE() AS db")
                result = cur.fetchone()
                database = result["DB"]

        if not database:
            print("Error: No database specified and no current database set", file=sys.stderr)
            sys.exit(1)

        print(f"Using database: {database}, schema: {args.schema}")

        print(f"\nStep 1: Creating stage {args.stage_name}...")
        __create_stage_if_not_exists(conn, database, args.schema, args.stage_name)

        print(f"\nStep 2: Uploading {len(args.pdfs)} PDF(s) to stage...")
        uploaded_files = __upload_pdfs_to_stage(
            conn, args.pdfs, database, args.schema, args.stage_name
        )

        if not uploaded_files:
            print("Error: No files were uploaded successfully", file=sys.stderr)
            sys.exit(1)

        print(f"\nStep 3: Parsing PDFs and creating chunks table with mode '{args.chunk_mode}'...")
        __parse_pdfs_and_create_chunks_table(
            conn,
            uploaded_files,
            database,
            args.schema,
            args.stage_name,
            args.table_name,
            args.chunk_mode,
            args.chunk_size,
            args.overlap,
        )

        print(f"\nStep 4: Creating Cortex Search Service on warehouse {args.warehouse}...")
        __create_cortex_search_service(
            conn,
            database,
            args.schema,
            args.table_name,
            args.service_name,
            args.warehouse,
            args.target_lag,
        )

        print(f"\n✓ Success! Cortex Search Service '{args.service_name}' is ready.")
        print(f"\nYou can query it with:")
        print(f"  SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(")
        print(f"    '{database}.{args.schema}.{args.service_name}',")
        print(f"    '{{'query': 'your search query', 'columns': ['chunk_text', 'pdf_file', 'page_index']}}'")
        print(f"  );")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
