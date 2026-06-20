"""Parse a Quantumult X profile: section detection and resource URL mapping."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

# Remote sections whose URLs get mirrored, mapped to their local subdirectory.
REMOTE_SECTIONS = {
    "filter_remote": "rules",
    "rewrite_remote": "rewrites",
}


def section_name(line: str) -> str | None:
    """Return the section name if ``line`` is a ``[section]`` header, else None."""
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip()
    return None


def is_resource_line(line: str) -> bool:
    """A live remote-resource line starts with a bare http(s) URL.

    Disabled (``;``/``#``) or keyword (``geo_location_checker = http...``) lines
    are therefore excluded.
    """
    stripped = line.strip()
    return stripped.startswith("http://") or stripped.startswith("https://")


def resource_url(line: str) -> str:
    """The URL is the first comma-separated field of a resource line."""
    return line.split(",", 1)[0].strip()


def url_to_relpath(url: str, subdir: str) -> str:
    """Map a URL to a collision-free local path mirroring host + path."""
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    if not path or path.endswith("/"):
        path = path + "index"
    relpath = f"{subdir}/{parsed.netloc}/{path}"
    if parsed.query:
        digest = hashlib.sha1(parsed.query.encode()).hexdigest()[:8]
        relpath = f"{relpath}.{digest}"
    return relpath
