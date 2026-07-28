# crypto-ohlc-dbt

Multi-venue crypto OHLC pipeline. Python ingesters land venue-native candles into
DuckDB; all reshaping, normalization, and modeling happens in dbt.

Three exchanges return three incompatible payload shapes — different containers,
different timestamp units, different column orders, different price types. Keeping
that reconciliation in dbt rather than in Python is the point of the project.

The guiding decisions and design notes live in [`docs/brief-addendum.md`](docs/brief-addendum.md) —
read that before adding models.

## Quickstart

```bash
uv sync                                       # install pinned dependencies
uv run python -m ingest.load --source fixture # land the committed sample payloads
uv run dbt build                              # build every model, run every test
```

That is the whole setup. No `~/.dbt` profile to write, and **no network access
required** — `profiles.yml` is committed at the project root (dbt reads the working
directory before `~/.dbt`), and `dbt_utils` is vendored in `dbt_packages/`, so
`dbt deps` is not needed.

## Layout

```
ingest/          venue definitions, fixture capture, and the loader
data/fixtures/   committed sample payloads so builds run offline
models/staging/  stg_<venue>__ohlc — renaming, UTC, DECIMAL casts
models/intermediate/
models/marts/
macros/          schema-name override and epoch conversion
scripts/         incremental-behaviour proof, also run in CI
```

## Ingestion

```bash
# Land rows into raw. --source=fixture is offline and reproducible; CI uses it.
uv run python -m ingest.load --source fixture
uv run python -m ingest.load --source web --venue kraken

# Re-capture payloads from the live venues (needs network).
uv run python -m ingest.capture_fixtures
```

Landing is append-only and does no reshaping: rows keep the venue's own column
names, order, timestamp units, and price representation. Prices land as `VARCHAR`
or `DECIMAL`, never `FLOAT` — Coinbase quotes numbers rather than strings, so the
loader decodes them with `Decimal` to avoid binary rounding on the way in. Each row
carries `_venue_symbol`, `_granularity`, `_loaded_at`, and `_batch_id`.

The committed fixtures are a **frozen snapshot** of July 2026 candles. That is
deliberate — it is what makes CI deterministic — so a fresh clone always builds the
same numbers rather than whatever the market is doing today. Run
`capture_fixtures` to refresh them.

## Models

```
stg_<venue>__ohlc      three incompatible shapes -> one contract
int_ohlc__unioned      stacked, with canonical asset_pair joined on
fct_ohlc_candles       incremental grain table, lookback + delete+insert
fct_venue_dislocation  cross-venue close dispersion, settled candles only
```

Models land in real DuckDB schemas — `raw`, `staging`, `intermediate`, `marts` —
rather than dbt's default `<target>_<custom>` concatenation. This mirrors how the
same models would land in Snowflake and keeps `dbt docs` lineage readable. The
override is in `macros/generate_schema_name.sql`.

### A caveat on cross-venue comparison

Binance.US quotes `BTCUSDT` while Coinbase and Kraken quote against USD. The
`venue_pair_map` seed maps all three to one canonical `asset_pair`, which assumes
USDT trades at parity with USD. That is usually close but not exact: a USDT depeg
would surface as apparent venue dislocation rather than as what it is. `quote_asset`
is carried through to the fact so the effect stays attributable.

## Verifying the incremental

The most recent candle in any pull is still forming, so its values change on the
next run. `scripts/verify_incremental.py` asserts three properties against a real
build, and CI runs it on every push:

1. **Idempotent** — re-running with no new data changes nothing.
2. **Restates rather than freezes or duplicates** — re-landing that candle with a
   moved close updates the row in place; row count unchanged, no duplicate
   surrogate keys. This is exactly what a naive
   `candle_start > max(candle_start)` filter gets wrong.
3. **Incremental == full refresh** — the two builds are row-for-row identical.

```bash
uv run python scripts/verify_incremental.py
```

## Status

Phases 0–4 are complete: pinned environment, dual-path ingestion, the three
staging models, intermediate and marts layers, the incremental fact with its
lookback window, and CI that builds and tests offline on every push.
`dbt build --full-refresh` runs **77 tests green** from an empty database.

Current fixture data: 1,571 candles, 499 comparable settled candles, mean
cross-venue spread 8.5 bps and max 20.7 bps.

Not yet built: the `snap_asset_pair` SCD2 snapshot described in
[§12](docs/brief-addendum.md), and a returns model.

## License

MIT — see [LICENSE](LICENSE).
