# GitHub Copilot Instructions for NMK CMS

## Project Overview

NMK CMS is a Django-based content management system for paleontological collections at the Natural History Museum (NMK). The application manages accessions, specimens, taxonomy data, and related metadata with support for import/export, OCR processing, and merge operations.

## Technology Stack

- **Python:** 3.10-slim
- **Django:** 4.2.25
- **Database:** MariaDB/MySQL
- **Cache:** Redis
- **Web Server:** Gunicorn (production) / Django dev server (development)
- **Containerization:** Docker with Docker Compose
- **Frontend:** W3.CSS framework with Font Awesome 6 icons
- **Key Django Extensions:**
  - django-allauth (authentication)
  - django-import-export (data import/export)
  - django-simple-history (audit logging)
  - django-select2 (autocomplete widgets)
  - django-filter (list filtering)
  - django-autocomplete-light

## Project Structure

```
nmk-cms/
├── app/
│   ├── cms/                    # Main CMS application
│   │   ├── models.py          # Data models
│   │   ├── views.py           # View logic
│   │   ├── admin.py           # Django admin configuration
│   │   ├── forms.py           # Form definitions
│   │   ├── filters.py         # Django-filter definitions
│   │   ├── templates/         # HTML templates
│   │   ├── static/            # Static assets (CSS, JS, images)
│   │   ├── tests/             # Test files
│   │   ├── management/        # Custom management commands
│   │   ├── merge/             # Merge functionality
│   │   ├── qc/                # Quality control features
│   │   └── taxonomy/          # Taxonomy management
│   ├── config/                # Django project settings
│   │   ├── settings.py        # Main settings file
│   │   ├── urls.py           # URL routing
│   │   └── wsgi.py           # WSGI configuration
│   ├── templates/             # Shared templates
│   ├── manage.py              # Django management script
│   └── requirements.txt       # Python dependencies
├── docs/                      # Documentation
│   ├── development/          # Developer guidelines
│   ├── admin/                # Admin guides
│   └── user/                 # User guides
├── nginx/                     # Nginx configuration
├── docker-compose.yml         # Development environment
└── docker-compose.prod.yml    # Production environment
```

## Development Practices

### Python and Django Coding Standards

1. **Follow PEP 8** and favor readability over cleverness
2. **Use type hints** for new code to improve IDE support and documentation
3. **Keep business logic in the model layer** - prefer model methods, services, or domain utilities
4. **Optimize database access:**
   - Use `select_related()` for foreign keys
   - Use `prefetch_related()` for many-to-many and reverse foreign keys
   - Paginate long lists (default: 10 items per page via `paginate_by`)
   - Avoid N+1 queries
5. **Validate through Django forms** - avoid duplicating validation in views
6. **Configuration:** Store secrets in environment variables (`.env` file)
7. **Error handling:** Log meaningfully and provide user-friendly error messages
8. **Imports:** Use explicit imports and keep them organized (stdlib, third-party, local)

### Template and Frontend Standards

1. **Base Template:** All templates must extend `base_generic.html`
2. **HTML5 Semantics:** Use semantic elements (`<header>`, `<main>`, `<section>`, `<article>`, `<footer>`)
3. **W3.CSS Framework:**
   - Use W3.CSS utility classes first before custom CSS
   - Load from CDN in base template
   - Custom overrides go in `static/css/custom.css` with `.nmk-` prefix
4. **Font Awesome 6:** Available globally, prefer "solid" style for actions
5. **Responsive Design:** Mobile-first using W3.CSS breakpoints
   - Phones: 0–600px
   - Tablets: 601–992px
   - Laptops: 993–1366px
   - Desktops: 1367px+
6. **Accessibility:** WCAG AA color contrast, ARIA attributes for dynamic widgets

### Page Patterns

#### List Views
- Wrap in `<div class="w3-container">`
- Use W3.CSS grid (`w3-row`, `w3-col`)
- Include "Show/Hide Filters" toggle with `fa-filter` icon
- Tables: `w3-responsive`, `w3-table-all w3-hoverable`
- Pagination: 10 items per page with Font Awesome chevrons
- Permission checks: Use `has_group` template filter

#### Detail Views
- Single-entity pages showing record metadata
- May include sub-lists or tabs for related items

#### Forms
- Use W3.CSS form styles
- Leverage Django's built-in validation
- Include client-side validation with HTML5 attributes

### Testing

1. **Test Location:** Each app's `tests/` directory
2. **Framework:** Use `django.test.TestCase` or `pytest`
3. **Coverage Areas:**
   - View logic and template context
   - HTML5 and W3.CSS structure
   - Widget functionality (Select2, autocomplete)
   - History views and audit logs
4. **Test Utilities:** Use `Client` or `RequestFactory`
5. **Fixtures:** Keep lightweight; prefer factory functions
6. **Run Tests:**
   ```bash
   docker compose exec web python manage.py test
   ```

### Common Operations

#### Development Environment

```bash
# Start development stack
docker compose up --build

# Run migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser

# Run tests
docker compose exec web python manage.py test

# Collect static files
docker compose exec web python manage.py collectstatic

# Access Django shell
docker compose exec web python manage.py shell

# View logs
docker compose logs -f web
```

#### Database Operations

```bash
# Create migrations
docker compose exec web python manage.py makemigrations

# Apply migrations
docker compose exec web python manage.py migrate

# Database shell
docker compose exec web python manage.py dbshell
```

