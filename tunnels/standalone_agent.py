#!/usr/bin/env python3
"""Single-file localmachine.in tunnel agent. Requires Python 3.10+."""

import argparse
import asyncio
import base64
import getpass
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit


if sys.version_info < (3, 10):
    raise SystemExit("The localmachine.in tunnel agent requires Python 3.10+.")


AGENT_VERSION = "0.1.0"
DEFAULT_SERVER = "wss://relay.localmachine.in/_tunnel/connect"
LOCAL_RELAY_SERVER = "ws://127.0.0.1:9000/_tunnel/connect"
DEFAULT_MAX_BODY_BYTES = 5 * 1024 * 1024
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def load_aiohttp():
    try:
        return importlib.import_module("aiohttp")
    except ModuleNotFoundError:
        pass

    cache = (
        Path.home()
        / ".cache"
        / "localmachine-agent"
        / f"python-{sys.version_info.major}.{sys.version_info.minor}"
    )
    cache.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(cache))
    try:
        return importlib.import_module("aiohttp")
    except ModuleNotFoundError:
        print("First run: installing the tunnel networking library...", file=sys.stderr)
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--quiet",
                    "--target",
                    str(cache),
                    "aiohttp>=3.12,<4.0",
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit(
                "Could not install aiohttp. Ensure Python includes pip and that "
                "pypi.org is reachable, then run this command again."
            ) from exc
        importlib.invalidate_caches()
        return importlib.import_module("aiohttp")


aiohttp = load_aiohttp()


def encode_body(body):
    return base64.b64encode(body).decode("ascii")


def decode_body(value):
    return base64.b64decode(value or "", validate=True)


def filtered_headers(headers, *, exclude_host=False):
    blocked = set(HOP_BY_HOP_HEADERS)
    if exclude_host:
        blocked.add("host")
    return [
        (name, value)
        for name, value in headers
        if name.lower() not in blocked
    ]


def ready_message(server, public_url, local_url):
    relay = urlsplit(server)
    if relay.scheme == "ws":
        relay_origin = f"http://{relay.netloc}"
        tunnel_hostname = urlsplit(public_url).hostname
        return (
            "\nLocal tunnel connected\n"
            f"  Tunnel URL:      {relay_origin}\n"
            f"  Tunnel hostname: {tunnel_hostname}\n"
            f"  Forwarding to:   {local_url}\n\n"
            "Test with:\n"
            f'  curl -H "Host: {tunnel_hostname}" {relay_origin}/\n\n'
            "Press Ctrl+C to stop."
        )
    return (
        "\nTunnel connected\n"
        f"  Tunnel URL:    {public_url}\n"
        f"  Forwarding to: {local_url}\n\n"
        "Press Ctrl+C to stop."
    )


