from .visibility import visibility_settings


def page_visibility(request):
    return visibility_settings()
