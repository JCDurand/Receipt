# Trello Card: Live CloudBeaver Database Visibility

## Description

Deliver D8 live database visibility as part of the standard application stack. The client can inspect PostgreSQL through a browser-based DBeaver experience without installing desktop software or manually configuring a local machine.

CloudBeaver starts with Docker, waits for PostgreSQL to become healthy, keeps its workspace persistent, and is opened automatically by the project startup script.

## Acceptance Criteria

- [ ] `./start.sh` starts the application, PostgreSQL, and CloudBeaver together.
- [ ] CloudBeaver is available at `http://localhost:8978/`.
- [ ] PostgreSQL is reachable inside the Docker network using host `db` and port `5432`.
- [ ] PostgreSQL remains available to host tools on `localhost:5433`.
- [ ] CloudBeaver workspace data persists through container restarts.
- [ ] Credentials can be configured with `DBEAVER_USER` and `DBEAVER_PASSWORD`.
- [ ] The README documents login, connection, and live inspection steps.

## Dependencies

- Docker and Docker Compose installed.
- A healthy PostgreSQL `db` service.
- Valid `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` values in `.env`.
- The application startup script must be executable.

## Code References

- [docker-compose.yml](../docker-compose.yml#L31-L48) - CloudBeaver image, port, volume, credentials, and database dependency.
- [start.sh](../start.sh#L1-L18) - Starts the stack and opens the application and CloudBeaver.
- [README.md](../README.md#L135-L168) - User setup and PostgreSQL connection instructions.
