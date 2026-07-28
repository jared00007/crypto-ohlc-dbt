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

## Ingestion

```bash
# Capture fresh payloads from the venues (needs network; run occasionally)
uv run python -m ingest.capture_fixtures

# Land rows into raw. --source=fixture is offline and reproducible; CI uses it.
uv run python -m ingest.load --source fixture
uv run python -m ingest.load --source web --venue kraken
```

Landing is append-only and does no reshaping: rows keep the venue's own column
names, order, timestamp units, and price representation. Prices land as `VARCHAR`
or `DECIMAL`, never `FLOAT` — Coinbase quotes numbers rather than strings, so the
loader decodes them with `Decimal` to avoid binary rounding. Each row carries
`_loaded_at` and `_batch_id`.

## Schemas

Models land in real DuckDB schemas — `raw`, `staging`, `intermediate`, `marts` —
rather than dbt's default `<target>_<custom>` concatenation. This mirrors how the
same models would land in Snowflake and keeps `dbt docs` lineage readable. The
override is in `macros/generate_schema_name.sql`.

## Status

Phases 0 and 1 are complete. Pinned environment, dbt project config, schema
override, committed fixtures for all three venues, a dual-path loader landing
1,571 rows into `raw`, and three `stg_<venue>__ohlc` models reconciling the
incompatible shapes into one contract. `dbt build` runs 45 tests green.

Cross-venue sanity check: at a shared `candle_start`, the three venues' closes
agree within 0.03–0.15%, which is real dislocation rather than a reshaping bug.

Next: intermediate and marts layers, then the Phase 3 incremental with the
lookback window.
