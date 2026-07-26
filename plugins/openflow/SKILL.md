---
name: openflow
description: Openflow data integration operations. Openflow is a Snowflake NiFi-based product for data replication and transformation. Use for connector deployment, configuration, diagnostics, and custom flows.
dependencies: python>=3.9, nipyapi[cli]>=1.5.0
min_nipyapi_version: "1.5.0"
skill_version: "2026-01-25"
---

# Openflow

## Session Prerequisites (Always First)

Before any operation, validate session state. Operations will fail without a valid session.

1. Load `references/core-guidelines.md` and `references/core-session.md`
2. Follow the Session Start Workflow (cache check, profile selection)
3. Only proceed once a profile is confirmed

**Context Management:**

- **Read references fully** when loading them, not just partial sections
- **Re-read references** at key workflow steps to ensure context is fresh
- If unsure of exact command syntax, run `--help` on the function before executing

---

## Routing Principles

1. **Session first** - Always validate session before routing to any operation
2. **Confirm before executing** - State detected intent, ask user for confirmation
3. **Primary wins ties** - If ambiguous between tiers, choose Primary
4. **Never suggest Advanced** - Only route to Advanced on explicit technical language
5. **Diary for complexity** - Use investigation diary methodology when Secondary/Advanced operations become complex
6. **Single nudge per session** - If an OpenFlow alert nudge has already been offered in this session (accepted or declined), do not offer another nudge from any section.

Track an internal session flag for this rule: set `alert_nudge_offered = true` immediately after the first nudge attempt.

**Confirmation checkpoint** (use before starting any workflow):

> "It sounds like you want to [detected intent]. Is that right, or were you looking for something else?"

---

## Primary Operations

These are the common operations users perform regularly. Route here confidently for any general data integration request.

**Optional monitoring nudge (Primary flows):**

After completing a Primary operation (for example deploy, setup, status, control, upgrade, or bulletins), offer this only if the single-nudge rule in Routing Principles allows it:

> "Would you like me to also set up recommended OpenFlow alerts so important OpenFlow issues are detected earlier?"

If the user accepts, follow **Alert Skill Handoff (Required on Opt-In)** below.

### Connector Name Detection

If the user mentions a data source by name, route to Primary tier:

**Known sources:** PostgreSQL, MySQL, SQL Server, SharePoint, Google Drive, Kafka, Salesforce, Box, Jira, Kinesis, Workday, Slack, Google Sheets, Google Ads, LinkedIn Ads, Meta Ads, Amazon Ads, Dataverse, MongoDB, HubSpot, Shopify

- **New connector request:** "I need PostgreSQL" → Deploy workflow
- **Existing connector:** "How's my PostgreSQL connector?" → Status workflow

### Primary Routing Table

| User Language | Operation | Reference |
|---------------|-----------|-----------|
| Deploy, set up, install, get X into Snowflake, new connector, add connector | Deploy Connector | `references/connector-main.md` |
| Pack multiple CDC connectors into one runtime, deploy dozens of connectors at once, declarative deploy, multi-connector setup, bin packing, multi-tenant SaaS replication | CDC Connector Packing | `references/cdc-connector-packing.md` |
| Status, check, how is it doing, what's running, health, is it working | Check Status | `references/ops-status-check.md` |
| Start, stop, pause, resume, turn on, turn off, enable, disable | Control Flow | `references/ops-status-check.md` |
| Upgrade, update, new version, stale, outdated | Upgrade Connector | `references/connector-upgrades.md` |
| Errors, bulletins, any problems, warnings, what's wrong | Check Bulletins | `references/ops-status-check.md` |
| List, show me, what connectors exist, what's deployed | List Flows | `references/ops-status-check.md` |
| Setup, first time, connect, missing profile, discover infrastructure | Initial Setup | `references/setup-main.md` |
| Kafka customization, Kinesis customization, change Kafka auth, change data type, add streaming transformation, add Kafka transformation, customize streaming connector, switch Snowflake auth, Private Key Auth streaming | Kafka/Streaming Customization | `references/connector-kafka.md` or `references/connector-streaming-main.md` |
| Kinesis setup, set up Kinesis, install Kinesis connector, create Kinesis stream/IAM/table, first-time Kinesis, Kinesis prerequisites | Kinesis Setup | `references/connector-kinesis-main.md` |

---

## Secondary Operations

Route here when user language contains explicit problem or operational indicators. These operations may become complex - consider using investigation diary methodology if they exceed 5-10 exchanges.

**Optional monitoring nudge (Secondary flows):**

After resolving a Secondary issue, offer this only if the single-nudge rule in Routing Principles allows it:

> "Now that we've addressed this issue, would you like to add OpenFlow alerts to catch similar failures earlier?"

If the user accepts, follow **Alert Skill Handoff (Required on Opt-In)** below.

**Confirm before routing:**

> "It sounds like you're experiencing [issue/need]. Would you like me to help with that?"

### Secondary Routing Table

