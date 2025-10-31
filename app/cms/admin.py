from typing import Any

from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db.models import Count, OuterRef, Exists
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget, DateWidget
from simple_history.admin import SimpleHistoryAdmin

from .forms import AccessionNumberSeriesAdminForm, DrawerRegisterForm
from .admin_merge import MergeAdminMixin
from .merge import merge_records

from .models import (
    AccessionNumberSeries,
    NatureOfSpecimen,
    Element,
    Person,
    Identification,
    Taxon,
    TaxonomyImport,
    Media,
    MediaQCLog,
    MediaQCComment,
    LLMUsageRecord,
    SpecimenGeology,
    GeologicalContext,
    AccessionReference,
    Locality,
    Place,
    Collection,
    Accession,
    AccessionRow,
    Subject,
    Comment,
    FieldSlip,
    Reference,
    Storage,
    User,
    Preparation,
    PreparationMaterial,
    PreparationMedia,
    DrawerRegister,
    Scanning,
    UnexpectedSpecimen,
    MergeLog,
)
from .resources import *

import logging

from django import forms
from django.utils.html import format_html, format_html_join
from django.utils.timezone import now, localtime
from django.contrib.auth import get_user_model

from .taxonomy import NowTaxonomySyncService

# Configure the logger
logging.basicConfig(level=logging.INFO)  # You can adjust the level as needed (DEBUG, WARNING, ERROR, etc.)
logger = logging.getLogger(__name__)  # Creates a logger specific to the current module

from cms.models import Accession

User = get_user_model()

import pprint


def _sync_permission_codename() -> str:
    return f"{Taxon._meta.app_label}.can_sync"


def _user_can_sync_taxa(user) -> bool:
    return bool(user and user.is_active and user.has_perm(_sync_permission_codename()))


def _serialize_changeset(update) -> list[dict[str, str]]:
    changes = []
    for field, new_value in update.changes.items():
        if field == "accepted_taxon":
            old_value = (
                update.instance.accepted_taxon.taxon_name if update.instance.accepted_taxon else ""
            )
            new_display = getattr(update.record, "accepted_name", "")
        else:
            old_value = getattr(update.instance, field, "")
            new_display = new_value
        changes.append(
            {
                "label": field.replace("_", " ").title(),
                "old": old_value or "—",
                "new": new_display or "—",
            }
        )
    return changes


def _serialize_preview_for_template(preview):
    return {
        "accepted_creates": [
            {
                "name": record.name,
                "rank": record.rank,
                "author_year": record.author_year,
                "external_id": record.external_id,
            }
            for record in preview.accepted_to_create
        ],
        "accepted_updates": [
            {
                "name": update.record.name,
                "external_id": update.record.external_id,
                "changes": _serialize_changeset(update),
            }
            for update in preview.accepted_to_update
        ],
        "synonym_creates": [
            {
                "name": record.name,
                "accepted_name": record.accepted_name,
                "external_id": record.external_id,
            }
            for record in preview.synonyms_to_create
        ],
        "synonym_updates": [
            {
                "name": update.record.name,
                "accepted_name": update.record.accepted_name,
                "external_id": update.record.external_id,
                "changes": _serialize_changeset(update),
            }
            for update in preview.synonyms_to_update
        ],
        "deactivations": [
            {
                "name": taxon.taxon_name,
                "external_id": taxon.external_id,
            }
            for taxon in preview.to_deactivate
        ],
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "context": issue.context,
            }
            for issue in preview.issues
        ],
    }


def _taxonomy_sync_preview_view(request):
    if not _user_can_sync_taxa(request.user):
        raise PermissionDenied

    service = NowTaxonomySyncService()

    try:
        preview = service.preview()
    except Exception as exc:  # pragma: no cover - defensive guard for runtime errors
        messages.error(
            request,
            _("Unable to fetch taxonomy data: %(error)s") % {"error": exc},
        )
        return redirect(
            f"admin:{Taxon._meta.app_label}_{Taxon._meta.model_name}_changelist"
        )

    preview_data = _serialize_preview_for_template(preview)

    context = {
        **admin.site.each_context(request),
        "opts": Taxon._meta,
        "title": _("Sync Taxa Now"),
        "preview": preview,
        "preview_data": preview_data,
        "counts": preview.counts,
        "source_version": preview.source_version,
        "apply_url": reverse("taxonomy_sync_apply"),
        "back_url": reverse(
            f"admin:{Taxon._meta.app_label}_{Taxon._meta.model_name}_changelist"
        ),
    }
    return TemplateResponse(request, "admin/taxonomy/sync_preview.html", context)


