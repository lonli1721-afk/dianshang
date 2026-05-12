# Data Lifecycle And Disk Policy

This project must not depend on manual SSH cleanup to stay online. Production disk usage is governed by risk-tiered backups, dry-run cleanup, and explicit retention windows.

## Goals

- Keep the system disk below 70% during normal operation.
- Prevent full media backups from filling the production disk.
- Preserve user-generated assets unless a user action or reviewed retention policy says otherwise.
- Preserve task and billing records even when projects or files are deleted.
- Make every cleanup auditable: dry-run first, execute second, report always.

## Data Classes

| Class | Examples | Default Policy |
| --- | --- | --- |
| Permanent records | users, projects, tasks, billing snapshots, settings | Keep. Back up with DB-only backup. |
| User assets | uploaded references, generated videos/images stored in user files | Keep unless explicitly deleted or reviewed cleanup says unreferenced. |
| Cache files | `cached_*.mp4`, temporary external downloads | TTL cleanup after review. Never delete billing records. |
| Cloud DB snapshots | `USER_DATA_DIR/cloud-dbs/*.db` | Keep newest 200 by default; cleanup only after dry-run review. |
| Auto DB backups | `USER_DATA_DIR/backups/auto/*` | Short retention window, usually 24-48 hours. |
| Local full media backups | `game-video-data-*.tar.gz` | R3 only. Keep latest local copy, move history off the system disk. |
| Code/front-end backups | release rollback packages, dist backups | Keep recent rollback points; old code packages may be pruned after release stabilization. |

## Backup Rules

### R0/R1

Docs, prompts, front-end-only changes, and read-only script changes do not require a full media backup. Keep a code rollback point and run health checks.

### R2

Single-feature writes, task-status changes, file-output changes, and model integration work require a code backup plus targeted DB backup when data writes are involved.

### R3

Authentication, schema migrations, data migrations, storage-path changes, backup script changes, and large feature releases require a full media backup before deployment.

Full media backups are not scheduled daily. Run them manually:

```bash
cd /home/deploy/game-video-tool
GAME_VIDEO_BACKUP_RETENTION_COUNT=1 deploy/backup-game-video-data.sh
```

Move older full media backups to object storage or an attached data volume. Do not keep multiple 8-10 GiB full backups on the 50 GiB system disk.

## Daily Operations

Use DB-only backups for normal daily recovery:

```bash
cd /home/deploy/game-video-tool
deploy/backup-game-video-dbs.sh
```

Use lifecycle reports for dry-run cleanup:

```bash
cd /home/deploy/game-video-tool
deploy/storage-lifecycle.py summary
deploy/storage-lifecycle.py cleanup-cloud-dbs --keep-count 200
deploy/storage-lifecycle.py cleanup-full-backups --keep-count 1
deploy/storage-lifecycle.py duplicate-files-report
```

Lifecycle and health reports show both logical size and unique size:

- `sizes` / logical size counts every visible path.
- `unique_sizes` counts each `(device, inode)` once inside that report scope.
- `hardlink_savings_bytes` is the difference between logical and unique size for
  the whole data directory, which reflects media hard-link dedupe savings.

Use the read-only health report for daily operational review:

```bash
cd /home/deploy/game-video-tool
deploy/health-report.py --json-report /home/deploy/game-video-backups/health-report.latest.json \
  > /home/deploy/game-video-backups/health-report.latest.txt
```

The health report checks local `/health`, local `/ops/provider-queue`, disk
usage, backup state, user storage top list, recent task status, stale
processing tasks, task error categories, service memory RSS/peak RSS, system
available memory, top memory processes, and recent provider error signals from
`app.log`. The `/ops/provider-queue` endpoint is for direct localhost checks
only and must not be exposed through a public reverse proxy. The report does
not modify files, databases, tasks, projects, provider settings, or running
processes.

Use the read-only media audit before any duplicate media cleanup:

```bash
cd /home/deploy/game-video-tool
deploy/media-audit.py --json-report /home/deploy/game-video-backups/media-audit.latest.json \
  > /home/deploy/game-video-backups/media-audit.latest.txt
```

The media audit verifies global/user duplicate files by SHA256 and scans SQLite
references. It only reports hard-link candidates; it does not delete, link, or
rewrite files. Do not run duplicate cleanup without reviewing this report.

Use the read-only task state audit before fixing stuck generation tasks:

```bash
cd /home/deploy/game-video-tool
deploy/task-state-audit.py --json-report /home/deploy/game-video-backups/task-state-audit.latest.json \
  > /home/deploy/game-video-backups/task-state-audit.latest.txt
```

The task audit scans all user SQLite databases in read-only mode and reports
long-running `processing` tasks by user, provider, model, project, and external
task id. It does not call providers, mutate task status, delete records, or
change billing history. Any future terminal-state repair must be a separate
reviewed step after this audit is checked.

If the audit finds stale Seedance/Jimeng tasks, use the read-only provider
status probe before any repair:

```bash
cd /home/deploy/game-video-tool
deploy/task-state-probe.py --json-report /home/deploy/game-video-backups/task-state-probe.latest.json \
  > /home/deploy/game-video-backups/task-state-probe.latest.txt
```

The probe calls the provider status API for existing external task ids only.
It does not update SQLite, cache videos, download provider results, delete
records, or change billing history. Treat its output as evidence for a later
reviewed repair step, not as an automatic state change.

After the audit is clean, use the hard-link dedupe tool in dry-run mode:

```bash
cd /home/deploy/game-video-tool
deploy/media-dedupe.py --json-report /home/deploy/game-video-backups/media-dedupe-dry-run.latest.json \
  > /home/deploy/game-video-backups/media-dedupe-dry-run.latest.txt
```

Only after reviewing the dry-run report, execute explicitly:

```bash
deploy/media-dedupe.py --execute \
  --json-report /home/deploy/game-video-backups/media-dedupe-execute.latest.json \
  > /home/deploy/game-video-backups/media-dedupe-execute.latest.txt
```

The dedupe tool keeps both URL paths valid by replacing the user-scoped duplicate
with a hard link to the global file. It verifies same device, same size, different
inode, and matching SHA256 before each replacement.

Destructive cleanup requires explicit `--execute`:

```bash
deploy/storage-lifecycle.py cleanup-cloud-dbs --keep-count 200 --execute
deploy/storage-lifecycle.py cleanup-full-backups --keep-count 1 --execute
```

## Disk Guard

Use `deploy/disk-guard.sh` as a cron/reporting check.

- Warn at 70% disk usage.
- Block high-risk operations at 90% or less than 5 GiB free.
- When blocked, do not deploy, run full backups, or start large batch generations until cleanup is reviewed.

Example:

```bash
GAME_VIDEO_DISK_WARN_PERCENT=70 \
GAME_VIDEO_DISK_BLOCK_PERCENT=90 \
GAME_VIDEO_DISK_MIN_FREE_GB=5 \
deploy/disk-guard.sh
```

## Long-Term Target

The long-term storage design should move toward content-addressed media:

1. Store each file once by content hash.
2. Keep user/project/task references in the database.
3. Convert duplicate global/user files into hard links only after an audited dry-run.
4. Offload historical media backups to object storage.
5. Keep billing snapshots independent from file/project deletion.

Until that storage model is implemented, do not directly delete user assets from production without a dry-run report and explicit approval.
