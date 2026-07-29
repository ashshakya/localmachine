from pathlib import Path

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import EmailAuthenticationForm, EmailRegistrationForm
from .models import TunnelIdentity
from .names import normalize_tunnel_name


class TunnelLoginView(LoginView):
    template_name = "tunnels/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


@require_GET
def standalone_agent(request):
    script = Path(__file__).with_name("standalone_agent.py").read_text(encoding="utf-8")
    response = HttpResponse(script, content_type="text/x-python; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="localmachine-tunnel.py"'
    response["Cache-Control"] = "public, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def register(request):
    if request.user.is_authenticated:
        return redirect("tunnels:dashboard")
    form = EmailRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            form.add_error("email", "An account with this email already exists.")
        else:
            login(request, user, backend="tunnels.auth.EmailBackend")
            return redirect("tunnels:dashboard")
    response = render(request, "tunnels/register.html", {"form": form})
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def sign_out(request):
    logout(request)
    return redirect("tunnels:login")


def _control_origin(request):
    if settings.PUBLIC_SITE_URL:
        return settings.PUBLIC_SITE_URL
    return f"{request.scheme}://{request.get_host()}"


def _serialize_identity(identity, request):
    token = identity.reveal_token()
    return {
        "username": identity.username,
        "token": token,
        "token_available": bool(token),
        "public_url": f"https://{identity.username}.{settings.TUNNEL_DOMAIN}",
        "agent_url": f"{_control_origin(request)}/tunnel",
        "enabled": identity.enabled,
        "created_at": identity.created_at,
        "updated_at": identity.updated_at,
    }


@login_required
@require_GET
def dashboard(request):
    identities = list(
        TunnelIdentity.objects.filter(owner=request.user).order_by("-created_at")
    )
    tunnels = [_serialize_identity(identity, request) for identity in identities]
    response = render(
        request,
        "tunnels/dashboard.html",
        {
            "tunnels": tunnels,
            "tunnel_domain": settings.TUNNEL_DOMAIN,
            "control_origin": _control_origin(request),
        },
    )
    response["Cache-Control"] = "no-store"
    return response


def _error(message, status):
    response = JsonResponse({"ok": False, "error": message}, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _identity_response(identity, request, status=200):
    response = JsonResponse(
        {"ok": True, "tunnel": _serialize_identity(identity, request)},
        status=status,
    )
    response["Cache-Control"] = "no-store"
    return response


def _require_api_user(request):
    if request.user.is_authenticated:
        return None
    response = _error("Authentication is required.", 401)
    response["WWW-Authenticate"] = "Session"
    return response


@require_GET
def tunnel_collection(request):
    unauthorized = _require_api_user(request)
    if unauthorized:
        return unauthorized
    identities = TunnelIdentity.objects.filter(owner=request.user).order_by("-created_at")
    response = JsonResponse(
        {
            "ok": True,
            "tunnels": [
                _serialize_identity(identity, request) for identity in identities
            ],
        }
    )
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["GET", "PUT", "POST", "DELETE"])
def tunnel_identity(request, username):
    unauthorized = _require_api_user(request)
    if unauthorized:
        return unauthorized

    try:
        normalized_username = normalize_tunnel_name(username)
    except ValueError as exc:
        return _error(str(exc), 400)

    if request.method == "PUT":
        identity = TunnelIdentity(
            owner=request.user,
            username=normalized_username,
        )
        identity.issue_token()
        try:
            with transaction.atomic():
                identity.save(force_insert=True)
        except IntegrityError:
            return _error(f'Tunnel username "{normalized_username}" is unavailable.', 409)
        return _identity_response(identity, request, 201)

    with transaction.atomic():
        identity = (
            TunnelIdentity.objects.select_for_update()
            .filter(username=normalized_username, owner=request.user)
            .first()
        )
        if identity is None:
            return _error(f'Tunnel username "{normalized_username}" was not found.', 404)

        if request.method == "GET":
            return _identity_response(identity, request)

        if request.method == "POST":
            identity.issue_token()
            identity.save(
                update_fields=["token_digest", "token_ciphertext", "updated_at"]
            )
            return _identity_response(identity, request)

        identity.delete()
        return HttpResponse(status=204, headers={"Cache-Control": "no-store"})
