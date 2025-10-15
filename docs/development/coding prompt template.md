# 🧱 Coding Prompt Template — Django (MySQL • Python 3.9 • nginx prod • GitHub Actions CI)

You are a **senior Django engineer**. Implement exactly one task from an approved feature plan.

---

## 🔧 Stack & Constraints
- **Python:** 3.9
- **Django:** 4.2
- **DB:** MySQL
- **Auth:** django-allauth
- **Auditing:** django-simple-history
- **Filtering/search:** django-filter
- **Templates/UI:** Django templates + W3.CSS (mobile-first) + Font Awesome
- **Template structure:** Extend `base_generic.html`; include HTML5 boilerplate and semantic regions (`<header>`, `<main>`, `<section>`, `<article>`, `<aside>`, `<footer>`)
- **Static/Media:** served by **nginx** in production
- **CI/CD:** GitHub Actions (lint, type-check, tests, migrations check, docs)
- **Project layout:** `/project/`, `/apps/<app_name>/`, `/templates/`, `/static/`
- **Config:** 12-factor (env vars); `requirements.txt` governs dependencies

---

## 📌 Task To Implement (Paste the single task object here)

> Replace the JSON below with the **exact** task object (T1/T2/…) from the approved plan.

```json
{
  "id": "T?",
  "title": "Short title",
  "summary": "What will be implemented",
  "app": "apps.<app_name>",
  "files_touched": [],
  "migrations": true,
  "settings_changes": [],
  "packages": [],
  "permissions": [],
  "acceptance_criteria": [],
  "test_plan": [],
  "docs_touched": [],
  "dependencies": [],
  "estimate_hours": 0.0,
  "risk_level": "low|med|high",
  "priority": "low|medium|high",
  "reviewer_notes": []
}
```
________________________________________
✅ Coding Requirements
-	Scope: Implement only the task above. No bonus features. Respect files_touched, migrations, settings_changes, and permissions.
-	Quality: Production-grade code. Follow black, isort, ruff. Use typing hints where reasonable.
-	Architecture: Prefer CBVs, forms/serializers, queryset filters via django-filter, and simple-history only if the task requires it.
-	DB: Ensure MySQL-safe field choices (e.g., CharField lengths, indexes, TextField where needed).
-	i18n: Wrap user-facing strings with gettext (ugettext_lazy/gettext_lazy as appropriate).
-	A11y: If templates are involved, ensure label/aria attributes and keyboard navigability.
-	Security: Respect auth/permissions from the task; avoid overexposing admin or API endpoints; validate input.
-	Settings: Change only if listed in settings_changes. Otherwise, reuse existing configuration.
-	Dependencies: Only use packages listed in packages. If empty, do not add new packages.
-	Migrations: Generate idempotent migrations. When altering existing models, prefer non-breaking operations; include RunPython data migrations if needed.
-	Admin: If applicable, add list_display, search_fields, list_filter, and history mixins.
-	URLs: Namespaced URLs under app; avoid global pollution. Use app_name = '<app_name>'.
-	Templates: Extend `base_generic.html`, use semantic HTML5 regions, apply W3.CSS utilities (mobile-first), and include Font Awesome icons specified in the plan/task.
-	Docs/Tests: Only include if the task’s files_touched or test_plan/docs_touched indicate them.
________________________________________
📤 Output Format (Strict)
Return only the changed/added files, each with:
1.	A file header line: # FILE: <path>
2.	The file contents in a fenced code block
If you modify multiple files, repeat the pattern. No commentary outside code.
If a file is deleted, include a header # FILE: <path> (deleted) with no code block.
Where partial snippets are appropriate (e.g., URL include), show the full file if feasible; otherwise clearly mark with # … existing code ….
Examples:
# FILE: apps/feedback/models.py
from django.db import models
from django.conf import settings
from simple_history.models import HistoricalRecords
from django.utils.translation import gettext_lazy as _

