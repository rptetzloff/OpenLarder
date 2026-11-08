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
