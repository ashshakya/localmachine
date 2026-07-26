import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MockCollection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="MockEndpoint",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("method", models.CharField(default="GET", max_length=10)),
                ("path", models.TextField()),
                ("status_code", models.PositiveSmallIntegerField(default=200)),
                ("response_body", models.TextField(blank=True)),
                ("headers", models.JSONField(blank=True, default=dict)),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "collection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mocks",
                        to="api_mocker.mockcollection",
                    ),
                ),
            ],
            options={"ordering": ["collection__name", "path", "method"]},
        ),
    ]
