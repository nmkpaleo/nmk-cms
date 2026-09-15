# NMK CMS

NMK CMS is the National Museums of Kenya collection management system for
palaeontological accessions, specimens, taxonomy, media, OCR, and quality-control
workflows. It is built with Python 3.10, Django 5.2 LTS, MariaDB, Redis, and
Docker Compose.

## Get started

Follow the [development environment guide](docs/development/environment-setup.md)
to configure the application and start the Docker Compose stack.

```bash
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
```

Do not use production credentials or production data in a development setup.

## Documentation

- [Developer guide](docs/development/README.md)
- [Testing](docs/development/testing.md)
- [GitHub workflow and security](docs/development/github-workflow.md)
- [Release checklist](docs/development/release-checklist.md)
- [Administrator guides](docs/admin/README.md)
- [User guides](docs/user/README.md)

Documentation is plain Markdown under `docs/`; this repository does not use
MkDocs.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report
suspected vulnerabilities privately according to [SECURITY.md](SECURITY.md),
never in a public issue.

## License

This project is available under the [MIT License](LICENSE).
