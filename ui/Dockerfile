# AI-CONTEXT: the PRODUCTION UI image, which did not exist (§23 entry 92).
#
# `Dockerfile.dev` runs the Vite dev server with the source bind-mounted and HMR
# attached. That is right for `make up` and wrong for anything reachable from the
# internet: it ships the source, watches the filesystem, and serves unminified
# modules one request at a time.
#
# This builds once and produces static files. The runtime stage is not a server —
# Caddy serves the assets directly from a shared volume (see infra/Caddyfile), so
# there is no second web server in the stack and nothing to keep patched.
FROM node:22-slim AS build

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# Vite inlines VITE_-prefixed vars AT BUILD TIME, so these are build args rather than
# runtime env. `VITE_API_BASE=/api` is what makes the deployed app same-origin — see
# the note on API_BASE in src/core/api.js for why a literal localhost was a bug that
# only a deployment could reveal.
ARG VITE_API_BASE=/api
ARG VITE_MAPBOX_TOKEN=
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_MAPBOX_TOKEN=$VITE_MAPBOX_TOKEN

RUN npm run build

# The "runtime" stage exists only to hand `dist` to a volume Caddy reads. It runs
# once and exits; compose treats that as success.
FROM alpine:3.20
WORKDIR /dist
COPY --from=build /app/dist /src
CMD ["sh", "-c", "rm -rf /dist/* && cp -r /src/. /dist/ && echo 'ui assets published' && ls /dist | head"]
