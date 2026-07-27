from django.db import models


class PageVisibility(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    command_center_enabled = models.BooleanField(
        default=True,
        help_text="Show the Command Center and allow access to its pages and APIs.",
    )
    api_mocker_enabled = models.BooleanField(
        default=True,
        help_text="Show the API Mocker and allow access to its management pages and APIs.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "page visibility"
        verbose_name_plural = "page visibility"

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return "Public page visibility"


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
