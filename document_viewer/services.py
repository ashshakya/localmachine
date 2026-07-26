import os
import tempfile
from pathlib import Path

from django.conf import settings

ALLOWED_EXTENSIONS = {".md", ".markdown", ".html", ".htm"}
MAX_FILE_SIZE = 5 * 1024 * 1024


def resolve_document(raw_path):
    if not raw_path or not str(raw_path).strip():
        raise ValueError("Enter a file path first.")

    path = Path(str(raw_path).strip()).expanduser()
    if not path.is_absolute():
        path = Path(settings.DOCUMENT_VIEWER_DEFAULT_DIRECTORY) / path
    path = path.resolve()
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Only Markdown (.md, .markdown) and HTML (.html, .htm) files are supported.")
    return path


def file_metadata(path):
    stat = path.stat()
    return {"mtime_ns": str(stat.st_mtime_ns), "size": stat.st_size}


def read_document(path):
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError("The selected path is not a file.")
    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("The file is larger than the 5 MB limit.")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("The file must use UTF-8 text encoding.") from exc


def write_document(path, content):
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError("The selected path is not a file.")
    if not os.access(path, os.W_OK):
        raise PermissionError(f"File is not writable: {path}")

    original_mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.chmod(original_mode)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
