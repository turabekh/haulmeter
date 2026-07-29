# Deploying the testing environment — haulmeter.online

A single Google Compute Engine VM running the whole stack in containers, including
Postgres. No managed database, by owner decision. **Testing environment** — the data in
it is disposable and the box is labelled `env=test`.

## What is running where

| | |
|---|---|
| Project / zone | `uzimiz-prod` · `us-central1-a` |
| Instance | `haulmeter-test`, `e2-medium` (2 vCPU / 4 GB), 20 GB pd-balanced |
| Static IP | `136.65.58.211` (`haulmeter-test-ip`, regional) |
| Firewall | `haulmeter-test-web` — **tcp:80 and tcp:443 only**, tag `haulmeter-web` |
| Source of truth | `/opt/haulmeter` on the VM, copied from the working tree |
| Compose file | `infra/docker-compose.deploy.yml` |

**Nothing but Caddy publishes a port.** Postgres, Redis, MinIO, Mailpit and the API are
reachable on the compose network and nowhere else — the dev compose publishes all of
them to the host, which is right on a laptop and wrong on a box with a public address.

## Why HTTPS is functional here, not cosmetic

Two of the product's core capabilities are gated by the browser on a *secure context*:

- **Geolocation.** F3's entire sensor — arrival detection, the detention clock, ON_SITE
  — needs `navigator.geolocation`. Over plain http the core loop cannot start.
- **SpeechRecognition.** The M11 copilot refuses to run outside a secure context. This
  is the bug in §23 entry 91, seen from the other side: reaching the dev server over a
  LAN IP is *why* voice never worked.

Caddy obtains and renews the certificate from the domain name alone, which is why it is
the proxy here rather than nginx.

## One origin

The UI is static files; `/api/*` is proxied to the API with the prefix stripped
(`handle_path` in `infra/Caddyfile`). Same origin means no CORS, no allowlist to keep in
step with the domain, and no mixed-content trap. The client half is
`VITE_API_BASE=/api`, baked in at build time — see the note on `API_BASE` in
`ui/src/core/api.js` for why a literal `localhost` was a bug only a deployment could
reveal.

## DNS (Namecheap)

Advanced DNS → remove the default parking/redirect records, then:

| Type | Host | Value | TTL |
|---|---|---|---|
| A | `@` | `136.65.58.211` | Automatic |
| A | `www` | `136.65.58.211` | Automatic |

Caddy retries ACME on its own; the certificate appears within a minute or two of the
record resolving. Until then it logs `no such host` and 443 refuses the handshake —
that is the expected waiting state, not a fault.

## Deploying a change

```
./scripts/deploy.sh          # bundle the working tree, copy, rebuild, restart
```

`infra/.env` on the VM is **never** shipped and never overwritten — it is created once,
owned root-readable only (`0600`), and holds secrets generated on the box (rule 9).

### The trap that script exists to prevent

macOS `tar` writes AppleDouble sidecars (`._name`) for files with extended attributes.
They are binary. Alembic globs `migrations/versions/*.py`, so `._0001_f01_identity.py`
was imported as Python and the API restart-looped on *"source code string cannot
contain null bytes"* — pointing at a migration that was perfectly fine. 678 of them rode
along on the first deploy. `COPYFILE_DISABLE=1` prevents them; the `find -name '._*'
-delete` on the far side is the second line of defence.

Also excluded: `api/data`, which is ingest SOURCE (OSM extracts) read only by the
`make ingest-*` targets. Including it made the first bundle 889 MB instead of 1.8 MB.

## Copying the local database up

> ### ⚠️ THIS REPLACES THE WHOLE DEPLOYED DATABASE — READ BEFORE RUNNING
>
> `pg_restore --clean --if-exists` **drops and recreates every table**, so everything
> that exists only on the box is destroyed: accounts, sessions, crowd reports, claims,
> evidence. On 29 July 2026 `driver@haulmeter.online` and `admin@haulmeter.online`
> existed **only on the VM** — zero locally. Their passwords were handed over in chat
> and written nowhere, and **F1 offers no `set_password` by design**, so restoring over
> them would have destroyed both logins with no way to recreate them.
>
> This procedure was written when the box held nothing but a seed. It is correct for
> **bootstrapping an empty box** and wrong for **updating one in use.**
>
> **To ADD facility data to a box already in use, ingest on the box instead** — it
> touches nothing but `f02`:
>
> ```bash
> gzip -c api/data/osm/<state>.geojson > /tmp/<state>.geojson.gz
> gcloud compute scp /tmp/<state>.geojson.gz haulmeter-test:/opt/haulmeter/ \
>   --project=uzimiz-prod --zone=us-central1-a
> # on the VM (api/data is NOT mounted there — the code is baked into the image):
> C="sudo docker compose -f docker-compose.deploy.yml --env-file .env"
> gunzip -kf /opt/haulmeter/<state>.geojson.gz
> CID=$($C ps -q api); sudo docker exec $CID mkdir -p /app/data/osm
> sudo docker cp /opt/haulmeter/<state>.geojson $CID:/app/data/osm/<state>.geojson
> $C exec -T api python -m scripts.ingest_osm /app/data/osm/<state>.geojson
> $C exec -T -e DRY_RUN=0 api python -m scripts.repair_colocated_scales
> $C exec -T -e DRY_RUN=0 api python -m scripts.repair_colocated_fuel
> ```
>
> **Both repair passes are required after every ingest — see the warning below.**
> Take a `pg_dump` first either way; the box has no backups.

