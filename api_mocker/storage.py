"""MySQL-backed repository for API mock collections and endpoints."""

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import MockCollection, MockEndpoint, MockRequestLog

DEFAULT_COLLECTION_ID = "00000000-0000-0000-0000-000000000001"
RESERVED_COLLECTION_SLUGS = {
    "admin",
    "api",
    "dashboard",
    "health",
    "mock",
    "mocks",
    "repositories",
    "static",
}


def _ensure_default_collection():
    collection, _ = MockCollection.objects.get_or_create(
        id=uuid.UUID(DEFAULT_COLLECTION_ID),
        defaults={
            "name": "Default",
            "slug": "default",
            "description": "Mocks migrated from the original ungrouped workspace.",
        },
    )
    return collection


def _serialize_mock(mock):
    return {
        "id": str(mock.id),
        "collection_id": str(mock.collection_id),
        "method": mock.method,
        "path": mock.path,
        "status_code": mock.status_code,
        "response_body": mock.response_body,
        "headers": mock.headers or {},
        "latency_ms": mock.latency_ms,
        "request_count": mock.request_count,
    }


def _serialize_collection(collection):
    return {
        "id": str(collection.id),
        "name": collection.name,
        "slug": collection.slug,
        "description": collection.description,
        "mock_count": collection.mock_count if hasattr(collection, "mock_count") else collection.mocks.count(),
    }


def _serialize_request_log(entry, detail=False):
    payload = {
        "id": str(entry.id),
        "collection_id": str(entry.collection_id) if entry.collection_id else None,
        "collection_name": entry.collection.name if entry.collection else entry.collection_slug,
        "collection_slug": entry.collection_slug,
        "mock_id": str(entry.mock_id) if entry.mock_id else None,
        "method": entry.method,
        "path": entry.path,
        "response_status": entry.response_status,
        "matched": entry.matched,
        "duration_ms": entry.duration_ms,
        "created_at": entry.created_at.isoformat(),
    }
    if detail:
        payload.update({
            "query_params": entry.query_params or {},
            "request_headers": entry.request_headers or {},
            "request_body": entry.request_body,
            "response_headers": entry.response_headers or {},
            "response_body": entry.response_body,
            "remote_addr": entry.remote_addr,
        })
    return payload


def get_all(collection_id=None):
    queryset = MockEndpoint.objects.select_related("collection")
    if collection_id is not None:
        try:
            queryset = queryset.filter(collection_id=collection_id)
        except (ValidationError, ValueError):
            return []
    return [_serialize_mock(mock) for mock in queryset]


def get_collections(query=""):
    _ensure_default_collection()
    queryset = MockCollection.objects.annotate(mock_count=Count("mocks"))
    normalized_query = str(query or "").strip()
    if normalized_query:
        queryset = queryset.filter(
            Q(name__icontains=normalized_query)
            | Q(slug__icontains=normalized_query)
            | Q(description__icontains=normalized_query)
        )
    return [_serialize_collection(collection) for collection in queryset]


def collection_exists(collection_id):
    if str(collection_id) == DEFAULT_COLLECTION_ID:
        _ensure_default_collection()
        return True
    try:
        return MockCollection.objects.filter(id=collection_id).exists()
    except (ValidationError, ValueError):
        return False


def _validate_collection_identity(name, exclude_id=None):
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("collection name is required")
    slug = slugify(normalized_name)[:80]
    if not slug:
        raise ValueError("collection name must contain letters or numbers")
    if slug in RESERVED_COLLECTION_SLUGS:
        raise ValueError("this collection name conflicts with a reserved application route")

    names = MockCollection.objects.filter(name__iexact=normalized_name)
    slugs = MockCollection.objects.filter(slug=slug)
    if exclude_id is not None:
        names = names.exclude(id=exclude_id)
        slugs = slugs.exclude(id=exclude_id)
    if names.exists():
        raise ValueError("a collection with this name already exists")
    if slugs.exists():
        raise ValueError("a collection with the same URL name already exists")
    return normalized_name[:120], slug


@transaction.atomic
def create_collection(name, description=""):
    normalized_name, slug = _validate_collection_identity(name)
    try:
        collection = MockCollection.objects.create(
            name=normalized_name,
            slug=slug,
            description=str(description or "")[:500],
        )
    except IntegrityError as exc:
        raise ValueError("a collection with this name or URL already exists") from exc
    collection.mock_count = 0
    return _serialize_collection(collection)


@transaction.atomic
def update_collection(collection_id, fields):
    collection = MockCollection.objects.filter(id=collection_id).first()
    if collection is None:
        return None
    if "name" in fields:
        collection.name, collection.slug = _validate_collection_identity(
            fields["name"],
            exclude_id=collection.id,
        )
    if "description" in fields:
        collection.description = str(fields["description"] or "")[:500]
    try:
        collection.save()
    except IntegrityError as exc:
        raise ValueError("a collection with this name or URL already exists") from exc
    collection.mock_count = collection.mocks.count()
    return _serialize_collection(collection)


