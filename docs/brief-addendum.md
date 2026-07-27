# Addendum to the Kickoff Brief — decisions locked & design notes

> Append this below the original brief when starting the `crypto-ohlc-dbt` session.
> It records decisions already made so we don't re-litigate them, plus two design
> notes that shape Phase 1 and Phase 3.

---

## 9. Decisions locked before Phase 0

| Topic | Decision | Rationale |
|---|---|---|
| **Repo** | `crypto-ohlc-dbt`, public | Portfolio asset; separate from unrelated repos |
| **Env** | `uv` with pinned `pyproject.toml` + `uv.lock` | Reproducible; preferred over venv+requirements |
| **Raw landing** | Narrow, **venue-native typed columns** — Python does *no* reshaping | The three incompatible shapes are the staging lesson; keep it in dbt. Avoids leaning on DuckDB JSON functions that won't port to Snowflake. |
| **Schemas** | Real DuckDB schemas `raw` / `staging` / `intermediate` / `marts` via a `generate_schema_name` override | Mirrors Snowflake; reads cleanly in `dbt docs` lineage |
| **Packages** | `dbt_utils` (pinned) — approved | `generate_surrogate_key` (incremental key), `expression_is_true` (OHLC invariants), `date_spine` (Snowflake-portable, unlike DuckDB `range()`) |
| **`dbt-audit-helper`** | Optional, decide in Phase 3 | For the "incremental == full refresh" proof via `compare_relations` |

Landing-table contract (all three venues): venue-native OHLCV columns as returned
(prices as `VARCHAR` or `DECIMAL`, **never `FLOAT`**), the venue-native timestamp
column untouched, plus audit columns `_loaded_at` and `_batch_id`. All
renaming, column reordering, UTC normalization, and `DECIMAL` casting happens in
`stg_<venue>__ohlc`.

> **Naming note:** do **not** name a column `interval` — it is a SQL reserved word
> on both DuckDB and Snowflake and needs quoting everywhere (it *will* get missed).
> Use `granularity` (e.g. `1m`/`1h`/`1d`) as the candle-size column throughout.

---

## 10. Design note — CI runs on fixtures, not live APIs

Phase 4 GitHub Actions `dbt build` must **not** call the exchange endpoints
(rate limits, non-determinism, flakiness). This changes how the Phase 1
ingesters are written:

- Each ingester needs **two load paths from day one**: `--source=web` (real
  fetch) and `--source=fixture` (read a committed sample payload from
  `data/fixtures/<venue>/`).
- Commit a small, deterministic sample (a few hundred candles per venue/pair)
  so CI lands raw → builds → tests offline and reproducibly.
- Don't retrofit this in Phase 4 — build the seam in Phase 1.

---

## 11. Design note — the incomplete-candle problem (Phase 3 core)

The most recent candle in any pull is still forming; its OHLCV values change on
the next run. The naive incremental filter is **wrong**:

```sql
-- WRONG: permanently freezes the still-forming candle at its first-seen values
where candle_start > (select max(candle_start) from {{ this }})
```

Idiomatic handling:

- **Lookback window** instead of a strict high-water mark, so the trailing,
  mutable region gets re-read and restated each run:

  ```sql
  {% if is_incremental() %}
  where candle_start >= (
      select {{ dbt.dateadd('hour', -1 * var('lookback_hours', 3),
                            "coalesce(max(candle_start), timestamp '1970-01-01')") }}
      from {{ this }}
  )
  {% endif %}
  ```

  Use dbt's cross-db `dbt.dateadd` rather than raw `- interval '3 hours'`. The
  bare interval form happens to parse on both DuckDB and Snowflake, but interval
  arithmetic is a portability hotspot (see below); the macro guarantees the port.
  (The `coalesce(..., '1970-01-01')` guard only matters on an empty table —
  `is_incremental()` is false on first build — so it's purely defensive.)

- **`incremental_strategy='delete+insert'`** (or `merge`) on a surrogate
  `unique_key = generate_surrogate_key(['venue','venue_symbol','granularity','candle_start'])`,
  so re-read rows overwrite rather than duplicate. Both strategies exist on
  dbt-duckdb and Snowflake; `merge` is the most portable.
- The lookback restatement lives in the **incremental staging/fact model** —
  it must re-read and persist the still-forming candle so later runs can restate
  it. Do **not** filter out the newest candle here.
- Excluding the single newest still-forming candle per (venue, symbol,
  granularity) belongs **downstream**, in the fact model/view that feeds
  dislocation/returns — not in the incremental model above. Filtering it
  upstream means it's never persisted and the lookback has nothing to restate.
- **Proof:** build a full-refresh into a scratch schema and `compare_relations`
  against the incremental build — they must match.

Portability hotspots to flag inline in models as we hit them: timestamp
normalization (`epoch_ms`/`to_timestamp` vs Snowflake `TO_TIMESTAMP`), interval /
date arithmetic (prefer `dbt.dateadd`/`dbt.datediff` over raw `interval`
literals), date-spine construction, and any JSON access (kept out of staging by
the narrow-landing decision above).

---

## 12. Note on the snapshot (`snap_asset_pair`)

Kept as a deliberate learning exercise for SCD2 mechanics (`check` vs `timestamp`
strategy), with eyes open that public candle endpoints expose little genuinely
drifting pair metadata — we may be manufacturing the drift. Not load-bearing
modeling; labeled as such.
