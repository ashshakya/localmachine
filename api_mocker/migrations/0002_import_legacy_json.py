import json
import uuid
from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.utils.text import slugify

DEFAULT_COLLECTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
RESERVED_SLUGS = {"admin", "api", "dashboard", "health", "mock", "mocks", "repositories", "static"}


def _uuid(value, namespace):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"api-mocker:{namespace}:{value}")


def import_legacy_json(apps, schema_editor):
    database_name = str(schema_editor.connection.settings_dict.get("NAME", ""))
    if database_name.startswith("test_") or database_name.startswith("file:memorydb_"):
        return

    source = Path(settings.API_MOCKER_LEGACY_DATA_FILE)
    if not source.is_file():
        return
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    if isinstance(raw, list):
        raw = {
            "collections": [{
                "id": str(DEFAULT_COLLECTION_ID),
                "name": "Default",
                "slug": "default",
                "description": "Mocks migrated from the original ungrouped workspace.",
            }],
            "mocks": raw,
        }
    if not isinstance(raw, dict):
        return

    MockCollection = apps.get_model("api_mocker", "MockCollection")
    MockEndpoint = apps.get_model("api_mocker", "MockEndpoint")
    source_collections = raw.get("collections") if isinstance(raw.get("collections"), list) else []
    source_mocks = raw.get("mocks") if isinstance(raw.get("mocks"), list) else []
    if not source_collections:
        source_collections = [{
            "id": str(DEFAULT_COLLECTION_ID),
            "name": "Default",
            "slug": "default",
            "description": "Mocks migrated from the original ungrouped workspace.",
        }]

    collection_ids = {}
    used_names = set()
    used_slugs = set()
    for index, item in enumerate(source_collections):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or f"collection-{index}")
        collection_id = _uuid(source_id, "collection")
        base_name = str(item.get("name") or "Untitled collection").strip()[:120] or "Untitled collection"
        name = base_name
        suffix = 2
        while name.casefold() in used_names:
            name = f"{base_name} ({suffix})"[:120]
            suffix += 1
        base_slug = slugify(str(item.get("slug") or name))[:80] or "collection"
        slug = base_slug
        suffix = 2
        while slug in used_slugs or slug in RESERVED_SLUGS:
            slug = f"{base_slug}-{suffix}"[:80]
            suffix += 1
        collection, _ = MockCollection.objects.update_or_create(
            id=collection_id,
            defaults={
                "name": name,
                "slug": slug,
                "description": str(item.get("description") or "")[:500],
            },
        )
        collection_ids[source_id] = collection.id
        used_names.add(name.casefold())
        used_slugs.add(slug)

    default_id = collection_ids.get(str(DEFAULT_COLLECTION_ID))
    if default_id is None:
        default, _ = MockCollection.objects.get_or_create(
            id=DEFAULT_COLLECTION_ID,
            defaults={
                "name": "Default",
                "slug": "default",
                "description": "Mocks migrated from the original ungrouped workspace.",
            },
        )
        default_id = default.id

    for index, item in enumerate(source_mocks):
        if not isinstance(item, dict):
            continue
        mock_id = _uuid(item.get("id") or f"mock-{index}", "mock")
        collection_id = collection_ids.get(str(item.get("collection_id")), default_id)
        try:
            status_code = int(item.get("status_code", 200))
            latency_ms = int(item.get("latency_ms", 0))
        except (TypeError, ValueError):
            continue
        headers = item.get("headers") if isinstance(item.get("headers"), dict) else {}
        MockEndpoint.objects.update_or_create(
            id=mock_id,
            defaults={
                "collection_id": collection_id,
                "method": str(item.get("method") or "GET").upper()[:10],
                "path": str(item.get("path") or "/"),
                "status_code": max(100, min(status_code, 599)),
                "response_body": str(item.get("response_body") or ""),
                "headers": headers,
                "latency_ms": max(0, min(latency_ms, 30000)),
            },
        )


class Migration(migrations.Migration):
    dependencies = [("api_mocker", "0001_initial")]

    operations = [migrations.RunPython(import_legacy_json, migrations.RunPython.noop)]