@transaction.atomic
def delete_collection(collection_id):
    if str(collection_id) == DEFAULT_COLLECTION_ID:
        raise ValueError("the Default collection cannot be deleted")
    collection = MockCollection.objects.filter(id=collection_id).first()
    if collection is None:
        return None
    deleted_mock_count = collection.mocks.count()
    collection.delete()
    return deleted_mock_count


@transaction.atomic
def create(mock):
    collection_id = str(mock.get("collection_id") or DEFAULT_COLLECTION_ID)
    collection = MockCollection.objects.filter(id=collection_id).first()
    if collection is None:
        if collection_id == DEFAULT_COLLECTION_ID:
            collection = _ensure_default_collection()
        else:
            raise ValueError("collection not found")
    created = MockEndpoint.objects.create(
        collection=collection,
        method=mock.get("method", "GET"),
        path=mock.get("path", "/"),
        status_code=mock.get("status_code", 200),
        response_body=mock.get("response_body", ""),
        headers=mock.get("headers") or {},
        latency_ms=mock.get("latency_ms", 0),
    )
    return _serialize_mock(created)


@transaction.atomic
def update(mock_id, updated_fields):
    mock = MockEndpoint.objects.filter(id=mock_id).first()
    if mock is None:
        return None
    if "collection_id" in updated_fields:
        collection = MockCollection.objects.filter(id=updated_fields.pop("collection_id")).first()
        if collection is None:
            raise ValueError("collection not found")
        mock.collection = collection
    for field in ("method", "path", "status_code", "response_body", "headers", "latency_ms"):
        if field in updated_fields:
            setattr(mock, field, updated_fields[field])
    mock.save()
    return _serialize_mock(mock)


def delete(mock_id):
    deleted, _ = MockEndpoint.objects.filter(id=mock_id).delete()
    return deleted > 0


def find_match(method, path):
    normalized_path = f"/{path.lstrip('/')}"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")
    for mock in MockEndpoint.objects.select_related("collection").filter(method__iexact=method):
        mock_path = f"/{mock.path.lstrip('/')}"
        if mock_path != "/":
            mock_path = mock_path.rstrip("/")
        if mock_path == normalized_path:
            return _serialize_mock(mock)
    return None


def find_collection_match(collection_slug, method, path):
    normalized_path = f"/{path.lstrip('/')}"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")
    queryset = MockEndpoint.objects.filter(
        collection__slug=collection_slug,
        method__iexact=method,
    )
    for mock in queryset:
        mock_path = f"/{mock.path.lstrip('/')}"
        if mock_path != "/":
            mock_path = mock_path.rstrip("/")
        if mock_path == normalized_path:
            return _serialize_mock(mock)
    return None


def record_request(
    *,
    collection_slug,
    mock_id,
    method,
    path,
    query_params,
    request_headers,
    request_body,
    response_status,
    response_headers,
    response_body,
    matched,
    duration_ms,
    remote_addr,
):
    collection = MockCollection.objects.filter(slug=collection_slug).first()
    if matched and mock_id:
        MockEndpoint.objects.filter(id=mock_id).update(request_count=F("request_count") + 1)
    return MockRequestLog.objects.create(
        collection=collection,
        mock_id=mock_id if matched else None,
        collection_slug=collection_slug,
        method=method,
        path=path,
        query_params=query_params,
        request_headers=request_headers,
        request_body=request_body,
        response_status=response_status,
        response_headers=response_headers,
        response_body=response_body,
        matched=matched,
        duration_ms=duration_ms,
        remote_addr=remote_addr,
    )


def get_request_history(collection_id=None, query="", limit=100):
    queryset = MockRequestLog.objects.select_related("collection", "mock")
    if collection_id:
        try:
            queryset = queryset.filter(collection_id=collection_id)
        except (ValidationError, ValueError):
            return []
    normalized_query = str(query or "").strip()
    if normalized_query:
        filters = (
            Q(method__icontains=normalized_query)
            | Q(path__icontains=normalized_query)
            | Q(collection_slug__icontains=normalized_query)
        )
        if normalized_query.isdigit():
            filters |= Q(response_status=int(normalized_query))
        queryset = queryset.filter(filters)
    return [_serialize_request_log(entry) for entry in queryset[:limit]]


def get_request_log(log_id):
    try:
        entry = MockRequestLog.objects.select_related("collection", "mock").filter(id=log_id).first()
    except (ValidationError, ValueError):
        return None
    return _serialize_request_log(entry, detail=True) if entry else None


def clear_request_history(collection_id=None):
    queryset = MockRequestLog.objects.all()
    if collection_id:
        try:
            queryset = queryset.filter(collection_id=collection_id)
        except (ValidationError, ValueError):
            return 0
    deleted, _ = queryset.delete()
    return deleted