The test box is worth more with the ingested facility data than with the demo seed —
4,568 facilities against 13. A full dump/restore rather than a table-by-table copy,
because the dump carries `alembic_version` too, so schema and data cannot drift apart.

```bash
# 1. dump locally (custom format, compressed — 59 MB of database is a 2.1 MB dump)
docker compose --project-directory infra exec -T postgres \
  pg_dump -U longhaul -d longhaul -p 5438 -Fc --no-owner --no-acl > /tmp/longhaul.dump

# 2. copy up
gcloud compute scp /tmp/longhaul.dump haulmeter-test:/opt/haulmeter/longhaul.dump \
  --project=uzimiz-prod --zone=us-central1-a

# 3. on the VM: stop the writers, restore, restart
#    --clean --if-exists so a re-run is safe; api and worker are stopped so nothing
#    races the restore or holds a connection to a table being dropped
cd /opt/haulmeter/infra
C="sudo docker compose -f docker-compose.deploy.yml --env-file .env"
$C stop api worker
sudo docker cp /opt/haulmeter/longhaul.dump $($C ps -q postgres):/tmp/longhaul.dump
$C exec -T postgres pg_restore -U longhaul -d longhaul -p 5438 \
  --clean --if-exists --no-owner --no-acl /tmp/longhaul.dump
$C start api worker
```

`--clean --if-exists` prints a wall of "does not exist, skipping" on a first run. That
is the flag working, not an error.

## Test accounts

| Account | Roles | For |
|---|---|---|
| `driver@haulmeter.online` | `driver` | ordinary driver — the whole app |
| `admin@haulmeter.online` | `driver`, `platform_admin` | the `/admin` console, and the driver app |

Both carry an `own_mc` driver profile, so detention claims render as **money owed to
them** rather than as an evidence pack handed to a carrier (M3 claim mode) — the more
useful of the two paths to exercise.

**Passwords are not in this repo and never will be** (rule 9). They were handed over
once, out of band. To issue new ones, create a new account: F1 offers no `set_password`
by design — `reset_credential` issues a temporary password and forces a change, because
"support that can read a password is support that can be social-engineered into
surrendering one".

Verified after creation: the driver logs in (200) and is **refused** `/admin/flags`
(403); the admin logs in and reaches it (200). The refusal is the half worth checking —
a role that grants nothing looks identical to one that grants everything until someone
tries the door.

## Operating it

```
# logs
gcloud compute ssh haulmeter-test --project=uzimiz-prod --zone=us-central1-a \
  --command='cd /opt/haulmeter/infra && sudo docker compose -f docker-compose.deploy.yml --env-file .env logs -f'

# seed demo data (not automatic — DEV_SEED only arms the flag)
... exec -T -e DEV_SEED=1 -e DEV_SEED_ORIGIN='32.7767,-96.7970' api python -m scripts.seed_demo

# Mailpit / MinIO console are internal by design — reach them over a tunnel
gcloud compute ssh haulmeter-test --project=uzimiz-prod --zone=us-central1-a -- -L 8038:localhost:8038
```

## Cost and teardown

Roughly **$28–30/month** (e2-medium ~$25, 20 GB pd-balanced ~$2, static IP free while
attached). To stop paying for compute without losing the data volumes:

```
gcloud compute instances stop haulmeter-test --project=uzimiz-prod --zone=us-central1-a
```

Full teardown — **destroys the data**:

```
gcloud compute instances delete haulmeter-test --project=uzimiz-prod --zone=us-central1-a
gcloud compute addresses delete haulmeter-test-ip --project=uzimiz-prod --region=us-central1
gcloud compute firewall-rules delete haulmeter-test-web --project=uzimiz-prod
```

## Known, and deliberate

- **All API keys from the local `infra/.env` are on this box** (Mapbox, Anthropic,
  Voyage, EIA) — owner decision, recorded here because an internet-facing test VM
  holding live keys is worth stating rather than discovering. The file is `0600` and
  the firewall admits only 80/443.
- `ENVIRONMENT=test`, and the deploy sends `X-Robots-Tag: noindex, nofollow`. That is
  honesty about what the box is, not a security control.
