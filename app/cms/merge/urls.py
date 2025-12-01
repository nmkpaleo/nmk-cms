"""URL routes for merge tooling, including per-field selection endpoints."""

from django.contrib.admin.views.decorators import staff_member_required
from django.urls import path

from cms.merge.views import FieldSelectionMergeView
from cms.views import MergeCandidateAdminView, MergeCandidateAPIView

app_name = "merge"


urlpatterns = [
    path("", staff_member_required(MergeCandidateAdminView.as_view()), name="merge_candidates"),
    path(
        "search/",
        staff_member_required(MergeCandidateAPIView.as_view()),
        name="merge_candidate_search",
    ),
    path(
        "field-selection/",
        staff_member_required(FieldSelectionMergeView.as_view()),
        name="merge_field_selection",
    ),
]
