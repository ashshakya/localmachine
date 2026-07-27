from functools import wraps

from django.db import OperationalError, ProgrammingError
from django.http import Http404

from .models import PageVisibility


PAGE_FIELDS = {
    "command_center": "command_center_enabled",
    "api_mocker": "api_mocker_enabled",
}


def visibility_settings():
    defaults = {field: True for field in PAGE_FIELDS.values()}
    try:
        stored = PageVisibility.objects.filter(pk=1).values(*defaults).first()
    except (OperationalError, ProgrammingError):
        stored = None
    if stored:
        defaults.update(stored)
    return defaults


def page_is_enabled(page):
    field = PAGE_FIELDS[page]
    return visibility_settings()[field]


def require_enabled_page(page):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not page_is_enabled(page):
                raise Http404
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
