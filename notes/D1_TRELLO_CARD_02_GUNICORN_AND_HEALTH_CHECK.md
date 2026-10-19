# Trello Card: [D1] Gunicorn Integration and Health Check

**List:** Current Sprint
**Labels:** Backend, Infrastructure

## Description

Type: Feature
Points: 2
Owner: Jean Durand
Depends on: [D1] Environment-Based Settings and Secure Authentication

Description:

Replace the Django development server with Gunicorn so the backend can serve production traffic. Gunicorn serves Django on the internal Docker network only; Nginx stays the public reverse proxy.

The container entrypoint applies migrations, then hands over to Gunicorn as the main process so `docker stop` shuts it down gracefully. A health-check endpoint reports whether the application and PostgreSQL are available, and documents left mid-parse by a restart are marked as failed instead of staying stuck.

## Acceptance Criteria

- [ ] Gunicorn is pinned in `requirements.txt`.
- [ ] `gunicorn.conf.py` sets worker count and thread count from `WEB_CONCURRENCY` and `GUNICORN_THREADS`, with sensible defaults.
- [ ] The request timeout is 95 seconds so scanned receipt parsing stays under Cloudflare's 100 second limit.
- [ ] Workers are recycled after a set number of requests, and access and error logs go to stdout.
- [ ] `entrypoint.sh` no longer runs `makemigrations` and applies `migrate --noinput`.
- [ ] `entrypoint.sh` starts Gunicorn with `exec` in production and `runserver` when `DJANGO_DEBUG=1`.
- [ ] `docker compose stop web` shows Gunicorn handling `SIGTERM` and exiting within the grace period.
- [ ] `GET /api/health/` returns `200` with database status without requiring authentication.
- [ ] `GET /api/health/` returns `503` when PostgreSQL is unreachable.
- [ ] The health-check endpoint is covered by a test in `core/tests.py`.
- [ ] A `fail_stale_processing` management command marks documents stuck in `processing` as `failed`, and runs at startup.
- [ ] `./start.sh` and `./test.sh` still work in development mode.

## Dependencies

- The `DJANGO_DEBUG` environment switch from "[D1] Environment-Based Settings and Secure Authentication".
- Migration files must be committed, because the container no longer generates them at startup.
- Existing `processing_status` field on receipts and bank statements.

## Code References

- [entrypoint.sh](../entrypoint.sh#L1-L8) - `makemigrations` on every start and `runserver` without `exec`.
- [requirements.txt](../requirements.txt) - Add pinned `gunicorn`.
- `gunicorn.conf.py` - New Gunicorn configuration file.
- [core/views.py](../core/views.py#L1185) - Background parse threads that a restart can cut off (also line 1278).
- [core/management/commands/prune_orphan_transactions.py](../core/management/commands/prune_orphan_transactions.py) - Existing management command to model `fail_stale_processing` on.
- [core/urls.py](../core/urls.py) - Register the health-check route.
