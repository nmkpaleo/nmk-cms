from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection, models
from django.test import TransactionTestCase
from django.test.utils import isolate_apps

from cms.merge.constants import MergeStrategy
from cms.merge.engine import merge_records
from cms.merge.mixins import MergeMixin
from cms.merge.serializers import serialize_instance
from cms.models import MergeLog


def _ensure_content_type_table() -> None:
    from django.contrib.contenttypes.models import ContentType

    existing_tables = set(connection.introspection.table_names())
    if ContentType._meta.db_table in existing_tables:
        return

    connection.disable_constraint_checking()
    try:
        with connection.schema_editor(atomic=False) as schema_editor:
            schema_editor.create_model(ContentType)
    finally:
        connection.enable_constraint_checking()


def _ensure_auth_and_merge_tables() -> None:
    """Create auth and merge log tables when migrations are unavailable."""

    from django.contrib.auth.models import Group, Permission, User
    from django.contrib.contenttypes.models import ContentType
    from django.contrib.sites.models import Site

    from cms.models import MergeLog

    _ensure_content_type_table()
    existing_tables = set(connection.introspection.table_names())
    models_to_create = [Permission, Group, User, Site, MergeLog]

    connection.disable_constraint_checking()
    try:
        with connection.schema_editor(atomic=False) as schema_editor:
            for model in models_to_create:
                if model._meta.db_table in existing_tables:
                    continue
                schema_editor.create_model(model)
    finally:
        connection.enable_constraint_checking()


