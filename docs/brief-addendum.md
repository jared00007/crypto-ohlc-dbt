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
