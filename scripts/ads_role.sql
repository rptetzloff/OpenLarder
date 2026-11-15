-- The database role the n8n workflow uses to copy sign-ups that followed an
-- ad click to the sheet Google Ads reads (src/openlarder/adclicks.py;
-- Ray, 2026-11-13). Run once, as a superuser, after migration 0075, with
-- the password kept in Coolify rather than typed into history:
--
--   psql "$SUPERUSER_URL" -v role=ads_exporter -v password="$ADS_DB_PASSWORD" \
--     -f scripts/ads_role.sql
--
-- It reads ad_conversions and marks a row exported, and that is all: it
-- can't add or delete a row, change a click id, or read any other table,
-- accounts least of all. scripts/ads_export.sql has the two statements it
-- runs. tests/test_ad_clicks.py runs this file against a throwaway role
-- and checks each of these.

CREATE ROLE :"role" LOGIN PASSWORD :'password';
GRANT CONNECT ON DATABASE :"DBNAME" TO :"role";
GRANT USAGE ON SCHEMA public TO :"role";
GRANT SELECT, UPDATE (exported_at) ON ad_conversions TO :"role";
