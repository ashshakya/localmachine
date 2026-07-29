# Local Project Dashboard — Django

A local-first Django dashboard that reads live Git metadata from your workspace,
checks local service endpoints, and stores notes and tasks in a local MySQL database.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8001
```

Open `http://127.0.0.1:8001` for Documentation Studio. It can open, edit,
preview, upload, and safely save local Markdown and HTML documents.

The project command center is available at `http://127.0.0.1:8001/dashboard/`.

The integrated API Mocker dashboard is available at
`http://127.0.0.1:8001/mocks/`. Mock definitions are persisted to
MySQL, grouped into searchable collections, and served from
`/<collection-name>/<path>` on the same server. Collection names and generated
URL slugs are unique. The first API Mocker migration imports existing
`data/mocks.json` collections and endpoints into MySQL automatically; the JSON
file is retained only as a recovery source and is no longer used at runtime.
Matched and unmatched mock requests are also stored in MySQL for collection-scoped
history, request/response inspection, replay, search, and clearing from the dashboard.
Sensitive request headers are redacted before storage.

For example, a `GET /users/123` definition in the `Payments` collection can be
called at:

```bash
curl http://127.0.0.1:8001/payments/users/123
```

MySQL connection values are read from the ignored `.env` file. Start from
`.env.example`, create the configured database with `utf8mb4`, and then run the
migrations above. Credentials are never stored in tracked source files.

The default workspace root is the parent workspace containing this repository.
Copy `.env.example` values into your shell environment to change repository
discovery or service endpoints.

## Docker deployment

Build the production image:

```bash
docker build -t local-project-dashboard .
```

Create a persistent volume and run the container:

```bash
docker volume create dashboard-data

docker run --rm -p 8000:8000 \
  --name local-project-dashboard \
  -e DASHBOARD_SECRET_KEY='replace-with-a-long-random-value' \
  -e DASHBOARD_ALLOWED_HOSTS='dashboard.example.com,localhost,127.0.0.1' \
  -v dashboard-data:/data \
  -v /absolute/path/to/workspace:/workspace:rw \
  local-project-dashboard
```

Docker uses SQLite at `/data/dashboard.sqlite3` by default. Keep `/data` on a
named volume or bind mount so mock definitions, collections, request history,
counters, notes, and tasks survive container replacement. The startup script
runs all pending Django database migrations before Gunicorn starts, including
when the SQLite database is first created. The container entrypoint explicitly
selects SQLite, so legacy MySQL values in a supplied environment file are
ignored.

After changing the database configuration, rebuild the image and replace any
container created from the old image:

```bash
docker build --no-cache -t local-project-dashboard .
docker rm -f local-project-dashboard 2>/dev/null || true
```

Set `DASHBOARD_CSRF_TRUSTED_ORIGINS=https://dashboard.example.com`,
`DASHBOARD_TRUST_PROXY_HEADERS=1`, and `DASHBOARD_SECURE_COOKIES=1` when
deploying behind an HTTPS reverse proxy. The container runs migrations at
startup by default; set `RUN_MIGRATIONS=0` when migrations are handled by a
separate deployment/release job. Gunicorn listens on `PORT` (default `8000`),
and worker count and timeout are controlled with `WEB_CONCURRENCY` and
`GUNICORN_TIMEOUT`.

## Tag-based releases

Pushing a semantic-version tag runs the GitHub Actions release pipeline. It
tests the project with SQLite, builds the production image, and publishes it to
GitHub Container Registry as:

```text
ghcr.io/ashshakya/localmachine
```

Create a release directly from the commit that should be deployed:

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

The pipeline publishes `1.0.0`, `1.0`, `1`, `latest`, and a commit-SHA image
tag. Pull and run the immutable version on the deployment host:

