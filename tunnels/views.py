import secrets
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import TunnelIdentity
from .names import normalize_tunnel_name


@require_GET
def standalone_agent(request):
    script = Path(__file__).with_name("standalone_agent.py").read_text(encoding="utf-8")
    response = HttpResponse(script, content_type="text/x-python; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="localmachine-tunnel.py"'
    response["Cache-Control"] = "public, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _bearer_token(request):
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _error(message, status):
    response = JsonResponse({"ok": False, "error": message}, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _token_response(identity, token, status):
    response = JsonResponse(
        {
            "ok": True,
            "username": identity.username,
            "token": token,
            "public_url": f"https://{identity.username}.{settings.TUNNEL_DOMAIN}",
        },
        status=status,
    )
    response["Cache-Control"] = "no-store"
    return response


def _registration_is_allowed(request):
    expected = settings.TUNNEL_REGISTRATION_SECRET
    if not expected:
        return True
    supplied = request.headers.get("X-Tunnel-Registration-Key", "")
    return bool(supplied and secrets.compare_digest(supplied, expected))


@csrf_exempt
@require_http_methods(["PUT", "POST", "DELETE"])
def tunnel_identity(request, username):
    try:
        normalized_username = normalize_tunnel_name(username)
    except ValueError as exc:
        return _error(str(exc), 400)

    if request.method == "PUT":
        if not _registration_is_allowed(request):
            return _error("A valid tunnel registration key is required.", 403)

        identity = TunnelIdentity(username=normalized_username)
        token = identity.issue_token()
        try:
            with transaction.atomic():
                identity.save(force_insert=True)
        except IntegrityError:
            return _error(f'Tunnel username "{normalized_username}" already exists.', 409)
        return _token_response(identity, token, 201)

    with transaction.atomic():
        identity = (
            TunnelIdentity.objects.select_for_update()
            .filter(username=normalized_username)
            .first()
        )
        if identity is None:
            return _error(f'Tunnel username "{normalized_username}" was not found.', 404)
        if not identity.token_matches(_bearer_token(request)):
            response = _error("A valid current tunnel token is required.", 401)
            response["WWW-Authenticate"] = "Bearer"
            return response

        if request.method == "POST":
            token = identity.issue_token()
            identity.save(update_fields=["token_digest", "updated_at"])
            return _token_response(identity, token, 200)

        identity.delete()
        return HttpResponse(status=204, headers={"Cache-Control": "no-store"})