| Explicit Indicators | Operation | Reference |
|---------------------|-----------|-----------|
| Investigate, troubleshoot, debug, figure out why, not working as expected | Investigation | `references/ops-flow-investigation.md` |
| Error, 401, can't connect, failed, access denied, connection error | Error Remediation | `references/core-troubleshooting.md` |
| Configure parameters, change settings, update credentials, set values | Parameter Config | `references/ops-parameters-main.md` |
| Create parameter context, bind context, delete context, assign context | Context Lifecycle | `references/ops-parameters-contexts.md` |
| EAI, network rule, firewall, external access, UnknownHostException | Network Access | `references/platform-eai.md` |
| Test network, validate connectivity, port blocked | Network Testing | `references/ops-network-testing.md` |
| Runtime errors, pod failures, logs, events table, crash loop | Platform Diagnostics | `references/platform-diagnostics.md` |
| Force stop, terminate threads, purge flowfiles, delete flow | Advanced Lifecycle | `references/ops-flow-lifecycle.md` |
| Inspect connection, FlowFile content, queue contents, peek data | Connection Inspection | `references/ops-connection-inspection.md` |
| Component state, CDC table state, clear state, reset processor | Component State | `references/ops-component-state.md` |
| Set processor properties, set controller properties, configure component | Component Config | `references/ops-component-config.md` |
| Upload asset, JAR, certificate, driver, binary file | Asset Upload | `references/ops-parameters-assets.md` |
| Snowflake destination, KEY_PAIR, auth errors, writes to Snowflake | Snowflake Auth | `references/ops-snowflake-auth.md` |
| Verify config, test connection, validate before start | Config Verification | `references/ops-config-verification.md` |
| LOCALLY_MODIFIED, version change without commit | Tracked Modifications | `references/ops-tracked-modifications.md` |

---

## Advanced Operations

Route here ONLY when user explicitly uses technical NiFi terminology. These users know what they're asking for. Do not suggest these operations to users who haven't asked.

Use investigation diary methodology for these operations - they are inherently complex.

### Advanced Routing Table

| Technical Language Required | Operation | Reference |
|-----------------------------|-----------|-----------|
| Custom flow, build from scratch, author, create new flow, design flow | Custom Authoring | `references/author-main.md` |
| Processor, add processor, create processor, modify flow structure | Component CRUD | `references/author-building-flows.md` |
| Export, import, backup, migrate, download flow | Flow Export/Import | `references/ops-flow-export.md` |
| Version control, commit, rollback, Git, save changes | Version Control | `references/ops-version-control.md` |
| Expression Language, EL, ${...}, attribute manipulation | EL Syntax | `references/nifi-expression-language.md` |
| RecordPath, record field, /path/to/field, JSON transformation | RecordPath | `references/nifi-recordpath.md` |
| Date format, timestamp conversion, epoch, SimpleDateFormat | Date Formatting | `references/nifi-date-formatting.md` |
| NAR, extension, upload NAR, Python processor, custom processor | Extensions | `references/ops-extensions.md` |
| Layout, position, organize canvas, tidy flow | Layout | `references/ops-layout.md` |
| Find processor, what processor for X, component selection | Component Selection | `references/author-component-selection.md` |
| Write to Snowflake, type mapping, logicalType, PutSnowpipeStreaming | Snowflake Destination | `references/author-snowflake-destination.md` |
| NiFi concepts, FlowFile, connections, backpressure | NiFi Concepts | `references/nifi-main.md` |
| REST API ingestion, file processing, ActiveMQ, JMS | Flow Patterns | `references/author-main.md` |
| GenerateJSON, synthetic data, test data, DataFaker, fake data | Data Generation | `references/author-pattern-data-generation.md` |

---

## Compound Requests

If the user describes multiple operations:

1. Create a todo list capturing all requested operations
2. Add this optional task only when relevant and when no alert nudge has already been offered in this session: `Optional: Set up OpenFlow monitoring alerts (best-practice templates).`
3. Ask the user to confirm the order with wording that matches whether step 2 included the optional alert task:
   - If step 2 included the optional alert task:
     > "I've identified these tasks: [list]. I can also add alert setup as a final optional step. What order would you like me to tackle them?"
   - If step 2 did not include the optional alert task:
     > "I've identified these tasks: [list]. What order would you like me to tackle them?"
4. Execute in confirmed order, completing each before moving to the next
5. Note: Some operations have natural dependencies (e.g., deploy before configure before start)

---

## Alert Skill Handoff (Required on Opt-In)

When an OpenFlow nudge is accepted, **load** `references/alert-skill-handoff.md` and follow it end-to-end.

---

## Reference Index

### Core (Load at Session Start)

| Reference | Purpose |
|-----------|---------|
| `references/core-guidelines.md` | Tool hierarchy, deployment types, workflow modes, safety reminders |
| `references/core-session.md` | Session check workflow, cache schema, profile selection |
| `references/core-investigation-diary.md` | Diary methodology for complex operations |
| `references/core-troubleshooting.md` | Error patterns and remediation |

### On Demand

| Reference | Purpose |
|-----------|---------|
| `references/alert-skill-handoff.md` | Opt-in handoff from OpenFlow to Alert skill. Load only when user accepts an OpenFlow alert nudge. |

