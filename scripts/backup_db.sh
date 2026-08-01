#!/usr/bin/env bash
# AI-CONTEXT: A12 requirement 1 — the automated database backup. Runs ON the deployed
# box from cron; `scripts/verify_restore.sh` is the half that proves it worked.
#
# WHY OFFSITE IS NOT OPTIONAL. Before this existed the box carried three
# `backup-2026072*.dump` files written by hand, sitting in /opt/haulmeter — on the same
# disk as the database they back up. That is not a backup, it is a second copy of the
# thing that dies when the thing dies. The upload is therefore a REQUIRED step: if it
# fails, this script fails, because a backup nobody can reach after the VM is gone has
# the same value as no backup and costs more confidence.
#
# Credentials are read from infra/.env on the box and never appear here (rule 9); the
# repo is public.
set -euo pipefail

BUCKET="${BACKUP_BUCKET:-gs://haulmeter-backups}"
KEEP_LOCAL="${KEEP_LOCAL:-3}"     # remote retention is the bucket's 30-day lifecycle
REMOTE_DIR=/opt/haulmeter
LOCAL_DIR="${BACKUP_DIR:-/opt/haulmeter/backups}"
COMPOSE="sudo docker compose -f docker-compose.deploy.yml --env-file .env"

cd "$REMOTE_DIR/infra"
DB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2)
USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2)
PORT=$(grep '^POSTGRES_PORT=' .env | cut -d= -f2)

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
NAME="haulmeter-${STAMP}.dump"
mkdir -p "$LOCAL_DIR"

echo "==> dumping $DB"
# -Fc: postgres custom format. Compressed, and `pg_restore` can read a single table out
# of it — which is what makes a restore into a SCRATCH database cheap enough that
# verify_restore.sh can run every time instead of never.
$COMPOSE exec -T postgres pg_dump -Fc -U "$USER" -d "$DB" -p "$PORT" > "$LOCAL_DIR/$NAME"
SIZE=$(stat -c%s "$LOCAL_DIR/$NAME")
echo "    $LOCAL_DIR/$NAME ($SIZE bytes)"

# A truncated dump is worse than a failed one: it looks like a backup. pg_dump exits 0
# having written a header even when a later table fails, so size is the cheap guard.
if [ "$SIZE" -lt 100000 ]; then
  echo "FAIL: dump is $SIZE bytes — too small to be this database" >&2
  rm -f "$LOCAL_DIR/$NAME"
  exit 1
fi

echo "==> uploading to $BUCKET"
# `gcloud storage`, not `gsutil`: on this box gsutil reports "Provided scope(s) are not
# authorized" even with devstorage.read_write on the instance and objectAdmin on the
# bucket. gcloud storage takes the metadata credentials correctly. Both halves are
# needed, and the scope error message hides the IAM one — the first 403 here was
# scopes, the second was a missing role, and they read identically.
gcloud storage cp "$LOCAL_DIR/$NAME" "$BUCKET/$NAME" >/dev/null
gcloud storage ls "$BUCKET/$NAME" >/dev/null  # readback: not uploaded until it is THERE
echo "    $BUCKET/$NAME"

echo "==> pruning local copies (keeping $KEEP_LOCAL)"
ls -1t "$LOCAL_DIR"/haulmeter-*.dump 2>/dev/null | tail -n +$((KEEP_LOCAL + 1)) | while read -r old; do
  echo "    rm $old"
  rm -f "$old"
done

echo "==> done  $NAME"
