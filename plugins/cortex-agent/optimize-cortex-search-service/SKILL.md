---
name: optimize-cortex-search-service
description: "Use for optimizing existing Cortex Search services.
---

# Optimize Cortex Search Service Skill

## When to Use

When a user wants to optimize an existing Cortex Search service.

## Prerequisites

- Fully qualified Cortex Search service name (i.e. DATABASE.SCHEMA.SEARCH_SERVICE)
- Snowflake access configured

## Step 1: Get Queries to Run on Search Service

Ask the user for a list of queries to evaluate the Cortex Search service on and then format it into a JSON file of the form:

```
{
    "queries": [
        {"query": "search query text"},
        ...
    ]
}
```

If they do not have such a list, generate a list of 30 queries via `../scripts/generate_synthetic_queries.py` (which will have the proper formatting) via a command such as:

```bash
python ../scripts/generate_synthetic_queries.py \
    --service <DATABASE.SCHEMA.SERVICE_NAME> \
    --connection <CONNECTION> \
    --num-queries 30 \
    --output <QUERY_OUTPUT_FILE>
```

## Step 2: Find Optimal Search Weights

Use `../scripts/optimize_search_weights.py` to generate the optimal weights for the Cortex Search service via a command such as:

```bash
python ../scripts/optimize_search_weights.py \
    --service <DATABASE.SCHEMA.SERVICE_NAME> \
    --queries <QUERY_FILE> \          
    --score-unjudged \
    --cache-file <CACHE_FILE> \
    --n-trials 20 \
    --connection <CONNECTION>
```

The `<QUERY_FILE>` should be the file generated from the previous step and the `<CACHE_FILE>` is used to speed up computation of this script within a single run of it and across runs.

## Step 3: Recommend Changes to User

Give the user the recommended weights computed in the previous step and suggest they use scoring profiles to optimize their Cortex Search service, but stress that this currently cannot be done for Cortex Search services called by a Cortex Agent.
