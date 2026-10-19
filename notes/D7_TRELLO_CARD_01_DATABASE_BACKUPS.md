# Trello Card: [D7] Automated PostgreSQL Backups

**List:** Current Sprint
**Labels:** Infrastructure, Data

## Description

Type: Feature
Points: 3
Owner: Jean Durand
Depends on: [D1] Production Deployment and Documentation

Description:

Protect the live deployment against data loss. A backup script takes a PostgreSQL snapshot and an archive of the uploaded documents every night, verifies the dump, and keeps a rolling set of copies on the server.

Copies are also synced to a private Oracle Object Storage bucket, which delivers the D7 off-site stretch goal, so a failed server does not take the backups with it. A restore script and a rehearsed restore drill prove the backups can be used.

## Acceptance Criteria

- [ ] `deploy/backup.sh` writes a timestamped `pg_dump -Fc` snapshot to `/var/backups/expense-tracker/` with `chmod 600`.
- [ ] The script also archives the `media` volume containing uploaded documents.
- [ ] Each dump is verified with `pg_restore --list`, and the script exits non-zero on any failure.
- [ ] Local retention keeps 7 daily and 4 weekly backups.
- [ ] Backups are synced to a private Oracle Object Storage bucket using a credential scoped to that bucket only.
- [ ] The bucket has a lifecycle rule that removes old backups (30 days).
- [ ] A systemd timer runs the backup nightly at 02:00 SAST and logs to journald.
- [ ] `deploy/deploy.sh` runs a backup before each deployment.
- [ ] `deploy/restore.sh` restores a dump, and a restore drill into a scratch database has been completed once.
- [ ] `DEPLOYMENT.md` documents the schedule, storage locations, and the restore procedure.
- [ ] A manual run of `deploy/backup.sh` can be shown in the terminal for the D7 demo, together with `systemctl list-timers`.

## Dependencies

- Live production stack with the `db` service and the `media` volume.
- Oracle Object Storage bucket and a credential limited to it.
- `rclone` or the `oci` CLI installed on the server.

## Code References

- `deploy/backup.sh` - New backup script: database dump, media archive, verification, retention, and off-site sync.
- `deploy/restore.sh` - New restore script used for the restore drill.
- `deploy/deploy.sh` - Calls the backup script before each deployment.
- `DEPLOYMENT.md` - Backup and restore section.
- [notes/SPAT-3-sprint-3-deliverables.md](SPAT-3-sprint-3-deliverables.md) - D7 requirements, stretch goal, and demo steps.
