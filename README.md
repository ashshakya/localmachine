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

## Live data sources

- Git branches, status, remotes, commit history, and contributors are read on demand.
- Service health is checked from Django every 30 seconds.
- Notes and tasks are stored in the configured local MySQL database.
- Repository and service links open their real configured destinations.
- API mock definitions and request history are managed from the dashboard and stored in MySQL.
- Markdown and HTML documents can be edited with a sandboxed live preview and external-change detection.
