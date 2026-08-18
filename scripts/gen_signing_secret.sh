#!/usr/bin/env bash
# AI-CONTEXT: give this box its own stable MEDIA_SIGNING_SECRET, once.
#
# Empty was documented as fine ("the API mints a per-process key; URLs stop working
# across a restart, and the next render mints fresh ones"). That reasoning holds for a
# contact sheet that re-renders. IT DOES NOT HOLD FOR A SCREEN THAT LOADS ITS URLS ONCE
# AND SITS THERE — M15's coaching screen mints its audio URLs on load, and a driver taps
# them minutes later. And dev runs `uvicorn --reload`, so the process restarts on EVERY
# FILE EDIT: during a working session every play button on screen dies the moment anyone
# touches a source file, with a 403 the surface has no way to explain.
#
# Generated per box rather than committed to .env.example: a signing secret everyone
# shares is a signing secret anyone can mint URLs with. Never overwrites an existing one.
set -euo pipefail
ENV_FILE="$(dirname "$0")/../infra/.env"
[ -f "$ENV_FILE" ] || exit 0
if grep -qE '^MEDIA_SIGNING_SECRET=.+' "$ENV_FILE"; then
  exit 0
fi
SECRET="$(openssl rand -base64 36 | tr -d '\n/+=' | cut -c1-48)"
if grep -qE '^MEDIA_SIGNING_SECRET=' "$ENV_FILE"; then
  tmp="$(mktemp)"
  sed "s|^MEDIA_SIGNING_SECRET=.*|MEDIA_SIGNING_SECRET=${SECRET}|" "$ENV_FILE" > "$tmp"
  mv "$tmp" "$ENV_FILE"
else
  printf '\nMEDIA_SIGNING_SECRET=%s\n' "$SECRET" >> "$ENV_FILE"
fi
echo "generated MEDIA_SIGNING_SECRET for this box (signed media URLs now survive a reload)"
