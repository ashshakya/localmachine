import json
import time

from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from workspace.visibility import require_enabled_page

from . import storage

MOCK_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
MAX_CAPTURE_BYTES = 1024 * 1024
SENSITIVE_REQUEST_HEADERS = {"authorization", "cookie", "proxy-authorization", "x-api-key"}


def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _capture_text(value):
    raw = value if isinstance(value, bytes) else str(value or "").encode("utf-8")
    truncated = len(raw) > MAX_CAPTURE_BYTES
    text = raw[:MAX_CAPTURE_BYTES].decode("utf-8", errors="replace")
    return f"{text}\n\n[truncated at 1 MB]" if truncated else text


def _capture_request_headers(request):
    return {
        str(key): "[redacted]" if str(key).lower() in SENSITIVE_REQUEST_HEADERS else str(value)
        for key, value in request.headers.items()
    }


def _record_mock_request(request, collection_slug, mock, response, started_at):
    try:
        storage.record_request(
            collection_slug=collection_slug,
            mock_id=mock.get("id") if mock else None,
            method=request.method,
            path=request.get_full_path(),
            query_params={key: request.GET.getlist(key) for key in request.GET},
            request_headers=_capture_request_headers(request),
            request_body=_capture_text(request.body),
            response_status=response.status_code,
            response_headers={str(key): str(value) for key, value in response.headers.items()},
            response_body=_capture_text(response.content),
            matched=mock is not None,
            duration_ms=max(0, round((time.monotonic() - started_at) * 1000)),
            remote_addr=str(request.META.get("REMOTE_ADDR") or "")[:64],
        )
    except (DatabaseError, ValueError):
        # Request history must never prevent a configured mock from responding.
        pass
    return response


def _validate_fields(data, partial=False):
    fields = {}

    if not partial or "collection_id" in data:
        collection_id = str(data.get("collection_id") or storage.DEFAULT_COLLECTION_ID)
        if not storage.collection_exists(collection_id):
            return None, "collection not found"
        fields["collection_id"] = collection_id

    if not partial or "method" in data:
        method = str(data.get("method") or "GET").upper()
        if method not in MOCK_METHODS:
            return None, f"method must be one of {', '.join(sorted(MOCK_METHODS))}"
        fields["method"] = method

    if not partial or "path" in data:
        path = str(data.get("path") or "/")
        if not path.startswith("/"):
            return None, "path must start with /"
        fields["path"] = path

    if not partial or "status_code" in data:
        try:
            status_code = int(data.get("status_code", 200))
        except (TypeError, ValueError):
            return None, "status_code must be a number"
        if not 100 <= status_code <= 599:
            return None, "status_code must be between 100 and 599"
        fields["status_code"] = status_code

    if not partial or "response_body" in data:
        fields["response_body"] = str(data.get("response_body") or "")

    if not partial or "headers" in data:
        headers = data.get("headers") or {}
        if not isinstance(headers, dict):
            return None, "headers must be an object"
        fields["headers"] = {str(key): str(value) for key, value in headers.items()}

    if not partial or "latency_ms" in data:
        try:
            latency_ms = int(data.get("latency_ms", 0))
        except (TypeError, ValueError):
            return None, "latency_ms must be a number"
        if not 0 <= latency_ms <= 30000:
            return None, "latency_ms must be between 0 and 30000"
        fields["latency_ms"] = latency_ms

    return fields, None


@require_GET
@require_enabled_page("api_mocker")
def dashboard(request):
    return render(request, "api_mocker/index.html")


@csrf_exempt
@require_enabled_page("api_mocker")
def mocks_collection(request):
    if request.method == "GET":
        return JsonResponse(storage.get_all(request.GET.get("collection_id")), safe=False)
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"}, status=405)

    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "request body must be a JSON object"}, status=400)
    fields, error = _validate_fields(data)
    if error:
        return JsonResponse({"error": error}, status=400)
    try:
        return JsonResponse(storage.create(fields), status=201)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@csrf_exempt
