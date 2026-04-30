from django.urls import re_path

from core.views import ExportDataView, ProfileDetailView, ProfileListCreateView, ProfileSearchView

urlpatterns = [
    re_path(r"^profiles/search/?$", ProfileSearchView.as_view(), name="profile-search"),
    re_path(r"^profiles/export/$", ExportDataView.as_view(), name="profile-export"),
    re_path(r"^profiles/?$", ProfileListCreateView.as_view(), name="profile-list-create"),
    re_path(
        r"^profiles/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$",
        ProfileDetailView.as_view(),
        name="profile-detail",
    ),
]