@isolate_apps("cms", "django.contrib.contenttypes")
class MergeEngineIntegrationTests(TransactionTestCase):
    """Exercise the merge engine end-to-end using concrete models."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class MergeSubject(MergeMixin):
            title = models.CharField(max_length=64)
            description = models.TextField(blank=True)
            archived_snapshots = models.JSONField(default=list, blank=True)

            merge_fields = {
                "title": MergeStrategy.LAST_WRITE,
                "description": {
                    "strategy": MergeStrategy.PREFER_NON_NULL.value,
                    "priority": ["source", "target"],
                },
            }

            class Meta:
                app_label = "cms"

            def archive_source_instance(self, source_instance: "MergeSubject") -> None:  # type: ignore[name-defined]
                snapshots = list(self.archived_snapshots or [])
                snapshots.append(serialize_instance(source_instance))
                self.archived_snapshots = snapshots
                self.save(update_fields=["archived_snapshots"])

        class Attachment(models.Model):
            owner = models.ForeignKey(
                MergeSubject,
                related_name="attachments",
                on_delete=models.CASCADE,
            )
            label = models.CharField(max_length=64)

            class Meta:
                app_label = "cms"

        class Badge(models.Model):
            name = models.CharField(max_length=64)
            subjects = models.ManyToManyField(
                MergeSubject,
                related_name="badges",
            )

            class Meta:
                app_label = "cms"

        class Profile(models.Model):
            owner = models.OneToOneField(
                MergeSubject,
                related_name="profile",
                on_delete=models.CASCADE,
            )
            bio = models.CharField(max_length=128, blank=True)

            class Meta:
                app_label = "cms"

        cls.MergeSubject = MergeSubject
        cls.Attachment = Attachment
        cls.Badge = Badge
        cls.Profile = Profile

        _ensure_auth_and_merge_tables()

        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.create_model(MergeSubject)
                schema_editor.create_model(Attachment)
                schema_editor.create_model(Badge)
                schema_editor.create_model(Profile)
        finally:
            connection.enable_constraint_checking()

    @classmethod
    def tearDownClass(cls):
        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.delete_model(cls.Profile)
                schema_editor.delete_model(cls.Badge)
                schema_editor.delete_model(cls.Attachment)
                schema_editor.delete_model(cls.MergeSubject)
        finally:
            connection.enable_constraint_checking()
        super().tearDownClass()

    def setUp(self):
        self.target = self.MergeSubject.objects.create(
            title="Target",
            description="Existing description",
        )
        self.source = self.MergeSubject.objects.create(
            title="Source",
            description="Replacement description",
        )

        self.attachment = self.Attachment.objects.create(
            owner=self.source,
            label="Document",
        )
        self.profile = self.Profile.objects.create(owner=self.source, bio="Source bio")

        self.shared_badge = self.Badge.objects.create(name="Shared")
        self.shared_badge.subjects.add(self.source, self.target)
        self.source_only_badge = self.Badge.objects.create(name="Source Only")
        self.source_only_badge.subjects.add(self.source)

    def test_merge_records_updates_fields_relations_and_logs(self):
        source_pk = self.source.pk
        result = merge_records(self.source, self.target, strategy_map=None, user=None)

        self.target.refresh_from_db()
        self.profile.refresh_from_db()
        self.attachment.refresh_from_db()

        self.assertEqual(self.target.title, "Source")
        self.assertEqual(self.target.description, "Replacement description")

        self.assertEqual(self.attachment.owner, self.target)
        self.assertEqual(self.profile.owner, self.target)

        badge_ids = sorted(self.target.badges.values_list("name", flat=True))
        self.assertEqual(badge_ids, ["Shared", "Source Only"])

        self.assertIn("title", result.resolved_values)
        self.assertEqual(result.resolved_values["title"].value, "Source")
        self.assertIn("description", result.resolved_values)
        self.assertEqual(result.resolved_values["description"].value, "Replacement description")

        relation_actions = result.relation_actions
        self.assertEqual(relation_actions["attachments"]["updated"], 1)
        self.assertEqual(relation_actions["profile"]["updated"], 1)
        self.assertEqual(relation_actions["badges"]["added"], 1)
        self.assertEqual(relation_actions["badges"]["skipped"], 1)

        log_entry = MergeLog.objects.filter(target_pk=str(self.target.pk)).latest("executed_at")
        self.assertEqual(log_entry.source_pk, str(source_pk))
        self.assertEqual(log_entry.target_pk, str(self.target.pk))
        self.assertEqual(log_entry.resolved_values["fields"]["title"]["value"], "Source")
        self.assertEqual(log_entry.relation_actions["attachments"]["updated"], 1)
        self.assertEqual(log_entry.relation_actions["badges"]["added"], 1)

        self.target.refresh_from_db()
        self.assertEqual(len(self.target.archived_snapshots), 1)
        archived_snapshot = self.target.archived_snapshots[0]
        self.assertEqual(archived_snapshot["title"], "Source")
        self.assertEqual(archived_snapshot["description"], "Replacement description")

        self.assertFalse(self.MergeSubject.objects.filter(pk=self.source.pk).exists())


@isolate_apps("cms", "django.contrib.contenttypes")
class FieldSelectionMergeLogTests(TransactionTestCase):
    """Ensure merge logs serialise user-valued fields for field-selection merges."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class LocalUser(models.Model):
            username = models.CharField(max_length=64)

            class Meta:
                app_label = "cms"

        class FieldSelectionSubject(MergeMixin):
            name = models.CharField(max_length=64)
            owner = models.ForeignKey(LocalUser, on_delete=models.CASCADE)

            merge_fields = {"owner": MergeStrategy.FIELD_SELECTION}

            class Meta:
                app_label = "cms"

            def archive_source_instance(self, source_instance: "MergeSubject") -> None:  # type: ignore[name-defined]
                return None

        cls.LocalUser = LocalUser
        cls.MergeSubject = FieldSelectionSubject

        _ensure_auth_and_merge_tables()

        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.create_model(LocalUser)
                schema_editor.create_model(FieldSelectionSubject)
        finally:
            connection.enable_constraint_checking()

    @classmethod
    def tearDownClass(cls):
        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.delete_model(cls.MergeSubject)
                schema_editor.delete_model(cls.LocalUser)
        finally:
            connection.enable_constraint_checking()
        super().tearDownClass()

    def setUp(self):
        self.owner_a = self.LocalUser.objects.create(username="owner-a")
        self.owner_b = self.LocalUser.objects.create(username="owner-b")
        self.target = self.MergeSubject.objects.create(name="Target", owner=self.owner_a)
        self.source = self.MergeSubject.objects.create(name="Source", owner=self.owner_b)
        self.audit_user = get_user_model().objects.create(username="auditor")

    def test_field_selection_owner_logs_primary_key(self):
        strategy_map = {
            "fields": {
                "owner": {
                    "strategy": MergeStrategy.FIELD_SELECTION,
                    "value": self.owner_b,
                }
            }
        }

        merge_records(self.source, self.target, strategy_map=strategy_map, user=self.audit_user)

        log_entry = MergeLog.objects.filter(target_pk=str(self.target.pk)).latest("executed_at")
        owner_log = log_entry.resolved_values["fields"]["owner"]
        self.assertEqual(owner_log["value"], self.owner_b.pk)
