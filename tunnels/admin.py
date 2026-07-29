from django.contrib import admin

from .models import TunnelIdentity


@admin.register(TunnelIdentity)
class TunnelIdentityAdmin(admin.ModelAdmin):
    list_display = ("username", "owner", "enabled", "created_at", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("username", "owner__username")
    autocomplete_fields = ("owner",)
    readonly_fields = (
        "token_digest",
        "token_ciphertext",
        "created_at",
        "updated_at",
    )
