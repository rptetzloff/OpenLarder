#!/bin/sh
# Time the search endpoints for each image against a production-sized copy
# of the catalog (scale.sql makes one), to find which change slowed what.
# Each figure is the median of 5 requests, after one to warm up. Images run
# without their entrypoint, so one older than the database's schema still
# starts; the database must be at least as new as each image.
#
#   sh scripts/perf/bench.sh openlarder:before openlarder:after
#
# Run from the repo root, with the compose database up.
B=$(docker compose exec -T db psql -U openlarder -d openlarder_perf -tAc "SELECT id FROM ingredients WHERE name='Butter'")
median() { sort -n | sed -n 3p; }
printf "%-8s %10s %10s %10s %10s\n" image "ing?q=but" "ing list" "search-i" "ing page"
for tag in "$@"; do
  docker rm -f bench >/dev/null 2>&1
  docker run -d --name bench --network openlarder_default -p 8003:8000 \
    -e OPENLARDER_DATABASE_URL=postgresql+psycopg://openlarder:openlarder@db:5432/openlarder_perf \
    --entrypoint uvicorn "$tag" openlarder.main:app --host 0.0.0.0 --port 8000 >/dev/null
  for i in $(seq 1 40); do curl -sf localhost:8003/healthz >/dev/null && break; sleep 1; done
  row="$tag"
  for u in "/api/ingredients?q=butter" "/api/ingredients" "/api/search?ingredient=$B" "/api/ingredients/$B"; do
    curl -s -o /dev/null "localhost:8003$u"
    t=$(for n in 1 2 3 4 5; do curl -s -o /dev/null -w "%{time_total}\n" "localhost:8003$u"; done | median)
    row="$row $t"
  done
  echo "$row" | awk '{printf "%-8s %10s %10s %10s %10s\n", $1, $2, $3, $4, $5}'
done
docker rm -f bench >/dev/null 2>&1
