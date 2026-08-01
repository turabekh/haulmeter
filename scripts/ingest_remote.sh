#!/usr/bin/env bash
# AI-CONTEXT: put an OSM extract on the DEPLOYED box and ingest it.
# `make osm-publish STATE=x` uploads; this pulls and loads. One state per run.
#
# WHY THIS EXISTS. A deploy ships CODE, not data — `api/data` is excluded from the
# bundle — so the first corrected extract reached the box by `gcloud storage cp` and
# then `docker cp` by hand. The next deploy recreated the api container and took the
# file with it, and a VM restart cleared /tmp and took the host copy too. The DATA
# survived (postgres is a named volume); the SOURCE did not. Doing that by hand for
# fifty states is not a process, it is fifty chances to load the wrong extract.
#
# The bucket is the durable copy. The container copy is deliberately treated as
# disposable, because it is.
set -euo pipefail

STATE="${1:-}"
[ -n "$STATE" ] || { echo "usage: $0 <state>   (e.g. $0 wisconsin)" >&2; exit 1; }

PROJECT="${GCP_PROJECT:-uzimiz-prod}"
ZONE="${GCP_ZONE:-us-central1-a}"
INSTANCE="${GCP_INSTANCE:-haulmeter-test}"
BUCKET="${SOURCES_BUCKET:-gs://haulmeter-sources}"
OBJ="$BUCKET/osm/$STATE.geojson.gz"

echo "==> checking $OBJ exists before touching the box"
gcloud storage ls "$OBJ" >/dev/null

echo "==> pulling and ingesting on $INSTANCE"
gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --quiet --command="
set -euo pipefail
gcloud storage cp '$OBJ' /tmp/$STATE.geojson.gz >/dev/null 2>&1
gunzip -f /tmp/$STATE.geojson.gz
sudo docker exec haulmeter-api-1 mkdir -p /app/data/osm
sudo docker cp /tmp/$STATE.geojson haulmeter-api-1:/app/data/osm/$STATE.geojson
rm -f /tmp/$STATE.geojson
cd /opt/haulmeter/infra
sudo docker compose -f docker-compose.deploy.yml --env-file .env exec -T api \
  python -m scripts.ingest_osm /app/data/osm/$STATE.geojson
# A12 req 3: what the box just loaded, by CONTENT — the answer to 'which extract is
# this map built from', which had none before.
sudo docker compose -f docker-compose.deploy.yml --env-file .env exec -T postgres \
  psql -U \$(grep POSTGRES_USER .env | cut -d= -f2) -d \$(grep POSTGRES_DB .env | cut -d= -f2) \
  -p \$(grep POSTGRES_PORT .env | cut -d= -f2) \
  -c \"select started_at::timestamp(0) as started, ok, summary->'snapshot'->>'name' as src,
             left(summary->'snapshot'->>'sha256', 16) as digest, summary->>'facilities' as facs
        from f14.job_run where job_name='ingest_osm' order by started_at desc limit 1;\"
"
echo "==> $STATE loaded"
