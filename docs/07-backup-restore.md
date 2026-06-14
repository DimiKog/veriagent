# SQLite Backup and Restore

Operator guide for backing up and recovering the VeriAgent production SQLite database on the Linux VM.

VeriAgent stores audit events, agent registry metadata, batches, and anchor records in a single SQLite file (default: `/opt/veriagent/backend/data/veriagent.db`, overridable via `VERIAGENT_DB_PATH` in `backend/.env`). Before v1.0, schedule regular backups and rehearse restore on a non-production copy when possible.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| `sqlite3` CLI | Used for online-consistent `.backup` while the API runs |
| `gzip` | Compresses each backup artifact |
| `systemctl` | Restore script stops/starts the `veriagent` systemd unit |
| Write access | `/opt/veriagent/backups/sqlite/` and the database directory |

Run backup and restore as a user that can read the database file and manage the service (typically `root` or a dedicated deploy user with sudo).

## Scripts

| Script | Purpose |
|--------|---------|
| [`scripts/backup_sqlite.sh`](../scripts/backup_sqlite.sh) | Hot backup via `sqlite3 ".backup"`, gzip, retention |
| [`scripts/restore_sqlite.sh`](../scripts/restore_sqlite.sh) | Stop service, emergency copy, restore, restart |

Both scripts resolve `VERIAGENT_DB_PATH` from `backend/.env` at the repo root (e.g. `/opt/veriagent/backend/.env` on the VM). If unset, they use `/opt/veriagent/backend/data/veriagent.db`.

Override the systemd unit name for restore with `VERIAGENT_SERVICE_NAME` (default: `veriagent`).

Make scripts executable once after deploy:

```bash
chmod +x /opt/veriagent/scripts/backup_sqlite.sh
chmod +x /opt/veriagent/scripts/restore_sqlite.sh
```

## Backup workflow

### Manual backup

```bash
sudo /opt/veriagent/scripts/backup_sqlite.sh
```

The script:

1. Locates the live database (`VERIAGENT_DB_PATH` or default path).
2. Runs `sqlite3 "$DB" ".backup '…'"` — **not** a raw `cp` — so the snapshot is consistent even while uvicorn holds the file open.
3. Compresses the result to `/opt/veriagent/backups/sqlite/veriagent-<UTC-timestamp>.db.gz`.
4. Deletes older gzip files, keeping the **14 most recent** backups.

Example output path:

```text
/opt/veriagent/backups/sqlite/veriagent-20260614T153045Z.db.gz
```

### Scheduled backup (cron)

Daily off-peak backup on the VM:

```bash
sudo crontab -e
```

```cron
15 3 * * * /opt/veriagent/scripts/backup_sqlite.sh >> /var/log/veriagent-backup.log 2>&1
```

Ensure `/opt/veriagent/backups/sqlite/` exists and is on durable disk (not tmpfs). Monitor `/var/log/veriagent-backup.log` or cron mail for failures.

### Verify a backup (optional)

With the API still running, inspect the gzip without restoring:

```bash
gunzip -c /opt/veriagent/backups/sqlite/veriagent-20260614T153045Z.db.gz \
  | sqlite3 /dev/stdin "SELECT COUNT(*) FROM audit_events;"
```

Adjust the table name if your schema differs; the goal is to confirm the file is readable SQLite.

## Restore workflow

**Restore replaces the live database.** Plan downtime: the API is unavailable while the service is stopped.

1. Identify the backup file (list newest first):

   ```bash
   ls -lt /opt/veriagent/backups/sqlite/veriagent-*.db.gz | head
   ```

2. Run restore with the **full path** to the chosen `.db.gz` file:

   ```bash
   sudo /opt/veriagent/scripts/restore_sqlite.sh \
     /opt/veriagent/backups/sqlite/veriagent-20260614T153045Z.db.gz
   ```

The restore script:

1. Stops `veriagent` (`systemctl stop veriagent`).
2. Copies the current database to `/opt/veriagent/backups/sqlite/emergency-<timestamp>-veriagent.db` if it exists.
3. Decompresses the selected backup over the live `VERIAGENT_DB_PATH`.
4. Starts `veriagent` and checks that the unit is active.

3. Confirm API health:

   ```bash
   curl -s https://veriagent.dimikog.org/health | jq .
   ```

4. Spot-check data (event count, recent batch) via API or SQLite on a **copy** of the restored file if needed.

### Roll back a bad restore

If the wrong backup was applied, stop the service and copy the emergency file back:

```bash
sudo systemctl stop veriagent
sudo cp /opt/veriagent/backups/sqlite/emergency-<timestamp>-veriagent.db \
  /opt/veriagent/backend/data/veriagent.db
sudo systemctl start veriagent
```

Use the emergency filename printed by the restore script.

## Operational notes

- **Hot vs cold:** Backup uses SQLite’s online backup API; restore requires a **stopped** service so the database file is not locked mid-write.
- **Secrets:** Backups contain application data (events, agent metadata, batch state). Treat `.db.gz` files like production data; restrict directory permissions (e.g. `chmod 700` on `backups/sqlite`).
- **Off-site copies:** Retention on the VM (14 files) protects against recent mistakes, not disk loss. Periodically copy backups to object storage or another host.
- **Anchoring:** Restoring to an earlier point may desync local batch/anchor state from Besu; document any on-chain reconciliation needed after a major rollback.
- **No API changes:** These scripts are operator tooling only; backend endpoints and behavior are unchanged.

## Related docs

- [Deployment guide](05-deployment.md) — VM layout, env vars, service restarts
- [Development log](02-devlog.md) — backup milestone entry
- [Threat model](06-threat-model.md) — operator trust and SQLite mutability assumptions
