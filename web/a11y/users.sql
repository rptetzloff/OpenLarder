-- Two people for the accessibility check (check.mjs): an admin, who adds the
-- catalog it looks at, and an ordinary person with a private collection and
-- a group. Their session tokens are fixed and known, so this is for a
-- throwaway database only: CI's, or a local one.
WITH people AS (
  INSERT INTO users (issuer, subject, display_name, is_admin)
  VALUES ('a11y-check', 'admin', 'Ada Admin', true),
         ('a11y-check', 'cook', 'Cy Cook', false)
  ON CONFLICT (issuer, subject) DO UPDATE SET display_name = EXCLUDED.display_name
  RETURNING id, subject
)
INSERT INTO user_sessions (user_id, token_hash, expires_at)
SELECT id, sha256(('a11y-check-token-' || subject || '-0123456789abcdef')::bytea),
       now() + interval '1 day'
FROM people
ON CONFLICT (token_hash) DO UPDATE SET expires_at = EXCLUDED.expires_at;

-- Suggestions for the admin queue, as n8n writes them; nothing in the API
-- adds one. The ingredients are used by nothing, so anyone may see them; the
-- third suggestion names one that has gone.
WITH i AS (
  INSERT INTO ingredients (name, match_key)
  VALUES ('Quick-Cooking Oats', 'a11y quick cooking oat'), ('Quick-Cook Oats', 'a11y quick cook oat')
  ON CONFLICT DO NOTHING
  RETURNING id, name
), pair AS (
  SELECT (SELECT id FROM i WHERE name = 'Quick-Cooking Oats') AS a,
         (SELECT id FROM i WHERE name = 'Quick-Cook Oats') AS b
)
INSERT INTO suggestions (kind, target, proposal, reason, confidence, model, prompt_version)
SELECT kind, jsonb_build_array(LEAST(a, x)::text, GREATEST(a, x)::text),
       jsonb_build_object('a_id', a, 'b_id', x, 'a_name', 'Quick-Cooking Oats', 'b_name', b_name,
                          'decision', decision, 'keep_name', 'a', 'similarity', similarity,
                          'certainty', certainty),
       'Interchangeable names for the same product.', 1, 'gemma4:12b', 'merge-v1'
FROM pair, (VALUES ('merge', 'same', '0.9875', 'Quick-Cook Oats', true, 'certain'),
                   ('parent', 'b_under_a', '0.84', 'Quick-Cook Oats', true, 'likely'),
                   ('merge', 'same', '0.81', 'Rolled Oats', false, NULL)) AS v(kind, decision, similarity, b_name, real, certainty),
     LATERAL (SELECT CASE WHEN real THEN b ELSE gen_random_uuid() END AS x) AS other
WHERE a IS NOT NULL
ON CONFLICT DO NOTHING;

-- A tag suggestion, as Workflow 4 writes one, for a recipe of a small public
-- source of its own (the check's catalog is added later, through the API).
WITH s AS (
  INSERT INTO sources (title) VALUES ('Tag Suggestion Kitchen') RETURNING id
), r AS (
  INSERT INTO recipes (source_id, title, chapter)
  SELECT id, 'Seeded Rye Loaf', 'Yeast Breads' FROM s RETURNING id
)
INSERT INTO suggestions (kind, target, proposal, reason, confidence, model, prompt_version)
SELECT 'tag', jsonb_build_array(r.id::text, t.id::text),
       jsonb_build_object('recipe_id', r.id, 'tag_id', t.id, 'recipe_title', 'Seeded Rye Loaf',
                          'tag_name', t.name, 'certainty', 'certain'),
       'A loaf of bread, in the Yeast Breads chapter.', 0.9, 'gemma4:12b', 'tag-v1'
FROM r, tags t WHERE t.kind = 'course' AND t.name = 'Bread'
ON CONFLICT DO NOTHING;
