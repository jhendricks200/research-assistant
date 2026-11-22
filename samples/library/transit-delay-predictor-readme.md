---
title: 'NYC Transit Delay Predictor: README'
source_type: article
status: published
topics: [Transit app]
tags: [GTFS-Realtime, data quality, deployment]
entities: [GTFS-Realtime, Expo, FastAPI]
---
# NYC Transit Delay Predictor

This repository contains the critical-path GTFS-Realtime collector, the Expo rider app, and a local
FastAPI service. The collector remains independently deployable. The local API deliberately reports
`schedule_only` until archived GTFS-RT labels and realtime heuristic inputs clear their quality gates;
the UI never presents those estimates as live delay predictions.

## OpenAI Build Week 2026

The judging package is in [`docs/build-week-2026/`](docs/build-week-2026/), including the submission
narrative, a sub-three-minute demo script, and commit-level eligibility evidence. Codex was the
primary engineering environment and produced the vast majority of the product; Claude Code assisted
with portions of the early UI and planning. The original product was developed primarily with Codex
and GPT-5.5; during Build Week, Codex desktop with GPT-5.6 Sol was used to inspect, extend, test, and
ship it as an external beta. This does not claim that either coding agent supplied transit facts or
prediction labels. For judging, treat only commits from
**2026-07-13 09:00 PT through 2026-07-21** as new work; the forecast and calibration core is
explicitly identified as pre-existing where applicable.

Reviewers can start with the local commands below, then use `make smoke-api` with the API running and
`cd mobile && npm run web` for the app. The package is a truthful review aid, not a claim of live
production availability or a substitute for credentials or secrets.

## Run the app locally

One command starts both the API and Expo web:

```bash
uv sync --dev
make dev
```

That runs the FastAPI service at `http://127.0.0.1:8000`, waits for Expo web at
`http://localhost:8081`, and opens it in your default browser.

**macOS (no terminal typing):** double-click **`Open Transit App.command`** at the repo root.
That starts both services, **clears local API test data**, disables sample-commute seeding, opens
the app at a blank-slate first-run state (nearby stations, no saved commute), and keeps Terminal
open until you press Ctrl+C.

For forecast screenshots or a pre-filled hero, double-click **`Open Transit App (Sample Commute).command`**
instead — seeds the Jay St → Times Sq sample commute when none exist.

`make dev` keeps your existing local data and does not change seeding flags.

Same behavior from the shell:

```bash
DEV_LOCAL_BLANK_SLATE=1 bash ops/dev-local.sh   # reviewer blank slate
DEV_LOCAL_SAMPLE_COMMUTE=1 bash ops/dev-local.sh # sample commute
```

Set `DEV_LOCAL_NO_OPEN=1` to skip the browser step (e.g. automation).

Manual two-terminal setup:

```bash
uv sync --dev
AUTH_REQUIRED=0 uv run transit-api
```

```bash
cd mobile
npm install
npm run web
```

The API serves interactive documentation at `/docs`. Devices and commutes persist in
`data/api/transit.db`. The mobile app reads `mobile/.env.local`; set
`EXPO_PUBLIC_API_MODE=http` and `EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` for the wired
local build (mock mode remains the default when those are unset).

### Local API smoke test

With the API running:

```bash
make smoke-api
```

This exercises `GET /v1/status`, device registration, commute creation, and forecast generation.
It prints only pass/fail lines (no device secrets).

### Reset local test data

All registered devices, saved commutes, and analytics events live in `data/api/transit.db`.
Stop `transit-api` first, then either:

```bash
bash ops/dev-reset-db.sh --confirm
```

or delete individual rows with the API (`DELETE /v1/devices/{id}` with the device Bearer token).
`Open Transit App.command` clears the database automatically before each review session;
`make dev` does not.

### Review with real people

See [docs/review-checklist.md](docs/review-checklist.md) for how to start the app, get reviewers
into a useful state in a few minutes, and what questions to ask (leave-by trust, commute assistant
vs. dashboard).

### Expo web QA

See [mobile/WEB_QA.md](mobile/WEB_QA.md) for a short manual checklist (first load, empty state,
forecast, backend-off error, mobile-width layout, refresh/reopen).

Current local forecast behavior:

- Uses the rider's saved service days, arrive-by time, and walking minutes.
- Generates only line/transfer paths supported by the static station graph.
- Applies the documented fixed p80 schedule buffers.
- Labels confidence as low and the source as schedule-only.
- Does not yet claim realtime alerts, line status, or learned delay calibration.

