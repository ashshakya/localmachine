import re
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings


def _git(repo: Path, *args: str, timeout: float = 1.5) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _remote_link(remote: str) -> str:
    remote = remote.strip()
    azure_git_ssh = re.match(r"git@ssh\.dev\.azure\.com:v3/([^/]+)/([^/]+)/(.+?)(?:\.git)?$", remote)
    if azure_git_ssh:
        organization, project, repository = azure_git_ssh.groups()
        return f"https://dev.azure.com/{organization}/{project}/_git/{repository.removesuffix('.git')}"
    azure_ssh = re.match(r"https://ssh\.dev\.azure\.com/v3/([^/]+)/([^/]+)/(.+?)(?:\.git)?$", remote)
    if azure_ssh:
        organization, project, repository = azure_ssh.groups()
        return f"https://dev.azure.com/{organization}/{project}/_git/{repository.removesuffix('.git')}"
    if remote.startswith(("http://", "https://")):
        return remote.removesuffix(".git")
    match = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", remote)
    if match:
        return f"https://{match.group(1)}/{match.group(2).removesuffix('.git')}"
    return ""


def _relative_time(timestamp: int) -> str:
    delta = max(0, int(time.time()) - timestamp)
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def discover_repositories() -> list[Path]:
    root = settings.WORKSPACE_ROOT
    candidates = []
    if (root / ".git").exists():
        candidates.append(root)
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return candidates
    candidates.extend(child for child in children if child.is_dir() and (child / ".git").exists())
    return candidates[: settings.REPOSITORY_LIMIT]


def find_repository(name: str) -> Path | None:
    return next((repo for repo in discover_repositories() if repo.name == name), None)


def repository_snapshot(repo: Path) -> dict:
    porcelain = _git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
    status_lines = [line for line in porcelain.splitlines() if line]
    modified = sum(1 for line in status_lines if not line.startswith("??"))
    untracked = sum(1 for line in status_lines if line.startswith("??"))
    branch = _git(repo, "branch", "--show-current") or "detached"
    ahead_behind = _git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    ahead = behind = 0
    if ahead_behind:
        parts = ahead_behind.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])
    last = _git(repo, "log", "-1", "--pretty=format:%ct|%an|%h|%s")
    last_timestamp, author, commit_hash, subject = 0, "", "", "No commits"
    if last:
        parts = last.split("|", 3)
        if len(parts) == 4:
            last_timestamp, author, commit_hash, subject = int(parts[0]), parts[1], parts[2], parts[3]
    remote = _remote_link(_git(repo, "remote", "get-url", "origin"))
    changes = modified + untracked
    return {
        "name": repo.name,
        "path": str(repo),
        "branch": branch,
        "modified": modified,
        "untracked": untracked,
        "changes": changes,
        "ahead": ahead,
        "behind": behind,
        "is_clean": changes == 0,
        "health": "clean" if changes == 0 else ("attention" if changes < 8 else "busy"),
        "last_commit": {"hash": commit_hash, "subject": subject, "author": author, "timestamp": last_timestamp, "relative": _relative_time(last_timestamp) if last_timestamp else "—"},
        "remote_url": remote,
    }


def activity_snapshot(repositories: list[Path], days: int = 30, limit: int = 16) -> tuple[list[dict], Counter, int]:
    events = []
    authors = Counter()
    total_commits = 0
    since_args = [] if days == 0 else [f"--since={days} days ago"]
    for repo in repositories:
        count = _git(repo, "rev-list", "--count", *since_args, "HEAD", timeout=3.0)
        total_commits += int(count) if count.isdigit() else 0

        shortlog = _git(repo, "shortlog", "-s", "--format=%an", *since_args, "HEAD", timeout=3.0)
        for line in shortlog.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0].isdigit():
                authors[parts[1]] += int(parts[0])

        output = _git(repo, "log", *since_args, "-10", "--pretty=format:%ct|%an|%h|%s", timeout=3.0)
        for line in output.splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            timestamp = int(parts[0])
            events.append({
                "timestamp": timestamp,
                "iso": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
                "relative": _relative_time(timestamp),
                "author": parts[1],
                "hash": parts[2],
                "subject": parts[3],
                "repository": repo.name,
            })
    return sorted(events, key=lambda event: event["timestamp"], reverse=True)[:limit], authors, total_commits


