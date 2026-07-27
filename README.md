# crypto-ohlc-dbt

Multi-venue crypto OHLC pipeline. Python ingesters land venue-native candles into
DuckDB; all reshaping, normalization, and modeling happens in dbt.

The guiding decisions and design notes live in [`docs/brief-addendum.md`](docs/brief-addendum.md) —
read that before adding models.

## Layout

```
ingest/          Python ingesters (--source=web | --source=fixture)
data/fixtures/   Committed sample payloads so CI builds offline
models/staging/  stg_<venue>__ohlc — renaming, UTC, DECIMAL casts
models/intermediate/
models/marts/
macros/          generate_schema_name override
```

## Setup

```bash
uv sync          # install pinned dependencies
uv run dbt deps  # install dbt packages (needs network access to hub.getdbt.com)
uv run dbt debug # verify profile and DuckDB connection
```

`profiles.yml` is committed at the project root, so no `~/.dbt` setup is needed —
dbt reads the working directory first.

## Schemas

Models land in real DuckDB schemas — `raw`, `staging`, `intermediate`, `marts` —
rather than dbt's default `<target>_<custom>` concatenation. This mirrors how the
same models would land in Snowflake and keeps `dbt docs` lineage readable. The
override is in `macros/generate_schema_name.sql`.

## Status

Phase 0 (scaffold) is complete: pinned environment, dbt project config, schema
override, and package declaration. `dbt debug` passes and the schema override is
verified against DuckDB.