## GTFS-Realtime collector

The worker polls all eight MTA subway/SIR GTFS-Realtime feeds and the dedicated subway-alert feed
every 30 seconds. Responses are written immediately to the persistent spool, then each feed's
snapshots are packed into one compressed minute bundle. Every response remains byte-for-byte
extractable with its original immutable manifest containing fetch time, feed timestamp, HTTP status,
latency, checksum, parser version, entity counts, and observed routes.

## Local verification

```bash
uv sync --dev
ARCHIVE_BACKEND=local uv run transit-collector --once
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Local bundles are written below `data/archive/`; unsealed snapshots and failed R2 uploads are durably
spooled below `SPOOL_DIR` and retried before each poll cycle.

## R2 object layout

```text
{R2_PREFIX}/bundles/{feed}/YYYY/MM/DD/HH/{minute_end_epoch_ms}-{sha256_prefix}.tar.gz
{R2_PREFIX}/bundles/{feed}/YYYY/MM/DD/HH/{minute_end_epoch_ms}-{sha256_prefix}.tar.gz.manifest.json
```

Each bundle contains the original `.pb` or error `.bin` response, its per-snapshot JSON manifest, and
a bundle index. Conditional writes (`If-None-Match: *`) make object keys immutable and retries
idempotent. At two R2 objects per feed per minute, the collector performs about 777,600 Class A writes
per 30-day month.

## Static route-map launch gate

After rebuilding `data/static/subway-gtfs.json` and before an App Store/TestFlight build, run:

```bash
uv run transit-static-gtfs-audit
```

The command exits non-zero on failure and prints a compact deterministic JSON report. It audits all
supported subway route patterns and both directions, stop-roster coverage, ordered and bounded
geometry, the West 4 St `A32`/`D20` complex, and representative direct, express, shuttle,
outer-borough, and transfer-complex segments. Use `--output path.json` only when a CI artifact is
needed; no large report is generated by default.

For the read-only production API gate, run:

```bash
uv run transit-production-smoke \
  --base-url https://<railway-host>
```

This makes GET requests only and requires no credentials. It checks `/healthz` plus representative
geometry, station departures, and actual-reported-or-empty vehicle responses across all seven
realtime feed families. It fails on schema drift, unreasonable response sizes, invalid coordinates,
missing stale/upstream semantics, HTTP errors, or requests slower than 10 seconds (configurable with
`--max-latency-ms`).

## Railway deployment

1. Create an R2 bucket and API token with object read/write access to that bucket.
2. Create a Railway service from this repository using the included Dockerfile. The service
   runs `transit-runtime` (from `railway.toml`), the full supervisor: collector + API +
   6-hour calibration worker. The Dockerfile `CMD` defaults to the same `transit-runtime`;
   Railway's `startCommand` is authoritative and overrides it.
3. Attach a persistent volume mounted at `/data` so state survives redeploys and restarts.
   What lives under `/data`:
   - `/data/spool` — the collector's upload spool (`SPOOL_DIR`); failed R2 uploads wait here.
   - `/data/api/transit.db` — the API's SQLite database (devices, commutes, events). The
     image sets `TRANSIT_API_DATABASE_PATH=/data/api/transit.db` so this durable path is used
     in the container without changing the repo-relative default that local dev uses. Losing
     this file loses every registered device, saved commute, and retention event. Set
     `DATABASE_BACKUP_ENABLED=1` to have the isolated backup worker publish daily verified,
     immutable copies to R2; see `ops/README.md` for object layout and recovery policy.
   - `/app/data/static/subway-gtfs.json` — the immutable compact subway index baked into the
     image. Docker sets `TRANSIT_API_STATIC_GTFS_PATH` explicitly because the Python package is
     installed under `site-packages`; local development resolves `data/static/subway-gtfs.json`
     from the repository working directory. Override this variable only for a custom index path.

   Calibration and holdout outputs are NOT the durability concern here: with
   `ARCHIVE_BACKEND=r2` the calibration worker publishes `residual-buffers.json`,
   `holdout-summary.json`, and the quality-history log to R2, and the API reads calibration
   back from R2. The container's local `data/calibration/` copies are scratch and may be lost
   on redeploy.
4. Configure the variables from `.env.example`. Production must use `ARCHIVE_BACKEND=r2`.
   Keep `RAILWAY_RUN_UID=0`; Railway volumes are mounted as root and otherwise cannot be written by
   this image's non-root runtime user.
5. Set `ALERT_WEBHOOK_URL` to the operations webhook that should receive archive-gap,
   calibration-staleness, recovery, and test events. Structured error logs are always emitted even
   without a webhook. Force-fire the channel once with `uv run transit-alert-test --detail "hello"`.
6. Deploy one replica only. The object keys are idempotent, but duplicate replicas waste feed and
   storage operations.

Required production variables:

- `ARCHIVE_BACKEND=r2`
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET`
- `SPOOL_DIR=/data/spool`
- `RAILWAY_RUN_UID=0`
- `ALERT_WEBHOOK_URL`
- `AUTH_REQUIRED=1`

