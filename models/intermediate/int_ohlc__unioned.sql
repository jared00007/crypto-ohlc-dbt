-- One row per venue candle, all three venues stacked, with the canonical asset_pair
-- attached so candles can be compared across venues.
--
-- Staging has already reconciled the three payload shapes, so this is a plain union.
-- Columns are listed by name rather than relying on `select *` position: DuckDB's
-- `union all by name` would be tidier but has no Snowflake equivalent, and a silent
-- positional mismatch here would swap price columns without failing.

{% set columns = [
    'venue',
    'venue_symbol',
    'granularity',
    'candle_start',
    'open',
    'high',
    'low',
    'close',
    'volume',
    '_loaded_at',
    '_batch_id',
] %}

with unioned as (

    {% for venue in ['binance_us', 'coinbase', 'kraken'] %}
    select
        {{ columns | join(',\n        ') }}
    from {{ ref('stg_' ~ venue ~ '__ohlc') }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

pair_map as (

    select * from {{ ref('venue_pair_map') }}

)

select
    unioned.venue,
    unioned.venue_symbol,
    pair_map.asset_pair,
    pair_map.base_asset,
    pair_map.quote_asset,
    unioned.granularity,
    unioned.candle_start,
    unioned.open,
    unioned.high,
    unioned.low,
    unioned.close,
    unioned.volume,
    unioned._loaded_at,
    unioned._batch_id

from unioned
inner join pair_map
    on unioned.venue = pair_map.venue
    and unioned.venue_symbol = pair_map.venue_symbol
