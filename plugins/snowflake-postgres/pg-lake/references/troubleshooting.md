# pg_lake Troubleshooting

Common errors and fixes encountered during pg_lake setup and usage.

## Storage Integration Errors

### Wrong integration type

**Error:** `Invalid storage integration type` or integration doesn't work with pg_lake

**Cause:** Used `EXTERNAL_STAGE` instead of `POSTGRES_EXTERNAL_STORAGE`

**Fix:** pg_lake requires `TYPE = POSTGRES_EXTERNAL_STORAGE`, not the standard Snowflake stage type:
```sql
CREATE STORAGE INTEGRATION my_int
  TYPE = POSTGRES_EXTERNAL_STORAGE  -- NOT EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ...
```

### Insufficient role

**Error:** `Insufficient privileges to operate on integration`

**Cause:** Not using ACCOUNTADMIN role

**Fix:** Storage integration operations require ACCOUNTADMIN:
```sql
USE ROLE ACCOUNTADMIN;
CREATE STORAGE INTEGRATION ...
```

## AWS / IAM Errors

### 12-hour session duration (most common)

**Symptom:** Storage integration creates successfully but pg_lake operations fail silently or timeout after ~1 hour

**Cause:** IAM role Maximum session duration left at default (1 hour). pg_lake sessions run longer.

**Fix:** In AWS Console → IAM → Roles → your role → Edit → Maximum session duration → **12 hours** (43200 seconds)

### Trust policy not updated

**Error:** pg_lake cannot access S3 after integration is attached

**Cause:** IAM trust policy still has placeholder values or wasn't updated with Snowflake's IAM user ARN and external ID

**Fix:**
1. Run `pg_lake_storage.py describe --name <integration>` to get the IAM values (written to secure file)
2. Update the IAM role trust policy with the `STORAGE_AWS_IAM_USER_ARN` as Principal and `STORAGE_AWS_EXTERNAL_ID` as condition

### Region mismatch

**Error:** `The bucket you are attempting to access must be addressed using the specified endpoint`

**Cause:** S3 bucket is in a different AWS region than the Snowflake account

**Fix:** Create the S3 bucket in the same region as your Snowflake account. Check your account region:
```sql
SELECT CURRENT_REGION();
```

### STS endpoint not active

**Error:** IAM assume-role fails

**Cause:** STS endpoint not activated for the bucket's region

**Fix:** AWS Console → IAM → Account settings → STS endpoints → Activate the endpoint for your region

## PostgreSQL Connection Errors

### Connection timeout to PG instance

**Symptom:** `psql` or `psycopg2` hangs then times out connecting to the Postgres host

**Causes:**
- No network policy attached to instance (required for external access)
- IP not in the network policy's allowed list
- VPN or corporate firewall blocking port 5432

**Fix:**
1. Create a network policy with `POSTGRES_INGRESS` mode:
```sql
CREATE NETWORK RULE my_rule TYPE = IPV4 VALUE_LIST = ('<your-ip>/32') MODE = POSTGRES_INGRESS;
CREATE NETWORK POLICY my_policy ALLOWED_NETWORK_RULE_LIST = ('my_rule');
ALTER POSTGRES INSTANCE <name> SET NETWORK_POLICY = 'my_policy';
```
2. Check your IP: `curl -s ifconfig.me`
3. Verify with `pg_lake_setup.py --check-extensions --connection-name <name>` — if it hangs, the IP isn't allowed

### Authentication failure after password reset

**Symptom:** `psql: FATAL: password authentication failed`

**Cause:** pgpass file has stale password

**Fix:** Reset credentials via script (updates pgpass automatically):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --reset --instance-name <NAME> --snowflake-connection <CONN>
```

## pg_lake Extension Errors

### Extension not available

**Error:** `extension "pg_lake" is not available`

**Cause:** pg_lake not enabled on the instance or instance needs upgrade

**Fix:** Check with `pg_lake_setup.py --check-extensions`. If not available, the instance may need a version upgrade or pg_lake needs to be enabled for the account.

### Permission denied on CREATE EXTENSION

**Error:** `permission denied to create extension "pg_lake"`

**Cause:** Not using the correct Postgres role

**Fix:** Connect as `snowflake_admin` (the default admin role for Snowflake Postgres instances):
```
psql "service=<name>" -c "CREATE EXTENSION IF NOT EXISTS pg_lake CASCADE"
```

### pg_lake_iceberg.default_location_prefix not persisting

**Symptom:** `pg_lake_iceberg.default_location_prefix` resets to empty on reconnect

**Cause:** Used session-level `SET` instead of a persistent method

**Fix:** Use persistent mode (tries ALTER SYSTEM SET):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --set-config s3://bucket/path --connection-name <name>
```

Check `persist_method` in the JSON output:
- `system` — persisted via ALTER SYSTEM, survives reconnections
- `session` — not persisted. The GUC is `PGC_SUSET` so ALTER DATABASE/ROLE SET won't work. In managed Snowflake Postgres, the platform typically sets this via `postgresql.conf` when the storage integration is attached. If ALTER SYSTEM is also blocked, session-level SET after each connect is the only option.

**Note:** The full GUC name is `pg_lake_iceberg.default_location_prefix` (not `default_location_prefix`). It's registered by the `pg_lake_iceberg` shared library.

## Iceberg Table Errors

### Cannot create Iceberg table

**Error:** `could not access storage` or `permission denied for schema`

**Cause:** Storage integration not attached, or default_location_prefix not set

**Fix:** Verify setup:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --check-config --verify-s3 --connection-name <name> --json
```

### lake_file.list() returns error

**Error:** `could not list files at s3://...`

**Cause:** S3 permissions issue — IAM role doesn't have the right S3 policy, or trust policy is wrong

**Fix:** Verify the IAM policy includes: `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:GetBucketLocation`, `s3:DeleteObject`
