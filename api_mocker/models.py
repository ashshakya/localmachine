import uuid

from django.db import models


class MockCollection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MockEndpoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(MockCollection, related_name="mocks", on_delete=models.CASCADE)
    method = models.CharField(max_length=10, default="GET")
    path = models.TextField()
    status_code = models.PositiveSmallIntegerField(default=200)
    response_body = models.TextField(blank=True)
    headers = models.JSONField(default=dict, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    request_count = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["collection__name", "path", "method"]

    def __str__(self):
        return f"{self.method} /{self.collection.slug}{self.path}"


class MockRequestLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(
        MockCollection,
        related_name="request_logs",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    mock = models.ForeignKey(
        MockEndpoint,
        related_name="request_logs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    collection_slug = models.SlugField(max_length=80)
    method = models.CharField(max_length=10)
    path = models.TextField()
    query_params = models.JSONField(default=dict, blank=True)
    request_headers = models.JSONField(default=dict, blank=True)
    request_body = models.TextField(blank=True)
    response_status = models.PositiveSmallIntegerField()
    response_headers = models.JSONField(default=dict, blank=True)
    response_body = models.TextField(blank=True)
    matched = models.BooleanField(default=False)
    duration_ms = models.PositiveIntegerField(default=0)
    remote_addr = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.method} {self.path} → {self.response_status}"
