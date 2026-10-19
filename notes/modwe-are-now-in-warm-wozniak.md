# Sprint 3 — Hardening, Deployment (D1) and Backups (D7)

## Context

Sprint 3 (ends Fri 16 Oct 2026) requires the Smart Expense Tracker to move from the local Docker stack to a live HTTPS site on an Oracle Cloud Free Tier instance behind a purchased domain, with Gunicorn behind Nginx, env-based secrets, persistent media, migrations, a health check, private CloudBeaver, deployment docs (D1) and automated PostgreSQL backups (D7).

The current stack is development-only. What I found that blocks or endangers a public deployment:

| Area | Current state | File |
|---|---|---|
| Django secrets/debug | Hardcoded `SECRET_KEY`, `DEBUG = True`, localhost-only `ALLOWED_HOSTS` | `config/settings.py:25-30` |
| CORS | `CORS_ALLOW_ALL_ORIGINS = True` with `CORS_ALLOW_CREDENTIALS = True` | `config/settings.py:212,242` |
| App server | `runserver`, started without `exec` (no SIGTERM → no graceful shutdown) | `entrypoint.sh:8` |
| Migrations | `makemigrations` runs at every container start | `entrypoint.sh:3` |
| Exposed ports | Django `8000`, Postgres `5433`, CloudBeaver `8978` (default login `admin`/`dbeaver`) all published | `docker-compose.yml` |
| Source mount | `.:/app` bind mount; media lives in the repo checkout | `docker-compose.yml:12` |
| Nginx | HTTP only, no `client_max_body_size` (1 MB default vs 50 MB app limit), no timeouts, headers or rate limits | `capitec++/nginx/default.conf` |
| Frontend API URL | Falls back to `http://localhost:8000/api`; no build-time value set | `capitec++/src/api/axiosClient.js:7`, `capitec++/src/utils/api.js:3` |
| Uploaded documents | Linked as `http://localhost:8000/media/...`, served only when `DEBUG`, with no auth check | `StatementDetail.jsx:116`, `UploadDetail.jsx:295`, `FileListTable.jsx:86`, `config/urls.py:34` |
| Token refresh | Frontend posts `/token/refresh/`, route is `api/token/refresh` (no slash) → 404, so sessions die after 15 min. `BLACKLIST_AFTER_ROTATION` is set but the blacklist app is not installed, and the rotated refresh token is never stored | `config/urls.py:29`, `axiosClient.js:58`, `AuthContext.jsx:75` |
| Abuse controls | No throttling on login, registration or the OCR upload endpoints | `config/settings.py:214` |
| Secrets in git | `.env` is tracked (dummy values) despite `*.env` in `.gitignore` | `.env` |
| Image | Runs as root, `uv:latest` unpinned, ships tests/notes/coverage | `Dockerfile` |

Decisions made: **Ampere A1 (arm64)** instance, **git pull + build on server**, backups **local + off-site (Oracle Object Storage)**. The domain is registered with **Cloudflare Registrar**, so DNS is necessarily hosted on Cloudflare; the site is served through the Cloudflare proxy (this also delivers the D1 CDN stretch goal). The origin still terminates TLS on Nginx with a publicly trusted Let's Encrypt certificate (DNS-01 via the Cloudflare API), so Cloudflare runs in Full (strict) mode and the proxy can be switched off in an emergency without breaking HTTPS. Local dev (`docker-compose.yml`, `start.sh`, CloudBeaver, CI) keeps working unchanged apart from the `.env` rename.

---

## Phase 1 — Application hardening (repo changes)

