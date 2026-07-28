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

## Models

```
stg_<venue>__ohlc      three incompatible shapes -> one contract
int_ohlc__unioned      stacked, with canonical asset_pair joined on
fct_ohlc_candles       incremental grain table, lookback + delete+insert
fct_venue_dislocation  cross-venue close dispersion, settled candles only
```

## Status

Phases 0–3 are complete. `dbt build --full-refresh` runs **77 tests green** from
an empty database.

The incremental in `fct_ohlc_candles` is verified three ways, not assumed:

1. **Idempotent** — re-running with no new data changes nothing, in either
   direction of an `except` comparison.
2. **Restates rather than freezes or duplicates** — re-landing the still-forming
   candle with a moved close updates that row in place; row count unchanged, no
   duplicate surrogate keys. This is precisely what the naive
   `candle_start > max(candle_start)` filter gets wrong.
3. **Incremental == full refresh** — the two builds are row-for-row identical.

Current fixture data: 1,571 candles, 499 comparable settled candles, mean
cross-venue spread 8.5 bps and max 20.7 bps.

Next: the `snap_asset_pair` SCD2 snapshot and Phase 4 CI.
