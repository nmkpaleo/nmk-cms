# Backups

The CMS uses `django-dbbackup` for database and media backups. The package
provides standard Django management commands for creating and restoring backups.

Backups use the `dbbackup` storage configured in Django `STORAGES`. By default,
this project stores backup files in `BACKUP_ROOT`, which defaults to:

```text
/src/app/backups/
```

inside the production web container.

## Create Backups

Create a database backup:

```bash
python manage.py dbbackup
```

Create a media backup:

```bash
python manage.py mediabackup
```

For production Docker Compose:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py dbbackup
docker compose -f docker-compose.prod.yml exec web python manage.py mediabackup
```

List backup files:

```bash
docker compose -f docker-compose.prod.yml exec web ls -lh /src/app/backups/
```

## Restore Backups

Restore the latest matching database backup:

```bash
python manage.py dbrestore
```

Restore the latest matching media backup:

```bash
python manage.py mediarestore
```

For production Docker Compose:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py dbrestore
docker compose -f docker-compose.prod.yml exec web python manage.py mediarestore
```

## Storage Notes

The default storage is local filesystem storage for simple server-side backups.
For off-server backups, configure the `dbbackup` storage backend to point to an
external storage service supported by Django storage backends.

Keep database and media backups from the same time window together when testing
restores or moving backups to external storage.
