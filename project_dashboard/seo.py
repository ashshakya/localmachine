from urllib.parse import urljoin

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_GET


def absolute_public_url(request, path):
    base_url = settings.PUBLIC_SITE_URL or request.build_absolute_uri("/")
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


@require_GET
def robots_txt(request):
    content = render_to_string(
        "seo/robots.txt",
        {"sitemap_url": absolute_public_url(request, reverse("sitemap_xml"))},
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml(request):
    content = render_to_string(
        "seo/sitemap.xml",
        {"home_url": absolute_public_url(request, reverse("document_viewer:home"))},
    )
    return HttpResponse(content, content_type="application/xml; charset=utf-8")
