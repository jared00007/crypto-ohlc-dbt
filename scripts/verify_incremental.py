"""Prove that the incremental fact model handles the still-forming candle correctly.

    uv run python scripts/verify_incremental.py

The most recent candle in any pull is still forming, so its OHLCV values change on
the next run. Three properties have to hold, and this asserts all of them against a
real build rather than leaving them to inspection:

1. Idempotent      — re-running with no new data changes nothing.
2. Restates        — re-landing that candle with a moved close updates the row in
                     place: no frozen first-seen value, no duplicate key.
3. Equals a full refresh — the incrementally built table is row-for-row identical
                     to one built from scratch.

Property 2 is the one a naive `candle_start > max(candle_start)` filter fails.
See docs/brief-addendum.md §11.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
DATABASE = REPO_ROOT / "crypto_ohlc.duckdb"
FACT = 'marts.fct_ohlc_candles'
RESTATED_CLOSE = 99999.0

failures: list[str] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    print(f"  {'PASS' if passed else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not passed:
        failures.append(label)


def dbt(*args: str) -> None:
    result = subprocess.run(
        ["dbt", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print(result.stdout[-3000:], file=sys.stderr)
        raise SystemExit(f"dbt {' '.join(args)} failed")


def rows_differ(con: duckdb.DuckDBPyConnection, left: str, right: str) -> tuple[int, int]:
    """Symmetric difference between two relations, as (in_left_only, in_right_only).

    Each result is fetched before the next execute: duckdb's execute() returns the
    connection itself, so holding two un-fetched cursors would read the same result.
    """
    left_only = con.execute(
        f"select count(*) from (select * from {left} except select * from {right})"
    ).fetchone()[0]
    right_only = con.execute(
        f"select count(*) from (select * from {right} except select * from {left})"
    ).fetchone()[0]
    return left_only, right_only


def main() -> int:
    print("Building from scratch...")
    DATABASE.unlink(missing_ok=True)
    subprocess.run(
        [sys.executable, "-m", "ingest.load", "--source", "fixture"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    dbt("build", "--full-refresh")

    con = duckdb.connect(str(DATABASE))
    con.execute("create schema if not exists proof")
    con.execute(f"create or replace table proof.baseline as select * from {FACT}")
    baseline_rows = con.execute("select count(*) from proof.baseline").fetchone()[0]
    print(f"  baseline: {baseline_rows} rows\n")

    # 1. Idempotency.
    print("1. Idempotent across reruns")
    con.close()
    dbt("run", "--select", "fct_ohlc_candles")
    con = duckdb.connect(str(DATABASE))
    left, right = rows_differ(con, FACT, "proof.baseline")
    now = con.execute(f"select count(*) from {FACT}").fetchone()[0]
    check("rerun changes nothing", left == 0 and right == 0 and now == baseline_rows,
          f"({now} rows, diff {left}/{right})")

    # 2. Restatement of the still-forming candle.
    print("\n2. Restates the still-forming candle in place")
    newest = con.execute("select max(open_time) from raw.binance_us__ohlc").fetchone()[0]
    before = con.execute(
        f"select close from {FACT} where venue = 'binance_us' order by candle_start desc limit 1"
    ).fetchone()[0]
    con.execute(f"""
        insert into raw.binance_us__ohlc
        select open_time, open, high, low, '{RESTATED_CLOSE}' as close, volume, close_time,
               quote_asset_volume, number_of_trades, taker_buy_base_asset_volume,
               taker_buy_quote_asset_volume, ignore, _venue_symbol, _granularity,
               _loaded_at + interval '1 hour', 'restatement-proof'
        from raw.binance_us__ohlc where open_time = {newest}
    """)
    con.close()
    dbt("run", "--select", "fct_ohlc_candles")
    con = duckdb.connect(str(DATABASE))

    after = con.execute(
        f"select close from {FACT} where venue = 'binance_us' order by candle_start desc limit 1"
    ).fetchone()[0]
    rows_after = con.execute(f"select count(*) from {FACT}").fetchone()[0]
    duplicates = con.execute(
        f"select count(*) from (select ohlc_key from {FACT} group by 1 having count(*) > 1)"
    ).fetchone()[0]

    check("close was restated", float(after) == RESTATED_CLOSE,
          f"({float(before):,.2f} -> {float(after):,.2f})")
    check("row count unchanged", rows_after == baseline_rows, f"({rows_after})")
    check("no duplicate surrogate keys", duplicates == 0)

    # 3. Incremental result equals a full refresh.
    print("\n3. Incremental equals full refresh")
    con.execute(f"create or replace table proof.incremental as select * from {FACT}")
    con.close()
    dbt("run", "--select", "fct_ohlc_candles", "--full-refresh")
    con = duckdb.connect(str(DATABASE))
    left, right = rows_differ(con, FACT, "proof.incremental")
    check("row-for-row identical", left == 0 and right == 0, f"(diff {left}/{right})")
    con.close()

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s) — {', '.join(failures)}")
        return 1
    print("All incremental properties hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