```bash
docker login ghcr.io
docker pull ghcr.io/ashshakya/localmachine:1.0.0

docker run -d \
  --name local-project-dashboard \
  --restart unless-stopped \
  -p 8000:8000 \
  -e DASHBOARD_SECRET_KEY='replace-with-a-long-random-value' \
  -e DASHBOARD_ALLOWED_HOSTS='dashboard.example.com,localhost,127.0.0.1' \
  -v dashboard-data:/data \
  -v /absolute/path/to/workspace:/workspace:rw \
  ghcr.io/ashshakya/localmachine:1.0.0
```

The repository workflow needs `Read and write permissions` for GitHub Actions
packages. Private GHCR packages also require an authenticated `docker login` on
the deployment host.

## Google Search discovery

Set the public HTTPS origin and the verification token supplied by Google Search
Console in the production environment:

```dotenv
DASHBOARD_PUBLIC_SITE_URL=https://dashboard.example.com
GOOGLE_SITE_VERIFICATION=replace-with-search-console-token
```

The site exposes `/robots.txt` and `/sitemap.xml` at the domain root. Only the
Documentation Studio home page is included in the sitemap; admin, API mocker,
repository, dashboard, and API routes are excluded from crawling or marked
`noindex` because they can contain internal workspace data.

After deployment, verify ownership in Google Search Console and submit:

```text
https://dashboard.example.com/sitemap.xml
```

Search indexing is not immediate or guaranteed. The public hostname must resolve
to the deployment, use a valid HTTPS certificate, and allow Googlebot to fetch
the home page, `robots.txt`, the sitemap, and the favicon without authentication.

## Live data sources

- Git branches, status, remotes, commit history, and contributors are read on demand.
- Service health is checked from Django every 30 seconds.
- Notes and tasks are stored in the configured local MySQL database.
- Repository and service links open their real configured destinations.
- API mock definitions and request history are managed from the dashboard and stored in MySQL.
- Markdown and HTML documents can be edited with a sandboxed live preview and external-change detection.

## Developer HTTP tunnels

The project includes an authenticated HTTP tunnel MVP. A developer runs the
agent beside a local service and receives a reserved URL such as:

```text
https://gringotts.localmachine.in
```

The public relay accepts HTTPS traffic for `*.localmachine.in`, sends each
request over an authenticated outbound WebSocket, and the agent forwards it to
the developer's local HTTP server. No inbound port or router change is needed on
the developer's network.

### One-time DNS and TLS setup

Create these DNS records, both pointing to the deployment server:

```text
localmachine.in       A  <SERVER_IP>
*.localmachine.in     A  <SERVER_IP>
```

Use an HTTPS certificate containing both `localmachine.in` and
`*.localmachine.in`. Let's Encrypt wildcard certificates require DNS-01
validation. Install the example [Nginx configuration](deploy/nginx-localmachine.conf)
after replacing certificate paths if necessary. The apex domain is proxied to
Django on port 8000; wildcard subdomains are proxied to the tunnel relay on
localhost port 9000.

### Reserve a developer name

Developers can claim an available username through the public API:

```bash
curl -X PUT https://localmachine.in/api/tunnels/gringotts
```

The successful `201 Created` response contains the token exactly once:

```json
{
  "ok": true,
  "username": "gringotts",
  "token": "<ONE_TIME_TOKEN>",
  "public_url": "https://gringotts.localmachine.in"
}
```

Store the token like a password. A duplicate username returns `409 Conflict`.
Reserved or invalid names return `400 Bad Request`.

Rotate the token by authenticating with the current token:

```bash
curl -X POST \
  -H "Authorization: Bearer <CURRENT_TOKEN>" \
  https://localmachine.in/api/tunnels/gringotts
```

The response contains a fresh token and immediately invalidates the old token.
Any agent still using the old token is disconnected on the next request. Delete
the username with:

```bash
curl -X DELETE \
  -H "Authorization: Bearer <CURRENT_TOKEN>" \
  https://localmachine.in/api/tunnels/gringotts
```

Deletion invalidates the token and disconnects an active tunnel on its next
request.