def _check_service(service: dict) -> dict:
    start = time.monotonic()
    try:
        request = Request(service["url"], headers={"User-Agent": "LocalProjectDashboard/1.0"}, method="GET")
        with urlopen(request, timeout=1.4) as response:
            code = response.status
        latency = round((time.monotonic() - start) * 1000)
        status = "online" if code < 500 and latency < 700 else "slow"
        return {**service, "status": status, "latency": latency, "status_code": code}
    except HTTPError as error:
        latency = round((time.monotonic() - start) * 1000)
        status = "online" if error.code < 500 else "offline"
        return {**service, "status": status, "latency": latency, "status_code": error.code}
    except Exception:
        return {**service, "status": "offline", "latency": None, "status_code": None}


def service_snapshot() -> list[dict]:
    services = []
    for index, item in enumerate(settings.SERVICE_ENDPOINTS.split(",")):
        if "|" not in item:
            continue
        name, url = item.split("|", 1)
        services.append({"id": index, "name": name.strip(), "url": url.strip()})
    with ThreadPoolExecutor(max_workers=max(1, len(services))) as pool:
        return list(pool.map(_check_service, services))


def _range_labels(days: int) -> tuple[str, str]:
    labels = {
        0: ("All time", "all time"),
        7: ("Last 7 days", "7 days"),
        30: ("Last 30 days", "30 days"),
        90: ("Last 3 months", "3 months"),
        180: ("Last 6 months", "6 months"),
        365: ("Last year", "1 year"),
        730: ("Last 2 years", "2 years"),
    }
    return labels.get(days, (f"Last {days} days", f"{days} days"))


def _commit_record(repo: Path, commit: str) -> dict:
    output = _git(repo, "show", "-s", "--pretty=format:%ct|%an|%h|%s", commit, timeout=3.0)
    parts = output.split("|", 3)
    if len(parts) != 4:
        return {"timestamp": 0, "iso": "", "relative": "—", "author": "", "hash": "", "subject": "No commits"}
    timestamp = int(parts[0])
    return {
        "timestamp": timestamp,
        "iso": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
        "relative": _relative_time(timestamp),
        "author": parts[1],
        "hash": parts[2],
        "subject": parts[3],
    }