class Feedback(models.Model):
    class Category(models.TextChoices):
        BUG = "bug", _("Bug")
        FEATURE = "feature", _("Feature")
        OTHER = "other", _("Other")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback")
    subject = models.CharField(max_length=200)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    message = models.TextField()
    screenshot = models.ImageField(upload_to="feedback/", blank=True, null=True)
    status = models.CharField(max_length=16, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.subject} ({self.get_category_display()})"
# FILE: apps/feedback/admin.py
from django.contrib import admin
from .models import Feedback
from simple_history.admin import SimpleHistoryAdmin

@admin.register(Feedback)
class FeedbackAdmin(SimpleHistoryAdmin):
    list_display = ("id", "user", "subject", "category", "status", "created_at")
    list_filter = ("category", "status", "created_at")
    search_fields = ("subject", "message", "user__email", "user__username")
# FILE: apps/feedback/migrations/0001_initial.py
# Generated by Django <version>
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("simple_history", "__latest__"),
    ]
    operations = [
        migrations.CreateModel(
            name="Feedback",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("subject", models.CharField(max_length=200)),
                ("category", models.CharField(max_length=16)),
                ("message", models.TextField()),
                ("screenshot", models.ImageField(blank=True, null=True, upload_to="feedback/")),
                ("status", models.CharField(max_length=16, default="pending")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feedback", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
# FILE: apps/feedback/urls.py
from django.urls import path
from .views import FeedbackCreateView

app_name = "feedback"

urlpatterns = [
    path("new/", FeedbackCreateView.as_view(), name="create"),
]
(Above are examples — your output must match the current task’s files.)
________________________________________
🧪 If Tests Are In-Scope for This Task
When test_plan indicates tests or files_touched includes tests, add files like:
# FILE: apps/feedback/tests/test_models.py
import pytest
from django.contrib.auth import get_user_model
from apps.feedback.models import Feedback

pytestmark = pytest.mark.django_db

def test_feedback_str():
    u = get_user_model().objects.create(username="alice")
    fb = Feedback.objects.create(user=u, subject="Hello", category="other", message="Hi")
    assert "Hello" in str(fb)
________________________________________
🔒 If Settings/Permissions Are In-Scope
-	Settings changes: show the exact diff within settings.py or settings/<env>.py as a full file or clear snippet:
# FILE: project/settings.py
# … existing imports …
INSTALLED_APPS += ["simple_history"]
MIDDLEWARE = ["simple_history.middleware.HistoryRequestMiddleware", *MIDDLEWARE]
-	Permissions: if Django permissions/groups are required, add fixtures or migration with RunPython creating perms/groups; or enforce via PermissionRequiredMixin/DRF permissions.
________________________________________
🧯 Non-Functional Requirements (apply when relevant to the task)
-	Performance: Add DB indexes if filtering/sorting heavy fields; use select_related/prefetch_related for N+1 hotspots.
-	MySQL specifics: Keep index lengths compatible (e.g., CharField(max_length=191) if needed); mindful of text/blob indexing.
-	Files/Media: For uploads, ensure proper upload_to and validate file types/sizes.
-	Email: If sending email, use configured backend; no hard-coded addresses; allow subject/body i18n.
________________________________________
🚫 Do Not
-	Do not include explanations, logs, or commentary outside the # FILE blocks.
-	Do not change unrelated files.
-	Do not introduce new packages unless explicitly listed in the task’s packages.
-	Do not bypass or modify CI settings.
________________________________________
🧾 Final Check Before Returning
-	All acceptance criteria in the task are satisfied.
-	Files compile (import-time errors avoided).
-	Migrations are present if migrations: true.
-	Admin/URLs/templates updated only if part of the task.
-	i18n applied to any new user-facing strings.
•	Code adheres to style (black/isort/ruff) and is MySQL-compatible.
Return your answer now as a series of # FILE: sections with code blocks only (no narrative).