@require_enabled_page("api_mocker")
def mock_detail(request, mock_id):
    if request.method == "PUT":
        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "request body must be a JSON object"}, status=400)
        fields, error = _validate_fields(data, partial=True)
        if error:
            return JsonResponse({"error": error}, status=400)
        try:
            updated = storage.update(mock_id, fields)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        if updated is None:
            return JsonResponse({"error": "mock not found"}, status=404)
        return JsonResponse(updated)

    if request.method == "DELETE":
        if not storage.delete(mock_id):
            return JsonResponse({"error": "mock not found"}, status=404)
        return HttpResponse(status=204)

    return JsonResponse({"error": "method not allowed"}, status=405)


@csrf_exempt
@require_enabled_page("api_mocker")
def collections(request):
    if request.method == "GET":
        return JsonResponse(storage.get_collections(request.GET.get("q", "")), safe=False)
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"}, status=405)

    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "request body must be a JSON object"}, status=400)
    try:
        return JsonResponse(
            storage.create_collection(data.get("name"), data.get("description", "")),
            status=201,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@csrf_exempt
@require_enabled_page("api_mocker")
def collection_detail(request, collection_id):
    if request.method == "PUT":
        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "request body must be a JSON object"}, status=400)
        fields = {key: data[key] for key in ("name", "description") if key in data}
        try:
            updated = storage.update_collection(collection_id, fields)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        if updated is None:
            return JsonResponse({"error": "collection not found"}, status=404)
        return JsonResponse(updated)

    if request.method == "DELETE":
        try:
            deleted_mock_count = storage.delete_collection(collection_id)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        if deleted_mock_count is None:
            return JsonResponse({"error": "collection not found"}, status=404)
        return JsonResponse({"ok": True, "deleted_mock_count": deleted_mock_count})

    return JsonResponse({"error": "method not allowed"}, status=405)


@csrf_exempt
@require_enabled_page("api_mocker")
def request_history(request):
    collection_id = request.GET.get("collection_id")
    if request.method == "GET":
        try:
            limit = max(1, min(int(request.GET.get("limit", 100)), 200))
        except (TypeError, ValueError):
            limit = 100
        return JsonResponse(
            storage.get_request_history(
                collection_id=collection_id,
                query=request.GET.get("q", ""),
                limit=limit,
            ),
            safe=False,
        )
    if request.method == "DELETE":
        deleted_count = storage.clear_request_history(collection_id=collection_id)
        return JsonResponse({"ok": True, "deleted_count": deleted_count})
    return JsonResponse({"error": "method not allowed"}, status=405)


@require_GET
@require_enabled_page("api_mocker")
def request_history_detail(request, log_id):
    entry = storage.get_request_log(log_id)
    if entry is None:
        return JsonResponse({"error": "request history entry not found"}, status=404)
    return JsonResponse(entry)


@csrf_exempt
def serve_mock(request, collection_slug, mock_path=""):
    started_at = time.monotonic()
    if request.method not in MOCK_METHODS:
        return JsonResponse({"error": "method not supported"}, status=405)

    path = f"/{mock_path}" if mock_path else "/"
    mock = storage.find_collection_match(collection_slug, request.method, path)
    if mock is None:
        response = JsonResponse(
            {
                "error": "No mock configured for this method + path",
                "method": request.method,
                "collection": collection_slug,
                "path": path,
            },
            status=404,
        )
        return _record_mock_request(request, collection_slug, None, response, started_at)

    latency_ms = mock.get("latency_ms", 0) or 0
    if latency_ms:
        time.sleep(min(int(latency_ms), 30000) / 1000)

    headers = {
        str(key): str(value)
        for key, value in (mock.get("headers") or {}).items()
        if str(key).lower() not in {"content-length", "transfer-encoding", "connection"}
    }
    if not any(key.lower() == "content-type" for key in headers):
        headers["Content-Type"] = "application/json"

    body = "" if request.method == "HEAD" else str(mock.get("response_body") or "")
    response = HttpResponse(body, status=int(mock.get("status_code", 200)), headers=headers)
    return _record_mock_request(request, collection_slug, mock, response, started_at)