def _taxonomy_sync_apply_view(request):
    if not _user_can_sync_taxa(request.user):
        raise PermissionDenied

    if request.method != "POST":
        return redirect("taxonomy_sync_preview")

    service = NowTaxonomySyncService()

    try:
        result = service.sync(apply=True)
    except Exception as exc:  # pragma: no cover - defensive guard for runtime errors
        messages.error(
            request,
            _("Unable to apply taxonomy sync: %(error)s") % {"error": exc},
        )
        return redirect("taxonomy_sync_preview")

    import_log = result.import_log
    log_url = None
    if import_log:
        log_url = reverse(
            f"admin:{import_log._meta.app_label}_{import_log._meta.model_name}_change",
            args=[import_log.pk],
        )

    preview = result.preview
    context = {
        **admin.site.each_context(request),
        "opts": Taxon._meta,
        "title": _("Sync Taxa Now"),
        "result": result,
        "preview": preview,
        "preview_data": _serialize_preview_for_template(preview),
        "counts": preview.counts,
        "source_version": preview.source_version,
        "import_log": import_log,
        "log_url": log_url,
        "back_url": reverse(
            f"admin:{Taxon._meta.app_label}_{Taxon._meta.model_name}_changelist"
        ),
        "preview_url": reverse("taxonomy_sync_preview"),
        "success": bool(import_log and import_log.ok),
    }

    return TemplateResponse(request, "admin/taxonomy/sync_result.html", context)


taxonomy_sync_preview_view = admin.site.admin_view(_taxonomy_sync_preview_view)
taxonomy_sync_apply_view = admin.site.admin_view(_taxonomy_sync_apply_view)


class MergeAdminActionMixin:
    """Provides a reusable action for invoking the merge engine manually."""

    actions = ["merge_records_action"]

    def merge_records_action(
        self,
        request,
        queryset,
        *,
        target=None,
        strategy_map=None,
        dry_run=False,
        archive=True,
    ):
        if not getattr(settings, "MERGE_TOOL_FEATURE", False):
            if request is not None:
                self.message_user(
                    request,
                    "The merge tool is currently disabled; no records were merged.",
                    level=logging.WARNING,
                )
            return

        selected = list(queryset)

        if target is None:
            if request is None:
                raise ValueError(
                    "Provide a `target` instance when calling this action manually from the shell."
                )
            if len(selected) < 2:
                self.message_user(
                    request,
                    "Select at least two records to merge.",
                    level=logging.WARNING,
                )
                return

            target_id = request.POST.get("merge_target")
            if not target_id:
                opts = self.model._meta
                changelist_url = reverse(
                    f"admin:{opts.app_label}_{opts.model_name}_changelist"
                )

                serializer = getattr(self, "_serialise_instance", None)
                preview_columns: list[str] = []
                serialised_rows: list[dict[str, Any]] = []
                if callable(serializer):
                    for obj in selected:
                        summary = serializer(obj)
                        preview_items = (summary or {}).get("preview", []) or []
                        preview_map: dict[str, Any] = {}
                        for item in preview_items:
                            label = item.get("field")
                            if not label:
                                continue
                            if label not in preview_columns:
                                preview_columns.append(label)
                            preview_map[label] = item.get("value")
                        serialised_rows.append(
                            {
                                "object": obj,
                                "label": (summary or {}).get("label", str(obj)),
                                "preview_map": preview_map,
                            }
                        )

                if not serialised_rows:
                    object_rows = [
                        {
                            "object": obj,
                            "label": str(obj),
                            "preview_values": [],
                        }
                        for obj in selected
                    ]
                else:
                    object_rows = []
                    for row in serialised_rows:
                        preview_values = [
                            row["preview_map"].get(column, "—") for column in preview_columns
                        ]
                        object_rows.append(
                            {
                                "object": row["object"],
                                "label": row["label"],
                                "preview_values": preview_values,
                            }
                        )

                context = {
                    "title": "Choose a target record",
                    "action_checkbox_name": ACTION_CHECKBOX_NAME,
                    "opts": opts,
                    "objects": selected,
                    "object_rows": object_rows,
                    "preview_columns": preview_columns,
                    "action_name": "merge_records_action",
                    "merge_target_field": "merge_target",
                    "changelist_url": changelist_url,
                    "select_across": request.POST.get("select_across"),
                }
                return render(
                    request,
                    "admin/cms/merge/manual_action_confirm.html",
                    context,
                )

            try:
                target = next(
                    obj for obj in selected if str(obj.pk) == str(target_id)
                )
            except StopIteration:
                try:
                    target = queryset.model._default_manager.get(pk=target_id)
                except queryset.model.DoesNotExist:
                    self.message_user(
                        request,
                        "Selected target is no longer available.",
                        level=logging.ERROR,
                    )
                    return
                selected.append(target)

        user = getattr(request, "user", None) if request is not None else None
        sources = [obj for obj in selected if obj.pk != getattr(target, "pk", None)]
        for source in sources:
            merge_records(
                source,
                target,
                strategy_map or {},
                user=user,
                dry_run=dry_run,
                archive=archive,
            )

        if request is not None:
            self.message_user(
                request,
                f"Merged {len(sources)} record(s) into {target}",
                level=logging.INFO,
            )

    merge_records_action.short_description = "Merge selected records (manual invocation)"
    merge_records_action.allowed_permissions = ("change",)


