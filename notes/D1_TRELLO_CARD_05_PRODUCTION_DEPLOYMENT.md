# Trello Card: [D1] Production Deployment and Documentation

**List:** Current Sprint
**Labels:** Infrastructure, Documentation

## Description

Type: Feature
Points: 3
Owner: Jean Durand
Depends on: [D1] Production Docker Images, Nginx, and Compose, [D1] Oracle Cloud Server, Domain, and HTTPS Setup

Description:

Put the hardened application live on the provisioned server and make the process repeatable. The repository is cloned onto the server, production secrets live in a protected `.env.prod` that never enters git, and a single deploy script pulls, builds, starts the stack, and confirms the health check before reporting success.

A `DEPLOYMENT.md` guide documents the architecture, first-time setup, deploy, rollback, and CloudBeaver access over an SSH tunnel, so any team member can redeploy before the final demo.

## Acceptance Criteria

- [ ] The repository is cloned to `/srv/expense-tracker` using a read-only GitLab deploy token.
- [ ] `.env.prod` exists on the server with freshly generated secrets, is owned by `deploy`, and has `chmod 600`.
- [ ] `deploy/deploy.sh` pulls, builds, starts the stack, and fails loudly if `/api/health/` does not return `200`.
- [ ] Database migrations are applied automatically before Gunicorn accepts traffic.
- [ ] `http://<domain>` redirects to HTTPS and `https://<domain>/api/health/` returns `200`.
- [ ] A user can register, log in, upload a statement larger than 1 MB, and open the uploaded document on the live site.
- [ ] Ports `8978`, `8000`, and `5433` time out from the internet; only 22, 80, and 443 are open.
- [ ] `https://<domain>/admin/` and `/media/` are not served.
- [ ] CloudBeaver is reachable only through `ssh -L 8978:127.0.0.1:8978` with the `admin` profile started.
- [ ] `docker compose stop web` shows Gunicorn handling `SIGTERM` and exiting within the grace period.
- [ ] Responses carry Cloudflare headers, and the Nginx access log shows real visitor IPs.
- [ ] A scanned receipt upload completes without a Cloudflare 524 timeout.
- [ ] A rollback to the previous commit is documented and tested once.
- [ ] `DEPLOYMENT.md` covers architecture, environment variables, first-time setup, deploy, rollback, CloudBeaver access, Cloudflare settings, and certificate renewal, and is linked from the README.
- [ ] The README architecture diagram no longer shows CloudBeaver as user-facing.

## Dependencies

- The three application cards (settings and authentication, Gunicorn and health check, production images and compose) merged to the deployed branch.
- Provisioned server with Docker, DNS, and a valid origin certificate.
- `git.cs.sun.ac.za` reachable from the Oracle instance; otherwise the source is copied with `rsync`.
- The pre-deploy backup step needs the script from "[D7] Automated PostgreSQL Backups" and can be added once that card is done.

## Code References

- `deploy/deploy.sh` - New deploy script: pull, build, start, and health-check poll.
- `docker-compose.prod.yml` - New production stack from "[D1] Production Docker Images, Nginx, and Compose".
- `.env.prod.example` - New template listing every production key without values.
- `DEPLOYMENT.md` - New deployment guide.
- [README.md](../README.md#L269-L321) - Mermaid architecture diagram that shows CloudBeaver as user-facing.
- [README.md](../README.md#L135-L168) - CloudBeaver instructions that need a production note.
