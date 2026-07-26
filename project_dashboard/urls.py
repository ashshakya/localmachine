from django.contrib import admin
from django.urls import include, path

from api_mocker.urls import dashboard_urlpatterns, public_mock_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("mocks/", include((dashboard_urlpatterns, "api_mocker"), namespace="api_mocker")),
    path("", include("document_viewer.urls")),
    path("", include("workspace.urls")),
    path(
        "<slug:collection_slug>/",
        include((public_mock_urlpatterns, "api_mocker_public"), namespace="api_mocker_public"),
    ),
]
