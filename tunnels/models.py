import hashlib
import secrets

from django.core.exceptions import ValidationError
from django.db import models

from .names import normalize_tunnel_name


class TunnelIdentity(models.Model):
    username = models.CharField(max_length=63, unique=True)
    token_digest = models.CharField(max_length=64, editable=False)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["username"]
        verbose_name = "tunnel identity"
        verbose_name_plural = "tunnel identities"

    def clean(self):
        try:
            self.username = normalize_tunnel_name(self.username)
        except ValueError as exc:
            raise ValidationError({"username": str(exc)}) from exc

    @staticmethod
    def digest_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue_token(self):
        token = secrets.token_urlsafe(32)
        self.token_digest = self.digest_token(token)
        return token

    def token_matches(self, token):
        if not self.enabled or not token:
            return False
        return secrets.compare_digest(self.token_digest, self.digest_token(token))

    def save(self, *args, **kwargs):
        self.username = normalize_tunnel_name(self.username)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.username
