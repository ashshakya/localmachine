import base64


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
