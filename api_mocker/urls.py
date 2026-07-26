from django.urls import path, re_path

from . import views

app_name = "api_mocker"

dashboard_urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/collections/", views.collections, name="collections"),
    path("api/collections/<uuid:collection_id>/", views.collection_detail, name="collection_detail"),
    path("api/mocks/", views.mocks_collection, name="mocks_collection"),
    path("api/mocks/<uuid:mock_id>/", views.mock_detail, name="mock_detail"),
    path("api/history/", views.request_history, name="request_history"),
    path("api/history/<uuid:log_id>/", views.request_history_detail, name="request_history_detail"),
]

public_mock_urlpatterns = [
    path("", views.serve_mock, name="serve_root"),
    re_path(r"^(?P<mock_path>.*)$", views.serve_mock, name="serve_mock"),
]