### 1.1 Env-driven settings — `config/settings.py`
Keep a single settings file; read everything from the environment with dev-safe defaults only where harmless.
- `SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]` when not debug; dev fallback only if `DJANGO_DEBUG=1`.
- `DEBUG = os.environ.get("DJANGO_DEBUG") == "1"` (default **off**). Set `DJANGO_DEBUG=1` in the dev `docker-compose.yml` and `.gitlab-ci.yml`.
- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` from comma-separated env vars; delete `CORS_ALLOW_ALL_ORIGINS = True` (enable it only under `DEBUG`). Production is same-origin so CORS lists can be empty.
- `MEDIA_ROOT` from env (compose already passes `MEDIA_ROOT` but settings ignores it).
- When not debug: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `JWT_AUTH_SECURE = True`, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY = "same-origin"`. HTTPS redirect and HSTS are done in Nginx (keeps the internal HTTP health check simple).
- DRF: JSON renderer only when not debug (no browsable API → no need to serve Django static files); add `DEFAULT_THROTTLE_CLASSES`/`RATES` (`anon`, `user`, plus scoped `auth` and `upload`), `NUM_PROXIES = 1`.
- Add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS` (its migrations ship with the package) so rotation actually invalidates old refresh tokens.
- `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` aligned with the existing `MAX_UPLOAD_SIZE`.
- Add a root logger at `WARNING` to the existing `LOGGING` dict so Django/Gunicorn errors reach `docker logs`.

Verify with `python manage.py check --deploy` and resolve what it reports.

### 1.2 Health check — `core/views.py`, `core/urls.py`
`GET /api/health/`: `AllowAny`, no throttle, runs `connection.ensure_connection()`; returns `200 {"status":"ok","database":"ok"}` or `503`. Add a test in `core/tests.py`.

### 1.3 Authenticated document download
Uploaded statements/receipts are financial documents and must not be world-readable.
- New view `documents/<pk>/file/` in `core/views.py`: resolve the `BankStatement`/`Receipt` scoped to `request.user` (same ownership filters the existing views use), return `FileResponse(default_storage.open(file_path))`.
- Frontend: replace the three `window.open("http://localhost:8000/media/...")` calls with a small helper in `capitec++/src/utils/` that fetches via `axiosClient` (`responseType: "blob"`) and opens an object URL.
- Nginx never exposes `/media/`; the dev-only `static()` route in `config/urls.py` can stay.

### 1.4 Auth fixes and throttles
- `config/urls.py:29`: add the trailing slash → `api/token/refresh/`.
- `axiosClient.js` and `AuthContext.jsx`: store `response.data.refresh` after a refresh (rotation is on).
- Apply `ScopedRateThrottle` scope `auth` to login/refresh/`register_user`, and `upload` to `UnifiedDocumentUploadView`, `DocumentParseView`, `upload_statement`.
- Known residual risk, documented not fixed this sprint: JWTs in `localStorage`. Mitigated by a strict CSP (1.6).

### 1.5 Gunicorn — `requirements.txt`, new `gunicorn.conf.py`, `entrypoint.sh`
- Add pinned `gunicorn` to `requirements.txt`; pin `psycopg[binary]`.
- `gunicorn.conf.py`: `bind 0.0.0.0:8000`, `worker_class = "gthread"`, `workers = int(env WEB_CONCURRENCY, 3)`, `threads = int(env GUNICORN_THREADS, 4)`, `timeout = 95` (synchronous OCR in `DocumentParseView`; must stay under Cloudflare's 100 s origin response limit, otherwise users get a 524), `graceful_timeout = 30`, `keepalive = 5`, `max_requests = 1000` + jitter (parser memory growth), access/error logs to stdout, `forwarded_allow_ips = "*"` (only reachable on the internal network).
- `entrypoint.sh`: drop `makemigrations`; `migrate --noinput`; then `exec gunicorn config.wsgi:application -c gunicorn.conf.py` when not debug, `exec python manage.py runserver` when `DJANGO_DEBUG=1`. `exec` makes Gunicorn PID 1 so `docker stop` delivers SIGTERM.
- Background parse threads (`core/views.py:1185,1278`) can be cut off by a restart, leaving rows stuck in `processing`. Add management command `core/management/commands/fail_stale_processing.py` (next to the existing `prune_orphan_transactions.py`) that marks such rows `failed`, and call it from `entrypoint.sh` before Gunicorn starts.

### 1.6 Images
- `Dockerfile`: pin the `uv` image tag, create and switch to a non-root user, `chown` the media dir, remove `curl` only if the healthcheck uses Python instead. Extend `.dockerignore` with `notes/`, `assets/`, `parser/tests/`, `tmp/`, `staticfiles/`, `coverage_report.txt`, `*.md`.
- `capitec++/Dockerfile`: `ARG VITE_API_BASE_URL=/api` → `ENV` before `npm run build`; copy an Nginx **template** selected by build arg so dev keeps `nginx/default.conf` and prod gets the new one.
- New `capitec++/nginx/prod.conf.template` (uses the nginx image's `envsubst` on `${DOMAIN}`):
  - `:80` → redirect everything to HTTPS (no ACME path needed; certificates use DNS-01).
  - `:443 ssl http2`, certs from `/etc/letsencrypt/live/${DOMAIN}/`, TLS 1.2/1.3, `server_tokens off`.
  - Default catch-all server returning `444` for unknown hosts.
  - Real client IP behind Cloudflare: new `capitec++/nginx/cloudflare-realip.conf` with `set_real_ip_from` for each published Cloudflare range and `real_ip_header CF-Connecting-IP`. Without this every visitor appears as a Cloudflare IP and the rate limits and DRF throttles would lump all users together.
  - `client_max_body_size 50m` (under Cloudflare Free's 100 MB cap); `proxy_read_timeout 100s`; forward `Host`, `X-Forwarded-Proto`, and `X-Forwarded-For $remote_addr` (overwritten, not appended, so `NUM_PROXIES = 1` resolves to the real client).
  - Only `/api/` is proxied — `/admin/` stays unreachable from the internet (use `manage.py` over SSH).
  - `limit_req` zones: tight on `/api/token/` and `/api/register/`, moderate on the rest of `/api/`.
  - Headers: HSTS, `X-Content-Type-Options`, `X-Frame-Options DENY`, `Referrer-Policy`, CSP (`default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-src blob:; object-src 'none'; frame-ancestors 'none'`) — the frontend loads no external origins.
  - gzip; long cache for hashed `/assets/`, `no-cache` for `index.html`.

### 1.7 Production compose — new `docker-compose.prod.yml` (standalone, not an override)
- `web`: no `ports`, no source bind mount, `env_file: .env.prod`, named volume `media:/app/document_storage`, `stop_grace_period: 40s`, healthcheck hitting `/api/health/`, `restart: unless-stopped`.
- `frontend`: ports `80:80`, `443:443`; mounts `/etc/letsencrypt:ro`; `DOMAIN` env; depends on `web` healthy.
- `db`: no `ports`, named volume, existing healthcheck.
- `dbeaver`: behind `profiles: ["admin"]`, bound to `127.0.0.1:8978` only, credentials **required** from env (no defaults). Reached with `ssh -L 8978:127.0.0.1:8978`. Not started by default.
- Log rotation (`json-file`, `max-size: 10m`, `max-file: 3`) on every service.

### 1.8 Secrets hygiene
- `git rm --cached .env`; add `.env.example` (dev) and `.env.prod.example` (all prod keys, no values). Update README step for dev (`cp .env.example .env`). Tell the team — this changes their setup step.
- The committed `SECRET_KEY` and `password` DB password are burned: production uses freshly generated values that never enter git.

---

## Phase 2 — Server provisioning and host hardening (Oracle Cloud)

1. **Instance**: `VM.Standard.A1.Flex`, Ubuntu 24.04 arm64, 2 OCPU / 12 GB (leaves headroom in the free allowance), boot volume ≥ 50 GB, SSH key only. Reserve a **public IP** so DNS survives a stop/start.
2. **OCI network**: security list / NSG ingress only `22` (restricted to your IP range if practical) and `80`/`443` **from Cloudflare's published IP ranges only**, so the origin cannot be reached by bypassing Cloudflare. Nothing else. (Emergency fallback if Cloudflare misbehaves before the demo: open 80/443 to `0.0.0.0/0` and switch the DNS record to "DNS only" — the Let's Encrypt cert keeps HTTPS valid.)
3. **Host firewall**: Oracle's Ubuntu images ship restrictive iptables rules — add ACCEPT for 80/443 and persist with `netfilter-persistent`. Note Docker-published ports bypass ufw, which is why prod compose publishes only 80/443 (+ loopback CloudBeaver).
4. **OS**: `apt upgrade`, `unattended-upgrades`, `fail2ban` (sshd jail), `sshd`: `PasswordAuthentication no`, `PermitRootLogin no`. Dedicated `deploy` user in the `docker` group. Set timezone; confirm NTP.
5. **Docker**: Engine + compose plugin from Docker's apt repo; `daemon.json` default log rotation.
6. **Cloudflare DNS** (dashboard, zone already exists via Registrar): proxied (orange-cloud) `A` record for the apex → reserved IP and a proxied `CNAME www` → apex. Enable DNSSEC (one click for Registrar domains). SSH to the server by IP — the proxied hostname does not carry SSH, and a "DNS only" record would reveal the origin address.
7. **Origin TLS**: create a Cloudflare API token scoped to *Zone → DNS → Edit* for this zone only; store it at `/etc/letsencrypt/cloudflare.ini` (`chmod 600`, root). Install `certbot` + `python3-certbot-dns-cloudflare`; `certbot certonly --dns-cloudflare --dns-cloudflare-credentials … -d <domain> -d www.<domain> --deploy-hook "docker compose -f … exec frontend nginx -s reload"`. Check with `certbot renew --dry-run`. No inbound port is needed for issuance or renewal.
8. **Cloudflare zone settings**:
   - SSL/TLS mode **Full (strict)**; Always Use HTTPS on; minimum TLS 1.2. HSTS stays in Nginx only (avoid setting it in both places).
   - Cache rule: **bypass cache for `/api/*`**. Default caching already covers the hashed `/assets/*` files; `index.html` is sent `no-cache` by Nginx.
   - Leave **Rocket Loader** and automatic **Web Analytics injection off** — both inject scripts that the CSP in 1.6 would block (or that would break the React bundle).
   - One free rate-limiting rule on `/api/token/` as an outer layer in front of the Nginx/DRF limits.
   - Optional extra lock-down: Authenticated Origin Pulls (Nginx `ssl_verify_client` with Cloudflare's origin-pull CA).
   - Cloudflare Free limits to respect: 100 MB request body, 100 s origin response time (reflected in 1.5/1.6).
9. **Idle reclamation**: Oracle may reclaim idle Always Free instances; confirm the current policy and, if it applies, converting the tenancy to Pay-As-You-Go (still free within limits) avoids it.

Capture steps 3–5 in `deploy/bootstrap.sh` so the box is reproducible.

---

## Phase 3 — Deployment

- Clone to `/srv/expense-tracker` with a **read-only GitLab deploy token** (first confirm `git.cs.sun.ac.za` is reachable from the instance; fallback is `rsync` of the source from a laptop, same script otherwise).
- `/srv/expense-tracker/.env.prod`, `chmod 600`, owned by `deploy`: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DOMAIN`, `POSTGRES_*`, `DATABASE_HOST=db`, `DATABASE_PORT=5432`, `MEDIA_ROOT`, `PYTHONPATH=parser/`, `LOGLEVEL=INFO`, `WEB_CONCURRENCY`, `DBEAVER_USER/PASSWORD`.
- New `deploy/deploy.sh`: `git pull --ff-only` → `docker compose -f docker-compose.prod.yml build` → `up -d` → poll `https://$DOMAIN/api/health/` until 200 or fail loudly → `docker image prune -f`. Migrations run in the entrypoint before Gunicorn accepts traffic. A pre-deploy backup (Phase 4 script) runs first.
- Rollback: `git checkout <previous sha>` + `deploy.sh`; restore DB from the pre-deploy dump if a migration must be undone.
- Docs: new `DEPLOYMENT.md` (architecture, env vars, first-time setup, deploy, rollback, CloudBeaver via SSH tunnel, Cloudflare zone settings and how to refresh the Cloudflare IP ranges in the OCI security list and `cloudflare-realip.conf`, cert renewal, backup/restore) linked from `README.md`; update the README mermaid diagram so CloudBeaver is no longer shown as user-facing.

---

## Phase 4 — Backups (D7)

- `deploy/backup.sh`: `docker compose exec -T db pg_dump -Fc` → `/var/backups/expense-tracker/db-<UTC timestamp>.dump`; tar of the `media` volume; `chmod 600`; fail non-zero on any error; verify the dump with `pg_restore --list`.
- Retention: 7 daily, 4 weekly locally.
- Off-site: `rclone` (or `oci` CLI) sync to a **private Oracle Object Storage bucket** using a credential scoped to that bucket only, with a bucket lifecycle rule (e.g. 30 days). Config file `chmod 600`.
- Schedule: systemd timer (or cron) nightly at 02:00 SAST, logging to journald; `deploy.sh` also calls it before each deploy.
- `deploy/restore.sh` + a documented restore drill into a scratch database, done once before the demo.

---

## Suggested order

1. Phase 1.1–1.5 + 1.8 (app hardening, Gunicorn, health check) — testable locally and in CI.
2. Phase 1.6–1.7 (prod images/compose) — smoke-test locally with a self-signed cert.
3. Phase 2 (server, Cloudflare DNS and zone settings, origin certificate).
4. Phase 3 (first deploy, docs).
5. Phase 4 (backups, restore drill).

## Verification

- **Local**: `./start.sh` and `./test.sh` still work in dev; `docker compose exec web python manage.py check --deploy` clean with prod env; CI pipeline green.
- **Prod smoke test locally**: bring up `docker-compose.prod.yml` with a self-signed cert; register, log in, upload a PDF > 1 MB, open the document, wait > 15 min and confirm the session refreshes.
- **Live (matches the D1 demo)**:
  - `curl -I http://<domain>` → 301 to HTTPS; `curl https://<domain>/api/health/` → 200 JSON.
  - Log in through the browser over HTTPS; upload and view a statement.
  - `curl -m 5 http://<domain>:8978`, `:8000`, `:5433` → all time out; `nmap` from outside shows only 22/80/443.
  - `https://<domain>/admin/` and `/media/...` → not served.
  - `docker compose stop web` logs Gunicorn "Handling signal: term" and exits within the grace period.
  - Response headers include `server: cloudflare` and `cf-ray`; `/assets/*` shows `cf-cache-status: HIT` on a repeat request, `/api/*` shows `DYNAMIC`/`BYPASS`.
  - `curl -m 5 -k https://<origin IP>` from a non-Cloudflare address times out (origin locked to Cloudflare).
  - Nginx access log shows real visitor IPs, not Cloudflare addresses.
  - SSL Labs grade A on the hostname; security headers present and no CSP violations in the browser console.
  - Hammer `/api/token/` → 429, while a second client on another IP is unaffected.
  - Upload a scanned (OCR) receipt and confirm it completes without a Cloudflare 524.
- **Backups (D7 demo)**: run `deploy/backup.sh` manually, show the dump locally and in the bucket, `systemctl list-timers`, and the restore drill result.