class HistoricalImportExportAdmin(SimpleHistoryAdmin, ImportExportModelAdmin):
    """Base admin class combining simple history and import-export."""
    pass


class HistoricalAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    """Base admin class for models using simple history."""
    pass

class DuplicateFilter(admin.SimpleListFilter):
    title = 'By Duplicate specimen_no + prefix'
    parameter_name = 'duplicates'

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Yes – Show Duplicates'),
            ('no', 'No – Show Unique Only'),
        ]

    def queryset(self, request, queryset):
        duplicate_subquery = (
            Accession.objects
            .filter(
                specimen_no=OuterRef('specimen_no'),
                specimen_prefix=OuterRef('specimen_prefix')
            )
            .values('specimen_no', 'specimen_prefix')
            .annotate(dups=Count('id'))
            .filter(dups__gt=1)
        )

        # Always annotate
        annotated = queryset.annotate(
            has_duplicates=Exists(duplicate_subquery)
        )

        if self.value() == 'yes':
            return annotated.filter(has_duplicates=True)
        elif self.value() == 'no':
            return annotated.filter(has_duplicates=False)
        else:
            return annotated  # ✅ return the annotated base queryset


class ManualImportMediaFilter(admin.SimpleListFilter):
    title = _("Manual QC provenance")
    parameter_name = "manual_import"

    def lookups(self, request, model_admin):
        return [
            ("manual", _("Manual QC import")),
            ("other", _("Other sources")),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if isinstance(value, list):
            value = value[0] if value else None
        if value in {"manual", "other"}:
            records = list(queryset)
            manual_ids = [
                media.pk for media in records if media.is_manual_import
            ]
            if value == "manual":
                return queryset.filter(pk__in=manual_ids)
            return queryset.exclude(pk__in=manual_ids)
        return queryset


class AccessionManualImportFilter(admin.SimpleListFilter):
    title = _("Manual QC provenance")
    parameter_name = "manual_import"

    def lookups(self, request, model_admin):
        return [
            ("manual", _("Manual QC import")),
            ("other", _("Other sources")),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if isinstance(value, list):
            value = value[0] if value else None
        if value in {"manual", "other"}:
            records = list(queryset.prefetch_related("media"))
            manual_ids = [
                accession.pk for accession in records if accession.is_manual_import
            ]
            if value == "manual":
                return queryset.filter(pk__in=manual_ids)
            return queryset.exclude(pk__in=manual_ids)
        return queryset

# Accession Model
class AccessionAdmin(HistoricalImportExportAdmin):
    resource_class = AccessionResource
    list_display = (
        'collection_abbreviation',
        'specimen_prefix_abbreviation',
        'specimen_no',
        'instance_number',
        'accessioned_by',
        'is_duplicate_display',
        'manual_import_badge',
    )
    list_filter = (
        'collection',
        'specimen_prefix',
        'accessioned_by',
        DuplicateFilter,
        AccessionManualImportFilter,
    )
    search_fields = ('specimen_no', 'collection__abbreviation', 'specimen_prefix__abbreviation', 'accessioned_by__username')
    ordering = ('specimen_no', 'specimen_prefix__abbreviation')

    def collection_abbreviation(self, obj):
        return obj.collection.abbreviation if obj.collection else None
    collection_abbreviation.short_description = 'Collection'

    def specimen_prefix_abbreviation(self, obj):
        return obj.specimen_prefix.abbreviation if obj.specimen_prefix else None
    specimen_prefix_abbreviation.short_description = 'Specimen Prefix'

    def is_duplicate_display(self, obj):
        count = Accession.objects.filter(
            specimen_no=obj.specimen_no,
            specimen_prefix=obj.specimen_prefix
        ).count()
        if count > 1:
            return format_html('<span style="color: orange;">Yes ({})</span>', count)
        return format_html('<span style="color: green;">No</span>')
    is_duplicate_display.short_description = 'Duplicate?'

    def manual_import_badge(self, obj):
        metadata = obj.get_manual_import_metadata()
        if not metadata:
            return "—"
        row_id = metadata.get("row_id") or _("Manual QC")
        created_by = metadata.get("created_by") or ""
        created_on = metadata.get("created_on") or ""
        tooltip_parts = [part for part in (created_by, created_on) if part]
        tooltip = " \u2014 ".join(tooltip_parts) if tooltip_parts else row_id
        return format_html(
            '<span class="manual-import" title="{}"><i class="fa fa-clipboard-check" aria-hidden="true"></i> {}</span>',
            tooltip,
            row_id,
        )

    manual_import_badge.short_description = _("Manual QC provenance")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related("media")

    def get_list_display(self, request):
        columns = list(super().get_list_display(request))
        if not request.user.has_perm("cms.can_import_manual_qc"):
            columns = [column for column in columns if column != "manual_import_badge"]
        return columns

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if not request.user.has_perm("cms.can_import_manual_qc"):
            filters = [flt for flt in filters if flt is not AccessionManualImportFilter]
        return filters


@admin.register(AccessionNumberSeries)
class AccessionNumberSeriesAdmin(HistoricalAdmin):
    form = AccessionNumberSeriesAdminForm
    change_form_template = "admin/cms/accessionnumberseries/change_form.html"
    list_display = ('user', 'start_from', 'end_at', 'current_number', 'is_active')
    list_filter = ('is_active', 'user')

    fieldsets = (
        (None, {
            'fields': ('user', 'start_from', 'current_number', 'count', 'is_active')
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return [f.name for f in self.model._meta.fields if f.editable and f.name != "id"] + ['count']
        return super().get_readonly_fields(request, obj)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['add'] = object_id is None  # True if adding
        return super().changeform_view(request, object_id, form_url, extra_context=extra_context)

    class Media:
        js = (
            "js/set_start_from.js",
            "js/accession_series_live_preview.js",
        )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)

        if db_field.name == "user":
            try:
                if hasattr(formfield.widget, 'attrs'):
                    formfield.widget.attrs.update(
                        AccessionNumberSeriesAdminForm._widget_metadata()
                    )

            except Exception as e:
                # Just log the issue, don't block the form rendering or validation
                import logging
                logging.warning(f"Series mapping failed: {e}")

        return formfield

class AccessionReferenceAdmin(HistoricalImportExportAdmin):
    resource_class = AccessionReferenceResource
    list_display = ('collection_abbreviation', 'specimen_prefix_abbreviation', 'specimen_number', 'page', 'reference')
    search_fields = ('accession__specimen_no', 'specimen_suffix', 'reference',)
    ordering = ('accession__collection__abbreviation', 'accession__specimen_prefix__abbreviation', 'accession__specimen_no',)

    def collection_abbreviation(self, obj):
        return obj.accession.collection.abbreviation if obj.accession.collection else None
    collection_abbreviation.short_description = 'Collection'

    def specimen_prefix_abbreviation(self, obj):
        return obj.accession.specimen_prefix.abbreviation if obj.accession.specimen_prefix else None
    specimen_prefix_abbreviation.short_description = 'Specimen Prefix'

    def specimen_number(self, obj):
        return obj.accession.specimen_no if obj.accession.specimen_no else None
    specimen_number.short_description = 'Specimen Number'

class AccessionRowAdmin(HistoricalImportExportAdmin):
    resource_class = AccessionRowResource
    list_display = ('collection_abbreviation', 'specimen_prefix_abbreviation', 'specimen_number', 'specimen_suffix', 'storage')
    search_fields = ('accession__specimen_no', 'specimen_suffix', 'storage__area',)
    ordering = ('accession__collection__abbreviation', 'accession__specimen_prefix__abbreviation', 'accession__specimen_no', 'specimen_suffix',)

    def collection_abbreviation(self, obj):
        return obj.accession.collection.abbreviation if obj.accession.collection else None
    collection_abbreviation.short_description = 'Collection'

    def specimen_prefix_abbreviation(self, obj):
        return obj.accession.specimen_prefix.abbreviation if obj.accession.specimen_prefix else None
    specimen_prefix_abbreviation.short_description = 'Specimen Prefix'

    def specimen_number(self, obj):
        return obj.accession.specimen_no if obj.accession.specimen_no else None
    specimen_number.short_description = 'Specimen Number'

# Comment Model
class CommentAdmin(HistoricalAdmin):
    list_display = ('specimen_no', 'comment', 'status', 'subject', 'comment_by')
    search_fields = ('comment', 'comment_by')
    list_filter = ('status', 'subject', 'comment_by')

# Collection Model
class CollectionAdmin(HistoricalImportExportAdmin):
    resource_class = CollectionResource
    list_display = ('abbreviation', 'description')
    search_fields = ('abbreviation', 'description')

# Element Model
class ElementAdmin(HistoricalImportExportAdmin):
    resource_class = ElementResource
    list_display = ('parent_element', 'name')
    list_filter = ('parent_element__name',)
    search_fields = ('name', 'parent_element__name')
    ordering = ('name',)

# FieldSlip Model
class FieldSlipAdmin(MergeAdminActionMixin, MergeAdminMixin, HistoricalImportExportAdmin):
    resource_class = FieldSlipResource
    list_display = ('field_number', 'discoverer', 'collector', 'collection_date', 'verbatim_locality', 'verbatim_taxon', 'verbatim_element')
    search_fields = ('field_number', 'discoverer', 'collector', 'verbatim_locality')
    list_filter = ('verbatim_locality',)
    ordering = ('verbatim_locality', 'field_number')

#  GeologicalContext
class GeologicalContextAdmin(HistoricalImportExportAdmin):
    list_display = ('geological_context_type', 'unit_name', 'name', 'parent_geological_context')
    search_fields = ('geological_context_type', 'unit_name', 'name')
    list_filter = ('geological_context_type',)
    ordering = ('name',)

# Identification Model
class IdentificationAdmin(HistoricalImportExportAdmin):
    resource_class = IdentificationResource
    list_display = ('accession_row', 'identification_qualifier', 'verbatim_identification', 'taxon', 'identified_by', 'date_identified', )
    search_fields = ('accession_row__accession__specimen_no', 'verbatim_identification', 'taxon__taxon_name', 'identified_by__last_name')
    list_filter = ('date_identified',)
    ordering = ('accession_row', 'date_identified')

# Locality Model
class LocalityAdmin(HistoricalImportExportAdmin):
    resource_class = LocalityResource
    list_display = ('abbreviation', 'name')
    search_fields = ('abbreviation', 'name')
    ordering = ('abbreviation', 'name')


class PlaceAdmin(HistoricalImportExportAdmin):
    resource_class = PlaceResource
    list_display = ('name', 'place_type', 'locality', 'relation_type', 'related_place')
    list_filter = ('place_type', 'relation_type', 'locality')
    search_fields = ('name', 'locality__name')

# Media


class MediaQCLogInline(admin.TabularInline):
    model = MediaQCLog
    extra = 0
    fields = (
        "created_on",
        "change_type",
        "field_name",
        "old_value_display",
        "new_value_display",
        "description",
        "changed_by",
        "comments_display",
    )
    readonly_fields = fields
    can_delete = False
    ordering = ("-created_on",)

    def has_add_permission(self, request, obj=None):
        return False

    def _format_value(self, value):
        if value in (None, {}, []):
            return "-"
        formatted = pprint.pformat(value, compact=True, width=60)
        return format_html("<pre style='white-space: pre-wrap;'>{}</pre>", formatted)

    def old_value_display(self, obj):
        return self._format_value(obj.old_value)

    old_value_display.short_description = "Previous Value"

    def new_value_display(self, obj):
        return self._format_value(obj.new_value)

    new_value_display.short_description = "New Value"

    def comments_display(self, obj):
        comments = obj.comments.all()
        if not comments:
            return "-"
        return format_html_join(
            "<br>",
            "<strong>{}</strong>: {} <em>({})</em>",
            [
                (
                    comment.created_by.get_full_name()
                    or comment.created_by.get_username()
                    if comment.created_by
                    else "System",
                    comment.comment,
                    localtime(comment.created_on).strftime("%Y-%m-%d %H:%M"),
                )
                for comment in comments
            ],
        )

    comments_display.short_description = "Comments"


class LLMUsageRecordInline(admin.StackedInline):
    model = LLMUsageRecord
    can_delete = False
    extra = 0
    fields = (
        "model_name",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost_usd",
        "response_id",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class MediaAdmin(HistoricalImportExportAdmin):
    list_display = (
        'file_name',
        'type',
        'format',
        'media_location',
        'license',
        'rights_holder',
        'scanning',
        'qc_status',
        'rows_rearranged',
        "manual_import_badge",
        "created_by",
        "created_on",
    )
    readonly_fields = (
        "created_by",
        "modified_by",
        "created_on",
        "modified_on",
        "intern_checked_by",
        "intern_checked_on",
        "expert_checked_by",
        "expert_checked_on",
    )
    search_fields = (
        'file_name',
        'type',
        'format',
        'media_location',
        'license',
        'rights_holder',
        'scanning__drawer__code',
    )
    autocomplete_fields = [
        'accession',
        'accession_row',
        'scanning',
    ]
    list_filter = ('type', 'format', 'qc_status', 'rows_rearranged', ManualImportMediaFilter)
    ordering = ('file_name',)
    inlines = [MediaQCLogInline, LLMUsageRecordInline]
    fieldsets = (
        (
            None,
            {
                'fields': (
                    'accession',
                    'accession_row',
                    'scanning',
                    'file_name',
                    'media_location',
                    'type',
                    'format',
                    'license',
                    'rights_holder',
                )
            },
        ),
        (
            'Quality Control',
            {
                'fields': (
                    'qc_status',
                    'rows_rearranged',
                    'intern_checked_by',
                    'intern_checked_on',
                    'expert_checked_by',
                    'expert_checked_on',
                )
            },
        ),
        (
            'OCR',
            {
                'fields': (
                    'ocr_status',
                    'ocr_data',
                )
            },
        ),
        (
            'Audit',
            {
                'fields': (
                    'created_by',
                    'created_on',
                    'modified_by',
                    'modified_on',
                ),
                'classes': ('collapse',),
            },
        ),
    )

    def manual_import_badge(self, obj):
        metadata = obj.get_manual_import_metadata()
        if not metadata:
            return "—"
        row_id = metadata.get("row_id") or _("Manual QC")
        created_by = metadata.get("created_by") or ""
        created_on = metadata.get("created_on") or ""
        tooltip_parts = [part for part in (created_by, created_on) if part]
        tooltip = " \u2014 ".join(tooltip_parts) if tooltip_parts else row_id
        return format_html(
            '<span class="manual-import" title="{}"><i class="fa fa-clipboard-check" aria-hidden="true"></i> {}</span>',
            tooltip,
            row_id,
        )

    manual_import_badge.short_description = _("Manual QC provenance")

    def get_list_display(self, request):
        columns = list(super().get_list_display(request))
        if not request.user.has_perm("cms.can_import_manual_qc"):
            columns = [column for column in columns if column != "manual_import_badge"]
        return columns

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if not request.user.has_perm("cms.can_import_manual_qc"):
            filters = [flt for flt in filters if flt is not ManualImportMediaFilter]
        return filters


class MediaQCCommentInline(admin.TabularInline):
    model = MediaQCComment
    extra = 0
    fields = ("comment", "created_by", "created_on")
    readonly_fields = ("created_on",)
    ordering = ("created_on",)


@admin.register(MediaQCLog)
class MediaQCLogAdmin(admin.ModelAdmin):
    list_display = ("media", "change_type", "field_name", "created_on", "changed_by")
    search_fields = ("media__file_name", "description", "field_name")
    list_filter = ("change_type", "created_on")
    readonly_fields = (
        "media",
        "change_type",
        "field_name",
        "old_value",
        "new_value",
        "description",
        "changed_by",
        "created_on",
    )
    inlines = [MediaQCCommentInline]
    ordering = ("-created_on",)

    def has_add_permission(self, request):
        return False

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, MediaQCComment) and not instance.created_by:
                instance.created_by = request.user
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()


@admin.register(LLMUsageRecord)
class LLMUsageRecordAdmin(admin.ModelAdmin):
    list_display = (
        "media",
        "model_name",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost_usd",
        "created_at",
    )
    search_fields = (
        "media__file_name",
        "media__uuid",
        "media__id",
        "model_name",
        "response_id",
    )
    list_filter = ("model_name", "created_at")
    readonly_fields = (
        "media",
        "model_name",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost_usd",
        "response_id",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False


# NatureOfSpecimen Model
class NatureOfSpecimenAdmin(HistoricalImportExportAdmin):
    resource_class = NatureOfSpecimenResource
    list_display = ('accession_row', 'element', 'side', 'condition', 'fragments')
    search_fields = ('accession_row__id', 'element__name', 'side', 'condition')
    ordering = ('accession_row', 'element')

# Person Model
class PersonAdmin(HistoricalImportExportAdmin):
    resource_class = PersonResource
    list_display = ('first_name', 'last_name', 'orcid')
    search_fields = ('first_name', 'last_name', 'orcid')

# Reference Model
class ReferenceAdmin(MergeAdminActionMixin, MergeAdminMixin, HistoricalImportExportAdmin):
    resource_class = ReferenceResource
    list_display = ('citation', 'doi')
    search_fields = ('citation', 'doi')

# SpecimenGeology
class SpecimenGeologyAdmin(HistoricalImportExportAdmin):
    list_display = ('accession', 'earliest_geological_context', 'latest_geological_context')
    search_fields = ('accession__specimen_prefix',)
    ordering = ('accession',)

# Storage Model
class StorageAdmin(MergeAdminActionMixin, MergeAdminMixin, HistoricalImportExportAdmin):
    resource_class = StorageResource
    list_display = ('area', 'parent_area')
    search_fields = ('area', 'parent_area__area')

# Subject Model
class SubjectAdmin(HistoricalAdmin):
    list_display = ('subject_name',)
    search_fields = ('subject_name',)
    list_filter = ('subject_name',)

# TaxonAdmin: Customizes the admin interface for the Taxon model
class TaxonAdmin(HistoricalImportExportAdmin):
    resource_class = TaxonResource

    # Columns to display in the admin list view
    list_display = ('taxon_name', 'taxon_rank', 'order', 'family', 'subfamily', 'tribe', 'genus', 'species', 'formatted_subspecies')
    list_filter = ('taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family')
    ordering = ('taxon_name', 'taxon_rank', 'kingdom', 'phylum', 'class_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')
    search_fields = ('taxon_name', 'order', 'superfamily', 'family', 'subfamily', 'tribe', 'genus', 'species', 'infraspecific_epithet', 'scientific_name_authorship')

    # Custom method to display the formatted taxon name
    def formatted_name(self, obj):
        return str(obj)  # Calls __str__ method of the Taxon model
    formatted_name.short_description = 'Taxon Name'

    # Custom method to handle subspecies display
    def formatted_subspecies(self, obj):
        return obj.infraspecific_epithet if obj.infraspecific_epithet else "-"
    formatted_subspecies.short_description = 'Subspecies'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        has_permission = _user_can_sync_taxa(request.user)
        extra_context["has_sync_permission"] = has_permission
        if has_permission:
            extra_context["sync_taxa_url"] = reverse("taxonomy_sync_preview")
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(TaxonomyImport)
class TaxonomyImportAdmin(HistoricalImportExportAdmin):
    list_display = ("id", "source", "source_version", "started_at", "finished_at", "ok")
    list_filter = ("source", "ok", "started_at", "finished_at")
    search_fields = ("source_version",)
    readonly_fields = ("report_json",)

# User Model
class UserAdmin(HistoricalImportExportAdmin):
    resource_class = UserResource
    list_display = ('username', 'first_name', 'last_name', 'email')
    search_fields = ('username', 'first_name', 'last_name', 'email')

class PreparationAdminForm(forms.ModelForm):
    """ Custom form for validation and dynamic field handling in admin. """
    
    class Meta:
        model = Preparation
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        preparator = cleaned_data.get("preparator")
        curator = cleaned_data.get("curator")
        status = cleaned_data.get("status")
        approval_status = cleaned_data.get("approval_status")

        # Ensure Curator is different from Preparator
        if preparator and curator and preparator == curator:
            raise ValidationError({"curator": "The curator must be different from the preparator."})

        # Ensure curation is only done for completed preparations
        if approval_status in ["approved", "declined"] and status != "Completed":
            raise ValidationError({"approval_status": "Preparation must be 'Completed' before approval or rejection."})

        return cleaned_data

class PreparationMediaInline(admin.TabularInline):
    model = PreparationMedia
    extra = 1
    autocomplete_fields = ["media"]
    fields = ("media", "context", "notes")


@admin.register(Preparation)
class PreparationAdmin(HistoricalImportExportAdmin):
    """ Custom admin panel for Preparation model. """

    resource_class = PreparationResource
    form = PreparationAdminForm
    list_display = ("accession_row", "preparator", "status", "curator", "approval_status", "approval_date", "admin_colored_status")
    list_filter = ("status", "approval_status", "preparator", "curator")
    search_fields = ("accession_row__accession__specimen_no", "preparator__username", "curator__username")
    readonly_fields = ("approval_date", "created_on", "modified_on", "admin_status_info")
    inlines = [PreparationMediaInline]
    
    fieldsets = (
        ("Preparation Details", {
            "fields": ("accession_row", "preparator", "preparation_type", "reason", "status", "started_on", "completed_on", "notes"),
        }),
        ("Storage & Condition", {
            "fields": ("original_storage", "temporary_storage", "condition_before", "condition_after", "preparation_method", "chemicals_used", "materials_used"),
            "classes": ("collapse",),
        }),
        ("Curation & Approval", {
            "fields": ("curator", "approval_status", "approval_date", "curator_comments"),
            "classes": ("collapse",),
        }),
        ("Audit Info", {
            "fields": ("created_on", "modified_on", "admin_status_info"),
        }),
    )

    def save_model(self, request, obj, form, change):
        """ Custom save logic to track status changes and auto-fill fields. """
        if not obj.preparator:
            obj.preparator = request.user  # Assign current user if no preparator set
        
        if obj.approval_status in ["approved", "declined"] and not obj.approval_date:
            obj.approval_date = now()  # Auto-fill approval date if approved/declined

        super().save_model(request, obj, form, change)

    def admin_colored_status(self, obj):
        """ Displays colored status for better visibility in admin. """
        color_map = {
            "Pending": "orange",
            "In Progress": "blue",
            "Completed": "green",
            "Approved": "darkgreen",
            "Declined": "red",
        }
        return format_html(f'<span style="color: {color_map.get(obj.status, "black")}; font-weight: bold;">{obj.status}</span>')
    
    admin_colored_status.short_description = "Status"

    def admin_status_info(self, obj):
        """ Displays summary of preparation status in admin view. """
        return format_html(
            "<b>Status:</b> {}<br><b>Curator:</b> {}<br><b>Approval Date:</b> {}",
            obj.status,
            obj.curator.username if obj.curator else "Not Assigned",
            obj.approval_date.strftime("%Y-%m-%d %H:%M") if obj.approval_date else "Not Approved",
        )

    admin_status_info.short_description = "Status Overview"

@admin.register(PreparationMaterial)
class PreparationMaterialAdmin(HistoricalImportExportAdmin):
    resource_class = PreparationMaterialResource
    list_display = ("name", "description")
    search_fields = ("name",)

# Register the models with the customized admin interface
admin.site.register(Accession, AccessionAdmin)
admin.site.register(AccessionReference, AccessionReferenceAdmin)
admin.site.register(AccessionRow, AccessionRowAdmin)
admin.site.register(Collection, CollectionAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(Element, ElementAdmin)
admin.site.register(FieldSlip, FieldSlipAdmin)
admin.site.register(Identification, IdentificationAdmin)
admin.site.register(Locality, LocalityAdmin)
admin.site.register(Place, PlaceAdmin)
admin.site.register(NatureOfSpecimen, NatureOfSpecimenAdmin)
admin.site.register(Person, PersonAdmin)
admin.site.register(Reference, ReferenceAdmin)
admin.site.register(Storage, StorageAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Taxon, TaxonAdmin)
# Unregister safely (may already be registered)
if admin.site.is_registered(User):
    admin.site.unregister(User)
# Optional: Register with custom admin if you need to modify
    admin.site.register(User, UserAdmin)
admin.site.register(Media, MediaAdmin)
admin.site.register(SpecimenGeology, SpecimenGeologyAdmin)
admin.site.register(GeologicalContext, GeologicalContextAdmin)
admin.site.register(UnexpectedSpecimen, HistoricalAdmin)


@admin.register(DrawerRegister)
class DrawerRegisterAdmin(HistoricalImportExportAdmin):
    resource_class = DrawerRegisterResource
    form = DrawerRegisterForm
    list_display = ("code", "description", "estimated_documents", "scanning_status")
    list_filter = ("scanning_status",)
    search_fields = ("code", "description")
    filter_horizontal = ("localities", "taxa", "scanning_users")


@admin.register(Scanning)
class ScanningAdmin(admin.ModelAdmin):
    list_display = ("drawer", "user", "start_time", "end_time")
    list_filter = ("user", "drawer")
    search_fields = ("drawer__code", "user__username")

# ----------------------------------------------------------------------
# Flat file import integration
# ----------------------------------------------------------------------
from django.urls import path, reverse
from django.contrib import messages
from django.shortcuts import render, redirect
from django import forms
from .importer import import_flat_file


class FlatImportForm(forms.Form):
    """Simple form for uploading a combined import file."""

    import_file = forms.FileField(label="Import CSV")


def flat_file_import_view(request):
    """Handle the flat file import process."""
    if request.method == "POST":
        form = FlatImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                count = import_flat_file(form.cleaned_data["import_file"])
                messages.success(request, f"Imported {count} rows successfully.")
                return redirect("admin:index")
            except Exception as exc:  # pragma: no cover - best effort
                messages.error(request, f"Import failed: {exc}")
    else:
        form = FlatImportForm()

    context = {"form": form, "title": "Flat File Import"}
    return render(request, "admin/flat_file_import.html", context)


original_get_urls = admin.site.get_urls


def get_urls():
    urls = original_get_urls()
    custom_urls = [
        path(
            "flat-file-import/",
            admin.site.admin_view(flat_file_import_view),
            name="flat-file-import",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = get_urls
@admin.register(MergeLog)
class MergeLogAdmin(admin.ModelAdmin):
    list_display = (
        "model_label",
        "source_pk",
        "target_pk",
        "performed_by",
        "executed_at",
    )
    list_filter = ("model_label", "performed_by")
    search_fields = ("source_pk", "target_pk", "model_label")
    readonly_fields = (
        "model_label",
        "source_pk",
        "target_pk",
        "resolved_values",
        "strategy_map",
        "source_snapshot",
        "target_before",
        "target_after",
        "performed_by",
        "executed_at",
        "created_on",
        "modified_on",
        "created_by",
        "modified_by",
    )

