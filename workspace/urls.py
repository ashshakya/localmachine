from django.urls import path
from . import views

app_name = "workspace"
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("repositories/<str:repository_name>/", views.repository_detail, name="repository_detail"),
    path("health/", views.health, name="health"),
    path("api/snapshot/", views.snapshot_api, name="snapshot"),
    path("api/repositories/open/", views.open_repository, name="open_repository"),
    path("api/note/", views.save_note, name="save_note"),
    path("api/tasks/", views.create_task, name="create_task"),
    path("api/tasks/<int:task_id>/toggle/", views.toggle_task, name="toggle_task"),
]
