from django.contrib import admin

from .models import DailyNote, PageVisibility, Task

admin.site.register(DailyNote)
admin.site.register(Task)


@admin.register(PageVisibility)
class PageVisibilityAdmin(admin.ModelAdmin):
    fields = ("command_center_enabled", "api_mocker_enabled", "updated_at")
    readonly_fields = ("updated_at",)
    list_display = (
        "command_center_enabled",
        "api_mocker_enabled",
        "updated_at",
    )
    list_display_links = None
    list_editable = ("command_center_enabled", "api_mocker_enabled")
    actions = None

    def has_add_permission(self, request):
        return not PageVisibility.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
