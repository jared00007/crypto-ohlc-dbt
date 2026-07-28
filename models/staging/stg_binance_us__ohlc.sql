-- Binance.US lands 12-element arrays: open time in epoch MILLISECONDS, prices as
-- strings, columns already in open/high/low/close order.

with source as (

    select * from {{ source('raw', 'binance_us__ohlc') }}

),

renamed as (

    select
        'binance_us' as venue,
        _venue_symbol as venue_symbol,
        _granularity as granularity,

        {{ epoch_millis_to_timestamp('open_time') }} as candle_start,

        cast("open" as decimal(38, 18)) as open,
        cast(high as decimal(38, 18)) as high,
        cast(low as decimal(38, 18)) as low,
        cast("close" as decimal(38, 18)) as close,
        cast(volume as decimal(38, 18)) as volume,

        _loaded_at,
        _batch_id

    from source

)

select * from renamed

-- Landing is append-only, so the same candle appears once per batch. Keep the most
-- recently loaded copy: a re-read of a still-forming candle supersedes the earlier
-- one. See docs/brief-addendum.md §11.
qualify row_number() over (
    partition by venue, venue_symbol, granularity, candle_start
    order by _loaded_at desc, _batch_id desc
) = 1
