-- Make a copy of the local catalog about production's size: every recipe 19
-- more times, with its lines, options and locations. Scratch database only.
CREATE TEMP TABLE rmap AS
  SELECT r.id AS old, gen_random_uuid() AS new, k
  FROM recipes r, generate_series(1, 19) k;
CREATE TEMP TABLE lmap AS
  SELECT ri.id AS old, gen_random_uuid() AS new, m.k, m.new AS recipe
  FROM recipe_ingredients ri JOIN rmap m ON m.old = ri.recipe_id;

INSERT INTO recipes (id, source_id, title, online_url, created_by)
  SELECT m.new, r.source_id, r.title || ' ' || m.k, r.online_url, r.created_by
  FROM rmap m JOIN recipes r ON r.id = m.old;
INSERT INTO recipe_ingredients (id, recipe_id, position, original_text)
  SELECT l.new, l.recipe, ri.position, ri.original_text
  FROM lmap l JOIN recipe_ingredients ri ON ri.id = l.old;
INSERT INTO ingredient_options (recipe_ingredient_id, recipe_id, rank, name, ingredient_id)
  SELECT l.new, l.recipe, o.rank, o.name, o.ingredient_id
  FROM lmap l JOIN ingredient_options o ON o.recipe_ingredient_id = l.old;
INSERT INTO recipe_locations (recipe_id, edition_id, source_id, page)
  SELECT m.new, rl.edition_id, rl.source_id, rl.page
  FROM rmap m JOIN recipe_locations rl ON rl.recipe_id = m.old
  WHERE rl.edition_id IS NOT NULL;
ANALYZE;
SELECT (SELECT count(*) FROM recipes) AS recipes, (SELECT count(*) FROM ingredient_options) AS options;
