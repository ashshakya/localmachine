import json

from django.test import TestCase
from django.urls import reverse

from workspace.models import PageVisibility

from .models import MockCollection, MockEndpoint, MockRequestLog


class ApiMockerTests(TestCase):
    def create_mock(self, **overrides):
        payload = {
            "method": "GET",
            "path": "/users/123",
            "status_code": 200,
            "response_body": '{"name":"Ada"}',
            "headers": {"X-Mock": "yes"},
            "latency_ms": 0,
            **overrides,
        }
        return self.client.post(
            reverse("api_mocker:mocks_collection"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def create_collection(self, name="Payments", description="Payment API mocks"):
        return self.client.post(
            reverse("api_mocker:collections"),
            data=json.dumps({"name": name, "description": description}),
            content_type="application/json",
        )

    def test_dashboard_renders(self):
        response = self.client.get(reverse("api_mocker:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API Mocker")
        self.assertContains(response, 'aria-label="Product navigation"')
        self.assertContains(response, reverse("document_viewer:home"))
        self.assertContains(response, reverse("workspace:dashboard"))
        self.assertContains(response, 'id="response-preview"')
        self.assertContains(response, "Response headers")
        self.assertContains(response, 'id="preview-eyebrow"')
        self.assertContains(response, 'id="prettify-response"')
        self.assertContains(response, "Prettify JSON")
        self.assertContains(response, 'id="history-list"')
        self.assertContains(response, "Request history")
        self.assertContains(response, "Replay request")

    def test_disabled_api_mocker_pages_and_management_apis_return_not_found(self):
        PageVisibility.objects.update_or_create(
            pk=1,
            defaults={"api_mocker_enabled": False},
        )

        for url in [
            reverse("api_mocker:dashboard"),
            reverse("api_mocker:collections"),
            reverse("api_mocker:mocks_collection"),
            reverse("api_mocker:request_history"),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_disabling_mocker_page_does_not_stop_public_mock_responses(self):
        self.create_mock()
        PageVisibility.objects.update_or_create(
            pk=1,
            defaults={"api_mocker_enabled": False},
        )

        response = self.client.get("/default/users/123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"name": "Ada"})

    def test_create_list_update_and_delete_mock(self):
        created = self.create_mock()
        self.assertEqual(created.status_code, 201)
        mock_id = created.json()["id"]

        listed = self.client.get(reverse("api_mocker:mocks_collection"))
        self.assertEqual(len(listed.json()), 1)

        updated = self.client.put(
            reverse("api_mocker:mock_detail", args=[mock_id]),
            data=json.dumps({"status_code": 201}),
            content_type="application/json",
        )
        self.assertEqual(updated.json()["status_code"], 201)

        deleted = self.client.delete(reverse("api_mocker:mock_detail", args=[mock_id]))
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(reverse("api_mocker:mocks_collection")).json(), [])

    def test_configured_mock_is_served(self):
        self.create_mock()
        response = self.client.get("/default/users/123")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Mock"], "yes")
        self.assertEqual(response.json(), {"name": "Ada"})
        self.client.get("/default/users/123")
        self.assertEqual(MockEndpoint.objects.get().request_count, 2)
        self.assertEqual(self.client.get("/mock/users/123").status_code, 404)

    def test_mock_matches_method_and_normalizes_trailing_slash(self):
        self.create_mock(method="POST", path="/orders/")
        self.assertEqual(self.client.get("/default/orders").status_code, 404)
        self.assertEqual(self.client.post("/default/orders").status_code, 200)

    def test_mock_requests_are_persisted_with_inspector_data(self):
        self.create_mock(method="POST", path="/orders")
        response = self.client.post(
            "/default/orders?expand=items",
            data='{"total":42}',
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer secret",
            HTTP_X_TRACE_ID="trace-123",
        )

        self.assertEqual(response.status_code, 200)
        entry = MockRequestLog.objects.get()
        self.assertTrue(entry.matched)
        self.assertEqual(entry.method, "POST")
        self.assertEqual(entry.path, "/default/orders?expand=items")
        self.assertEqual(entry.query_params, {"expand": ["items"]})
        self.assertEqual(entry.request_body, '{"total":42}')
        self.assertEqual(entry.request_headers["Authorization"], "[redacted]")
        self.assertEqual(entry.request_headers["X-Trace-Id"], "trace-123")
        self.assertEqual(entry.response_status, 200)
        self.assertIn('"name":"Ada"', entry.response_body)

    def test_unmatched_requests_are_recorded(self):
        self.create_mock()
        response = self.client.get("/default/missing")

        self.assertEqual(response.status_code, 404)
        entry = MockRequestLog.objects.get()
        self.assertFalse(entry.matched)
        self.assertIsNone(entry.mock_id)
        self.assertEqual(entry.collection.slug, "default")
        self.assertEqual(entry.response_status, 404)
        self.assertEqual(MockEndpoint.objects.get().request_count, 0)

    def test_history_can_be_listed_inspected_and_cleared_by_collection(self):
        collection = self.create_collection(name="History APIs").json()
        self.create_mock(collection_id=collection["id"], path="/events")
        self.client.get("/history-apis/events")

        listed = self.client.get(
            reverse("api_mocker:request_history"),
            {"collection_id": collection["id"]},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        log_id = listed.json()[0]["id"]

        detail = self.client.get(reverse("api_mocker:request_history_detail", args=[log_id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["path"], "/history-apis/events")
        self.assertIn("response_headers", detail.json())

        cleared = self.client.delete(
            f'{reverse("api_mocker:request_history")}?collection_id={collection["id"]}'
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["deleted_count"], 1)
        self.assertFalse(MockRequestLog.objects.exists())
        self.assertEqual(MockEndpoint.objects.get().request_count, 1)

    def test_invalid_definition_is_rejected(self):
        response = self.create_mock(status_code=700)
        self.assertEqual(response.status_code, 400)
        self.assertIn("status_code", response.json()["error"])

    def test_collections_are_searchable_and_group_mocks(self):
        payments = self.create_collection()
        self.assertEqual(payments.status_code, 201)
        collection_id = payments.json()["id"]
        self.create_collection(name="Catalog", description="Product APIs")

        created = self.create_mock(collection_id=collection_id, path="/payments/session")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["collection_id"], collection_id)

        searched = self.client.get(reverse("api_mocker:collections"), {"q": "payment"})
        self.assertEqual([collection["name"] for collection in searched.json()], ["Payments"])
        self.assertEqual(searched.json()[0]["mock_count"], 1)
        self.assertEqual(searched.json()[0]["slug"], "payments")

        filtered_mocks = self.client.get(
            reverse("api_mocker:mocks_collection"),
            {"collection_id": collection_id},
        )
        self.assertEqual(len(filtered_mocks.json()), 1)
        self.assertEqual(filtered_mocks.json()[0]["path"], "/payments/session")
        self.assertEqual(self.client.get("/payments/payments/session").status_code, 200)

    def test_collection_update_and_delete_removes_its_mocks(self):
        created = self.create_collection()
        collection_id = created.json()["id"]
        self.create_mock(collection_id=collection_id)

        updated = self.client.put(
            reverse("api_mocker:collection_detail", args=[collection_id]),
            data=json.dumps({"name": "Checkout"}),
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Checkout")

        deleted = self.client.delete(reverse("api_mocker:collection_detail", args=[collection_id]))
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_mock_count"], 1)
        self.assertEqual(self.client.get(reverse("api_mocker:mocks_collection")).json(), [])

    def test_default_collection_cannot_be_deleted(self):
        response = self.client.delete(
            reverse("api_mocker:collection_detail", args=["00000000-0000-0000-0000-000000000001"])
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be deleted", response.json()["error"])

    def test_collections_and_mocks_are_persisted_in_mysql_models(self):
        collection_response = self.create_collection(name="Persistent APIs")
        collection_id = collection_response.json()["id"]
        mock_response = self.create_mock(collection_id=collection_id, path="/persistent")

        collection = MockCollection.objects.get(id=collection_id)
        mock = MockEndpoint.objects.get(id=mock_response.json()["id"])
        self.assertEqual(collection.slug, "persistent-apis")
        self.assertEqual(mock.collection, collection)
        self.assertEqual(mock.path, "/persistent")

    def test_collection_names_and_url_slugs_are_unique(self):
        created = self.create_collection(name="My APIs")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["slug"], "my-apis")

        duplicate_name = self.create_collection(name="my apis")
        self.assertEqual(duplicate_name.status_code, 400)
        self.assertIn("name already exists", duplicate_name.json()["error"])

        duplicate_slug = self.create_collection(name="my-apis")
        self.assertEqual(duplicate_slug.status_code, 400)
        self.assertIn("URL name already exists", duplicate_slug.json()["error"])

    def test_collection_names_cannot_conflict_with_application_routes(self):
        response = self.create_collection(name="Dashboard")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reserved application route", response.json()["error"])
