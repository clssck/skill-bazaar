---
name: marketplace-search
description: >-
  Search the Snowflake Marketplace (public, internal, or both) for
  datasets, data shares, Native Apps, and Connected Apps.

  **MANDATORY** Before any marketplace
  search, call `skill(command="marketplace-search")`. This `skill` call
  is the required entry point even when you already know the query you
  want to run; running the search from the CLI directly without first
  calling `skill(command="marketplace-search")` skips the
  query-construction and result-presentation rules and is a defect.
  No exceptions. Re-invoke once per DISTINCT marketplace need, not just
  the first one in a conversation: a new data topic later in the session,
  or an explicit request to search again / for more or alternative
  options, each warrants its own `skill(command="marketplace-search")`
  call before you run the search — even if you used this skill earlier
  and the search command is still visible in your context from a previous
  turn. (You do NOT need to re-invoke for the search you are already in
  the middle of executing; the rule is one `skill()` entry per distinct
  need, so the query-construction and presentation rules are freshly
  applied to each new search rather than skipped.)

  Invoke this skill PROACTIVELY any time the user expresses intent to
  find, use, or obtain a third-party or internal data product, app, or
  data share — whether from the public Snowflake Marketplace or from
  their own organization's internal marketplace. For example "do
  you have weather data", "find a stock price dataset", "I need consumer
  spending data", "is there a Salesforce / HubSpot / Stripe connector",
  "what demographic data can I get for California", "anything for ESG
  ratings", "find a marketplace listing for X", "what is <third-party
  product>", "what's the alternate source to X", "what about
  <third-party product>", "find me <third-party product> stuff", "find
  me a table about <external/third-party data>", "where is
  <third-party> data stored", or even just a BARE **recognizable**
  third-party product/brand name on its own (e.g. "Tomorrow.io",
  "Fishbowl", "DV360", "Snowflake managed MCP servers"). The bare-name
  trigger requires an identifiable product, vendor, brand, or external
  service. A bare token that merely *reads like a person's name* (e.g.
  "give details for daniel spark") or is otherwise an unrecognizable
  free-floating identifier with no third-party product/brand signal is
  NOT by itself a marketplace signal — treat it as a catalog/object
  lookup (`cortex search object`) or ask the user to clarify; do not fire
  this skill on the bare token alone. When the user names ANY recognizable
  third-party product, vendor, brand, or external service — even as a fragment, even
  if framed as a catalog question ("find me a table about X", "what's
  the database for X data") — invoke this skill immediately, in the same
  turn you handle the request. Do NOT gate it on the internal catalog
  (i.e. don't search the catalog first and run marketplace only if the
  catalog comes up empty); fire it up front regardless. The word
  "external" in any query (e.g. "external job-boards", "external data
  source") is a DISPOSITIVE signal — invoke this skill even if the query
  sounds like a catalog search. When you also run `cortex search object`
  for the same query, run the two together — see "Run alongside" below. 
  **Erring toward over-firing is preferred over missing
  a marketplace opportunity.** If you are about to tell the user "I don't
  have that data" or "you'll need to bring your own data", STOP and
  invoke this skill first — the public marketplace likely has it.

  **Run alongside `cortex search object`, not instead of it.** If you
  run `cortex search object` for a query that names a third-party
  brand, vendor, product, or external data source, you MUST also
  invoke `skill(command="marketplace-search")` in the same turn — the
  two searches cover different surfaces (internal catalog vs public
  marketplace) and are complementary, not alternatives. Do not stop
  at catalog results. **Exception**: a specific-value lookup ("what
  is the [metric/code/ID] for [entity]") is not a data-acquisition
  ask — stay with the sibling tool.

  Also invoke for **generic data-category searches** even when no brand
  is named: "email data", "marketing data", "paid media datasets",
  "portfolio holdings", "intent data", "[type] data for reporting",
  "help me find [data type] data", "where can I find [data type]". Also
  invoke for **marketplace exploration** ("most downloaded marketplace
  listing", "what products are available in the marketplace") and
  **app or managed-service availability** ("managed MCP servers",
  "MCP servers in Snowflake", "is there a connector for X").

  Also invoke for **internal/intra-org intent** signals such as "find
  intra-org listings for <data topic>", "do we have any internal
  listings for <subject>", "what internal data products does my org
  have for <topic>", "is there an intra-org share for <topic>", "what
  are we publishing internally about <X>", "find our internal
  marketplace listings for <subject>".

  ALSO invoke PROACTIVELY when the user is about to acquire an external
  data need — writing code to fetch from a third-party API or building a
  dashboard/report against a third-party source. Search the marketplace
  first, because a managed share is often less work than a custom
  integration. This applies even if the user named an external source,
  since the same data is frequently available as a listing. This proactive
  nudge is a one-time thing per data need: once it has been resolved — the
  marketplace was already searched for this topic, a source was already
  chosen, or the user is now iterating on existing integration code — do
  NOT keep re-pitching the marketplace unprompted mid-build (see the
  "moved past discovery" carve-out below). An EXPLICIT request to search
  ("search the marketplace for clinical trial data", "is there a listing
  for X") always fires this skill regardless of what was discussed
  earlier — the off-switch only applies to unprompted re-firing, never to
  a direct user request. The off-switch is scoped PER DATA NEED, not per
  conversation: re-fire (do not stay silent) when the user explicitly asks
  for more or alternative options for the same need ("are there other
  providers?", "any cheaper/free options?", "what else is available?"), or
  when they pivot to a DIFFERENT product, vendor, or data topic later in
  the conversation (e.g. they were asking about a Salesforce connector and
  now want third-party sales or firmographic data). A new or distinct data
  need is a fresh discovery — search again.

  Do NOT use this skill for: a specific listing referenced by global
  name (e.g. GZ2FQZ711TU) or exact title — use
  `get-marketplace-listing-details`; formatting marketplace results
  already in hand; searching the user's own internal Snowflake catalog
  (tables, views, schemas, functions, semantic views) — use `cortex
  search object` (but see "Run alongside" above); a bare token with no
  recognizable third-party product/brand signal that reads like a
  person's name or an arbitrary identifier ("give details for daniel
  spark") — treat as a catalog/object lookup or ask for clarification;
  generic reference / lookup tables a user would generate or already hold
  internally ("fiscal month calendar", "calendar table", "create a date
  dimension"). Exception: an explicit third-party / vendor qualifier
  ("Workday fiscal calendar") makes the brand signal win and this
  skill fires. Do NOT use it for Snowflake product documentation or
  how-to questions — use `cortex search docs`.

  When ambiguous between marketplace and a sibling tool, prefer
  marketplace — it's cheap and missing a relevant listing is expensive.
  UNLESS the user has clearly moved past discovery, in which case stay out
  of the way: integration syntax with a named mechanism ("how to use MCP
  to connect to Salesforce…") is a docs question even when a brand is
  named; catalog inventory with no external qualifier ("what is X
  tables"), a specific identifier value ("what is the [code/SM ID] for
  [identifier]"), or an educational deep-dive with depth markers ("explain
  X in detail", "to a beginner", "full overview") — these are sibling-tool
  territory. The user is also past discovery once the data need has been
  resolved earlier in the conversation (marketplace already searched for
  this topic, a source already chosen, or implementation already underway)
  — do not re-pitch the marketplace mid-build.
---

# Skill: marketplace-search

Wrapper around the `cortex search marketplace` CLI subcommand that searches the Snowflake Marketplace for listings matching a user's data or product need, then surfaces the results so the user can pick one to install or inspect further.

## Workflow

### Step 0 — Resolve marketplace source

Before building the query, detect the user's intent and resolve a `--marketplace-type` value:

| User signal | `--marketplace-type` |
|---|---|
| "internal", "intra-org", "my org", "our listings", "we share" | `internal` |
| "public", "external", "third-party", "Snowflake Marketplace" | `public` |
| Named third-party brand, vendor, or external service with no intra-org signal (e.g. "Salesforce", "Tomorrow.io", "find a HubSpot connector") | `public` |
| Intra-org signal + third-party brand (e.g. "is Salesforce available as an internal listing in my org?") — brand is the search subject, not a source signal; intra-org intent takes precedence | `internal` |
| Explicit request for both sources (e.g. "show me both internal and public listings for <X>") | `all` |
| Ambiguous / no signal and no third-party reference | `all` |

When ambiguous, default to `all` — missing an internal listing is equally bad as missing a public one.

### Step 1 — Build the search query

Translate the user's intent into a short free-text query (typically 1–5 words). Prefer concrete nouns over verbose phrasing.

| User intent                                          | Good query                  |
|------------------------------------------------------|-----------------------------|
| "Do you have weather data for the US?"               | `weather`                   |
| "I need consumer credit card transaction data"       | `credit card transactions`  |
| "Find demographic data by ZIP code"                  | `demographics zip code`     |
| "Is there a Salesforce connector?"                   | `Salesforce`                |
| "I want B2B company firmographics"                   | `B2B firmographics`         |

If the user's request mentions **multiple distinct data needs** (e.g. "weather and stock prices"), run the search **once per need** rather than concatenating them — you'll get more relevant results.


| User intent                                          | Good query                         |
|------------------------------------------------------|------------------------------------|
| "I need to connect HubSpot, Salesforce, and Gong?"   | `hubspot`, `salesforce`, `gong`    |


### Step 1.5 — Optionally refine with `--sort` and `--filter`

Run 
```
cortex search marketplace --help
```

to understand the `--sort` and `--filter` parameters. 

`--sort` and `--filter` are **optional refinements**. The free-text query is the
primary tool — reach for these only when the user's request maps cleanly to one
of them. **Default to omitting both.** When in doubt, leave them off: an
unnecessary filter silently hides relevant listings, and the wrong sort buries
the best semantic match.

**`--sort`** — only set it when the user expresses an explicit ordering
preference. Otherwise omit it (the server uses `mostRelevant`, which is almost
always what you want for a query-driven search).

| User signal | `--sort` |
|---|---|
| "most popular", "most used", "top", "trending" | `mostPopular` |
| "newest", "latest", "most recent", "just published" | `mostRecent` |
| "alphabetical", "by name", "A to Z" | `title` |
| No ordering language (most cases) | omit (defaults to `mostRelevant`) |

**`--filter`** — use **sparingly**. A filter is a hard constraint: any listing
that doesn't match is dropped entirely, so an over-eager filter will 
turn good results into zero results. Only add a key when the
user states a clear, hard requirement that maps to a supported filter key. Do
**not** infer filters from soft or topical language — topical intent belongs in
the **query string**, not the filter. Prefer one or two narrow keys over a
broad filter object.

Apply a filter key only when the user's requirement is unambiguous, e.g.:

| User requirement | `--filter` (JSON object string) |
|---|---|
| "only free data", "no paid listings" | `'{"pricing":["free","freeToTry"]}'` |
| "HIPAA / SOC2 compliant" | `'{"complianceBadge":["HIPAA", "SOC2"]}'` |
| "in the AWS us-west-2 region" | `'{"cloudRegion":["AWS_US_WEST_2"]}'` |

The `category` and `businessNeed` filter keys exist, but they are **NOT** for
ordinary topical queries. Search is a semantic ranker: the topic *is* the
ranking signal, so a plain need like "weather data" or "weather patterns in Lake
Tahoe" should go entirely in the **query string** (`weather`, `weather lake tahoe`) 
with **no** category filter. A `category`/`businessNeed` filter only
includes/excludes — it does not rank — so using it for a normal topical request
both discards relevance ranking and risks dropping well-matched but mis-tagged
listings. Reach for these keys only in two narrow cases, and always **in
addition to** (never as a replacement for) the specific query terms:

- **Cross-domain disambiguation** — the query word is polysemous and dragging in
  unrelated results (e.g. "mercury" the planet/element/metric, "apple" the
  brand/fruit). Add a `category`/`businessNeed` facet to pin the domain.
- **Explicit browse intent** — the user wants to enumerate a whole domain or
  use-case rather than match a specific need ("what weather data is available",
  "listings for fraud-detection use cases").

When you do use them: `category` matches the product's domain (`'{"category":["WEATHER"]}'`),
while `businessNeed` matches the problem/workflow the user wants to solve
(`'{"businessNeed":["Fraud Detection"]}'`). Pass names (case-insensitive) or
numeric IDs; see the "FILTER CONTRACT" section of `--help` for the allowed names.

Rules of thumb for `--filter`:

- The value is a single JSON object string. Keys are AND-ed; array values within
  one key are OR-ed.
- Do **not** set `includePrivateListings` / `includeIntraOrgListings` — those are
  controlled by `--marketplace-type` (Step 0).
- For the full list of supported keys, allowed values, and category /
  business-need names, consult `cortex search marketplace --help` (the
  "FILTER CONTRACT" section) rather than guessing key names or values.
- If a filtered search returns zero or very few results, **re-run without the
  filter** (or with fewer keys) before telling the user nothing exists — the
  filter, not the data, is usually the cause.

### Step 2 — Run the search

**First decide the scope: marketplace-only, or marketplace + catalog?**

Before running anything, classify the request — this decides whether the catalog
search runs at all:

- **Marketplace-only → run ONLY `cortex search marketplace`. Do NOT run
  `cortex search object`.** Choose this when the user explicitly scopes the
  request to the marketplace or to third-party/external sourcing. Signals: any
  mention of "the marketplace" / "the Snowflake Marketplace" (e.g. "...on the
  marketplace", "...in the Marketplace", "search the marketplace for..."),
  "third party" / "3rd party" (data / provider / solution), "external provider
  / source". **An explicit marketplace mention ALWAYS wins — even when the topic
  by itself would be a dual-surface example.** For instance "Do you have weather
  data on the marketplace?" is marketplace-only (skip the catalog), even though a
  bare "weather data" with no marketplace mention would be dual-surface. The user
  has already told you they want acquired data, so a catalog search is off-target
  noise — **skip it.**
- **Dual-surface (default for brand-less data needs) → run BOTH `cortex search
  object` and `cortex search marketplace`.** Choose this for a generic
  data-discovery / acquisition need with no marketplace or third-party scoping,
  e.g. "I'm looking for weather data", "find healthcare data", "where can I get
  demographic data".

Decide from the user's words, not the topic's vibe. The marketplace-only path
requires an explicit scoping signal (a marketplace mention, "third party" / "3rd
party", or an external provider). A topic merely being commonly sold by data
vendors is **not** a marketplace-only signal on its own — without an explicit
qualifier, treat it as the dual-surface default (the user may hold a first-party
version or an already-licensed vendor feed internally). The word "external" on
its own is likewise **contextual**, not a marketplace-only signal: "external
data" usually just means data the user doesn't have yet → dual-surface; treat it
as marketplace-only only when paired with explicit marketplace / third-party /
provider sourcing language.

**Search the internal catalog — dual-surface case ONLY (skip entirely for marketplace-only)**

```bash
cortex search object "<query>"
```

Run it in the same turn as the marketplace search. `cortex search object` has no
`--sort` / `--filter` options, so pass only the text query. The catalog covers
data the user may already have internally; the marketplace covers data they'd
need to acquire — present both sets so the user sees the full picture.

The command prints a JSON envelope on stdout:

```json
{
  "query": "weather",
  "results": "Found 50 object(s):\n\n1. ...\n2. ..."
}
```

The `results` string is a numbered, human-readable list. For each object, extract
at minimum its fully qualified name (`DATABASE.SCHEMA.OBJECT`) and type
(`TABLE`, `VIEW`, etc.); a column list or comment may also be present and is
useful context when presenting.

**Search the marketplace**

Invoke the CLI through the available shell tool:

```bash
cortex search marketplace "<query>" --marketplace-type=<public|internal|all> [--sort=<field>] [--filter='<json-object>']
```

Conventions:

- Pass the `--marketplace-type` value resolved in Step 0.
- Add `--sort` / `--filter` only when Step 1.5 says they apply; otherwise omit
  them and let the server defaults stand.
- Default `--max-results=15` is fine for most queries; only raise it (cap is server-side) if the user asks for a broader sweep.
- **Always quote the query** so multi-word queries are passed as a single argument. Likewise, **single-quote the `--filter` JSON** so the braces and inner double quotes survive the shell.
- Do not pass `--connection` unless the user has named a specific saved connection; the CLI uses the active one by default.

The command prints a JSON envelope on stdout:

```json
{
  "query": "<query>",
  "results": "Found N marketplace result(s):\n\n1. ...\n2. ..."
}
```

The `results` string is a numbered, human-readable list. For each match, extract at minimum:

- **Listing title** (human-readable name).
- **Global name** — an alphanumeric `GZ...` identifier. This is the listing's id.
- **Listing URL** — `https://app.snowflake.com/marketplace/listing/<global_name>`. If the URL is not literally in the output, construct it from the global name.

The response will also include the listing subtitle, description, provider name, provider description which can be used when presenting the results. 

### Step 3 — Present results

If you searched the internal catalog, you **MUST present those results before the marketplace results**, under a clear heading (e.g. `## In your account (catalog)`). For each object, show its fully qualified name `DATABASE.SCHEMA.OBJECT` and type, plus a one-line description from the comment/columns if available:

```
- **DATABASE.SCHEMA.OBJECT** (TABLE) — <optional one-line description / key columns>
```

If the catalog search returned no objects, say so briefly (one line) and move on to the marketplace results — do not omit the marketplace section just because the catalog was empty.

For the results from the marketplace search:

Every response that uses this skill **MUST give each listing its URL at least once** — the URL is the actionable artifact the user clicks to inspect or install, so a listing the user can't get to is not useful. Include the URL at the listing's **primary mention** (where you introduce or present it); you don't need to repeat it on every later reference to the same listing. This holds **even when you summarize, rank, recommend, or show only a shortlist**: any listing you put in front of the user must be reachable via its `https://app.snowflake.com/marketplace/listing/<global_name>` URL somewhere in the response. Don't present a shortlist of titles or providers with no URLs at all.

Use a consistent one-listing-per-line format, e.g.:

```
- **<Listing title>** — https://app.snowflake.com/marketplace/listing/<global_name>
  <optional one-line description / provider / why it fits>
```

You may add description, provider info, example usage, or a recommendation tailored to the conversation. **NEVER** make up any information about the listing — everything must come from the search output. If an optional field is missing, omit it; but the name and URL are always available (construct the URL from the global name if it isn't printed literally).

When `--marketplace-type=all`, the CLI already labels results by source in the output (`## Snowflake Marketplace Results` and `## Internal (Intra-Org) Marketplace Results`). Preserve these section headers when presenting results to the user.

If `cortex search marketplace` returns "No marketplace listings found" or zero matches:
- If you passed `--filter`, **re-run without it (or with fewer keys) first** — an over-restrictive filter is the most common cause of empty results.
- For `--marketplace-type=internal`: suggest both (1) rephrasing the query and (2) re-running with `--marketplace-type=all` or `--marketplace-type=public` — the data may exist on the public marketplace even if the org hasn't published it internally.
- For `--marketplace-type=public` or `--marketplace-type=all`: suggest one or two alternative query phrasings (a synonym, a broader category) before giving up.

## Troubleshooting

- **`Marketplace search failed: ...`** — surface the error verbatim. Common causes: no active Snowflake connection (run `cortex connections list` to inspect), expired session token, or transient network issue. Ask the user how to proceed rather than retrying the same query blindly.
- **`Object search failed: ...` (the `cortex search object` catalog search errors, in the dual-surface case)** — surface the error verbatim; same common causes as a marketplace failure (no active connection, expired session, transient network). Because the catalog search is the *secondary* surface, do not let its failure block the run: still report the marketplace results, and note that the internal-catalog search could not be completed (offer to retry it). Do not retry the same command blindly.
- **`Connection '<name>' not found`** — the `--connection` flag was passed but does not match any saved connection. Drop the flag (so the active connection is used) or have the user run `cortex connections set <name>` first.
- **`results` is empty / "No marketplace listings found"** — treat the same as the zero-match case in Step 3: tell the user, then suggest reformulated queries.
- **`cortex: command not found`** — the Cortex Code CLI is not installed on this machine. Tell the user; DO NOT attempt to install it silently.

## CRITICAL - Anti-patterns

- Do not default to `--marketplace-type=internal` or `=all` when the user's intent is clearly public/third-party. Use `internal` or `all` only when the user's message signals intra-org intent or is ambiguous between both sources.
- NEVER use `cortex search object --types=marketplace`. 
- Do NOT run `cortex search object` when the user explicitly scoped the request to the marketplace or to third-party / external sourcing ("...in the Marketplace", "Snowflake Marketplace", "third party" / "3rd party", "external provider"). Those are marketplace-only — running a catalog search is off-target. The dual-surface catalog search is for brand-less data needs with no such scoping (e.g. "I'm looking for weather data").
- NEVER re-run the same query just because the first attempt found something the user did not ask for — refine the query string instead.
- Do NOT add `--filter` (or `--sort`) speculatively. Topical intent belongs in the query string, not a filter — filters are hard constraints that drop non-matching listings, so apply a key only for an explicit, hard user requirement.
- NEVER invent listing titles, providers, URLs, or descriptions that did not appear in the search output. If a field is missing, omit it.
- NEVER present a shortlist of listings as bare names or providers with no URLs. Curating to a "top picks" set or describing options in prose is fine, but each listing must be reachable via its `https://app.snowflake.com/marketplace/listing/<global_name>` URL at its primary mention (you needn't repeat the URL on every later reference) — a name with no URL anywhere forces the user to go hunting and defeats the point of the search. This is easy to slip on deep in a long conversation, where the temptation is to summarize providers by name; include the URLs anyway.
- NEVER skip the search and answer "the marketplace might have it" — actually run the command and report what came back.
- NEVER run `cortex search marketplace` directly from bash without **first** calling `skill(command="marketplace-search")` in the same turn. The `skill` call is the mandatory entry point even when you already know the exact query you want to run — going straight to the CLI skips the query-construction and result-presentation rules and is a defect.
- When a NEW marketplace need arises later in a conversation — a different data topic, or an explicit "search again / show me other options" request — re-invoke `skill(command="marketplace-search")` before searching. Do NOT skip the wrapper and go straight to the CLI just because you loaded the skill earlier and the `cortex search marketplace` command is still in your context. This is the most common multi-turn defect: the wrapper is loaded once on the first search, then later distinct searches run from bash directly. (You don't need to re-invoke for the same search you're already executing — the rule is one `skill()` entry per distinct need, not per CLI call.)
