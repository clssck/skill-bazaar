---
name: get-marketplace-listing-details
description: >-
  Present detailed information about a single Snowflake Marketplace listing
  (data share, native app, private/targeted, or request-only) and explain why
  it is useful given the user's existing Snowflake data and current
  conversation. Use when the user asks about ONE specific listing by title or
  by global name (e.g. "tell me about GZ2FQZ711TU", "what's in the Consumer
  Pricing listing", "describe this marketplace listing", "details on listing
  X"). Do NOT use for marketplace search results spanning multiple listings —
  use `marketplace-listing-formatting` instead.
---

# Skill: get-marketplace-listing-details

Defines how to present detailed information about a single marketplace listing. The goal is to communicate the core details about the listing as well as **why it is useful for the user** in the context of the current conversation and their existing Snowflake data.

## When to use

- The user references **one** listing by title (e.g. "Consumer pricing data") or by global name (e.g. `GZ2FQZ711TU`).
- The user wants details, an overview, or a "should I get this?" recommendation about a listing.

**Do NOT** use this skill when:

- The user is browsing or searching across multiple listings — use `marketplace-listing-formatting` instead.
- It is unclear which specific listing is meant (see Prerequisites — always ask for clarification first).

## Prerequisites

### Identify the listing

This skill must be invoked with the **global name** of the listing.

- The **global name** is an alphanumeric string like `GZ2FQZ711TU`.
- The **title** is a human-readable name like "Consumer pricing data".

**CRITICAL**: If it is unclear which listing is being referred to, **always** ask the user for clarification. If the user provided only a title, search the previous conversation context to find the matching global name. If you cannot find one, ask.

### Fetch the listing

**ALWAYS** run **Query A** below using the available SQL execution tool (for example `snowflake_sql_execute`, or `snow sql` when running locally). Then, **for data-share listings**, also run **Query B** to retrieve the data dictionary URLs.

**Query A and Query B are the ONLY SQL queries this skill executes.** Every field referenced elsewhere in this skill (`metadata.title`, `profile.description`, `metadata.usage`, etc.) is read from the parsed JSON in your own reasoning — *not* fetched with a follow-up query. In particular, **do NOT issue any SQL that wraps Query A in `PARSE_JSON(...)`, `FLATTEN(...)`, `TABLE(...)`, or otherwise re-runs `SYSTEM$BULK_GET_LISTINGS` to "extract", "flatten", or "parse" sub-fields** like `metadata`, `profile`, `usage`, `businessNeeds`, `compliance_badges`, etc. Running such queries is wasted work — the data is already in the Query A result — and it pollutes the response with internal retrieval steps the user does not need.

**Query A — `SYSTEM$BULK_GET_LISTINGS`** (the source of truth for nearly every field — title/description, business needs, **`metadata.usage` SQL examples**, provider info, monetization, type detection, region availability, consumer state, etc.):

```sql
SELECT SYSTEM$BULK_GET_LISTINGS(
  'SNOWFLAKE_DATA_MARKETPLACE',
  '{"listingGlobalEntityIds":["<global_name>"]}'
);
```

**Query B — `SYSTEM$GET_DATA_DICTIONARY_METADATA`** (data-share listings only — returns presigned URLs to JSON files describing the share's tables, columns, and "featured" objects):

```sql
SELECT SYSTEM$GET_DATA_DICTIONARY_METADATA(
  '<global_name>',
  'SNOWFLAKE_DATA_MARKETPLACE'
);
```

#### Parsing the responses

Both queries return a single column whose value is a **JSON string**. **Parse this JSON in your own reasoning — do not issue additional SQL to extract sub-fields.** Each field reference below (e.g. `metadata.title`, `profile.description`, `metadata.usage[*].query`) is a key path on the parsed JSON object, not a column to `SELECT`.

- **Query A** parses to an **array** with one object per requested listing — read element `[0]`. Several inner fields (`metadata`, `profile`, `application_data`, `compliance_badges`, `product_types`, `pricing_plan`) are themselves **JSON-encoded strings** that must be parsed a second time before reading their sub-fields. Do this parsing in your reasoning — not by re-running the query through `PARSE_JSON` / `FLATTEN` in SQL.
- **Query B** parses to an **object** of shape `{presignedUrlMap: {<filename>: <presigned URL>, ...}, updatedOn: <epoch_ms>}`. Filenames typically include `<global_name>dictionary_<n>.json` (column dictionary), `<global_name>objects.json` (table list), and `<global_name>featured.json` (featured objects). **The presigned URLs typically expire within an hour** — if you intend to fetch them via a web-fetch tool, do so promptly.

#### Field reference (Query A — `SYSTEM$BULK_GET_LISTINGS`)

Any field can be `null`, missing, or an empty string for a given listing — defer to what the query actually returned.

| Field path                                          | Type / shape                                                                                       | Use in this skill                                                                                              |
|-----------------------------------------------------|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| `global_name`                                       | string                                                                                             | Verify it matches the requested listing                                                                        |
| `state`                                             | string (`PUBLISHED`, `RETIRED`, `DRAFT`, …)                                                        | If not `PUBLISHED`, surface that status before continuing                                                       |
| `metadata.title`                                    | string                                                                                             | Display as the listing name                                                                                    |
| `metadata.subtitle`, `metadata.description`         | string                                                                                             | Source for the summary section (Step 2)                                                                        |
| `metadata.share`                                    | string (e.g. `EQUILAR PEOPLE BUSINESS INTELLIGENCE TOP 500`)                                       | The Snowflake share name behind the listing — useful technical context                                         |
| `metadata.businessNeeds`                            | array of `{type, name?, key?, description}` — predefined needs use `key` (numeric); custom use `name` | Step 1 enrichment + Step 2 relevance summary; render the `description` text directly when `name`/`key` is opaque |
| `metadata.usage`                                    | array of `{title, description, query, isPaid?, numRows?, isValid?}`                                | **Step 4 SQL examples for data listings** — these are real, runnable queries. Mark `isPaid: true` entries as paid |
| `metadata.link`                                     | string URL                                                                                         | Documentation URL for Step 3 "More details" + Step 1 enrichment                                                |
| `metadata.videoLink`                                | string URL                                                                                         | Demo / video link for Step 3 (render as "Demo")                                                                |
| `metadata.termsOfService`, `metadata.isWithStandardTerms`, `metadata.areTermsProvidedOffline` | URL / boolean / boolean                                  | Surface a one-line note if non-standard or offline-provided terms apply                                         |
| `metadata.attributes.refreshRate`                   | string (e.g. `daily`)                                                                              | Surface in More details when relevant (e.g. "Refresh: daily")                                                  |
| `metadata.attributes.geography`                     | object `{geoOption, granularity[], coverage{states[], continents{}}}`                              | Geographic coverage — summarize concisely (e.g. "United States, city-level")                                   |
| `metadata.attributes.time`                          | object `{range{frame, startDate}, granularity}`                                                    | Time-series coverage / history depth                                                                           |
| `metadata.attributes.features`                      | array of strings                                                                                   | Free-tier capabilities / sample data                                                                           |
| `metadata.paidAttributes`                           | object same shape as `metadata.attributes`                                                         | Paid-tier capabilities — when `is_monetized = true`, contrast `attributes.features` (free) vs `paidAttributes.features` (paid) |
| `metadata.categories`                               | object keyed by numeric category id (e.g. `{"6": true, "27": true}`)                               | Internal numeric ids — **not human-readable**. Skip this row if you have no other category source.             |
| `organization_profile_name`                         | string (may be empty)                                                                              | Provider display name — prefer when non-empty                                                                  |
| `profile`                                           | parsed object `{name, description, image, supportUrl, privacyUrl, contactInfo}`                    | Provider subsection — fall back to `profile.name` when `organization_profile_name` is empty; use `profile.description` for the overview |
| `profile_global_name`                               | string (e.g. `GZ2FQZ711TI`)                                                                        | Opaque internal id — **never print this** (see Step 3)                                                         |
| `product_types`                                     | parsed array of `{type, is_addon}` (e.g. `[{"type":"SHARE",...}]`, `[{"type":"NATIVE_APP",...}]`)  | Type detection (see "Determine the listing type")                                                              |
| `application_data`                                  | parsed object describing the Native App package (`privileges`, `version`, `packageType`, `referenceDefinitions`, `diagnostics`, …) | Native App context — privileges required, current version, etc.                                                |
| `share_type`                                        | string (e.g. `DATA`, `APPLICATION`, `SECURE_VIEW`)                                                 | Secondary type signal alongside `product_types`                                                                |
| `private`                                           | boolean                                                                                            | If `true`, the listing is privately shared / targeted to the consumer's account                                |
| `distribution`                                      | string (`EXTERNAL`, `INTERNAL`, …)                                                                 | Secondary signal for private/internal listings                                                                 |
| `autofulfillment`                                   | boolean                                                                                            | If `false`, the listing typically requires provider approval (request-/contact-driven)                         |
| `is_monetized`, `monetization_version`              | boolean / string                                                                                   | Mention in the More details "Pricing" row when `is_monetized = true`                                           |
| `pricing_plan`                                      | parsed object `{type, currency, base_fee, paid_data_description, free_data_description, billing_duration, payment_type}` (present when `is_monetized = true`) | Render concrete pricing in the Pricing row (e.g. "$500 USD / billing period, paid in arrears")                |
| `compliance_badges`                                 | parsed array of `{type, expiry}` (e.g. `[{"type":"ISO27001","expiry":"06-12-2027"}]`); may be missing entirely | More details "Certifications" — list each `type`, include `expiry` when set                                    |
| `customized_contact_info`                           | string                                                                                             | More details "Contact" — combine with `profile.supportUrl` / `profile.contactInfo`                             |
| `is_available_for_importing`, `is_imported`, `is_share_imported`, `is_purchased` | boolean                                              | The consumer's current relationship to the listing — affects Step 5 wording                                    |
| `regions`                                           | comma-separated string                                                                             | Optional: mention region availability when relevant                                                            |
| `first_published_on`, `last_published_on`, `updated_on` | ISO-8601 timestamp strings                                                                     | Optional: surface freshness when relevant                                                                      |
| `blocked`, `unpublished_by_admin_reason`            | boolean / string                                                                                   | If `blocked = true` or an unpublish reason is set, surface that to the user                                    |
| `provided_by_you`                                   | boolean                                                                                            | If `true`, the listing belongs to the consumer's own account/org — note this                                   |

#### Field reference (Query B — `SYSTEM$GET_DATA_DICTIONARY_METADATA`)

Only fetched for data-share listings.

| Field path                                          | Type / shape                                                                                       | Use in this skill                                                                                              |
|-----------------------------------------------------|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| `presignedUrlMap`                                   | object `{<filename>: <presigned URL>, ...}` — typical filenames: `<global_name>dictionary_<n>.json`, `<global_name>objects.json`, `<global_name>featured.json` | URLs to JSON files describing the share's tables, columns, and featured objects. Use to discover real schema before writing Step 4 SQL — **fetch promptly; URLs expire within ~1 hour**. |
| `updatedOn`                                         | epoch milliseconds                                                                                 | Optional: when the data dictionary was last refreshed                                                          |

**Opaque identifiers — never print:**

- `profile_global_name` and the inner `profile.profileGlobalName` (e.g. `GZ2FQZ711TI`, `GZTYZY3AR0A`).

These are internal IDs. Concretely, **do NOT**:

- Render them as the provider name.
- Put them in a parenthetical or footnote (e.g. "Equilar (`GZ2FQZ711TI`)").
- Put them in a code span anywhere in the response.
- Add a "Profile ID", "Provider ID", "Listing ID", or "Internal ID" row to the More details table or the Provider subsection. **The user does not need any opaque internal id.**

The listing's own `global_name` (e.g. `GZ2FQZ711TU`) is fine to mention — only the **provider/profile** ids are forbidden.

**If a query fails or the listing is not live:**

- *Listing not found / invalid identifier / empty BULK_GET array* — confirm the global name with the user.
- *Insufficient privileges* or *not granted* (common for private and request-only listings) — tell the user the listing is not currently available to their role and suggest requesting access via the provider.
- *`state` is not `PUBLISHED`* (e.g. `RETIRED`, `DRAFT`), or `blocked = true`, or `unpublished_by_admin_reason` is set — surface that status; do not present a retired, blocked, or draft listing as if it were live.
- *Query A succeeds, Query B fails (or is empty)* — proceed with the BULK_GET data and note that the data dictionary was unavailable. Examples in Step 4 must then be derived from `metadata.usage` / `metadata.description` only — do not invent table or column names.
- *Other errors* — surface the error verbatim and ask the user how to proceed.

### Determine the listing type

Apply the following table to the parsed BULK_GET result. Step 4 routes on the type:

| Listing type                       | Detection                                                                                                                                                                |
|------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Data listing                       | `product_types` contains an entry with `type` in (`SHARE`, `DATA_SHARE`, `SECURE_VIEW`), **or** `share_type` in (`DATA`, `SECURE_VIEW`)                                  |
| Native App listing                 | `product_types` contains `{type: "NATIVE_APP"}`, **or** `share_type = "APPLICATION"`, **or** `application_data` is a non-empty object                                    |
| Connected App listing (SaaS)       | `product_types` contains `{type: "SAAS_CONNECTED_APP"}`. `share_type` is typically empty / missing for these, and `application_data` is empty (the app does **not** run inside Snowflake). |
| Private / Targeted listing         | `private = true` (often combined with a non-`EXTERNAL` `distribution` value)                                                                                              |
| Request-only listing               | `autofulfillment = false`                                                                                                                                                 |

A listing may match more than one row (for example a request-only data listing, or a private connected app). Treat the types as additive when generating examples in Step 4. Only run Query B (data dictionary) for **data listings** — Native Apps and Connected Apps don't have a queryable data dictionary.

## Workflow

**CRITICAL — response shape:** The response MUST contain, **in this order**, the five sections from the "Example response shape" template at the bottom: a `# {title}` heading, the Step 2 summary, a "More details" section (with a Provider subsection), a Step 4 usage-examples section, and a final **`### Get this listing`** section whose body contains the constructed marketplace URL `https://app.snowflake.com/marketplace/listing/<global_name>`. **Every response, without exception, MUST end with the "Get this listing" section and that URL** — do not replace it with a "Next steps" paragraph, do not substitute the provider's contact email for the URL, do not omit it because the listing is request-only / private / monetized. If your draft ends without that URL, you have not finished the response.

**CRITICAL**: **NEVER** use the `marketplace-listing-formatting` skill to reformat the response when using this skill — that skill produces `<marketplace_listing_list>` tags for *list* responses, while this skill produces a single detail view.

**CRITICAL**: **NEVER** make up or assume information about the listing. Use only what the two queries returned and what the enrichment fetches in Step 1 confirmed.

### Step 1 — Gather context

1. Read `metadata.businessNeeds` and `metadata.description` to understand the listing's intended use cases. For **Native App** listings, also read `application_data` (privileges, version, `referenceDefinitions`) for what the app needs to run and integrate. For **Connected App** listings, `application_data` is empty — the SaaS product runs outside Snowflake — so rely on `metadata.description`, `metadata.link` (product docs), and `profile.supportUrl` for capabilities and integration patterns.
2. For **data listings**, parse `presignedUrlMap` from Query B and, if a web fetch tool is available, fetch the `objects.json` and `dictionary_*.json` files for the table / column inventory. These are the source of truth for table and column names you may reference in Step 4 examples (`metadata.usage` queries already use these — verify before adding new examples).
3. If a web fetch tool is available, fetch `metadata.link` (and `profile.supportUrl` when present) for additional product context that the structured fields don't capture.
4. Use the available search tool (e.g. `snowscope_search` / `snowflake_marketplace_search`) and any data-discovery tools to understand what data the **user** currently has in Snowflake. This is required so Step 2's relevance summary and Step 4's examples are concrete rather than generic.

### Step 2 — Generate the summary

- A maximum **2-sentence** description of the listing.
- A maximum **5-sentence** overview of how the listing is useful **to this user**, grounded in the context gathered in Step 1.

### Step 3 — Generate "More details"

Render a 2-column key/value table. Omit any row whose source field is `null`, missing, or an empty string rather than printing an empty value:

| Field           | Value                                                                                                                                     |
|-----------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| Documentation   | `metadata.link`. Optionally include `metadata.videoLink` as a "Demo" link.                                                                |
| Certifications  | List each `type` from `compliance_badges` (e.g. `ISO27001`, `SOC2_TYPE_II`), include `expiry` when set. Omit if `compliance_badges` is missing/empty. |
| Categories      | Comma-joined `metadata.attributes.features` values when they read as category-style tags (e.g. "Sales Intelligence, Executive Data"). **Never** use the numeric `metadata.categories` ids. Omit the row if no useful labels are available. |
| Refresh         | `metadata.attributes.refreshRate` (e.g. "daily") — surface when present.                                                                  |
| Coverage        | One short summary line combining `metadata.attributes.geography` (countries / states / granularity) and `metadata.attributes.time` (history depth, granularity). Omit if both are absent. |
| Contact         | Combine non-empty values from `profile.supportUrl`, `profile.contactInfo`, and `customized_contact_info`.                                 |
| Regions         | Summarize the regions list if relevant to the user, otherwise omit.                                                                       |

Then include a **Provider** subsection with a maximum **3-sentence** overview of the provider.

- Prefer `organization_profile_name` for the display name when it is a non-empty string; otherwise fall back to `profile.name` (parsed from the `profile` JSON object).
- Use `profile.description` as the primary source for the provider overview. If it is empty, fall back to detail extracted from the listing description or fetched documentation.
- `profile_global_name` and the inner `profile.profileGlobalName` (e.g. `GZ2FQZ711TI`, `GZTYZY3AR0A`) are opaque internal identifiers. **Never mention any of these values anywhere in your response — not as the provider name, not in a parenthetical, not in a code span, not as "internal id".** The user does not need them.
- **Do not invent a provider name** — if no name is recoverable, write a short factual sentence about what the provider does without naming them.

### Step 4 — Generate usage examples

Branch on the listing type(s) determined in Prerequisites.

#### Data listings (data shares)

Examples **must be** SQL queries that could be run to get insights from the listing's data. Prefer the entries in `metadata.usage` verbatim — each one has a `title`, `description`, and a real `query` field. When `isPaid: true`, mark the example as paid (the underlying data may not be available without a paid subscription). Where possible, augment one example with a join against tables the user already has access to (discovered in Step 1) to surface novel insights specific to their setup. If `metadata.usage` is null/empty, derive queries from the data dictionary fetched in Step 1 — do not invent table or column names; if the schema is not knowable, describe the query at a higher level instead of fabricating identifiers.

#### Native App listings

Examples **must be** descriptions of how the app solves the user's stated needs, grounded in the app's documented capabilities (description, business needs, `application_data.referenceDefinitions` / `privileges`, and any fetched docs).

#### Connected App listings (SaaS)

A Connected App is a SaaS product that runs **outside** Snowflake but integrates with the user's account (typically via OAuth / a service connection). Unlike a Native App, there is no `application_data` package, no install-time privilege grant, and no SQL surface to query. Examples **must be** descriptions of how the SaaS product integrates with Snowflake and what value it provides — for example: "After authorizing the app, it reads from `<schema>.<table>` and pushes results back to `<other_schema>`", or "The app's UI lives at `<provider URL>` and uses your Snowflake warehouse to run analyses on demand". Ground every claim in `metadata.description`, `metadata.businessNeeds`, `metadata.link` (product docs), and any documentation fetched in Step 1. **Do not** write fabricated SQL queries against the connected app's "data" — there is no queryable data share. **Do not** describe install steps as if it were a Native App (no `CREATE APPLICATION`, no privilege list, no warehouse reference binding) — Connected Apps install via a "Connect" / OAuth flow on the marketplace listing page.

#### Private / Targeted listings

Treat as the underlying data or app listing (data share examples or app examples), but prefix the section with a one-line note that the listing is privately shared with the user's account (signal: `private = true`).

#### Request-only listings

Examples **must be** plausible services or deliverables the provider may offer **based only on the information in the listing**. Do not speculate beyond what the listing says, and do not write fabricated SQL queries for these listings.

### Step 5 — Get this listing

This section is **MANDATORY** in every response — never omit it, regardless of listing type.

**If the `marketplace-install-formatting` skill is available, prefer it.** Render the body of this section as a single self-closing `<marketplace_listing_install listingId="<global_name>"/>` tag and **omit** the marketplace URL and any CTA prose — the install card is the entire CTA. Section heading still says `### Get this listing`.

If the `marketplace-install-formatting` skill is **not** available, fall back to a call-to-action link to the listing:

- **Else, always include the marketplace URL.** `SYSTEM$BULK_GET_LISTINGS` does not return a `uniform_listing_locator`, so construct it as `https://app.snowflake.com/marketplace/listing/<global_name>` and render it as a clickable link or plain URL. This applies even for **request-only** and **private/targeted** listings — the marketplace page is where the consumer requests access / sees the provider's contact form, so it must always appear in this section.
- If `is_imported`, `is_share_imported`, or `is_purchased` is `true`, mention that the consumer has already obtained this listing and link to it for reference rather than as a "Get" call-to-action.
- For private/targeted (`private = true`) or request-only (`autofulfillment = false`) listings, frame the call-to-action around requesting access / contacting the provider — but **still** include the marketplace URL (the request flow lives on the marketplace page).
- For monetized listings (`is_monetized = true`), note that paid features require purchase / a paid subscription, then still include the marketplace URL.
- For **Connected App** listings, frame the call-to-action around clicking through to the marketplace page and using the provider's "Connect" / OAuth flow there to authorize the SaaS product against the user's Snowflake account — not as a `CREATE APPLICATION` install.

### Step 6 — Self-check before sending

Before you finalize the response, verify each of these three items. If any fails, fix it and re-check.

1. **The Get-this-listing section is present.** Scroll to the bottom of your draft. The very last section MUST be `### Get this listing`. Its body MUST contain **either** a `<marketplace_listing_install listingId="<global_name>"/>` tag (when the `marketplace-install-formatting` skill is available) **or** the marketplace URL `https://app.snowflake.com/marketplace/listing/<global_name>` (when it is not). Substituting "Next steps:", "Bottom line:", a `mailto:` link, or the provider's contact email **does not satisfy this requirement**. If your draft ends with anything else (a wrap-up paragraph, a "Conclusion", etc.), append the section now.
2. **No opaque profile ids.** Search your draft for the value of `profile_global_name` (and the inner `profile.profileGlobalName`). If it appears anywhere — in a "Profile ID" row, a parenthetical, a code span, a footnote — delete it. The user does not need any internal id.
3. **Listing-type framing matches the type.** For Connected App listings, your draft must NOT contain `CREATE APPLICATION`, `IMPORTED PRIVILEGES`, `EXECUTE TASK`, `APPLICATION PACKAGE`, or other Native-App install boilerplate. For Native App listings, your draft must NOT contain fabricated `SELECT ... FROM <made-up-table>` queries against the app's data. For request-only / private listings, your draft must NOT contain fabricated SQL queries. If you find any of these, rewrite that section.
4. **No retrieval queries are exposed.** Search your draft for `SYSTEM$BULK_GET_LISTINGS`, `SYSTEM$GET_DATA_DICTIONARY_METADATA`, `PARSE_JSON`, and section headings like "Queries executed", "Queries run", "How this was retrieved", "Data retrieval", or "Source queries". None of those queries or sections belong in the response — they are internal retrieval steps. Note that this restriction is about *retrieval* queries; the Step 4 usage-example SQL pulled from `metadata.usage` (queries against the listing's actual data tables) is expected and stays. If a retrieval section snuck in, delete it before sending.

## Example response shape

```
# {Listing title}

{Step 2 summary — 2-sentence description + 5-sentence relevance overview}

### More details

{Step 3 key/value table}

#### Provider

{Step 3 provider overview}

### Usage examples

{Step 4 examples appropriate to the listing type(s)}

### Get this listing

{Step 5 link}
```
