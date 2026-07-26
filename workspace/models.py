from django.db import models


class DailyNote(models.Model):
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        note, _ = cls.objects.get_or_create(pk=1)
        return note


class Task(models.Model):
    title = models.CharField(max_length=240)
    repository = models.CharField(max_length=120, blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["completed", "-created_at"]