### Connector Operations

| Reference | Purpose |
|-----------|---------|
| `references/connector-main.md` | Connector deployment workflow and routing |
| `references/connector-upgrades.md` | Version management for connectors |
| `references/known-issues-common.md` | Known issues shared across connectors (e.g. StandardPrivateKeyService INVALID on managed-token deployments) |
| `references/connector-cdc.md` | CDC connector specifics (PostgreSQL, MySQL) |
| `references/connector-sqlserver.md` | SQL Server CDC connector (Change Tracking setup, multi-DB replication, troubleshooting) |
| `references/connector-oracle.md` | Oracle CDC connector (Embedded & BYOL licensing, XStream setup, troubleshooting) |
| `references/cdc-connector-packing.md` | Pack many CDC connectors onto one runtime — declarative, plan-then-apply (fleet/multi-tenant) |
| `references/connector-mongodb.md` | MongoDB CDC connector (change-stream replication, snapshot + incremental, collection state recovery) |
| `references/connector-googledrive.md` | Google Drive connector specifics |
| `references/connector-sharepoint-simple.md` | SharePoint connector specifics |
| `references/connector-hubspot.md` | HubSpot connector (Private App Token auth) |
| `references/connector-jira.md` | Jira Cloud connector (API token auth; core + optional agile flow; legacy-to-current migration) |
| `references/connector-kafka.md` | Kafka broker auth customization (SASL, MSK IAM, mTLS) |
| `references/connector-kinesis-main.md` | Kinesis connector router (initial setup vs streaming customizations) |
| `references/connector-kinesis-setup.md` | Kinesis initial setup (AWS stream/IAM/keys + Snowflake db/schema/table/role/grants, configure and start) |
| `references/connector-streaming-main.md` | Streaming (Kafka, Kinesis) customization router (data type, transformations, DLQ, auth) |
| `references/connector-streaming-snowflake-auth.md` | Streaming Snowflake Private Key Auth (PublishSnowpipeStreaming KEY_PAIR, StandardPrivateKeyService) |
| `references/connector-streaming-datatypes.md` | Streaming data type switching (JSON → Avro/Protobuf, Confluent Schema Registry) |
| `references/connector-streaming-transformations.md` | Streaming custom transformations (filter, map, topic-to-table, content routing, defaults, Groovy) |
| `references/connector-streaming-dlq.md` | Streaming dead letter queue handling (raw + optional structured payload to Kafka/Kinesis or a Snowflake table) |
| `references/connector-shopify.md` | Shopify connector (custom-app auth, registry-driven objects, Object Definitions Override, deletes) |

### Flow Operations

| Reference | Purpose |
|-----------|---------|
| `references/ops-status-check.md` | Quick status checks, list flows, basic start/stop (Primary) |
| `references/ops-flow-lifecycle.md` | Advanced lifecycle: force stop, purge, delete (Secondary) |
| `references/ops-flow-investigation.md` | Problem-oriented diagnostic workflows |
| `references/ops-flow-deploy.md` | Deploy flows from registries (used by connector-main) |
| `references/ops-flow-export.md` | Export/import flow definitions (Advanced) |

### Parameter Operations

| Reference | Purpose |
|-----------|---------|
| `references/ops-parameters-main.md` | Parameter context management router |
| `references/ops-parameters-contexts.md` | Create, bind, delete parameter contexts |
| `references/ops-parameters-assets.md` | Binary asset upload (JARs, certificates) |
| `references/ops-snowflake-auth.md` | Snowflake destination authentication |
| `references/ops-config-verification.md` | Validate configuration before start |

### Platform Operations

| Reference | Purpose |
|-----------|---------|
| `references/platform-eai.md` | External Access Integration for SPCS |
| `references/platform-diagnostics.md` | Runtime/pod diagnostics |
| `references/ops-network-testing.md` | Network connectivity validation |

### Flow Authoring (Advanced)

| Reference | Purpose |
|-----------|---------|
| `references/author-main.md` | Flow authoring router and design principles |
| `references/author-building-flows.md` | Component CRUD, inspect-modify-test cycle |
| `references/author-component-selection.md` | Find the right processor |
| `references/author-snowflake-destination.md` | Type mapping for Snowflake writes |
| `references/author-pattern-rest-api.md` | REST API ingestion pattern |
| `references/author-pattern-files.md` | Cloud file processing pattern |
| `references/author-pattern-activemq.md` | ActiveMQ/JMS messaging pattern |
| `references/author-pattern-data-generation.md` | Synthetic test record data with GenerateJSON |

### NiFi Technical (Advanced)

| Reference | Purpose |
|-----------|---------|
| `references/nifi-main.md` | NiFi reference router |
| `references/nifi-expression-language.md` | FlowFile attribute manipulation |
| `references/nifi-recordpath.md` | Record field transformation |
| `references/nifi-date-formatting.md` | Date/time patterns |
| `references/nifi-concepts.md` | FlowFile, connections, backpressure |

### Development

| Reference | Purpose |
|-----------|---------|
| `references/core-skill-development.md` | Guidelines for extending this skill |
