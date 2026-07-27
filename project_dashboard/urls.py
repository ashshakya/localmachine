from django.contrib import admin
from django.urls import include, path

from api_mocker.urls import dashboard_urlpatterns, public_mock_urlpatterns
from project_dashboard import seo

urlpatterns = [
    path("robots.txt", seo.robots_txt, name="robots_txt"),
    path("sitemap.xml", seo.sitemap_xml, name="sitemap_xml"),
    path("admin/", admin.site.urls),
    path("mocks/", include((dashboard_urlpatterns, "api_mocker"), namespace="api_mocker")),
    path("", include("document_viewer.urls")),
    path("", include("workspace.urls")),
    path(
        "<slug:collection_slug>/",
        include((public_mock_urlpatterns, "api_mocker_public"), namespace="api_mocker_public"),
    ),
]
