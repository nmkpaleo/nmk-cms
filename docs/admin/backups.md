# Backups

Superusers can create and restore CMS backups from **Admin -> Backups**.

## Create a backup

1. Open **Backups** in the admin header.
2. Choose **Back up CMS now**.
3. Wait for the job to show **Succeeded** in **Backup and restore jobs**.
4. Download both generated files:
   - `paleocms_database_<timestamp>_<run-id>.sql`
   - `paleocms_files_<timestamp>_<run-id>.tar.gz`

The database file is a MariaDB/MySQL dump. The files archive contains the
contents of `MEDIA_ROOT`.

## Restore

1. Open **Backups** in the admin header.
2. Use **Restore database** to upload a `.sql` dump.
3. Use **Restore media files** to upload a `.tar.gz` media archive.
4. Tick the confirmation checkbox before submitting either restore form.
5. Wait for the restore job to show **Succeeded** or **Failed** in **Backup and restore jobs**.

Restore actions overwrite live CMS data. Take a fresh backup first and use a
maintenance window when restoring production.

Backup and restore jobs are stored in the database and processed by the
`backup_worker` service. Keep exactly one worker service running; do not scale it
to multiple instances.

## Configuration

- `CMS_BACKUP_ROOT`: directory where generated backup files are stored. The
  default is `/vol/backups`, mounted as persistent, private storage by the
  supplied Compose deployments.
- The application image includes a MySQL/MariaDB client so the admin backup
  page can run `mysqldump` and `mysql` against the configured database.
- Restore uploads pass through Nginx, whose production default
  `NGINX_CLIENT_MAX_BODY_SIZE` is `5m`. Set this environment variable to a
  value larger than the largest expected SQL or media archive, then recreate
  the Nginx service before uploading larger restores.
