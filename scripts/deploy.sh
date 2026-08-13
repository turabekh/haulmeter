#!/usr/bin/env bash
# AI-CONTEXT: push the working tree to the haulmeter testing VM and rebuild it.
#
# A deploy is a copy of the WORKING TREE, not a `git clone` — which makes this script the
# only record of what "deployed" means, and means uncommitted edits ship. (This comment
# used to say the repo had no remote and must never be pushed; it has been public at
# github.com/turabekh/haulmeter since §23 entry 99, and CLAUDE.md rule 3 governs — push
# and deploy are each the owner's call, every time.)
#
# THE TRAP THIS SCRIPT EXISTS TO PREVENT. macOS `tar` writes AppleDouble sidecars
# (`._name`) for files carrying extended attributes. They are BINARY. Alembic globs
# `migrations/versions/*.py`, so `._0001_f01_identity.py` was imported as Python and
# the API restart-looped on `SyntaxError: source code string cannot contain null
# bytes`. 678 of them rode along on the first deploy. `COPYFILE_DISABLE=1` stops tar
# emitting them; the `find -delete` on the far side is the belt to that braces,
# because the cost of one slipping through is an outage whose error message points at
# a migration that is fine.
set -euo pipefail

PROJECT="${GCP_PROJECT:-uzimiz-prod}"
ZONE="${GCP_ZONE:-us-central1-a}"
INSTANCE="${GCP_INSTANCE:-haulmeter-test}"
REMOTE_DIR=/opt/haulmeter
COMPOSE="sudo docker compose -f docker-compose.deploy.yml --env-file .env"

cd "$(dirname "$0")/.."
BUNDLE="$(mktemp -t haulmeter-src).tgz"
trap 'rm -f "$BUNDLE"' EXIT

echo "==> bundling working tree"
# api/data is ingest SOURCE (OSM extracts, ~1 GB) and is never read at runtime — only
# by the `make ingest-*` targets. Including it made the first bundle 889 MB.
COPYFILE_DISABLE=1 tar \
  --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
  --exclude='.venv' --exclude='ui/dist' --exclude='ui/test-results' \
  --exclude='infra/.env' --exclude='api/data' --exclude='.pytest_cache' \
  --exclude='*.pyc' --exclude='.DS_Store' \
  -czf "$BUNDLE" api ui infra scripts Makefile
echo "    $(du -h "$BUNDLE" | cut -f1)"

echo "==> copying to $INSTANCE"
gcloud compute scp "$BUNDLE" "$INSTANCE:$REMOTE_DIR/src.tgz" \
  --project="$PROJECT" --zone="$ZONE" --quiet

echo "==> unpacking, rebuilding, restarting"
# infra/.env is NEVER shipped — it is created once on the VM and left alone, so a
# deploy can never overwrite the box's secrets with a laptop's (rule 9).
gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --quiet --command="
set -euo pipefail
cd $REMOTE_DIR
tar xzf src.tgz && rm -f src.tgz
find . -name '._*' -delete
find . -name '.DS_Store' -delete
test -f infra/.env || { echo 'infra/.env missing on the VM — create it before deploying'; exit 1; }
cd infra
$COMPOSE up -d --build
# AI-CONTEXT: caddy is FORCE-RECREATED, and the reason is a trap that hid a live defect
# for as long as the edge config had been wrong.
#
# The Caddyfile is a SINGLE-FILE bind mount (`./Caddyfile:/etc/caddy/Caddyfile`). This
# script replaces files by unpacking a tar over them, which writes a NEW INODE — and a
# file bind mount resolves to the inode it was created with, so the container goes on
# serving the old contents forever. `up -d --build` does not recreate it, because nothing
# about the service DEFINITION changed. `caddy reload` does not help either: it re-reads
# the same stale inode and reports success.
#
# Measured: the box had the corrected config on disk and caddy was adapting a twelve-day-
# old copy, so every broker following a link from a counterparty email still reached the
# driver app's sign-in screen. Recreating is cheap, and the alternative is a class of
# change that deploys, reports success and does nothing.
$COMPOSE up -d --force-recreate caddy
$COMPOSE ps --format 'table {{.Service}}\t{{.Status}}'
"

echo "==> done. Logs:  gcloud compute ssh $INSTANCE --project=$PROJECT --zone=$ZONE --command='cd $REMOTE_DIR/infra && $COMPOSE logs -f'"
