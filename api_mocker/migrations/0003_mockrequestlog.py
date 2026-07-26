import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api_mocker", "0002_import_legacy_json")]

    operations = [
        migrations.CreateModel(
            name="MockRequestLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("collection_slug", models.SlugField(max_length=80)),
                ("method", models.CharField(max_length=10)),
                ("path", models.TextField()),
                ("query_params", models.JSONField(blank=True, default=dict)),
                ("request_headers", models.JSONField(blank=True, default=dict)),
                ("request_body", models.TextField(blank=True)),
                ("response_status", models.PositiveSmallIntegerField()),
                ("response_headers", models.JSONField(blank=True, default=dict)),
                ("response_body", models.TextField(blank=True)),
                ("matched", models.BooleanField(default=False)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("remote_addr", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "collection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="request_logs",
                        to="api_mocker.mockcollection",
                    ),
                ),
                (
                    "mock",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="request_logs",
                        to="api_mocker.mockendpoint",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
