from unittest.mock import patch
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from .models import DailyNote, Task
from .services import _remote_link


SNAPSHOT = {
    "generated_at": "2026-07-21T00:00:00+00:00",
    "workspace_root": "/workspace",
    "repositories": [],
    "activity": [],
    "services": [],
    "contributors": [],
    "range_days": 30,
    "range_label": "Last 30 days",
    "range_short_label": "30 days",
    "stats": {"repositories": 0, "open_changes": 0, "commits_in_range": 0, "commits_30d": 0, "healthy_services": 0, "total_services": 0, "clean_repositories": 0},
}

DETAIL_SNAPSHOT = {
    "generated_at": "2026-07-21T00:00:00+00:00",
    "repository": {"name": "gringotts", "path": "/workspace/gringotts", "branch": "main", "health": "clean", "is_clean": True, "changes": 0, "modified": 0, "untracked": 0, "ahead": 0, "behind": 0, "remote_url": "", "last_commit": {"hash": "abc123", "subject": "Test", "author": "A", "relative": "now"}},
    "range_days": 90, "range_label": "Last 3 months", "range_short_label": "3 months",
    "activity": [], "contributors": [], "branches": [], "working_files": [], "file_types": [], "heatmap_weeks": [],
    "first_commit": {"iso": "", "relative": "", "author": "", "hash": "", "subject": ""},
    "last_commit": {"iso": "", "relative": "", "author": "", "hash": "", "subject": ""},
    "stats": {"total_commits": 12, "commits_in_range": 4, "contributors": 2, "branches": 1, "tags": 0, "tracked_files": 20, "files_touched": 3, "additions": 10, "deletions": 2, "merges": 1, "age_days": 100, "commits_per_week": 1.2},
}


class DashboardTests(TestCase):
    def test_azure_ssh_remote_becomes_clickable_web_url(self):
        remote = "git@ssh.dev.azure.com:v3/GoFynd/FyndPlatformCore/gringotts"
        self.assertEqual(
            _remote_link(remote),
            "https://dev.azure.com/GoFynd/FyndPlatformCore/_git/gringotts",
        )

    @patch("workspace.views.dashboard_snapshot", return_value=SNAPSHOT)
    def test_dashboard_renders(self, _snapshot):
        response = self.client.get(reverse("workspace:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reverse("workspace:dashboard"), "/dashboard/")
        self.assertContains(response, "Your work, as it is now")
        self.assertContains(response, "No static tasks here")
        self.assertContains(response, reverse("api_mocker:dashboard"))
        self.assertContains(response, 'aria-label="Product navigation"')
        self.assertContains(response, reverse("document_viewer:home"))

    @patch("workspace.views.dashboard_snapshot", return_value=SNAPSHOT)
    def test_snapshot_api(self, _snapshot):
        response = self.client.get(reverse("workspace:snapshot"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stats"]["repositories"], 0)

    @patch("workspace.views.dashboard_snapshot", return_value=SNAPSHOT)
    def test_snapshot_api_uses_selected_commit_range(self, snapshot):
        response = self.client.get(reverse("workspace:snapshot"), {"days": "365"})
        self.assertEqual(response.status_code, 200)
        snapshot.assert_called_once_with(days=365)

    @patch("workspace.views.dashboard_snapshot", return_value=SNAPSHOT)
    def test_snapshot_api_accepts_custom_commit_days(self, snapshot):
        response = self.client.get(reverse("workspace:snapshot"), {"days": "120"})
        self.assertEqual(response.status_code, 200)
        snapshot.assert_called_once_with(days=120)

    @patch("workspace.views.dashboard_snapshot", return_value=SNAPSHOT)
    def test_invalid_commit_range_falls_back_to_30_days(self, snapshot):
        response = self.client.get(reverse("workspace:snapshot"), {"days": "forever"})
        self.assertEqual(response.status_code, 200)
        snapshot.assert_called_once_with(days=30)

    @patch("workspace.views.repository_detail_snapshot", return_value=DETAIL_SNAPSHOT)
    @patch("workspace.views.find_repository", return_value=Path("/workspace/gringotts"))
    def test_repository_detail_renders_live_summary(self, _find, detail):
        response = self.client.get(reverse("workspace:repository_detail", args=["gringotts"]), {"days": "90"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Repository intelligence")
        self.assertContains(response, "12")
        self.assertContains(response, 'aria-label="Product navigation"')
        self.assertContains(response, reverse("api_mocker:dashboard"))
        detail.assert_called_once_with(Path("/workspace/gringotts"), days=90)

    @patch("workspace.views.find_repository", return_value=None)
    def test_repository_detail_rejects_unknown_repository(self, _find):
        response = self.client.get(reverse("workspace:repository_detail", args=["missing"]))
        self.assertEqual(response.status_code, 404)

    def test_note_is_persisted(self):
        response = self.client.post(reverse("workspace:save_note"), data='{"content":"Ship the dashboard"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DailyNote.current().content, "Ship the dashboard")

    def test_task_create_and_toggle(self):
        response = self.client.post(reverse("workspace:create_task"), data='{"title":"Review branch","repository":"gringotts"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        task = Task.objects.get()
        toggle = self.client.post(reverse("workspace:toggle_task", args=[task.pk]), data="{}", content_type="application/json")
        self.assertTrue(toggle.json()["completed"])

    @patch("workspace.views.sys.platform", "linux")
    @patch("workspace.views.subprocess.run")
    @patch("workspace.views.shutil.which", return_value="/usr/local/bin/smerge")
    @patch("workspace.views.discover_repositories", return_value=[__import__("pathlib").Path("/workspace/gringotts")])
    def test_open_repository_uses_sublime_merge(self, _repositories, _which, run):
        run.return_value.returncode = 0
        response = self.client.post(
            reverse("workspace:open_repository"),
            data='{"path":"/workspace/gringotts"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["/usr/local/bin/smerge", "/workspace/gringotts"])

    @patch("workspace.views.Path.is_file", return_value=True)
    @patch("workspace.views.sys.platform", "darwin")
    @patch("workspace.views.subprocess.run")
    @patch("workspace.views.shutil.which", return_value=None)
    @patch("workspace.views.discover_repositories", return_value=[__import__("pathlib").Path("/workspace/gringotts")])
    def test_open_repository_uses_macos_launch_services(self, _repositories, _which, run, _is_file):
        run.return_value.returncode = 0
        response = self.client.post(
            reverse("workspace:open_repository"),
            data='{"path":"/workspace/gringotts"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/open", "-a", "Sublime Merge", "/workspace/gringotts"],
        )

    @patch("workspace.views.sys.platform", "linux")
    @patch("workspace.views.subprocess.run")
    @patch("workspace.views.shutil.which", return_value="/usr/local/bin/smerge")
    @patch("workspace.views.discover_repositories", return_value=[__import__("pathlib").Path("/workspace/gringotts")])
    def test_open_repository_reports_launcher_failure(self, _repositories, _which, run):
        run.return_value.returncode = 1
        run.return_value.stderr = "Sublime Merge rejected the repository."
        response = self.client.post(
            reverse("workspace:open_repository"),
            data='{"path":"/workspace/gringotts"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], "Sublime Merge rejected the repository.")

    @patch("workspace.views.discover_repositories", return_value=[__import__("pathlib").Path("/workspace/gringotts")])
    def test_open_repository_rejects_paths_outside_workspace(self, _repositories):
        response = self.client.post(
            reverse("workspace:open_repository"),
            data='{"path":"/tmp/not-a-repository"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
