{#
    Epoch -> UTC timestamp conversion. This is a portability hotspot, so it lives
    in one place rather than being spelled out in each staging model.

    Why not `to_timestamp(seconds)`: on DuckDB that returns TIMESTAMP WITH TIME
    ZONE, and casting it to TIMESTAMP applies the *session* timezone. The same
    candle then lands at 16:00 in UTC CI and 12:00 on a laptop set to
    America/New_York, which silently breaks cross-venue joins on candle_start.
    `epoch_ms` returns a plain TIMESTAMP and is timezone-independent.

    Snowflake equivalent: TO_TIMESTAMP_NTZ(<value>, 3) for milliseconds and
    TO_TIMESTAMP_NTZ(<value>) for seconds — both already UTC-anchored and free of
    the session-timezone problem, so the port is a straight swap of this macro.
#}

{% macro epoch_millis_to_timestamp(column) -%}
    epoch_ms(cast({{ column }} as bigint))
{%- endmacro %}


{% macro epoch_seconds_to_timestamp(column) -%}
    {#- cast before multiplying: seconds * 1000 overflows INT32 -#}
    epoch_ms(cast({{ column }} as bigint) * 1000)
{%- endmacro %}
