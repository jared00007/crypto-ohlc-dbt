{{
    config(
        materialized='incremental',
        unique_key='ohlc_key',
        incremental_strategy='delete+insert',
    )
}}

-- Grain: one row per venue / asset_pair / granularity / candle_start.
--
-- The most recent candle in any pull is still forming — its OHLCV values change on
-- the next run. A strict high-water mark (`candle_start > max(candle_start)`) would
-- freeze that candle at its first-seen values forever, so this re-reads a trailing
-- window instead and lets delete+insert on the surrogate key restate what changed.
-- See docs/brief-addendum.md §11.
--
-- The still-forming candle is deliberately KEPT here. Excluding it belongs
-- downstream, in the models that need only settled candles; filtering it out at this
-- layer would mean it never persists and the lookback would have nothing to restate.

with source as (

    select * from {{ ref('int_ohlc__unioned') }}

    {% if is_incremental() %}
    -- Portability: dbt.dateadd rather than `- interval '3 hours'`. The bare interval
    -- form happens to parse on both DuckDB and Snowflake, but interval arithmetic is
    -- a portability hotspot and the macro guarantees the port.
    where candle_start >= (
        select {{ dbt.dateadd(
            'hour',
            -1 * var('lookback_hours'),
            "coalesce(max(candle_start), timestamp '1970-01-01')"
        ) }}
        from {{ this }}
    )
    {% endif %}

)

select
    {{ dbt_utils.generate_surrogate_key([
        'venue',
        'venue_symbol',
        'granularity',
        'candle_start',
    ]) }} as ohlc_key,

    venue,
    venue_symbol,
    asset_pair,
    base_asset,
    quote_asset,
    granularity,
    candle_start,

    open,
    high,
    low,
    close,
    volume,

    _loaded_at,
    _batch_id

from source
