import re


TUNNEL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_TUNNEL_NAMES = {
    "admin",
    "api",
    "dashboard",
    "mail",
    "relay",
    "static",
    "tunnel",
    "www",
}


def normalize_tunnel_name(value):
    name = str(value or "").strip().lower()
    if not TUNNEL_NAME_RE.fullmatch(name):
        raise ValueError(
            "Username must be 1-63 lowercase letters, numbers, or hyphens, "
            "and cannot start or end with a hyphen."
        )
    if name in RESERVED_TUNNEL_NAMES:
        raise ValueError(f'"{name}" is reserved and cannot be used as a tunnel username.')
    return name


def username_from_host(host, domain):
    hostname = str(host or "").split(":", 1)[0].lower().rstrip(".")
    suffix = f".{domain.lower().strip('.')}"
    if not hostname.endswith(suffix):
        return None
    label = hostname[: -len(suffix)]
    if "." in label:
        return None
    try:
        return normalize_tunnel_name(label)
    except ValueError:
        return None
