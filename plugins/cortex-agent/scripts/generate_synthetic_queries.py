#!/usr/bin/env python3
"""
Generate synthetic queries from a Cortex Search service's backing data.

This script samples documents from a search service or table and uses
Cortex LLM functions to generate realistic search queries.

Usage:
    python generate_synthetic_queries.py \
        --service "DATABASE.SCHEMA.SERVICE_NAME" \
        --connection my_connection \
        --num-queries 30 \
        --output queries.json

Or from a table directly:
    python generate_synthetic_queries.py \
        --table "DATABASE.SCHEMA.TABLE_NAME" \
        --text-column "TEXT" \
        --connection my_connection \
        --output queries.json
"""
import argparse
import json
import os
import random
import re
import sys
from typing import Any, Dict, List, Optional

import snowflake.connector
from snowflake.connector import DictCursor

# Default LLM model for query generation
DEFAULT_MODEL = "llama3.1-70b"

# Prompt for generating queries from a document
QUERY_GENERATION_PROMPT = """You are helping create test queries for a search system.

Given the following document, generate {num_queries} diverse search queries that a user might type to find this document or similar information.

Requirements:
- Generate natural, realistic search queries (not full sentences)
- Vary query styles: some short (2-3 words), some longer (5-8 words)
- Include different query types: factual, how-to, conceptual
- Queries should be answerable by the document content
- Don't use exact phrases from the document; paraphrase naturally

Document:
{document}

Respond with ONLY a JSON array of query strings, like:
["query 1", "query 2", "query 3"]"""

# Prompt for understanding the corpus and generating diverse queries
CORPUS_ANALYSIS_PROMPT = """Analyze these sample documents from a search corpus and generate {num_queries} diverse search queries that users might ask.

Sample documents:
{samples}

Requirements:
- Generate natural, realistic search queries
- Cover different topics and themes present in the corpus
- Vary query styles: short keywords, questions, how-to queries
- Include both specific and broad queries
- Make queries realistic for what users would actually search

Respond with ONLY a JSON array of query strings, like:
["query 1", "query 2", "query 3"]"""


def _execute_llm_and_parse_queries(
    conn: snowflake.connector.SnowflakeConnection,
    sql: str,
    error_context: str = "Query generation",
) -> List[str]:
    """Execute an LLM query and parse JSON array response."""
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        row = cursor.fetchone()
        if row and row[0]:
            response = row[0].strip()
            try:
                # Find JSON array in response
                match = re.search(r'\[.*\]', response, re.DOTALL)
                if match:
                    queries = json.loads(match.group())
                    return [q.strip() for q in queries if isinstance(q, str) and q.strip()]
            except json.JSONDecodeError:
                pass
        return []
    except Exception as e:
        print(f"  Warning: {error_context} failed: {e}")
        return []
    finally:
        cursor.close()


def get_service_info(
    conn: snowflake.connector.SnowflakeConnection,
    service: str,
) -> Dict[str, Any]:
    """Get information about a Cortex Search service."""
    sql = f"DESCRIBE CORTEX SEARCH SERVICE {service}"
    cursor = conn.cursor(DictCursor)
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        info = {}
        for row in rows:
            # DESCRIBE returns name/value pairs
            if "property" in row:
                info[row["property"]] = row.get("value", row.get("property_value"))
            elif len(row) >= 2:
                keys = list(row.keys())
                info[row[keys[0]]] = row[keys[1]]
        return info
    except Exception as e:
        print(f"Warning: Could not describe service: {e}")
        return {}
    finally:
        cursor.close()


def sample_documents_from_service(
    conn: snowflake.connector.SnowflakeConnection,
    service: str,
    sample_queries: List[str],
    columns: List[str],
    results_per_query: int = 5,
) -> List[str]:
    """Sample documents by running broad queries against the service."""
    documents = set()

    for query in sample_queries:
        sql = f"""
            SELECT PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                    '{service}',
                    %s
                )
            )['results'] as results;
        """
        payload = {"query": query, "columns": columns, "limit": results_per_query}

        cursor = conn.cursor()
        try:
            cursor.execute(sql, (json.dumps(payload),))
            for row in cursor:
                if row[0]:
                    results = json.loads(row[0])
                    for result in results:
                        # Get text from first available column
                        for col in columns:
                            if col in result and result[col]:
                                documents.add(result[col])
                                break
        except Exception as e:
            print(f"  Warning: Query '{query}' failed: {e}")
        finally:
            cursor.close()

    return list(documents)


