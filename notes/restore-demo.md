# Database Restore Demo

Run on the production server as `deploy`. Run steps 2–6 in the same shell, because `$BEFORE` only exists in that session.

Before the demo, deploy the `deploy/restore.sh` and `deploy/lib.sh` changes. Without them the demo dump cannot be restored and the scripts look for backups in the wrong folder.

## 1. Show what's in the live database now

```bash
cd /srv/expense-tracker
```

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT username FROM core_user;" -c "SELECT count(*) AS transactions FROM core_transaction;"'
```

## 2. Take a backup and remember its file name

```bash
deploy/backup.sh
```

```bash
BEFORE=$(ls -1 /mnt/data/backups/expense-tracker/daily/db-*.dump | tail -n 1); echo "$BEFORE"
```

## 3. Restore drill (the live site isn't touched)

Restores the newest backup into a scratch database, prints what's in it and drops it again.

```bash
deploy/restore.sh drill
```

## 4. Replace the live site with the demo dataset

Type `restore` when asked. The script takes a backup of the current state first.

```bash
deploy/restore.sh live demo/newspeak-demo.dump
```

## 5. Show the result

Rerun the query from step 1. It should now list `newspeak_demo` and 1956 transactions.

Log in on the site with:

- **Username:** `newspeak_demo`
- **Password:** `NewspeakDemo2026!`

## 6. Roll back to the backup from step 2

```bash
deploy/restore.sh live "$BEFORE"
```

If you're in a new shell, find the file by its timestamp:

```bash
ls /mnt/data/backups/expense-tracker/daily/
```
