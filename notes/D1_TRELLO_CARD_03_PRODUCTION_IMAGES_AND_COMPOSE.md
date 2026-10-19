# Trello Card: [D1] Production Docker Images, Nginx, and Compose

**List:** Current Sprint
**Labels:** Infrastructure, Environment

## Description

Type: Feature
Points: 3
Owner: Jean Durand
Depends on: [D1] Environment-Based Settings and Secure Authentication, [D1] Gunicorn Integration and Health Check

Description:

Package the application for production without changing the development stack. The current compose file publishes the Django, PostgreSQL, and CloudBeaver ports, mounts the source tree into the container, and Nginx serves HTTP only with a 1 MB upload limit.

A separate `docker-compose.prod.yml` publishes only ports 80 and 443, stores uploaded documents in a named volume, and keeps CloudBeaver private. A production Nginx configuration terminates HTTPS, proxies only the API, and adds security headers and rate limits. The existing `docker-compose.yml` and `./start.sh` remain the development workflow.

## Acceptance Criteria

- [ ] The backend image runs as a non-root user and uses a pinned `uv` base image tag.
- [ ] `.dockerignore` excludes notes, assets, parser tests, temporary files, and coverage output.
- [ ] The frontend image builds with `VITE_API_BASE_URL=/api` and selects the development or production Nginx configuration by build argument.
- [ ] The production Nginx configuration redirects HTTP to HTTPS and serves TLS 1.2 and 1.3 with the Let's Encrypt certificate.
- [ ] Requests for unknown hostnames are dropped.
- [ ] Uploads up to 50 MB are accepted and the proxy timeout is 100 seconds.
- [ ] Only `/api/` is proxied to Django; `/admin/` and `/media/` are not reachable.
- [ ] The real client IP is restored from Cloudflare's `CF-Connecting-IP` header for Cloudflare's published IP ranges.
- [ ] Nginx rate limits `/api/token/` and `/api/register/` more tightly than the rest of the API.
- [ ] Responses include HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a Content Security Policy, with no CSP violations in the browser console.
- [ ] Hashed `/assets/` files are cached long term and `index.html` is sent with `no-cache`.
- [ ] `docker-compose.prod.yml` publishes only ports 80 and 443, with no source bind mount and a named volume for media.
- [ ] The `web` service has a health check on `/api/health/`, a 40 second stop grace period, and restarts automatically.
- [ ] CloudBeaver sits behind an `admin` profile, is bound to `127.0.0.1:8978`, and requires credentials from the environment with no defaults.
- [ ] Every service has log rotation configured.
- [ ] `.env.prod.example` lists every production key without values.
- [ ] The production stack passes a local smoke test with a self-signed certificate: register, log in, upload a PDF larger than 1 MB, and open the document.

## Dependencies

- Environment-driven settings and the authenticated document endpoint from "[D1] Environment-Based Settings and Secure Authentication".
- Gunicorn and `/api/health/` from "[D1] Gunicorn Integration and Health Check".
- Cloudflare's published IP ranges for the real-IP configuration.
- This card blocks "[D1] Production Deployment and Documentation".

## Code References

- [Dockerfile](../Dockerfile#L8) - Runs as root with an unpinned `uv:latest` image.
- [capitec++/Dockerfile](../capitec++/Dockerfile#L1-L10) - Frontend build with no `VITE_API_BASE_URL` build argument.
- [capitec++/nginx/default.conf](../capitec++/nginx/default.conf#L5-L23) - HTTP-only proxy with no upload size limit, timeouts, or headers; stays as the development configuration.
- [capitec++/src/api/axiosClient.js](../capitec++/src/api/axiosClient.js#L7) - API base URL fallback to localhost; also in `capitec++/src/utils/api.js` line 3.
- [docker-compose.yml](../docker-compose.yml#L9-L51) - Published Django, CloudBeaver, and PostgreSQL ports, and the source bind mount.
- `capitec++/nginx/prod.conf.template` - New production Nginx configuration.
- `capitec++/nginx/cloudflare-realip.conf` - New list of Cloudflare IP ranges for real client IPs.
- `docker-compose.prod.yml` - New standalone production stack.
- `.env.prod.example` - New production environment template.
