"""Land venue-native OHLC rows into the DuckDB `raw` schema.

    uv run python -m ingest.load --source fixture           # all venues, offline
    uv run python -m ingest.load --source web --venue kraken

Two load paths exist from day one so CI can build without touching the exchanges.
See docs/brief-addendum.md §10.

What this does NOT do: rename columns, reorder them, normalize timestamps, or cast
prices. Rows land under the venue's own column names, in the venue's own order,
with the venue's own timestamp units. All of that is dbt's job in
`stg_<venue>__ohlc`. Landing is append-only — `_batch_id` distinguishes runs and
the incremental models deduplicate on the surrogate key.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import httpx

from ingest.venues import VENUES, VENUES_BY_NAME, Venue

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
DEFAULT_DATABASE = REPO_ROOT / "crypto_ohlc.duckdb"
RAW_SCHEMA = "raw"
TIMEOUT_SECONDS = 30.0
USER_AGENT = "crypto-ohlc-dbt/0.1"


def _parse(text: str) -> Any:
    """Parse JSON with exact decimals.

    Coinbase quotes prices as JSON numbers. Parsing those as float would introduce
    binary rounding before the value ever reaches the database, so decode them as
    Decimal and preserve the payload text exactly.
    """
    return json.loads(text, parse_float=Decimal)


def read_fixture(venue: Venue) -> Any:
    path = FIXTURE_ROOT / venue.name / venue.fixture_name
    if not path.exists():
        raise FileNotFoundError(
            f"No fixture at {path.relative_to(REPO_ROOT)}. "
            f"Run `python -m ingest.capture_fixtures` from a networked machine."
        )
    return _parse(path.read_text())


def fetch_web(venue: Venue) -> Any:
    with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(venue.url, params=venue.params)
        response.raise_for_status()
        return _parse(response.text)


def ensure_table(con: duckdb.DuckDBPyConnection, venue: Venue) -> None:
    columns = ",\n    ".join(f'"{name}" {sql_type}' for name, sql_type in venue.columns)
    con.execute(f"create schema if not exists {RAW_SCHEMA}")
    con.execute(
        f"""
        create table if not exists {RAW_SCHEMA}."{venue.table}" (
            {columns},
            "_venue_symbol" VARCHAR,
            "_granularity" VARCHAR,
            "_loaded_at" TIMESTAMP,
            "_batch_id" VARCHAR
        )
        """
    )


def load_venue(
    con: duckdb.DuckDBPyConnection, venue: Venue, source: str, batch_id: str
) -> int:
    payload = fetch_web(venue) if source == "web" else read_fixture(venue)
    rows = venue.extract_rows(payload)

    width = len(venue.columns)
    for index, row in enumerate(rows):
        if len(row) != width:
            raise ValueError(
                f"{venue.name}: row {index} has {len(row)} fields, expected {width}. "
                f"The venue's payload shape changed; update Venue.columns."
            )

    ensure_table(con, venue)
    loaded_at = datetime.now(UTC)
    # Symbol and granularity are request parameters, and Binance.US and Coinbase do
    # not echo them in the payload. Landing them as provenance keeps a row
    # self-describing once more than one pair is loaded.
    audit = [venue.venue_symbol, venue.granularity, loaded_at, batch_id]
    placeholders = ", ".join(["?"] * (width + len(audit)))
    con.executemany(
        f'insert into {RAW_SCHEMA}."{venue.table}" values ({placeholders})',
        [[*row, *audit] for row in rows],
    )
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source",
        choices=("web", "fixture"),
        required=True,
        help="web hits the live venue API; fixture reads the committed payload",
    )
    parser.add_argument(
        "--venue",
        choices=sorted(VENUES_BY_NAME),
        action="append",
        help="load one venue; repeatable. Defaults to all venues.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"DuckDB file to land into (default: {DEFAULT_DATABASE.name})",
    )
    args = parser.parse_args(argv)

    venues = [VENUES_BY_NAME[name] for name in args.venue] if args.venue else list(VENUES)
    batch_id = str(uuid.uuid4())
    failures: list[str] = []

    print(f"batch {batch_id}  source={args.source}  -> {args.database.name}")
    with duckdb.connect(str(args.database)) as con:
        for venue in venues:
            try:
                count = load_venue(con, venue, args.source, batch_id)
            except Exception as exc:  # noqa: BLE001 - report and continue to the next venue
                failures.append(venue.name)
                print(f"  FAIL  {venue.name}: {exc}", file=sys.stderr)
                continue
            print(f'  ok    {venue.name:<11} {count:>4} rows -> {RAW_SCHEMA}."{venue.table}"')

    if failures:
        print(f"\n{len(failures)} of {len(venues)} venues failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
