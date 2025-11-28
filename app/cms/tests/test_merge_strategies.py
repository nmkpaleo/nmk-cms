from __future__ import annotations

from django.db import models
from django.test import SimpleTestCase, override_settings
from django.test.utils import isolate_apps

from cms.merge.constants import MergeStrategy
from cms.merge.mixins import MergeMixin
from cms.merge.strategies import PendingResolution, StrategyResolver, UNCHANGED


def custom_concat_handler(**kwargs):
    source_value = kwargs.get("source_value") or ""
    target_value = kwargs.get("target_value") or ""
    combined = " | ".join(part for part in (target_value, source_value) if part)
    return combined, "custom handler executed"


@isolate_apps("cms")
class StrategyResolverTests(SimpleTestCase):
    def setUp(self):
        class StrategyModel(MergeMixin):
            name = models.CharField(max_length=64, null=True, blank=True)
            description = models.CharField(max_length=128, null=True, blank=True)
            notes = models.TextField(null=True, blank=True)
            summary = models.TextField(null=True, blank=True)

            class Meta:
                app_label = "cms"

        self.Model = StrategyModel

    def test_last_write_prefers_source(self):
        resolver = StrategyResolver(self.Model, {"name": MergeStrategy.LAST_WRITE})
        source = self.Model(name="Source Value")
        target = self.Model(name="Target Value")

        resolution = resolver.resolve_field("name", source=source, target=target)

        self.assertEqual(resolution.value, "Source Value")
        self.assertIn("source", resolution.note.lower())

    def test_prefer_non_null_respects_priority(self):
        resolver = StrategyResolver(
            self.Model,
            {
                "description": {
                    "strategy": MergeStrategy.PREFER_NON_NULL,
                    "priority": ["source", "target"],
                }
            },
        )
        source = self.Model(description="Described by Source")
        target = self.Model(description="")

        resolution = resolver.resolve_field("description", source=source, target=target)

        self.assertEqual(resolution.value, "Described by Source")
        self.assertIn("source", resolution.note.lower())

        target.description = "Existing Target"
        source.description = ""
        fallback = resolver.resolve_field("description", source=source, target=target)
        self.assertEqual(fallback.value, "Existing Target")
        self.assertIn("target", fallback.note.lower())

    def test_concatenate_text_with_custom_delimiter_and_deduplication(self):
        resolver = StrategyResolver(
            self.Model,
            {
                "notes": {
                    "strategy": MergeStrategy.CONCAT_TEXT,
                    "delimiter": "; ",
                }
            },
        )
        source = self.Model(notes="  Beta ")
        target = self.Model(notes="Alpha")

        combined = resolver.resolve_field("notes", source=source, target=target)
        self.assertEqual(combined.value, "Alpha; Beta")
        self.assertIn("; ", combined.note)

        duplicate = resolver.resolve_field(
            "notes",
            source=self.Model(notes=" Alpha "),
            target=self.Model(notes="Alpha"),
        )
        self.assertEqual(duplicate.value, "Alpha")
        self.assertIn("no change", duplicate.note.lower())

    def test_whitelist_blocks_and_allows_field_updates(self):
        allowed_resolver = StrategyResolver(
            self.Model,
            {
                "summary": {
                    "strategy": MergeStrategy.WHITELIST,
                    "allow": ["summary"],
                }
            },
        )
        source = self.Model(summary="Source Summary")
        target = self.Model(summary="Target Summary")

        allowed = allowed_resolver.resolve_field("summary", source=source, target=target)
        self.assertEqual(allowed.value, "Source Summary")
        self.assertIn("whitelist", allowed.note.lower())

        blocked_resolver = StrategyResolver(
            self.Model,
            {
                "summary": {
                    "strategy": MergeStrategy.WHITELIST,
                    "allow": ["other"],
                }
            },
        )
        blocked = blocked_resolver.resolve_field("summary", source=source, target=target)
        self.assertIs(blocked.value, UNCHANGED)
        self.assertIn("not in whitelist", blocked.note.lower())
        self.assertEqual(blocked.as_log_payload()["status"], "unchanged")

    def test_field_selection_prefers_user_choice_or_value(self):
        explicit_resolver = StrategyResolver(
            self.Model,
            {
                "name": {
                    "strategy": MergeStrategy.FIELD_SELECTION,
                    "value": "User Chosen",
                }
            },
        )
        explicit = explicit_resolver.resolve_field(
            "name", source=self.Model(name="Source"), target=self.Model(name="Target")
        )
        self.assertEqual(explicit.value, "User Chosen")
        self.assertIn("user-selected", explicit.note)

        choice_resolver = StrategyResolver(
            self.Model,
            {
                "description": {
                    "strategy": MergeStrategy.FIELD_SELECTION,
                    "selected_from": "source",
                }
            },
        )
        choice = choice_resolver.resolve_field(
            "description",
            source=self.Model(description="Source Description"),
            target=self.Model(description="Target Description"),
        )
        self.assertEqual(choice.value, "Source Description")
        self.assertIn("source", choice.note.lower())

        fallback_resolver = StrategyResolver(
            self.Model,
            {"summary": {"strategy": MergeStrategy.FIELD_SELECTION}},
        )
        fallback = fallback_resolver.resolve_field(
            "summary",
            source=self.Model(summary="Source Summary"),
            target=self.Model(summary="Target Summary"),
        )
        self.assertIs(fallback.value, UNCHANGED)
        self.assertIn("unchanged", fallback.note.lower())

    @override_settings(
        MERGE_CUSTOM_STRATEGIES={
            "cms.StrategyModel": {
                "notes": "cms.tests.test_merge_strategies.custom_concat_handler"
            }
        }
    )
    def test_custom_strategy_loaded_from_settings(self):
        resolver = StrategyResolver(self.Model, {"notes": MergeStrategy.CUSTOM})
        source = self.Model(notes="from source")
        target = self.Model(notes="from target")

        resolution = resolver.resolve_field("notes", source=source, target=target)

        self.assertEqual(resolution.value, "from target | from source")
        self.assertIn("custom handler", resolution.note)

    def test_user_prompt_raises_pending_resolution(self):
        resolver = StrategyResolver(self.Model, {"name": MergeStrategy.USER_PROMPT})

        with self.assertRaises(PendingResolution):
            resolver.resolve_field("name", source=self.Model(), target=self.Model())

    def test_merge_field_defaults_are_applied(self):
        self.Model.merge_fields = {"description": MergeStrategy.LAST_WRITE}
        resolver = StrategyResolver(self.Model, None)
        source = self.Model(description="Preferred")
        target = self.Model(description="Existing")

        resolution = resolver.resolve_field("description", source=source, target=target)

        self.assertEqual(resolution.value, "Preferred")
        self.assertIn("source", resolution.note.lower())
