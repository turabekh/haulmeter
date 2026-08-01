#!/usr/bin/env bash
# AI-CONTEXT: A12 requirement 1's second half, and the half that is normally skipped —
# "automated database backups WITH A PROVEN RESTORE". v2.0 §7 item 7 is not "a backup
# exists", it is "a database restore has been PERFORMED AND VERIFIED".
#
# An untested backup is worse than none, because it is the same thing plus confidence.
# This session took a manual `pg_dump` before mutating production and recorded it as
# debt for exactly that reason: nobody had restored it.
#
# It pulls from the BUCKET, never from the local copy. The failure this exists to catch
# is "the VM is gone", and in that scenario the local file is gone too — so verifying
# the local one proves nothing about the case that matters.
#
# Restores into a SCRATCH database and drops it. The live database is never touched;
# a verification that could damage what it verifies would not be run.
set -euo pipefail

BUCKET="${BACKUP_BUCKET:-gs://haulmeter-backups}"
SCRATCH="${SCRATCH_DB:-haulmeter_restore_check}"
REMOTE_DIR=/opt/haulmeter
COMPOSE="sudo docker compose -f docker-compose.deploy.yml --env-file .env"

cd "$REMOTE_DIR/infra"
DB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2)
USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2)
PORT=$(grep '^POSTGRES_PORT=' .env | cut -d= -f2)
PSQL="$COMPOSE exec -T postgres psql -U $USER -p $PORT"

LATEST=$(gcloud storage ls "$BUCKET/haulmeter-*.dump" 2>/dev/null | sort | tail -1)
[ -n "$LATEST" ] || { echo "FAIL: no backup in $BUCKET" >&2; exit 1; }
echo "==> verifying $LATEST"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"; $PSQL -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null 2>&1 || true' EXIT
gcloud storage cp "$LATEST" "$TMP/backup.dump" >/dev/null

echo "==> restoring into $SCRATCH"
$PSQL -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null
$PSQL -d postgres -c "CREATE DATABASE $SCRATCH;" >/dev/null
# PostGIS/pgvector live in the dump as extension statements; --no-owner because the
# scratch database has no reason to carry the live role graph.
$COMPOSE exec -T postgres pg_restore --no-owner -U "$USER" -p "$PORT" -d "$SCRATCH" \
  < "$TMP/backup.dump" 2>&1 | grep -vE "^$" | tail -5 || true

echo "==> verifying the restored copy against the live one"
fail=0
# 1. schema version. A restore that came back at the wrong migration is a restore of
#    something else, and row counts would not reveal it.
live_rev=$($PSQL -d "$DB" -Atc "select version_num from alembic_version;")
rest_rev=$($PSQL -d "$SCRATCH" -Atc "select version_num from alembic_version;")
printf "    alembic  live=%s  restored=%s  " "$live_rev" "$rest_rev"
[ "$live_rev" = "$rest_rev" ] && echo "OK" || { echo "MISMATCH"; fail=1; }

# 2. the tables that would make this product worthless if they came back empty. Counted
#    rather than sampled: "the restore ran" and "the restore contains the data" are
#    different claims and only the second one is worth anything.
for tbl in f02.facility f01.account f10.belief f14.analytics_event; do
  live=$($PSQL -d "$DB" -Atc "select count(*) from $tbl;" 2>/dev/null || echo ERR)
  rest=$($PSQL -d "$SCRATCH" -Atc "select count(*) from $tbl;" 2>/dev/null || echo ERR)
  printf "    %-22s live=%-8s restored=%-8s " "$tbl" "$live" "$rest"
  if [ "$live" = "ERR" ] || [ "$rest" = "ERR" ]; then echo "ERROR"; fail=1
  elif [ "$rest" -eq 0 ] && [ "$live" -gt 0 ]; then echo "EMPTY"; fail=1
  # the live database keeps moving while the dump is being verified, so equality is the
  # wrong test — "restored is not materially smaller" is the honest one.
  elif [ "$rest" -lt "$((live * 95 / 100))" ]; then echo "SHORT"; fail=1
  else echo "OK"; fi
done

# 3. PostGIS survived. Geometry columns restore as bytes if the extension is missing,
#    and every map query would fail on a database that restored "successfully".
geom=$($PSQL -d "$SCRATCH" -Atc "select count(*) from f02.facility where geom is not null;" 2>/dev/null || echo ERR)
printf "    %-22s %s  " "postgis geometry" "$geom"
[ "$geom" != "ERR" ] && [ "$geom" -gt 0 ] && echo "OK" || { echo "FAIL"; fail=1; }

if [ "$fail" -ne 0 ]; then
  echo "==> RESTORE VERIFICATION FAILED for $LATEST" >&2
  exit 1
fi
echo "==> restore verified: $LATEST"
