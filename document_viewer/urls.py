from django.urls import path

from . import views

app_name = "document_viewer"

urlpatterns = [
    path("", views.index, name="home"),
    path("api/documents/load/", views.load_file, name="load"),
    path("api/documents/render/", views.render_content, name="render"),
    path("api/documents/save/", views.save_file, name="save"),
    path("api/documents/status/", views.file_status, name="status"),
]