## Key Integrations and Features

### Django Admin Customization
- Extensive admin customization in `admin.py` and `admin_merge.py`
- Custom admin actions for bulk operations
- Inline editing for related models

### Import/Export
- Uses `django-import-export` with custom resources in `resources.py`
- Support for CSV, Excel formats
- Custom import logic in `importer.py` and `manual_import.py`

### Merge Functionality
- Complex merge strategies in `cms/merge/` directory
- Support for merging duplicate records with conflict resolution
- Located in `admin_merge.py` and related modules

### History and Audit Logging
- `django-simple-history` tracks all model changes
- History views accessible from detail pages
- Automatic user tracking via `django-userforeignkey`

### File Processing
- OCR processing in `ocr_processing.py`
- Upload handling in `upload_processing.py`
- Scanning utilities in `scanning_utils.py`

### Authentication
- Uses `django-allauth` for authentication
- ORCID integration for researcher accounts
- Environment variables: `ORCID_CLIENT_ID`, `ORCID_SECRET`

## Environment Variables

Key environment variables (see `.env` file):

```
DEBUG=1                                    # Debug mode (0 for production)
ALLOWED_HOSTS=*                            # Comma-separated host list
SECRET_KEY=<random-string>                 # Django secret key
DB_HOST=db                                 # Database host
DB_PORT=3306                               # Database port
DB_NAME=nmk_dev                           # Database name
DB_USER=nmk_dev                           # Database user
DB_PASS=<password>                        # Database password
SITE_DOMAIN=localhost:8000                # Site domain
SITE_NAME=NMK CMS                         # Site name
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
ORCID_CLIENT_ID=<client-id>              # ORCID OAuth client ID
ORCID_SECRET=<secret>                     # ORCID OAuth secret
```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- `docs/development/README.md` - Coding standards and guidelines
- `docs/development/environment-setup.md` - Setup instructions
- `docs/development/django-integrations.md` - Framework integration details
- `docs/admin/` - Administrator guides
- `docs/user/` - End-user documentation

## Code Style and Conventions

1. **Naming:**
   - Models: Singular noun (e.g., `Accession`, `Specimen`)
   - Views: Descriptive verb-noun combinations
   - Templates: Match view names or use descriptive names
   - URLs: Lowercase with hyphens (e.g., `project-list`)

2. **Model Methods:**
   - `__str__()`: Return meaningful string representation
   - `get_absolute_url()`: Return canonical URL for object
   - Custom methods: Place business logic here rather than in views

3. **View Patterns:**
   - Class-based views preferred for CRUD operations
   - Function-based views for complex or unique operations
   - Mixins for reusable functionality

4. **Template Conventions:**
   - Block names: `title`, `content`, `extra_head`, `extra_scripts`
   - Include templates in `partials/` subdirectory
   - Template tags in `templatetags/` directory

## Security Considerations

1. **Secrets:** Never commit secrets to source control
2. **User Permissions:** Always check permissions in views and templates
3. **SQL Injection:** Use Django ORM; avoid raw SQL unless necessary
4. **XSS Protection:** Django auto-escapes templates; be careful with `safe` filter
5. **CSRF Protection:** Ensure `{% csrf_token %}` in all forms
6. **File Uploads:** Validate file types and sizes in forms

## Deployment

- **Development:** Uses `docker-compose.yml` with hot-reload
- **Production:** Uses `docker-compose.prod.yml` with Gunicorn and Nginx
- **CI/CD:** GitHub Actions workflows in `.github/workflows/`
- **Docker Image:** Built from `app/Dockerfile`
- **Entrypoints:**
  - Development: `app/scripts/entrypoint.sh`
  - Production: `app/scripts/entrypoint.prod.sh`

## Common Pitfalls to Avoid

1. **Line Endings:** Entrypoint scripts (`app/scripts/entrypoint.sh` and `app/scripts/entrypoint.prod.sh`) must use Unix (LF) line endings, not Windows (CRLF)
2. **Migration Conflicts:** Always pull latest before creating migrations
3. **Static Files:** Run `collectstatic` after changing CSS/JS in production
4. **Database Queries:** Watch for N+1 problems; use `select_related`/`prefetch_related`
5. **Template Inheritance:** Always extend `base_generic.html` for consistency
6. **Custom CSS:** Prefix with `.nmk-` to avoid W3.CSS conflicts
7. **Test Data:** Don't commit test data or personal information

## When Making Changes

1. **Before coding:**
   - Check existing documentation in `docs/`
   - Look for similar patterns in the codebase
   - Understand the page archetype (List, Detail, Form, etc.)

2. **During development:**
   - Test in Docker environment: `docker compose up`
   - Run tests frequently: `docker compose exec web python manage.py test`
   - Check for migrations: `python manage.py makemigrations --dry-run`
   - Validate HTML and accessibility

3. **Before committing:**
   - Ensure all tests pass
   - Check that static files are collected if needed
   - Verify responsive design at different breakpoints
   - Review for accessibility (ARIA labels, keyboard navigation)
   - Update documentation if adding new features

## Getting Help

- Review existing code in `app/cms/` for examples
- Check `docs/development/` for detailed guidelines
- Look at test files in `app/cms/tests/` for usage patterns
- Refer to Django documentation for framework features