`PUT` registration is public by default. For a private beta, set
`TUNNEL_REGISTRATION_SECRET` on the server and give approved developers the
registration key. They then claim a name using:

```bash
curl -X PUT \
  -H "X-Tunnel-Registration-Key: <REGISTRATION_KEY>" \
  https://localmachine.in/api/tunnels/gringotts
```

Operators can still create or rotate identities using
`python manage.py create_tunnel_identity gringotts [--rotate]`, and identities
can be disabled from Django admin.

### Run the relay and developer agent

The production Compose file starts the relay automatically. For local relay
development:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python -m tunnels.relay
```

Keep the relay running on port 9000. In another terminal, claim a username
against the local Django server:

```bash
curl -X PUT http://127.0.0.1:8000/api/tunnels/gringotts
```

Then start the downloaded agent with the local-relay shortcut:

```bash
curl -fsSL http://127.0.0.1:8000/tunnel \
  | python3 - gringotts 8000 --local-relay
```

Enter the token returned by the `PUT` request. Test the tunnel locally while
preserving the public hostname. The agent prints the exact command:

```text
Local tunnel connected
  Tunnel URL:      http://127.0.0.1:9000
  Tunnel hostname: gringotts.localmachine.in
  Forwarding to:   http://127.0.0.1:8000

Test with:
  curl -H "Host: gringotts.localmachine.in" http://127.0.0.1:9000/
```

The hostname is required because the relay uses it to select the tunnel. The
relay URL alone does not identify which developer agent should receive the
request:

```bash
curl -H "Host: gringotts.localmachine.in" \
  http://127.0.0.1:9000/health/
```

Without `--local-relay`, the agent intentionally connects to the production
`wss://relay.localmachine.in` endpoint.

On the developer machine, the shortest setup is one command:

```bash
curl -fsSL https://localmachine.in/tunnel.py | python3 - gringotts 8000
```

The script securely prompts for the token printed when `gringotts` was reserved.
It requires Python 3.10 or newer, downloads only its small `aiohttp` networking
dependency on first use, and caches it under `~/.cache/localmachine-agent`.
Developers do not need to clone this repository or create a virtual environment.

To keep the script for repeated use:

```bash
curl -fsSL https://localmachine.in/tunnel.py -o localmachine-tunnel.py
python3 localmachine-tunnel.py gringotts 8000
```

Tokens can also come from the environment, which is useful in CI:

```bash
TUNNEL_TOKEN='<ONE_TIME_TOKEN>' \
  python3 localmachine-tunnel.py gringotts 8000
```

Requests to `https://gringotts.localmachine.in` now reach the developer's local
port 8000. The agent reconnects with exponential backoff after network changes.
Production HTTPS requires the deployed certificate to contain both
`localmachine.in` and `*.localmachine.in`; a certificate containing only the
apex and `www` names will fail for the relay and developer subdomains.

### Request logs

Every tunnel request is logged on both sides with the same opaque request ID.
The developer agent prints:

```text
[tunnel] request id=abc123 method=POST path=/webhook request_bytes=42
[tunnel] response id=abc123 status=200 response_bytes=18 duration_ms=7
```

The relay logs receipt and completion:

```text
tunnel_request_received id=abc123 username=gringotts method=POST path=/webhook request_bytes=42 client_ip=203.0.113.10
tunnel_request_completed id=abc123 username=gringotts status=200 response_bytes=18 duration_ms=9
```

Production relay logs are available with:

```bash
docker logs -f localmachine-tunnel-relay
```

Tokens, headers, bodies, and query-string values are intentionally excluded from
these logs. Use the request ID to correlate the developer and relay entries.

This first version supports concurrent HTTP requests with request and response
bodies up to 5 MB. Public WebSocket forwarding, streaming bodies, multi-instance
relay coordination, account-based registration, and rate limiting are
deliberately left for later production-hardening phases.
