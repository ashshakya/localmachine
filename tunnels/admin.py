from django.contrib import admin

from .models import TunnelIdentity


@admin.register(TunnelIdentity)
class TunnelIdentityAdmin(admin.ModelAdmin):
    list_display = ("username", "enabled", "created_at", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("username",)
    readonly_fields = ("token_digest", "created_at", "updated_at")