def sample_documents_from_table(
    conn: snowflake.connector.SnowflakeConnection,
    table: str,
    text_column: str,
    num_samples: int = 20,
) -> List[str]:
    """Sample random documents from a table."""
    # Use SAMPLE for random sampling
    sql = f"""
        SELECT {text_column}
        FROM {table}
        SAMPLE ({num_samples} ROWS)
    """

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        documents = [row[0] for row in cursor if row[0]]
        return documents
    except Exception as e:
        # Fallback to LIMIT with ORDER BY RANDOM()
        print(f"  Note: SAMPLE failed, using LIMIT: {e}")
        sql = f"""
            SELECT {text_column}
            FROM {table}
            ORDER BY RANDOM()
            LIMIT {num_samples}
        """
        cursor.execute(sql)
        documents = [row[0] for row in cursor if row[0]]
        return documents
    finally:
        cursor.close()


def generate_queries_from_document(
    conn: snowflake.connector.SnowflakeConnection,
    document: str,
    num_queries: int = 3,
    model: str = DEFAULT_MODEL,
) -> List[str]:
    """Generate queries from a single document using LLM."""
    # Truncate long documents
    doc_text = document[:3000] if len(document) > 3000 else document

    prompt = QUERY_GENERATION_PROMPT.format(
        num_queries=num_queries,
        document=doc_text,
    )

    escaped_prompt = prompt.replace("'", "''")
    sql = f"""
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            '{model}',
            '{escaped_prompt}'
        ) as response;
    """

    return _execute_llm_and_parse_queries(conn, sql, "Query generation")


def generate_queries_from_corpus(
    conn: snowflake.connector.SnowflakeConnection,
    documents: List[str],
    num_queries: int = 30,
    model: str = DEFAULT_MODEL,
) -> List[str]:
    """Generate diverse queries by analyzing the corpus."""
    # Create sample summaries (truncate each doc)
    samples = "\n\n---\n\n".join([
        f"Document {i+1}:\n{doc[:500]}..."
        for i, doc in enumerate(documents[:10])
    ])

    prompt = CORPUS_ANALYSIS_PROMPT.format(
        num_queries=num_queries,
        samples=samples,
    )

    escaped_prompt = prompt.replace("'", "''")
    sql = f"""
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            '{model}',
            '{escaped_prompt}'
        ) as response;
    """

    return _execute_llm_and_parse_queries(conn, sql, "Corpus query generation")


