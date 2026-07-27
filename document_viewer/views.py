import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from markdown import markdown

from project_dashboard.seo import absolute_public_url

from .services import MAX_FILE_SIZE, file_metadata, read_document, resolve_document, write_document


def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _error(message, status=400, **extra):
    return JsonResponse({"ok": False, "error": str(message), **extra}, status=status)


@require_GET
@ensure_csrf_cookie
def index(request):
    default_directory = f"{settings.DOCUMENT_VIEWER_DEFAULT_DIRECTORY}/"
    return render(request, "document_viewer/index.html", {
        "canonical_url": absolute_public_url(request, request.path),
        "default_document_directory": default_directory,
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
    })


@require_POST
def load_file(request):
    data = _json_body(request)
    if data is None:
        return _error("Request body must be a JSON object.")
    try:
        path = resolve_document(data.get("path", ""))
        content = read_document(path)
        return JsonResponse({
            "ok": True,
            "path": str(path),
            "name": path.name,
            "kind": "markdown" if path.suffix.lower() in {".md", ".markdown"} else "html",
            "content": content,
            **file_metadata(path),
        })
    except (OSError, ValueError) as exc:
        return _error(exc)


@require_POST
@csrf_exempt
def render_content(request):
    data = _json_body(request)
    if data is None:
        return _error("Request body must be a JSON object.")
    content = data.get("content", "")
    kind = data.get("kind", "markdown")
    if not isinstance(content, str):
        return _error("Document content must be text.")
    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        return _error("The document is larger than the 5 MB limit.")
    if kind not in {"markdown", "html"}:
        return _error("Document kind must be markdown or html.")

    rendered = content
    if kind == "markdown":
        rendered = markdown(
            content,
            extensions=["extra", "sane_lists", "smarty", "toc"],
            output_format="html5",
        )
    return JsonResponse({"ok": True, "html": rendered})


@require_POST
def save_file(request):
    data = _json_body(request)
    if data is None:
        return _error("Request body must be a JSON object.")
    try:
        path = resolve_document(data.get("path", ""))
        content = data.get("content", "")
        expected_mtime = data.get("mtime_ns")
        if not isinstance(content, str):
            raise ValueError("Document content must be text.")
        if len(content.encode("utf-8")) > MAX_FILE_SIZE:
            raise ValueError("The document is larger than the 5 MB limit.")

        current = file_metadata(path)
        if expected_mtime is not None and current["mtime_ns"] != str(expected_mtime) and not data.get("force"):
            return _error("The file changed outside this editor.", status=409, conflict=True)

        write_document(path, content)
        return JsonResponse({"ok": True, **file_metadata(path)})
    except (OSError, ValueError) as exc:
        return _error(exc)


@require_POST
def file_status(request):
    data = _json_body(request)
    if data is None:
        return _error("Request body must be a JSON object.")
    try:
        path = resolve_document(data.get("path", ""))
        return JsonResponse({"ok": True, **file_metadata(path)})
    except (OSError, ValueError) as exc:
        return _error(exc)