With `AUTH_REQUIRED=1`, every device-scoped request must carry the one-time secret returned by
registration. A database row created before device secrets existed has `secret_hash = NULL` and is
always rejected: there is no credential with which it can prove ownership. The app will register a
fresh device and secret during bootstrap. Its old saved commutes cannot be transferred securely and
must be recreated; the backend never silently grants access to the legacy row. Authentication
defaults on when the variable is absent; `make dev` explicitly sets `AUTH_REQUIRED=0` for local web
development unless the caller overrides it.

Optional off-volume API database backup variables:

- `DATABASE_BACKUP_ENABLED` defaults to `0`; set to `1` only after the R2 variables are present.
- `DATABASE_BACKUP_INTERVAL_SECONDS` defaults to 86400 (24 hours).
- `DATABASE_BACKUP_STARTUP_DELAY_SECONDS` defaults to 60, allowing API initialization first.
- `DATABASE_BACKUP_R2_PREFIX` defaults to `database-backups`.
- `DATABASE_BACKUP_RESTART_BACKOFF_SECONDS` defaults to 300 for unexpected worker exits.

Optional alert tuning variables:

- `CALIBRATION_STALENESS_ALERTS=0` disables calibration-staleness alerts.
- `CALIBRATION_STALE_ALERT_SECONDS` defaults to 129600 (36 hours), matching the API/UI stale
  calibration threshold.
- `CALIBRATION_STALENESS_STATE_PATH` defaults to `{SPOOL_DIR}/calibration-health-state.json` so
  the worker does not send repeated stale alerts across restarts.
- `CALIBRATION_WORKER_STATUS_PATH` defaults to `{SPOOL_DIR}/calibration-worker-status.json`.
  The calibration worker writes phase status there, and `/healthz` exposes it as
  `calibrationWorker` when present. Use this to confirm whether calibration or holdout is running,
  completed, or failed without streaming Railway logs. The public response includes only overall
  and per-phase status plus phase timestamps; exception and error message text remains internal.

Optional backend error monitoring variables:

- `SENTRY_BACKEND_DSN` enables Sentry for the API, collector, calibration/holdout worker, push
  worker, database-backup worker, and their runtime supervisor. It is disabled when unset.
- `SENTRY_BACKEND_ENVIRONMENT` labels the deployment environment; on Railway it otherwise falls
  back to `RAILWAY_ENVIRONMENT_NAME`.
- `SENTRY_BACKEND_RELEASE` identifies the deployed revision; on Railway it otherwise falls back to
  `RAILWAY_GIT_COMMIT_SHA`.

Only error events are enabled: tracing and profiling sample rates are zero, request bodies and
default PII are disabled, and a final event scrubber removes authentication data, device ids, push
tokens, coordinates, URLs, and common secret fields. Existing JSON logs and Slack operational
alerts remain independent. Verify a new configuration in Sentry with a deliberately labeled test
error before relying on it in production.

Optional archive replay tuning:

- `ARCHIVE_READ_WORKERS` defaults to 4. R2 bundle reads are submitted through a bounded window, so
  calibration and holdout retain at most this many loaded bundle results at once. Increase it only
  after confirming the service has enough RAM in Railway Metrics.

## Health gate

After the worker has run for 24 hours, audit the archive:

```bash
uv run transit-collector-audit --hours 24
```

The command exits successfully only when every feed has at least 99% valid snapshots and no gap
between valid snapshots exceeds 75 seconds. The audit reads every original per-poll manifest embedded
in the compressed bundles; it does not treat a bundle-level sidecar as proof that every response was
valid. Any gap over the limit resets the healthy-window clock. Do not start the monorepo or UI before
this gate passes.

The subsequent seven-day audit must additionally evaluate route-level coverage, forecast horizons,
stale timestamps, trip continuity, and usable station-passage labels. Those consumers will read the
immutable manifests and raw protobufs created here; they must never reinterpret projected stop times
as actual arrivals.

### Deploy acceptance checklist (Railway)

