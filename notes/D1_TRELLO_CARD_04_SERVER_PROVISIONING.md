# Trello Card: [D1] Oracle Cloud Server, Domain, and HTTPS Setup

**List:** Current Sprint
**Labels:** Infrastructure, Environment

## Description

Type: Feature
Points: 3
Owner: Jean Durand
Depends on: None

Description:

Provision and lock down the server that will host the live application. An Oracle Cloud Free Tier Ampere A1 (arm64) instance runs Ubuntu 24.04 with Docker, reachable only over SSH and through Cloudflare.

The purchased domain is registered with Cloudflare Registrar, so DNS is hosted on Cloudflare and the site is served through the Cloudflare proxy. This also delivers the D1 CDN stretch goal. Nginx on the server still terminates TLS with a Let's Encrypt certificate, so Cloudflare runs in Full (strict) mode and the proxy can be switched off in an emergency without breaking HTTPS.

## Acceptance Criteria

- [ ] A `VM.Standard.A1.Flex` instance (2 OCPU, 12 GB RAM, boot volume of at least 50 GB) runs Ubuntu 24.04 arm64 with a reserved public IP.
- [ ] The OCI security list allows inbound `22`, and `80`/`443` from Cloudflare's published IP ranges only.
- [ ] The host firewall accepts 80 and 443 and the rules persist across a reboot.
- [ ] SSH accepts key authentication only, root login is disabled, and `fail2ban` and `unattended-upgrades` are active.
- [ ] A dedicated `deploy` user exists in the `docker` group.
- [ ] Docker Engine and the compose plugin are installed with default log rotation.
- [ ] The host firewall, OS hardening, and Docker steps are captured in `deploy/bootstrap.sh`.
- [ ] The domain has a proxied `A` record for the apex and a proxied `CNAME` for `www`, with DNSSEC enabled.
- [ ] A Let's Encrypt certificate for the apex and `www` is issued with the Cloudflare DNS-01 challenge, and `certbot renew --dry-run` succeeds.
- [ ] Cloudflare is set to Full (strict) with Always Use HTTPS, a minimum of TLS 1.2, and a cache bypass rule for `/api/*`.
- [ ] Rocket Loader and automatic Web Analytics injection are off so they do not conflict with the Content Security Policy.
- [ ] A Cloudflare rate-limiting rule covers `/api/token/`.
- [ ] Oracle's idle-instance reclamation policy is checked and the outcome is recorded.

## Dependencies

- Oracle Cloud Free Tier account with Ampere A1 capacity available in the chosen region.
- Purchased domain in Cloudflare Registrar.
- Cloudflare API token scoped to DNS edit on this zone only.
- An SSH key pair for the `deploy` user.

## Code References

- `deploy/bootstrap.sh` - New script that reproduces the host firewall, OS hardening, and Docker installation.
- `capitec++/nginx/cloudflare-realip.conf` - New file from "[D1] Production Docker Images, Nginx, and Compose" that must list the same Cloudflare IP ranges as the OCI security list.
- [notes/SPAT-3-sprint-3-deliverables.md](SPAT-3-sprint-3-deliverables.md) - D1 requirements and the Cloudflare stretch goal.