class TunnelAgent:
    def __init__(
        self,
        server,
        username,
        token,
        local_url,
        max_body_bytes,
        preserve_host=False,
    ):
        self.server = server
        self.username = username
        self.token = token
        self.local_url = local_url.rstrip("/")
        self.max_body_bytes = max_body_bytes
        self.preserve_host = preserve_host
        self.send_lock = asyncio.Lock()

    async def send_response(self, websocket, payload):
        async with self.send_lock:
            await websocket.send_json(payload)

    async def forward(self, session, websocket, request):
        request_id = request.get("request_id", "")
        method = str(request.get("method", "GET")).upper()
        path = str(request.get("path", "/"))
        safe_path = urlsplit(path).path or "/"
        started_at = time.monotonic()
        request_body = b""
        try:
            if not path.startswith("/"):
                raise ValueError("Tunnel request path must start with a slash.")
            request_body = decode_body(request.get("body"))
            print(
                f"[tunnel] request id={request_id} method={method} "
                f"path={safe_path} request_bytes={len(request_body)}",
                flush=True,
            )
            async with session.request(
                method,
                f"{self.local_url}{path}",
                headers=filtered_headers(
                    request.get("headers", []),
                    exclude_host=not self.preserve_host,
                ),
                data=request_body,
                allow_redirects=False,
            ) as response:
                body = await response.content.read(self.max_body_bytes + 1)
                if len(body) > self.max_body_bytes:
                    raise ValueError("Local response exceeded the configured body limit.")
                payload = {
                    "type": "response",
                    "request_id": request_id,
                    "status": response.status,
                    "headers": filtered_headers(response.headers.items()),
                    "body": encode_body(body),
                }
        except Exception as exc:
            print(
                f"Local upstream error for request {request_id}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            payload = {
                "type": "response",
                "request_id": request_id,
                "status": 502,
                "headers": [("Content-Type", "text/plain; charset=utf-8")],
                "body": encode_body(
                    b"The local upstream could not complete the request."
                ),
            }
            body = decode_body(payload["body"])
        print(
            f"[tunnel] response id={request_id} status={payload['status']} "
            f"response_bytes={len(body)} "
            f"duration_ms={round((time.monotonic() - started_at) * 1000)}",
            flush=True,
        )
        await self.send_response(websocket, payload)

    async def connect_once(self):
        timeout = aiohttp.ClientTimeout(total=None, connect=15)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": f"localmachine-agent/{AGENT_VERSION}",
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                self.server,
                params={"username": self.username},
                headers=headers,
                heartbeat=20,
                max_msg_size=1_048_576,
            ) as websocket:
                async for message in websocket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(message.data)
                        if payload.get("type") == "ready":
                            print(
                                ready_message(
                                    self.server,
                                    payload["public_url"],
                                    self.local_url,
                                ),
                                flush=True,
                            )
                        elif payload.get("type") == "request":
                            asyncio.create_task(
                                self.forward(session, websocket, payload)
                            )
                    elif message.type in {
                        aiohttp.WSMsgType.ERROR,
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                    }:
                        break

    async def run(self):
        delay = 1
        while True:
            try:
                await self.connect_once()
                delay = 1
            except aiohttp.ClientConnectorCertificateError as exc:
                raise SystemExit(
                    "TLS certificate validation failed for the relay. "
                    "For local testing, add --local-relay and run the relay on port 9000. "
                    "For production, install a certificate containing *.localmachine.in."
                ) from exc
            except aiohttp.WSServerHandshakeError as exc:
                if exc.status in {401, 403, 409}:
                    raise SystemExit(
                        f"Tunnel connection rejected ({exc.status}). "
                        "Check the username/token or whether the name is already online."
                    ) from exc
                print(
                    f"Tunnel disconnected: HTTP {exc.status}; reconnecting in {delay}s",
                    file=sys.stderr,
                )
            except (
                aiohttp.ClientError,
                OSError,
                asyncio.TimeoutError,
                json.JSONDecodeError,
            ) as exc:
                print(
                    f"Tunnel disconnected: {exc}; reconnecting in {delay}s",
                    file=sys.stderr,
                )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Expose a local HTTP port at <username>.localmachine.in."
    )
    parser.add_argument("username", help="Reserved tunnel username, for example gringotts")
    parser.add_argument(
        "port",
        type=int,
        nargs="?",
        default=8000,
        help="Local HTTP port (default: 8000)",
    )
    parser.add_argument("--token", default=os.environ.get("TUNNEL_TOKEN"))
    relay_group = parser.add_mutually_exclusive_group()
    relay_group.add_argument(
        "--server",
        default=os.environ.get("TUNNEL_SERVER_URL", DEFAULT_SERVER),
    )
    relay_group.add_argument(
        "--local-relay",
        action="store_true",
        help=f"Connect to the development relay at {LOCAL_RELAY_SERVER}.",
    )
    parser.add_argument("--local-url")
    parser.add_argument(
        "--preserve-host",
        action="store_true",
        help="Forward the public Host header to the local service.",
    )
    parser.add_argument("--version", action="version", version=AGENT_VERSION)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not args.token:
        args.token = getpass.getpass("Tunnel token: ").strip()
    if not args.token:
        parser.error("a tunnel token is required")
    if not args.local_url:
        args.local_url = f"http://127.0.0.1:{args.port}"
    if args.local_relay:
        args.server = LOCAL_RELAY_SERVER
    return args


def main():
    args = parse_args()
    print(f"Connecting {args.username} to {args.local_url}...", flush=True)
    agent = TunnelAgent(
        args.server,
        args.username,
        args.token,
        args.local_url,
        DEFAULT_MAX_BODY_BYTES,
        args.preserve_host,
    )
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\nTunnel stopped.")


if __name__ == "__main__":
    main()
