# Backups

Superusers can create and restore CMS backups from **Admin -> Backups**.

## Create a backup

1. Open **Backups** in the admin header.
2. Choose **Back up CMS now**.
3. Download both generated files:
   - `paleocms_database_<timestamp>.sql`
   - `paleocms_files_<timestamp>.tar.gz`

The database file is a MariaDB/MySQL dump. The files archive contains the
contents of `MEDIA_ROOT`.

## Restore

1. Open **Backups** in the admin header.
2. Use **Restore database** to upload a `.sql` dump.
3. Use **Restore media files** to upload a `.tar.gz` media archive.
4. Tick the confirmation checkbox before submitting either restore form.

Restore actions overwrite live CMS data. Take a fresh backup first and use a
maintenance window when restoring production.

## Configuration

- `CMS_BACKUP_ROOT`: directory where generated backup files are stored. The
  default is a `backups` directory next to `MEDIA_ROOT`.
- The application image includes a MySQL/MariaDB client so the admin backup
  page can run `mysqldump` and `mysql` against the configured database.
