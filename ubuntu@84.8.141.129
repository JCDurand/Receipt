#!/bin/bash
# Prepares a new Oracle Cloud Ubuntu 24.04 server for the app: host firewall,
# OS hardening, Docker, and the tools for certificates and backups.
# Safe to run again. See DEPLOYMENT.md for the steps before and after it.
#
#   sudo deploy/bootstrap.sh
set -euo pipefail

DEPLOY_USER=deploy
APP_DIR=/srv/expense-tracker
BACKUP_DIR=/mnt/data/backups/expense-tracker
TIMEZONE=Africa/Johannesburg

[ "$(id -u)" = 0 ] || { echo "Run this script with sudo." >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "==> Updating the system"
apt-get update
apt-get -y upgrade
apt-get -y install ca-certificates curl git fail2ban unattended-upgrades \
    iptables-persistent netfilter-persistent \
    certbot python3-certbot-dns-cloudflare rclone

echo "==> SSH: keys only, no root login"
# The first value sshd reads wins, hence a name that sorts before the others
cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
sshd -t
systemctl reload ssh

echo "==> fail2ban for SSH"
cat > /etc/fail2ban/jail.local <<'CONF'
[sshd]
enabled = true
maxretry = 5
findtime = 10m
bantime = 1h
CONF
systemctl enable fail2ban
systemctl restart fail2ban

echo "==> Automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
systemctl enable --now unattended-upgrades

echo "==> Time zone"
timedatectl set-timezone "$TIMEZONE"

echo "==> The $DEPLOY_USER user"
id "$DEPLOY_USER" > /dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"

# The same keys as the user who ran this script, unless it already has its own
deploy_home=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)
admin_keys=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)/.ssh/authorized_keys
if [ ! -s "$deploy_home/.ssh/authorized_keys" ] && [ -s "$admin_keys" ]; then
    install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$deploy_home/.ssh"
    install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$admin_keys" "$deploy_home/.ssh/authorized_keys"
fi

install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$BACKUP_DIR"

echo
echo "==> Done. Check these:"
timedatectl | grep -E 'Time zone|synchronized'
fail2ban-client status sshd | grep -E 'Currently banned' || true
docker --version
docker compose version
echo "Open a second terminal and confirm 'ssh $DEPLOY_USER@<server ip>' works before closing this one."
