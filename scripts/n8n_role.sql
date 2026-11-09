-- The database role n8n uses for the local-model workflows (SCOPING.md,
-- LLM-assisted data processing). Run once, as a superuser, after migration
-- 0029, with the password kept in Coolify rather than typed into history:
--
--   psql "$SUPERUSER_URL" -v role=n8n_suggester -v password="$N8N_DB_PASSWORD" \
--     -f scripts/n8n_role.sql
--
-- It reads only the public_ views, never the tables, so nothing from a private
-- family collection reaches a model or the suggestion queue. It writes
-- embeddings, and adds suggestions it can't change afterwards: deciding them
-- is the site's. tests/test_suggestions.py runs this file against a
-- throwaway role and checks each of these.

CREATE ROLE :"role" LOGIN PASSWORD :'password';
GRANT CONNECT ON DATABASE :"DBNAME" TO :"role";
GRANT USAGE ON SCHEMA public TO :"role";
GRANT SELECT ON public_ingredients, public_ingredient_aliases, public_ingredient_lines,
  public_open_flags TO :"role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ingredient_embeddings TO :"role";
GRANT SELECT, INSERT ON suggestions TO :"role";
