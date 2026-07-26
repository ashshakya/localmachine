import json
import shutil
import subprocess
import sys
from pathlib import Path

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import DailyNote, Task
from .services import dashboard_snapshot, discover_repositories, find_repository, repository_detail_snapshot

COMMIT_RANGES = [
    (7, "7 days"),
    (30, "30 days"),
    (90, "3 months"),
    (180, "6 months"),
    (365, "1 year"),
    (730, "2 years"),
    (0, "All time"),
]


def _commit_range(request):
    try:
        days = int(request.GET.get("days", "30"))
    except (TypeError, ValueError):
        return 30
    return days if days == 0 or 1 <= days <= 3650 else 30


def dashboard(request):
    days = _commit_range(request)
    snapshot = dashboard_snapshot(days=days)
    return render(request, "workspace/dashboard.html", {
        **snapshot,
        "commit_ranges": COMMIT_RANGES,
        "note": DailyNote.current(),
        "tasks": Task.objects.all(),
    })


def repository_detail(request, repository_name):
    repo = find_repository(repository_name)
    if repo is None:
        raise Http404("Repository was not found in the configured workspace.")
    days = _commit_range(request)
    snapshot = repository_detail_snapshot(repo, days=days)
    return render(request, "workspace/repository_detail.html", {
        **snapshot,
        "commit_ranges": COMMIT_RANGES,
        "tasks": Task.objects.filter(repository=repository_name),
    })


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def snapshot_api(request):
    return JsonResponse(dashboard_snapshot(days=_commit_range(request)))


@require_POST
def open_repository(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "The repository request is invalid."}, status=400)

    requested_path = Path(str(payload.get("path", ""))).expanduser().resolve()
    allowed_paths = {repo.resolve() for repo in discover_repositories()}
    if requested_path not in allowed_paths:
        return JsonResponse({"ok": False, "error": "Repository is outside the configured workspace."}, status=403)

    launch_commands = []
    if sys.platform == "darwin" and Path("/usr/bin/open").is_file():
        # Launch Services can locate Sublime Merge even when it was installed
        # outside /Applications or the Django process has a limited PATH.
        launch_commands.append(["/usr/bin/open", "-a", "Sublime Merge", str(requested_path)])

    smerge = shutil.which("smerge")
    if not smerge:
        app_cli = Path("/Applications/Sublime Merge.app/Contents/SharedSupport/bin/smerge")
        smerge = str(app_cli) if app_cli.is_file() else ""
    if smerge:
        launch_commands.append([smerge, str(requested_path)])

    if not launch_commands:
        return JsonResponse({"ok": False, "error": "Sublime Merge is not installed or its CLI is unavailable."}, status=503)

    errors = []
    for command in launch_commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
            continue
        if result.returncode == 0:
            return JsonResponse({"ok": True, "repository": requested_path.name})
        errors.append(result.stderr.strip() or f"Launcher exited with status {result.returncode}.")

    return JsonResponse(
        {"ok": False, "error": errors[-1] if errors else "Sublime Merge could not be opened."},
        status=500,
    )


@require_POST
def save_note(request):
    payload = json.loads(request.body or b"{}")
    note = DailyNote.current()
    note.content = str(payload.get("content", ""))[:10000]
    note.save(update_fields=["content", "updated_at"])
    return JsonResponse({"ok": True, "updated_at": note.updated_at.isoformat()})


@require_POST
def create_task(request):
    payload = json.loads(request.body or b"{}")
    title = str(payload.get("title", "")).strip()
    if not title:
        return JsonResponse({"ok": False, "error": "A task title is required."}, status=400)
    task = Task.objects.create(title=title[:240], repository=str(payload.get("repository", ""))[:120])
    return JsonResponse({"ok": True, "task": {"id": task.pk, "title": task.title, "repository": task.repository, "completed": task.completed}})


@require_POST
def toggle_task(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    task.completed = not task.completed
    task.save(update_fields=["completed", "updated_at"])
    return JsonResponse({"ok": True, "completed": task.completed})
