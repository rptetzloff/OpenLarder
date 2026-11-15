-- The two statements the n8n workflow runs, as the ads_exporter role
-- (scripts/ads_role.sql), to copy sign-ups that followed an ad click to
-- the sheet Google Ads reads (src/openlarder/adclicks.py; README.md has
-- the workflow). tests/test_ad_clicks.py runs both as that role.

-- name: pending
-- The rows not yet in the sheet, oldest first, as the sheet's columns:
-- gclid | gbraid | wbraid | conversion_name | conversion_time | order_id.
-- Exactly one of the first three is filled. The time is UTC with its
-- offset written out. The order id is the row's own id, which is how
-- Google ignores a row it has read before.
SELECT
  CASE WHEN click_id_type = 'gclid' THEN click_id ELSE '' END AS gclid,
  CASE WHEN click_id_type = 'gbraid' THEN click_id ELSE '' END AS gbraid,
  CASE WHEN click_id_type = 'wbraid' THEN click_id ELSE '' END AS wbraid,
  'OpenLarder sign-up' AS conversion_name,
  to_char(converted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') || '+00:00'
    AS conversion_time,
  id AS order_id
FROM ad_conversions
WHERE exported_at IS NULL
ORDER BY converted_at
LIMIT 500;

-- name: exported
-- Once for each row the sheet confirmed, with its order_id as $1.
UPDATE ad_conversions SET exported_at = now() WHERE id = CAST($1 AS uuid) AND exported_at IS NULL;
