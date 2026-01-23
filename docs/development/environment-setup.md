# Environment Setup Guide

These steps walk you through preparing a laptop for day-to-day development and a local server for a small production-style deployment. Instructions stay light on jargon and call out where Windows and Linux differ.

## 1. Know the Moving Pieces

| Item | Where It Is Used | Notes |
| --- | --- | --- |
| `docker-compose.yml` | Laptop development | Builds the app image from `./app` and mounts the source code so changes reload.
| `docker-compose.prod.yml` | Local production server | Pulls a ready-made image defined by `DOCKER_PROD_IMAGE` and serves static files through Nginx.
| `app/scripts/entrypoint.sh` | Development container | Starts Django and background workers in development.
| `app/scripts/entrypoint.prod.sh` | Production container | Runs database checks, collects static files, and launches Gunicorn.
| Watchtower service | Optional production auto-update | The `watchtower` service in `docker-compose.prod.yml` checks Docker Hub for new images.

> **Line endings matter.** Both entrypoint scripts must keep Unix line feeds (LF). Windows converts files to CRLF by default, so double-check before starting containers.

## 2. Prepare Your Laptop for Development

Follow the steps for your operating system. The commands below use sample values; adjust if your ports or passwords need to change.

### 2.1 Install the basics

**Windows**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and enable the "Use WSL 2" option.
2. Install Git for Windows. During setup choose "Checkout as-is, commit Unix-style line endings".
3. Open Windows Terminal or PowerShell for commands.

**Linux (Ubuntu example)**
1. Install Docker Engine and the Compose plugin:
   ```bash
   sudo apt update
   sudo apt install docker.io docker-compose-plugin
   ```
2. Add your user to the Docker group so you can run commands without `sudo`:
   ```bash
   sudo usermod -aG docker $USER
   ```
   Log out and back in to apply the change.
3. Install Git:
   ```bash
   sudo apt install git
   ```

### 2.2 Get the source code

Run these commands in a working folder:

```bash
git clone https://github.com/nmkpaleo/nmk-cms.git
cd nmk-cms
```

If you are on Windows, run the commands inside the WSL shell provided by Docker Desktop for best compatibility.

### 2.3 Create your `.env` file

Copy the template below into a new `.env` file at the project root. Adjust the passwords to suit your laptop.

```bash
cat <<'ENV' > .env
COMPOSE_FILE=docker-compose.yml
DEBUG=1
ALLOWED_HOSTS=*
SITE_DOMAIN=localhost:8000
SITE_NAME=NMK CMS
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
ORCID_CLIENT_ID=changeme
ORCID_SECRET=changeme
DB_HOST=db
DB_PORT=3306
DB_NAME=nmk_dev
DB_USER=nmk_dev
DB_PASS=changeme
DB_ROOT_PASS=changeme
#SECRET_KEY=changeme
#APP_DOMAIN=localhost
#PMA_DOMAIN=localhost
#PMA_UPLOAD_LIMIT=10M
#PMA_MEMORY_LIMIT=512M
#NGINX_CLIENT_MAX_BODY_SIZE=5m
#SCAN_UPLOAD_MAX_BYTES=5242880
#SCAN_UPLOAD_BATCH_MAX_BYTES=0
#SCAN_UPLOAD_TIMEOUT_SECONDS=60
#DOCKER_PROD_IMAGE=palaeontologyhelsinki/nmk-cms:latest

# Redis-related variables.
# Redis is used for caching and the Celery task queue.
# If you are using Docker, set this to true. Otherwise, set it to false.
# If you are using Pythonanywhere, set this to false.
USE_REDIS=true
ENABLE_ADMIN_MERGE=1
TAXON_NOW_ACCEPTED_URL=https://raw.githubusercontent.com/nowcommunity/NOW-Data/refs/heads/main/data/now-export/latest_taxonomy.tsv
TAXON_NOW_SYNONYMS_URL=https://raw.githubusercontent.com/nowcommunity/NOW-Data/refs/heads/main/data/now-export/latest_taxonomy_synonyms.tsv
OPENAI_API_KEY=changeme
ENV
```

### 2.4 Keep scripts in Unix format (Windows only)

Run the following once after cloning:

```powershell
wsl dos2unix app/scripts/entrypoint.sh app/scripts/entrypoint.prod.sh
```

If `dos2unix` is not installed in WSL, add it with `sudo apt install dos2unix`. Linux users can skip this step because Git already keeps the files in LF format.

### 2.5 Start the development stack

```bash
docker compose up --build
```

This command builds the app image, starts MariaDB, Redis, phpMyAdmin, and the Django app. Visit `http://localhost:8000` for the site and `http://localhost:8001` for phpMyAdmin.

To stop the stack, press `Ctrl+C`, then run:

```bash
docker compose down
```

### 2.6 Useful development helpers

| Task | Command |
| --- | --- |
| Run migrations | `docker compose exec web python manage.py migrate` |
| Create a superuser | `docker compose exec web python manage.py createsuperuser` |
| Tail application logs | `docker compose logs -f web` |

