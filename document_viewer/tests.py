import json
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse

from workspace.models import PageVisibility

from .services import resolve_document


class DocumentViewerTests(TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.default_directory = Path(self.temporary_directory.name)
        self.settings_override = override_settings(DOCUMENT_VIEWER_DEFAULT_DIRECTORY=self.default_directory)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.temporary_directory.cleanup()

    def post_json(self, name, payload):
        return self.client.post(reverse(f"document_viewer:{name}"), json.dumps(payload), content_type="application/json")

    def test_documentation_studio_is_homepage(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Documentation Studio")
        self.assertContains(response, reverse("workspace:dashboard"))
        self.assertContains(response, reverse("api_mocker:dashboard"))
        self.assertContains(response, 'aria-label="Product navigation"')
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, 'id="pasteMarkdown"')
        self.assertContains(response, "Paste Markdown directly")

    def test_disabled_tools_are_hidden_from_product_navigation(self):
        PageVisibility.objects.update_or_create(
            pk=1,
            defaults={
                "command_center_enabled": False,
                "api_mocker_enabled": False,
            },
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("workspace:dashboard"))
        self.assertNotContains(response, reverse("api_mocker:dashboard"))

    def test_relative_paths_start_in_default_directory(self):
        self.assertEqual(resolve_document("guides/start.md"), (self.default_directory / "guides/start.md").resolve())

    def test_load_render_and_save_markdown(self):
        document = self.default_directory / "guide.md"
        document.write_text("# Hello\n\nOriginal", encoding="utf-8")

        loaded = self.post_json("load", {"path": str(document)})
        self.assertEqual(loaded.status_code, 200)
        payload = loaded.json()
        self.assertEqual(payload["kind"], "markdown")
        self.assertEqual(payload["content"], "# Hello\n\nOriginal")

        rendered = self.post_json("render", {"kind": "markdown", "content": "# New title"})
        self.assertEqual(rendered.status_code, 200)
        self.assertIn("<h1", rendered.json()["html"])

        saved = self.post_json("save", {
            "path": str(document),
            "content": "# Updated",
            "mtime_ns": payload["mtime_ns"],
        })
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(document.read_text(encoding="utf-8"), "# Updated")

    def test_rejects_unsupported_files(self):
        document = self.default_directory / "notes.txt"
        document.write_text("nope", encoding="utf-8")
        response = self.post_json("load", {"path": str(document)})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only Markdown", response.json()["error"])

    def test_save_detects_external_change(self):
        document = self.default_directory / "guide.html"
        document.write_text("<h1>One</h1>", encoding="utf-8")
        original = self.post_json("load", {"path": str(document)}).json()
        document.write_text("<h1>Changed elsewhere</h1>", encoding="utf-8")

        response = self.post_json("save", {
            "path": str(document),
            "content": "<h1>Mine</h1>",
            "mtime_ns": original["mtime_ns"],
        })
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["conflict"])

    def test_csrf_is_required_for_file_writes(self):
        csrf_client = self.client_class(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("document_viewer:save"),
            data='{"path":"guide.md","content":"# Test"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_markdown_rendering_does_not_require_a_csrf_cookie(self):
        csrf_client = self.client_class(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("document_viewer:render"),
            data='{"kind":"markdown","content":"# Test"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<h1", response.json()["html"])
