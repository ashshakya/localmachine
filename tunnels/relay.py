import asyncio
import json
import logging
import os
import time
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project_dashboard.settings")

import django

django.setup()

from aiohttp import WSMsgType, web
from asgiref.sync import sync_to_async
from django.conf import settings

from .models import TunnelIdentity
from .names import normalize_tunnel_name, username_from_host
from .protocol import decode_body, encode_body, filtered_headers


logger = logging.getLogger(__name__)


class TunnelOfflineError(Exception):
    pass


class AgentSession:
    def __init__(self, username, token, websocket):
        self.username = username
        self.token = token
        self.websocket = websocket
        self.pending = {}
        self.send_lock = asyncio.Lock()

    async def request(self, payload, timeout):
        request_id = payload["request_id"]
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            async with self.send_lock:
                await self.websocket.send_json(payload)
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.pending.pop(request_id, None)

    def resolve(self, payload):
        future = self.pending.get(payload.get("request_id"))
        if future is not None and not future.done():
            future.set_result(payload)

    def close_pending(self):
        for future in self.pending.values():
            if not future.done():
                future.set_exception(TunnelOfflineError("The tunnel agent disconnected."))


def bearer_token(request):
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


@sync_to_async(thread_sensitive=True)
def identity_is_valid(username, token):
    identity = TunnelIdentity.objects.filter(username=username, enabled=True).first()
    return bool(identity and identity.token_matches(token))


async def agent_connect(request):
    try:
        username = normalize_tunnel_name(request.query.get("username"))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from exc

    token = bearer_token(request)
    if not await identity_is_valid(username, token):
        raise web.HTTPUnauthorized(
            text="Invalid tunnel username or token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sessions = request.app["sessions"]
    if username in sessions:
        raise web.HTTPConflict(text=f'Tunnel "{username}" already has a connected agent.')

    websocket = web.WebSocketResponse(heartbeat=20, max_msg_size=1_048_576)
    await websocket.prepare(request)
    session = AgentSession(username, token, websocket)
    sessions[username] = session

    await websocket.send_json(
        {
            "type": "ready",
            "username": username,
            "public_url": f"https://{username}.{settings.TUNNEL_DOMAIN}",
        }
    )

    try:
        async for message in websocket:
            if message.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError:
                    await websocket.close(code=1003, message=b"Messages must be valid JSON.")
                    break
                if payload.get("type") == "response":
                    session.resolve(payload)
            elif message.type in {WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED}:
                break
    finally:
        if sessions.get(username) is session:
            sessions.pop(username, None)
        session.close_pending()

    return websocket


async def public_request(request):
    username = username_from_host(request.host, settings.TUNNEL_DOMAIN)
    if username is None:
        raise web.HTTPNotFound(text="This hostname is not a valid tunnel.")

    started_at = time.monotonic()
    request_id = uuid.uuid4().hex
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.rsplit(",", 1)[-1].strip() or request.remote or "-"
    logger.info(
        "tunnel_request_received id=%s username=%s method=%s path=%s "
        "request_bytes=%s client_ip=%s",
        request_id,
        username,
        request.method,
        request.path,
        request.content_length if request.content_length is not None else "unknown",
        client_ip,
    )

    if request.headers.get("Upgrade"):
        _log_request_completed(started_at, request_id, username, 501, 0)
        raise web.HTTPNotImplemented(text="Public WebSocket forwarding is not supported yet.")

    session = request.app["sessions"].get(username)
    if session is None:
        _log_request_completed(started_at, request_id, username, 502, 0)
        raise web.HTTPBadGateway(text=f'Tunnel "{username}" is offline.')
    if not await identity_is_valid(username, session.token):
        if request.app["sessions"].get(username) is session:
            request.app["sessions"].pop(username, None)
        session.close_pending()
        await session.websocket.close(
            code=1008,
            message=b"The tunnel token was rotated, disabled, or deleted.",
        )
        _log_request_completed(started_at, request_id, username, 502, 0)
        raise web.HTTPBadGateway(text=f'Tunnel "{username}" is no longer authorized.')

    try:
        body = await request.read()
    except web.HTTPRequestEntityTooLarge:
        _log_request_completed(started_at, request_id, username, 413, 0)
        raise
    forwarded_headers = [
        (name, value)
        for name, value in filtered_headers(request.headers.items(), exclude_host=True)
        if name.lower()
        not in {"x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"}
    ]
    forwarded_headers.append(("Host", request.host))
    forwarded_headers.append(("X-Forwarded-Host", request.host))
    forwarded_proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    forwarded_headers.append(("X-Forwarded-Proto", forwarded_proto.split(",", 1)[0].strip()))
    if client_ip:
        forwarded_headers.append(("X-Forwarded-For", client_ip))

    payload = {
        "type": "request",
        "request_id": request_id,
        "method": request.method,
        "path": request.path_qs,
        "headers": forwarded_headers,
        "body": encode_body(body),
    }

    try:
        agent_response = await session.request(payload, settings.TUNNEL_REQUEST_TIMEOUT)
        response_body = decode_body(agent_response.get("body"))
        status = int(agent_response.get("status", 502))
        response_headers = filtered_headers(agent_response.get("headers", []))
    except asyncio.TimeoutError as exc:
        _log_request_completed(started_at, request_id, username, 504, 0)
        raise web.HTTPGatewayTimeout(text="The local service did not respond in time.") from exc
    except (TunnelOfflineError, ValueError, TypeError) as exc:
        _log_request_completed(started_at, request_id, username, 502, 0)
        raise web.HTTPBadGateway(text="The tunnel agent returned an invalid response.") from exc

    _log_request_completed(
        started_at,
        request_id,
        username,
        status,
        len(response_body),
    )
    return web.Response(body=response_body, status=status, headers=response_headers)


def _log_request_completed(started_at, request_id, username, status, response_bytes):
    logger.info(
        "tunnel_request_completed id=%s username=%s status=%s "
        "response_bytes=%s duration_ms=%s",
        request_id,
        username,
        status,
        response_bytes,
        round((time.monotonic() - started_at) * 1000),
    )


async def health(request):
    return web.json_response(
        {"status": "ok", "connected_tunnels": len(request.app["sessions"])}
    )


def create_app():
    app = web.Application(client_max_size=settings.TUNNEL_MAX_BODY_BYTES)
    app["sessions"] = {}
    app.router.add_get("/_tunnel/health", health)
    app.router.add_get("/_tunnel/connect", agent_connect)
    app.router.add_route("*", "/{path:.*}", public_request)
    return app


def main():
    web.run_app(
        create_app(),
        host=settings.TUNNEL_RELAY_HOST,
        port=settings.TUNNEL_RELAY_PORT,
        # Structured tunnel logs above intentionally omit query values and
        # credentials, so disable aiohttp's duplicate raw request-line log.
        access_log=None,
    )


if __name__ == "__main__":
    main()