## 3. Prepare a Local Production Server

These steps assume a Linux host (for example, Ubuntu Server) that will run containers in the background.

### 3.1 Install runtime tools

```bash
# Update Linux:
sudo apt update
sudo apt list --upgradable
sudo apt upgrade

sudo apt install docker.io docker-compose-plugin
sudo systemctl enable docker --now
```

Create a deployment folder and copy the repository or the necessary files onto the server:

```bash
mkdir -p /opt/nmk-cms
cd /opt/nmk-cms
```

You can either clone the repository or copy over the `docker-compose.prod.yml`, `nginx/`, and any other configuration files you maintain.

### 3.2 Provide production secrets

Create `/opt/nmk-cms/.env` with values that match your server. At minimum set:

```bash
COMPOSE_FILE=docker-compose.prod.yml
DEBUG=0
ALLOWED_HOSTS=*
SITE_DOMAIN=localhost:8000
SITE_NAME=NMK CMS
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
ORCID_CLIENT_ID=changeme
ORCID_SECRET=changeme
DB_HOST=db
DB_PORT=3306
DB_NAME=changeme
DB_USER=changeme
DB_PASS=changeme
DB_ROOT_PASS=changeme
SECRET_KEY=changeme
APP_DOMAIN=localhost
PMA_DOMAIN=localhost
PMA_UPLOAD_LIMIT=10M
PMA_MEMORY_LIMIT=512M
NGINX_CLIENT_MAX_BODY_SIZE=5m
SCAN_UPLOAD_MAX_BYTES=5242880
SCAN_UPLOAD_BATCH_MAX_BYTES=0
SCAN_UPLOAD_TIMEOUT_SECONDS=60
DOCKER_PROD_IMAGE=palaeontologyhelsinki/nmk-cms:latest

# Redis-related variables.
# Redis is used for caching and the Celery task queue.
# If you are using Docker, set this to true. Otherwise, set it to false.
# If you are using Pythonanywhere, set this to false.
USE_REDIS=true
ENABLE_ADMIN_MERGE=1
TAXON_NOW_ACCEPTED_URL=https://raw.githubusercontent.com/nowcommunity/NOW-Data/refs/heads/main/data/now-export/latest_taxonomy.tsv
TAXON_NOW_SYNONYMS_URL=https://raw.githubusercontent.com/nowcommunity/NOW-Data/refs/heads/main/data/now-export/latest_taxonomy_synonyms.tsv
OPENAI_API_KEY=changeme
```

Ensure `app/scripts/entrypoint.prod.sh` keeps LF endings. You can run `dos2unix app/scripts/entrypoint.prod.sh` before copying the file, or check with `file app/scripts/entrypoint.prod.sh`.

### 3.3 Start the production stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

This command starts the application container (pulling the image defined by `DOCKER_PROD_IMAGE`), Redis, MariaDB, Nginx, phpMyAdmin, Certbot, and Watchtower. Nginx serves the site on ports 80 and 443. The static files volume `static` is shared between the app and Nginx.

To review logs:

```bash
docker compose -f docker-compose.prod.yml logs -f web
```

To update containers manually:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### 3.4 Watchtower auto-updates

The `watchtower` service checks Docker Hub every 30 seconds (`--interval 30`). It pulls the latest tag defined in `DOCKER_PROD_IMAGE` and restarts the container when a new image appears. Keep these tips in mind:

- Set `DOCKER_PROD_IMAGE` to a versioned tag (for example, `nmk-cms:2024-05-01`) if you want predictable upgrades.
- To pause automatic updates, stop the service:
  ```bash
  docker compose -f docker-compose.prod.yml stop watchtower
  ```
- To remove Watchtower entirely, comment out the service block or delete it from the compose file.
- Containers marked with the label `com.centurylinklabs.watchtower.enable=false` (Nginx, Certbot, phpMyAdmin) are skipped automatically.

### 3.5 Backups and maintenance checklist

| Task | Frequency | Command |
| --- | --- | --- |
| Database backup | Daily | `docker compose -f docker-compose.prod.yml exec db mysqldump -u root -p"$DB_ROOT_PASS" $DB_NAME > backup.sql` |
| Check container status | Weekly | `docker compose -f docker-compose.prod.yml ps` |
| Renew certificates | Automatic via Certbot | Ensure ports 80/443 stay open |

## 4. Quick Comparison: Windows vs Linux

| Topic | Windows laptop | Linux laptop/server |
| --- | --- | --- |
| Preferred shell | PowerShell or WSL bash | Bash |
| Line endings | Convert entrypoint scripts to LF with `dos2unix` | Already LF; no action needed |
| Docker command | `docker compose ...` (Docker Desktop) | `docker compose ...` (Docker Engine) |
| File paths | Use `/mnt/c/...` inside WSL | Standard Linux paths |
| Permissions | Run terminal as Administrator the first time to let Docker share drives | Ensure your user is in the `docker` group |

With these steps you can spin up the CMS locally for coding or run it on a local server that mirrors production behaviour while keeping the deployment process simple.
