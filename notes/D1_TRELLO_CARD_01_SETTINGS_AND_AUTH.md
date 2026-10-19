# Trello Card: [D1] Environment-Based Settings and Secure Authentication

**List:** Current Sprint
**Labels:** Backend, Frontend

## Description

Type: Feature
Points: 3
Owner: Jean Durand
Depends on: None

Description:

Remove the development-only assumptions from the Django configuration and the frontend so the application is safe to expose to the public internet. Secrets and `DEBUG` are currently hardcoded, CORS is open to every origin, uploaded financial documents are world-readable, and the frontend links to `http://localhost:8000`.

Settings become environment-driven with `DEBUG` off by default, document downloads require authentication, token refresh is repaired, and the login and upload endpoints are rate limited. Local development with `./start.sh` keeps working.

This card absorbs two existing cards: "Remove .env file from repository" and "[Backend] Auth token expires too quickly, user has to log in again frequently".

## Acceptance Criteria

- [ ] `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, CORS origins, and `MEDIA_ROOT` are read from the environment, with `DEBUG` off by default.
- [ ] `CORS_ALLOW_ALL_ORIGINS` is only enabled when `DJANGO_DEBUG=1`.
- [ ] Secure cookie, proxy SSL header, and content-type settings are applied when `DEBUG` is off.
- [ ] `python manage.py check --deploy` reports no issues with production environment values.
- [ ] Uploaded statements and receipts are downloaded through an authenticated endpoint scoped to the owning user.
- [ ] The frontend no longer contains hardcoded `http://localhost:8000/media/` links and opens documents through the authenticated endpoint.
- [ ] Token refresh works end to end: the route has a trailing slash, the rotated refresh token is stored, and the token blacklist app is installed.
- [ ] A session stays logged in past the 15 minute access-token lifetime.
- [ ] Login, token refresh, registration, and upload endpoints are rate limited and return `429` when the limit is exceeded.
- [ ] `.env` is removed from git tracking, `.env.example` is added, and the README setup step is updated.
- [ ] The team is told about the new setup step (`cp .env.example .env`).
- [ ] `./start.sh`, `./test.sh`, and the CI pipeline still pass with `DJANGO_DEBUG=1`.

## Dependencies

- None from other cards. This card blocks "[D1] Gunicorn Integration and Health Check" and "[D1] Production Docker Images, Nginx, and Compose".
- Leo Mischker currently owns the two absorbed cards, so agree who closes them.
- `DJANGO_DEBUG=1` must be set in the development `docker-compose.yml` and in `.gitlab-ci.yml`.

## Code References

- [config/settings.py](../config/settings.py#L25-L30) - Hardcoded `SECRET_KEY`, `DEBUG = True`, and localhost-only `ALLOWED_HOSTS`.
- [config/settings.py](../config/settings.py#L167) - `MEDIA_ROOT` that ignores the environment value passed by compose.
- [config/settings.py](../config/settings.py#L212-L242) - CORS credentials, DRF settings, JWT rotation settings, and `CORS_ALLOW_ALL_ORIGINS`.
- [config/urls.py](../config/urls.py#L28-L35) - Token refresh route without a trailing slash, and the debug-only media route.
- [capitec++/src/api/axiosClient.js](../capitec++/src/api/axiosClient.js#L58) - Refresh call that does not store the rotated refresh token.
- [capitec++/src/components/AuthContext.jsx](../capitec++/src/components/AuthContext.jsx#L75) - Second refresh call with the same problem.
- [capitec++/src/pages/StatementDetail.jsx](../capitec++/src/pages/StatementDetail.jsx#L116) - Hardcoded media URL; also in `UploadDetail.jsx` line 295 and `FileListTable.jsx` line 86.
- `.env.example` - New development template replacing the tracked `.env`.
