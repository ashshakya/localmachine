import asyncio
from contextlib import redirect_stdout
import io
import sys
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import TunnelIdentity
from .names import normalize_tunnel_name, username_from_host
from .protocol import decode_body, encode_body
from .agent import TunnelAgent, ready_message
from .relay import create_app
from . import standalone_agent


class TunnelNameTests(SimpleTestCase):
    def test_normalizes_valid_username(self):
        self.assertEqual(normalize_tunnel_name("  Gringotts  "), "gringotts")

    def test_rejects_invalid_and_reserved_names(self):
        for value in ("-bad", "bad-", "two.parts", "relay"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_tunnel_name(value)

    def test_extracts_username_from_exact_wildcard_host(self):
        self.assertEqual(
            username_from_host("gringotts.localmachine.in:443", "localmachine.in"),
            "gringotts",
        )
        self.assertIsNone(
            username_from_host("nested.gringotts.localmachine.in", "localmachine.in")
        )


class StandaloneAgentDownloadTests(SimpleTestCase):
    def test_download_is_a_valid_self_contained_python_script(self):
        response = self.client.get(reverse("tunnel_agent"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/x-python; charset=utf-8")
        self.assertIn("localmachine-tunnel.py", response["Content-Disposition"])
        source = response.content.decode()
        compile(source, "localmachine-tunnel.py", "exec")
        self.assertIn("wss://relay.localmachine.in/_tunnel/connect", source)
        self.assertIn("ws://127.0.0.1:9000/_tunnel/connect", source)
        self.assertIn("--local-relay", source)
        self.assertNotIn("from tunnels", source)

    def test_local_relay_flag_selects_unencrypted_local_websocket(self):
        with patch.object(
            sys,
            "argv",
            [
                "localmachine-tunnel.py",
                "gringotts",
                "8000",
                "--local-relay",
                "--token",
                "test-token",
            ],
        ):
            args = standalone_agent.parse_args()

        self.assertEqual(
            args.server,
            "ws://127.0.0.1:9000/_tunnel/connect",
        )

    def test_local_ready_message_shows_relay_url_hostname_and_curl(self):
        message = ready_message(
            "ws://127.0.0.1:9000/_tunnel/connect",
            "https://localtunnel.localmachine.in",
            "http://127.0.0.1:5000",
        )

        self.assertIn("Local tunnel connected", message)
        self.assertIn("Tunnel URL:      http://127.0.0.1:9000", message)
        self.assertIn("Tunnel hostname: localtunnel.localmachine.in", message)
        self.assertIn("Forwarding to:   http://127.0.0.1:5000", message)
        self.assertIn(
            'curl -H "Host: localtunnel.localmachine.in" http://127.0.0.1:9000/',
            message,
        )

    def test_production_ready_message_shows_public_url(self):
        message = ready_message(
            "wss://relay.localmachine.in/_tunnel/connect",
            "https://localtunnel.localmachine.in",
            "http://127.0.0.1:5000",
        )

        self.assertIn("Tunnel URL:    https://localtunnel.localmachine.in", message)
        self.assertNotIn('curl -H "Host:', message)


class TunnelIdentityTests(TestCase):
    def test_token_is_hashed_encrypted_and_can_be_revealed(self):
        identity = TunnelIdentity(username="gringotts")
        token = identity.issue_token()
        identity.save()

        self.assertNotEqual(identity.token_digest, token)
        self.assertNotEqual(identity.token_ciphertext, token)
        self.assertTrue(identity.token_matches(token))
        self.assertEqual(identity.reveal_token(), token)
        self.assertFalse(identity.token_matches("wrong-token"))

    def test_management_command_reserves_unique_username(self):
        output = __import__("io").StringIO()
        call_command("create_tunnel_identity", "gringotts", stdout=output)

        self.assertTrue(TunnelIdentity.objects.filter(username="gringotts").exists())
        self.assertIn("https://gringotts.localmachine.in", output.getvalue())
        with self.assertRaises(CommandError):
            call_command("create_tunnel_identity", "gringotts")


class TunnelIdentityApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alice",
            password="A-secure-password-123!",
        )
        self.other_user = get_user_model().objects.create_user(
            username="bob",
            password="Another-secure-password-123!",
        )
        self.client.force_login(self.user)

    def endpoint(self, username="gringotts"):
        return reverse("tunnel_identity", kwargs={"username": username})

    def create_identity(self, username="gringotts", **headers):
        return self.client.put(self.endpoint(username), **headers)

    def test_put_claims_owned_username_and_returns_recoverable_token(self):
        response = self.create_identity()

        self.assertEqual(response.status_code, 201)
        payload = response.json()["tunnel"]
        self.assertEqual(payload["username"], "gringotts")
        self.assertEqual(payload["public_url"], "https://gringotts.localmachine.in")
        self.assertTrue(payload["token"])
        self.assertEqual(response["Cache-Control"], "no-store")
        identity = TunnelIdentity.objects.get(username="gringotts")
        self.assertEqual(identity.owner, self.user)
        self.assertTrue(identity.token_matches(payload["token"]))
        self.assertEqual(identity.reveal_token(), payload["token"])
        self.assertNotEqual(identity.token_digest, payload["token"])

    def test_trailing_slash_form_is_also_supported(self):
        response = self.client.put(
            reverse("tunnel_identity_slash", kwargs={"username": "localtest"})
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["tunnel"]["username"], "localtest")

    def test_put_rejects_duplicate_and_reserved_username(self):
        self.assertEqual(self.create_identity().status_code, 201)
        self.assertEqual(self.create_identity().status_code, 409)
        self.assertEqual(self.create_identity("relay").status_code, 400)

    def test_post_rotates_token_and_invalidates_previous_token(self):
        original_token = self.create_identity().json()["tunnel"]["token"]
        response = self.client.post(self.endpoint())

        self.assertEqual(response.status_code, 200)
        new_token = response.json()["tunnel"]["token"]
        self.assertNotEqual(new_token, original_token)
        identity = TunnelIdentity.objects.get(username="gringotts")
        self.assertFalse(identity.token_matches(original_token))
        self.assertTrue(identity.token_matches(new_token))
        self.assertEqual(identity.reveal_token(), new_token)

    def test_delete_removes_owned_tunnel(self):
        self.create_identity()
        response = self.client.delete(self.endpoint())
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TunnelIdentity.objects.filter(username="gringotts").exists())

    def test_mutation_of_unknown_username_returns_not_found(self):
        response = self.client.post(self.endpoint())
        self.assertEqual(response.status_code, 404)

    def test_get_and_collection_return_only_current_users_tunnels(self):
        self.create_identity("alice-service")
        other = TunnelIdentity(owner=self.other_user, username="bob-service")
        other.issue_token()
        other.save()

        detail = self.client.get(self.endpoint("alice-service"))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["tunnel"]["username"],
            "alice-service",
        )
        collection = self.client.get(reverse("tunnel_collection"))
        self.assertEqual(collection.status_code, 200)
        self.assertEqual(
            [item["username"] for item in collection.json()["tunnels"]],
            ["alice-service"],
        )
        self.assertEqual(self.client.get(self.endpoint("bob-service")).status_code, 404)
        self.assertEqual(self.client.post(self.endpoint("bob-service")).status_code, 404)
        self.assertEqual(self.client.delete(self.endpoint("bob-service")).status_code, 404)

    def test_anonymous_api_requests_are_rejected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("tunnel_collection")).status_code, 401)
        self.assertEqual(self.create_identity().status_code, 401)

    def test_mutating_api_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.put(self.endpoint())

        self.assertEqual(response.status_code, 403)