def _commit_heatmap(repo: Path) -> list[dict]:
    today = datetime.now(tz=timezone.utc).date()
    first_week = today - timedelta(days=today.weekday(), weeks=11)
    counts = Counter()
    output = _git(repo, "log", f"--since={first_week.isoformat()}", "--pretty=format:%ct", timeout=5.0)
    for value in output.splitlines():
        if not value.isdigit():
            continue
        commit_date = datetime.fromtimestamp(int(value), tz=timezone.utc).date()
        counts[commit_date] += 1
    maximum = max(counts.values(), default=1)
    return [
        {
            "label": (first_week + timedelta(weeks=week_index)).strftime("%b %d"),
            "days": [
                {
                    "date": (first_week + timedelta(weeks=week_index, days=day_index)).isoformat(),
                    "label": (first_week + timedelta(weeks=week_index, days=day_index)).strftime("%b %d, %Y"),
                    "count": counts[first_week + timedelta(weeks=week_index, days=day_index)],
                    "level": 0 if counts[first_week + timedelta(weeks=week_index, days=day_index)] == 0 else min(
                        4,
                        max(1, (counts[first_week + timedelta(weeks=week_index, days=day_index)] * 4 + maximum - 1) // maximum),
                    ),
                    "future": first_week + timedelta(weeks=week_index, days=day_index) > today,
                }
                for day_index in range(7)
            ],
        }
        for week_index in range(12)
    ]


def repository_detail_snapshot(repo: Path, days: int = 90) -> dict:
    repository = repository_snapshot(repo)
    since_args = [] if days == 0 else [f"--since={days} days ago"]
    activity, authors, commits_in_range = activity_snapshot([repo], days=days, limit=30)
    total_commits_text = _git(repo, "rev-list", "--count", "HEAD", timeout=5.0)
    total_commits = int(total_commits_text) if total_commits_text.isdigit() else 0
    merge_count_text = _git(repo, "rev-list", "--count", "--merges", "HEAD", timeout=5.0)
    merge_count = int(merge_count_text) if merge_count_text.isdigit() else 0

    root_hashes = _git(repo, "rev-list", "--max-parents=0", "HEAD", timeout=4.0).splitlines()
    first_commit = _commit_record(repo, root_hashes[-1]) if root_hashes else _commit_record(repo, "HEAD")
    last_commit = _commit_record(repo, "HEAD")
    age_days = max(1, (datetime.now(tz=timezone.utc).timestamp() - first_commit["timestamp"]) // 86400) if first_commit["timestamp"] else 1
    period_days = age_days if days == 0 else days

    numstat = _git(repo, "log", *since_args, "--numstat", "--format=", timeout=8.0)
    additions = deletions = 0
    touched_files = set()
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        if parts[0].isdigit():
            additions += int(parts[0])
        if parts[1].isdigit():
            deletions += int(parts[1])
        touched_files.add(parts[2])

    branch_output = _git(
        repo,
        "for-each-ref",
        "--sort=-committerdate",
        "--count=12",
        "--format=%(refname:short)|%(committerdate:unix)|%(authorname)|%(objectname:short)|%(subject)",
        "refs/heads",
        timeout=4.0,
    )
    branches = []
    for line in branch_output.splitlines():
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        timestamp = int(parts[1]) if parts[1].isdigit() else 0
        branches.append({
            "name": parts[0], "current": parts[0] == repository["branch"], "author": parts[2],
            "hash": parts[3], "subject": parts[4], "relative": _relative_time(timestamp) if timestamp else "—",
        })

    tracked_files = _git(repo, "ls-files", timeout=5.0).splitlines()
    file_types = Counter()
    for filename in tracked_files:
        path = Path(filename)
        label = path.suffix.lower().lstrip(".") or "other"
        file_types[label] += 1
    top_file_types = [
        {"name": name.upper(), "count": count, "percent": round(count / max(1, len(tracked_files)) * 100)}
        for name, count in file_types.most_common(8)
    ]

    status_output = _git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
    working_files = []
    for line in status_output.splitlines()[:30]:
        if len(line) < 4:
            continue
        code = line[:2].strip() or "?"
        working_files.append({"code": code, "path": line[3:], "kind": "new" if line.startswith("??") else "changed"})

    tag_count = len(_git(repo, "tag", "--list", timeout=4.0).splitlines())
    range_label, range_short_label = _range_labels(days)
    contributor_total = max(1, sum(authors.values()))
    contributors = [
        {"name": name, "commits": count, "percent": round(count / contributor_total * 100)}
        for name, count in authors.most_common(10)
    ]
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "repository": repository,
        "range_days": days,
        "range_label": range_label,
        "range_short_label": range_short_label,
        "activity": activity,
        "contributors": contributors,
        "branches": branches,
        "working_files": working_files,
        "file_types": top_file_types,
        "heatmap_weeks": _commit_heatmap(repo),
        "first_commit": first_commit,
        "last_commit": last_commit,
        "stats": {
            "total_commits": total_commits,
            "commits_in_range": commits_in_range,
            "contributors": len(authors),
            "branches": len(_git(repo, "for-each-ref", "--format=%(refname)", "refs/heads", timeout=4.0).splitlines()),
            "tags": tag_count,
            "tracked_files": len(tracked_files),
            "files_touched": len(touched_files),
            "additions": additions,
            "deletions": deletions,
            "merges": merge_count,
            "age_days": int(age_days),
            "commits_per_week": round(commits_in_range / max(1, period_days / 7), 1),
        },
    }


def dashboard_snapshot(days: int = 30) -> dict:
    repo_paths = discover_repositories()
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(repo_paths)))) as pool:
        repositories = list(pool.map(repository_snapshot, repo_paths))
    repositories.sort(key=lambda repo: repo["last_commit"]["timestamp"], reverse=True)
    activity, authors, total_commits = activity_snapshot(repo_paths, days=days)
    range_label, range_short_label = _range_labels(days)
    total_changes = sum(repo["changes"] for repo in repositories)
    healthy_services = 0
    services = service_snapshot()
    healthy_services = sum(service["status"] in {"online", "slow"} for service in services)
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "range_days": days,
        "range_label": range_label,
        "range_short_label": range_short_label,
        "workspace_root": str(settings.WORKSPACE_ROOT),
        "repositories": repositories,
        "activity": activity,
        "services": services,
        "contributors": [{"name": name, "commits": count} for name, count in authors.most_common(5)],
        "stats": {
            "repositories": len(repositories),
            "open_changes": total_changes,
            "commits_in_range": total_commits,
            "commits_30d": total_commits if days == 30 else None,
            "healthy_services": healthy_services,
            "total_services": len(services),
            "clean_repositories": sum(repo["is_clean"] for repo in repositories),
        },
    }