def generate_synthetic_queries(
    conn: snowflake.connector.SnowflakeConnection,
    documents: List[str],
    num_queries: int = 30,
    model: str = DEFAULT_MODEL,
    verbose: bool = True,
) -> List[str]:
    """Generate synthetic queries from sampled documents."""
    all_queries = set()

    if verbose:
        print(f"\nGenerating queries from {len(documents)} sampled documents...")

    # Strategy 1: Generate queries from the overall corpus understanding
    if verbose:
        print("  Step 1: Analyzing corpus to generate diverse queries...")

    corpus_queries = generate_queries_from_corpus(
        conn, documents, min(num_queries, 20), model
    )
    all_queries.update(corpus_queries)
    if verbose:
        print(f"    Generated {len(corpus_queries)} queries from corpus analysis")

    # Strategy 2: Generate queries from individual documents
    if len(all_queries) < num_queries:
        if verbose:
            print("  Step 2: Generating queries from individual documents...")

        # Calculate how many more queries we need
        remaining = num_queries - len(all_queries)
        queries_per_doc = max(2, remaining // min(len(documents), 10))

        # Sample documents for individual query generation
        sample_docs = random.sample(documents, min(len(documents), 10))

        for i, doc in enumerate(sample_docs):
            if len(all_queries) >= num_queries:
                break

            doc_queries = generate_queries_from_document(
                conn, doc, queries_per_doc, model
            )
            all_queries.update(doc_queries)

            if verbose:
                print(f"    Document {i+1}: generated {len(doc_queries)} queries")

    # Convert to list and limit to requested number
    final_queries = list(all_queries)[:num_queries]

    if verbose:
        print(f"\nTotal unique queries generated: {len(final_queries)}")

    return final_queries


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic search queries from a Cortex Search service or table"
    )

    # Input source (at least one required)
    parser.add_argument(
        "--service",
        help="Cortex Search service name (DATABASE.SCHEMA.SERVICE)",
    )
    parser.add_argument(
        "--table",
        help="Table to sample documents from (DATABASE.SCHEMA.TABLE)",
    )
    parser.add_argument(
        "--text-column",
        default="TEXT",
        help="Column containing document text (default: TEXT)",
    )
    parser.add_argument(
        "--columns",
        nargs="+",
        default=None,
        help="Columns to retrieve from search (defaults to text-column)",
    )
    parser.add_argument(
        "--connection",
        default=None,
        help="Snowflake connection name",
    )
    parser.add_argument(
        "--num-queries",
        type=int,
        default=30,
        help="Number of queries to generate (default: 30, range: 10-50 recommended)",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=20,
        help="Number of documents to sample (default: 20)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Cortex LLM model for generation (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path for generated queries (JSON)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    if not args.service and not args.table:
        parser.error("Either --service or --table is required")

    if args.seed is not None:
        random.seed(args.seed)

    connection_name = args.connection or os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
    columns = args.columns or [args.text_column]

    # Connect to Snowflake
    print(f"Connecting to Snowflake using connection: {connection_name}")
    conn = snowflake.connector.connect(connection_name=connection_name)

    try:
        # Sample documents
        if args.table:
            print(f"\nSampling {args.num_samples} documents from table: {args.table}")
            documents = sample_documents_from_table(
                conn, args.table, args.text_column, args.num_samples
            )
        else:
            # For service, we need to run some broad queries to sample
            print(f"\nSampling documents from service: {args.service}")
            print("  Running broad queries to sample documents...")

            # Use generic queries to sample diverse content
            sample_queries = [
                "what",
                "how to",
                "why",
                "when",
                "where",
                "who",
                "guide",
                "documentation",
                "example",
                "overview",
            ]

            documents = sample_documents_from_service(
                conn,
                args.service,
                sample_queries,
                columns,
                results_per_query=args.num_samples // len(sample_queries) + 1,
            )

        print(f"Sampled {len(documents)} unique documents")

        if not documents:
            print("Error: No documents sampled. Check your service/table configuration.")
            sys.exit(1)

        # Generate queries
        queries = generate_synthetic_queries(
            conn=conn,
            documents=documents,
            num_queries=args.num_queries,
            model=args.model,
            verbose=not args.quiet,
        )

        if not queries:
            print("Error: No queries generated")
            sys.exit(1)

        # Save output in format compatible with other scripts
        output_data = {
            "queries": [{"query": q} for q in queries],
            "metadata": {
                "source": args.service or args.table,
                "model": args.model,
                "num_samples": len(documents),
                "generated_count": len(queries),
            },
        }

        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"\n{'='*60}")
        print(f"Generated {len(queries)} queries")
        print(f"Saved to: {args.output}")
        print(f"{'='*60}")

        # Show sample queries
        print("\nSample queries:")
        for q in queries[:5]:
            print(f"  - {q}")
        if len(queries) > 5:
            print(f"  ... and {len(queries) - 5} more")

        # Print next steps
        service_name = args.service or "DATABASE.SCHEMA.YOUR_SERVICE"
        print(f"\nNext step:")
        print(f"\nOptimize weights:")
        print(f"   python optimize_search_weights.py \\")
        print(f"     --service \"{service_name}\" \\")
        print(f"     --queries relevance_labels.json")

    finally:
        conn.close()


if __name__ == "__main__":
    main()

