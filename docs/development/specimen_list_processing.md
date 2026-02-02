# Specimen List PDF Processing (Operations)

## Overview
Specimen list PDFs are queued for offline processing to avoid large PDF splits inside web requests. Use the management command to process queued PDFs and create page records.

## Management command
Run the command from the project root:

```
python app/manage.py process_specimen_list_pdfs
```

Optional flags:
- `--limit 5` to process a smaller batch.
- `--ids 12 13` to process specific uploads.

## PythonAnywhere setup
1. Open the **Tasks** tab.
2. Add a scheduled task that runs every few minutes, for example:

```
python /home/<user>/<project>/app/manage.py process_specimen_list_pdfs --limit 5
```

3. Keep the batch size small to avoid timeouts on shared workers.
4. Monitor the admin status fields to confirm pages are created.

## Docker production setup
Add a lightweight worker that runs the command on a schedule. Two common options:

### Option A: Cron container
- Add a small cron container that runs the command every minute.
- Example command:

```
python app/manage.py process_specimen_list_pdfs --limit 10
```

### Option B: Dedicated worker service
- Add a service to `docker-compose.prod.yml` that runs a loop:

```
while true; do
  python app/manage.py process_specimen_list_pdfs --limit 10
  sleep 60
done
```

Use environment variables to keep the limit and sleep interval configurable for each deployment.
