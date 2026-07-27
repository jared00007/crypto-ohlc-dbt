{#
    Use custom schema names verbatim instead of dbt's default
    "<target_schema>_<custom_schema>" concatenation.

    This gives real `raw` / `staging` / `intermediate` / `marts` schemas rather than
    `main_staging` etc., which mirrors how the same models would land in Snowflake and
    keeps `dbt docs` lineage readable. See docs/brief-addendum.md §9.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
