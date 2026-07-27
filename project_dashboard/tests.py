from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    MIDDLEWARE=(),
    PUBLIC_SITE_URL="https://dashboard.example.com",
)
class SearchDiscoveryTests(TestCase):
    def test_robots_file_points_to_absolute_sitemap(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(
            response,
            "Sitemap: https://dashboard.example.com/sitemap.xml",
        )
        self.assertContains(response, "Disallow: /admin/")

    def test_sitemap_contains_canonical_home_page(self):
        response = self.client.get(reverse("sitemap_xml"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        self.assertContains(
            response,
            "<loc>https://dashboard.example.com/</loc>",
        )

    @override_settings(GOOGLE_SITE_VERIFICATION="verification-token")
    def test_home_page_contains_search_metadata(self):
        response = self.client.get(reverse("document_viewer:home"))

        self.assertContains(
            response,
            '<link rel="canonical" href="https://dashboard.example.com/">',
            html=True,
        )
        self.assertContains(
            response,
            '<meta name="google-site-verification" content="verification-token">',
            html=True,
        )