class TunnelAccountDashboardTests(TestCase):
    def test_registration_creates_email_account_and_signs_in(self):
        response = self.client.post(
            reverse("tunnels:register"),
            {
                "email": "NewDeveloper@Example.COM",
                "password1": "A-strong-password-123!",
                "password2": "A-strong-password-123!",
            },
        )

        self.assertRedirects(response, reverse("tunnels:dashboard"))
        user = get_user_model().objects.get(
            username="newdeveloper@example.com"
        )
        self.assertEqual(user.email, "newdeveloper@example.com")
        dashboard = self.client.get(reverse("tunnels:dashboard"))
        self.assertContains(dashboard, "newdeveloper@example.com")

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        get_user_model().objects.create_user(
            username="developer@example.com",
            email="developer@example.com",
            password="A-secure-password-123!",
        )

        response = self.client.post(
            reverse("tunnels:register"),
            {
                "email": "Developer@Example.com",
                "password1": "A-strong-password-123!",
                "password2": "A-strong-password-123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email already exists.")
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_sign_in_uses_email_address(self):
        get_user_model().objects.create_user(
            username="legacy-developer",
            email="developer@example.com",
            password="A-secure-password-123!",
        )

        response = self.client.post(
            reverse("tunnels:login"),
            {
                "username": "Developer@Example.COM",
                "password": "A-secure-password-123!",
            },
        )

        self.assertRedirects(response, reverse("tunnels:dashboard"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("tunnels:dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('tunnels:login')}?next={reverse('tunnels:dashboard')}",
        )

    def test_dashboard_shows_only_owned_token_and_copyable_command(self):
        user = get_user_model().objects.create_user(
            username="alice",
            password="A-secure-password-123!",
        )
        other = get_user_model().objects.create_user(
            username="bob",
            password="Another-secure-password-123!",
        )
        owned = TunnelIdentity(owner=user, username="alice-service")
        token = owned.issue_token()
        owned.save()
        hidden = TunnelIdentity(owner=other, username="bob-service")
        hidden.issue_token()
        hidden.save()
        self.client.force_login(user)

        response = self.client.get(reverse("tunnels:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertContains(response, "alice-service.localmachine.in")
        self.assertContains(response, token)
        self.assertContains(response, "curl -fsSL http://testserver/tunnel")
        self.assertNotContains(response, "/tunnel/tunnel")
        self.assertContains(response, "python3 - alice-service 5000")
        self.assertContains(response, "5000 is your local project's running port")
        self.assertNotContains(response, "bob-service")

    def test_logout_requires_post(self):
        user = get_user_model().objects.create_user(
            username="alice",
            password="A-secure-password-123!",
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("tunnels:logout")).status_code, 405)
        self.assertRedirects(
            self.client.post(reverse("tunnels:logout")),
            reverse("tunnels:login"),
        )


@override_settings(
    TUNNEL_DOMAIN="localmachine.in",
    TUNNEL_REQUEST_TIMEOUT=2,
    TUNNEL_MAX_BODY_BYTES=1024,
)
class RelayIntegrationTests(SimpleTestCase):
    def test_public_request_round_trip(self):
        asyncio.run(self._round_trip())

    async def _round_trip(self):
        with patch("tunnels.relay.identity_is_valid", new=AsyncMock(return_value=True)):
            async with TestServer(create_app()) as server:
                async with ClientSession() as client:
                    websocket = await client.ws_connect(
                        server.make_url("/_tunnel/connect?username=gringotts"),
                        headers={"Authorization": "Bearer test-token"},
                    )
                    ready = await websocket.receive_json()
                    self.assertEqual(ready["public_url"], "https://gringotts.localmachine.in")

                    async def agent_response():
                        request = await websocket.receive_json()
                        self.assertEqual(request["method"], "POST")
                        self.assertEqual(request["path"], "/webhook?event=paid")
                        self.assertEqual(decode_body(request["body"]), b'{"id": 42}')
                        await websocket.send_json(
                            {
                                "type": "response",
                                "request_id": request["request_id"],
                                "status": 201,
                                "headers": [("Content-Type", "application/json")],
                                "body": encode_body(b'{"received": true}'),
                            }
                        )

                    responder = asyncio.create_task(agent_response())
                    with self.assertLogs("tunnels.relay", level="INFO") as relay_logs:
                        response = await client.post(
                            server.make_url("/webhook?event=paid"),
                            headers={"Host": "gringotts.localmachine.in"},
                            data=b'{"id": 42}',
                        )
                    self.assertEqual(response.status, 201)
                    self.assertEqual(await response.read(), b'{"received": true}')
                    combined_logs = "\n".join(relay_logs.output)
                    self.assertIn("tunnel_request_received", combined_logs)
                    self.assertIn("method=POST path=/webhook", combined_logs)
                    self.assertIn("request_bytes=10", combined_logs)
                    self.assertIn("tunnel_request_completed", combined_logs)
                    self.assertIn("status=201", combined_logs)
                    self.assertNotIn("event=paid", combined_logs)
                    await responder
                    await websocket.close()

    def test_unknown_subdomain_is_offline(self):
        asyncio.run(self._offline())

    async def _offline(self):
        async with TestServer(create_app()) as server:
            async with ClientSession() as client:
                response = await client.get(
                    server.make_url("/"),
                    headers={"Host": "gringotts.localmachine.in"},
                )
                self.assertEqual(response.status, 502)
                self.assertIn("offline", await response.text())

    def test_real_agent_forwards_to_local_http_service(self):
        asyncio.run(self._agent_round_trip())

    async def _agent_round_trip(self):
        async def local_handler(request):
            return web.json_response(
                {
                    "method": request.method,
                    "path": request.path,
                    "payload": await request.json(),
                },
                status=202,
            )

        local_app = web.Application()
        local_app.router.add_post("/payments", local_handler)
        relay_app = create_app()

        with patch("tunnels.relay.identity_is_valid", new=AsyncMock(return_value=True)):
            async with TestServer(local_app) as local_server:
                async with TestServer(relay_app) as relay_server:
                    server_url = str(
                        relay_server.make_url("/_tunnel/connect")
                    ).replace("http://", "ws://", 1)
                    agent = TunnelAgent(
                        server_url,
                        "gringotts",
                        "test-token",
                        str(local_server.make_url("/")).rstrip("/"),
                        1024,
                    )
                    agent_task = asyncio.create_task(agent.connect_once())

                    for _ in range(100):
                        if "gringotts" in relay_app["sessions"]:
                            break
                        await asyncio.sleep(0.01)
                    self.assertIn("gringotts", relay_app["sessions"])

                    agent_logs = io.StringIO()
                    with redirect_stdout(agent_logs):
                        async with ClientSession() as client:
                            response = await client.post(
                                relay_server.make_url("/payments"),
                                headers={"Host": "gringotts.localmachine.in"},
                                json={"amount": 99},
                            )
                            self.assertEqual(response.status, 202)
                            self.assertEqual(
                                await response.json(),
                                {
                                    "method": "POST",
                                    "path": "/payments",
                                    "payload": {"amount": 99},
                                },
                            )

                    client_log_output = agent_logs.getvalue()
                    self.assertIn(
                        "method=POST path=/payments request_bytes=14",
                        client_log_output,
                    )
                    self.assertIn("status=202", client_log_output)
                    self.assertIn("response_bytes=", client_log_output)
                    self.assertIn("duration_ms=", client_log_output)

                    await relay_app["sessions"]["gringotts"].websocket.close()
                    await asyncio.wait_for(agent_task, timeout=1)