Before pointing the app at the cloud API, confirm all of the following against the deployed box.
Each must pass once, end to end:

1. `/healthz` returns 200 (`curl https://<railway-host>/healthz`), and `calibrationWorker`
   eventually shows both `calibration` and `holdout` phase completion after a worker cycle.
2. The forecast endpoint reports the calibrated source: a forecast response's calibration source is
   `archive_calibrated`, not a fallback. This confirms the API is reading real R2 calibration.
3. The collector is writing to R2: new bundle objects are appearing under the
   `{R2_PREFIX}/bundles/...` prefix (and `/data/spool` is draining rather than growing).
4. A calibration refresh succeeds on the box: the supervised worker completes a run and republishes
   `residual-buffers.json` to R2 (check the worker logs and the object's timestamp).
5. A holdout refresh succeeds on the box: the same worker cycle republishes `holdout-summary.json`
   to R2.
6. The app can save a commute against the cloud API: from an HTTP-mode client pointed at the Railway
   host, register a device and save a commute, then confirm the row persists (and still exists after
   a redeploy, proving the `/data` volume is durable).

### Rollback

If the deployed box is unhealthy or a bad build ships, point the app away from it:

- Fastest: set the mobile client back to a known-good API. Either mock mode
  (`EXPO_PUBLIC_API_MODE` unset or `mock`) for a zero-dependency fallback, or HTTP mode against the
  local backend (`EXPO_PUBLIC_API_MODE=http`, `EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`).
- Or redeploy the previous known-good Railway build (Railway keeps prior deployments; roll back to
  the last one that passed this checklist). The `/data` volume is retained across redeploys, so
  devices, commutes, and events are preserved.

## Push sender groundwork

The backend has the durable pieces needed for leave-now pushes. `src/transit_api/push.py` can select
notification-enabled devices with saved commutes, compute the current forecast, reserve a de-dupe key
in `notification_deliveries`, and send an Expo push message through an injected client. The recurring
worker reuses one MTA alerts service across passes so forecasts include current or cached realtime
alerts without failing a pass when the feed is unavailable. Expo's HTTP response is not considered a
successful delivery until every push ticket is structurally valid and reports `ok`. The table prevents
repeated sends for the same scheduled commute occurrence even if its forecast timing moves.

The scheduled worker exists as `transit-push-worker` and `transit-runtime` supervises it only when
`PUSH_SENDER_ENABLED=1`. It is disabled by default. Keep it off until EAS/app identity and real
device-token registration are complete. Tuning:

- `PUSH_INTERVAL_SECONDS` defaults to 60.
- `PUSH_DUE_WINDOW_SECONDS` defaults to 300, meaning a leave-now push is eligible only for five
  minutes after the computed recommended departure time.
- `PUSH_BETA_DEVICE_IDS` is an optional comma-separated allowlist for recurring beta sends. When the
  variable is present, only exact listed device ids are eligible; an empty value allows none.

For a one-device installation check, use the separate operator command. It never starts or enables
the recurring worker, requires an exact device id, and is a dry run unless `--send` is present:

```bash
# Safe preview: validates the device and registered token; no network request.
uv run transit-push-test --device-id dev_example

# Explicitly send exactly one test message to that one device.
uv run transit-push-test --device-id dev_example --send
```

Set `TRANSIT_API_DATABASE_PATH` when operating against a non-default database. The command reports
only the device id and outcome; it never prints the push token. Keep `PUSH_SENDER_ENABLED` off while
using this test path.

After a scheduled canary, correlate the durable delivery id with device receive/open events and check
for duplicates using the read-only pilot report:

```bash
sqlite3 -readonly data/api/transit.db < ops/push_pilot.sql
```

On Railway, use `/data/api/transit.db`. The report does not modify the database.

## Station-passage labels

Generate realized station-passage labels directly from successive archived vehicle snapshots:

```bash
uv run transit-labeler --hours 24
```

The command reads R2 when `ARCHIVE_BACKEND=r2` and otherwise reads `LOCAL_ARCHIVE_DIR`. It validates
every payload checksum, excludes SIR and alerts by default, and writes newline-delimited labels to
`data/labels/station-passages.ndjson`. Each label contains lower and upper arrival bounds. A midpoint
is emitted only for intervals of 90 seconds or less. Feed gaps, stale snapshots, non-monotonic stop
sequences, changed stop IDs at the same sequence, reroutes, and ambiguous trip identities are
rejected and counted in the JSON audit report. Use `--include-sir` only for explicit non-MVP audits.
