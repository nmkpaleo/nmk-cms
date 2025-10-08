from django.db import connection, models
from django.test import TransactionTestCase
from django.test.utils import isolate_apps

from cms.merge.engine import merge_records
from cms.merge.mixins import MergeMixin
from cms.models import MergeLog


@isolate_apps("cms")
class RelationMergeTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class MergeParent(MergeMixin):
            name = models.CharField(max_length=64)

            relation_strategies = {"notes": "skip"}

            class Meta:
                app_label = "cms"

        class Child(models.Model):
            parent = models.ForeignKey(
                MergeParent,
                related_name="children",
                on_delete=models.CASCADE,
            )
            name = models.CharField(max_length=64)

            class Meta:
                app_label = "cms"

        class Label(models.Model):
            name = models.CharField(max_length=64)
            parents = models.ManyToManyField(
                MergeParent,
                related_name="labels",
            )

            class Meta:
                app_label = "cms"

        class Identity(models.Model):
            code = models.CharField(max_length=32)
            owner = models.OneToOneField(
                MergeParent,
                related_name="identity",
                on_delete=models.CASCADE,
            )

            class Meta:
                app_label = "cms"

        class Note(models.Model):
            body = models.TextField()
            owner = models.ForeignKey(
                MergeParent,
                related_name="notes",
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
            )

            class Meta:
                app_label = "cms"

        cls.MergeParent = MergeParent
        cls.Child = Child
        cls.Label = Label
        cls.Identity = Identity
        cls.Note = Note

        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.create_model(MergeParent)
                schema_editor.create_model(Child)
                schema_editor.create_model(Label)
                schema_editor.create_model(Identity)
                schema_editor.create_model(Note)
        finally:
            connection.enable_constraint_checking()

    @classmethod
    def tearDownClass(cls):
        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.delete_model(cls.Note)
                schema_editor.delete_model(cls.Identity)
                schema_editor.delete_model(cls.Label)
                schema_editor.delete_model(cls.Child)
                schema_editor.delete_model(cls.MergeParent)
        finally:
            connection.enable_constraint_checking()
        super().tearDownClass()

    def setUp(self):
        self.target = self.MergeParent.objects.create(name="Target")
        self.source = self.MergeParent.objects.create(name="Source")

    def test_relations_reassigned_and_logged(self):
        child = self.Child.objects.create(parent=self.source, name="Minor")
        identity = self.Identity.objects.create(owner=self.source, code="SRC")
        note = self.Note.objects.create(owner=self.source, body="Sensitive")

        label_a = self.Label.objects.create(name="Alpha")
        label_b = self.Label.objects.create(name="Beta")
        label_a.parents.add(self.source)
        label_a.parents.add(self.target)
        label_b.parents.add(self.source)

        result = merge_records(
            self.source,
            self.target,
            strategy_map=None,
            archive=False,
        )

        child.refresh_from_db()
        self.assertEqual(child.parent, self.target)

        identity.refresh_from_db()
        self.assertEqual(identity.owner, self.target)

        note.refresh_from_db()
        self.assertIsNone(note.owner)

        target_labels = list(self.target.labels.order_by("pk").values_list("pk", flat=True))
        self.assertEqual(target_labels, [label_a.pk, label_b.pk])

        actions = result.relation_actions
        self.assertEqual(actions["children"]["updated"], 1)
        self.assertEqual(actions["identity"]["updated"], 1)
        self.assertEqual(actions["labels"]["added"], 1)
        self.assertEqual(actions["labels"]["skipped"], 1)
        self.assertEqual(actions["notes"]["action"], "skip")

        log_entry = MergeLog.objects.order_by("-executed_at").first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.relation_actions["children"]["updated"], 1)
        self.assertEqual(log_entry.relation_actions["labels"]["added"], 1)
