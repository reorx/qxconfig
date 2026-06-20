"""Orchestrate building a self-contained Quantumult X profile directory."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .clash import convert_proxies, load_proxies
from .config import (
    REMOTE_SECTIONS,
    is_resource_line,
    resource_url,
    section_name,
    url_to_relpath,
)
from .types import BuildResult, RemoteResource, SkippedProxy

Fetcher = Callable[[str], bytes]
Progress = Callable[[int, int, str], None]


def default_fetcher(url: str) -> bytes:
    import httpx

    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def build(
    source,
    base_url: str,
    clash_path,
    out_dir,
    fetcher: Fetcher = default_fetcher,
    progress: Progress | None = None,
    force: bool = False,
) -> BuildResult:
    source = Path(source)
    clash_path = Path(clash_path)
    out_dir = Path(out_dir)
    base = base_url.rstrip("/")
    progress = progress or (lambda *a: None)

    lines = source.read_text(encoding="utf-8").splitlines()
    out_lines, resources = _rewrite_resource_lines(lines, base)

    results = convert_proxies(load_proxies(clash_path.read_text(encoding="utf-8")))
    node_lines = [r.line for r in results if r.supported]
    skipped = [
        SkippedProxy(name=r.name, type=r.type, reason=r.reason or "")
        for r in results
        if not r.supported
    ]
    out_lines = _inject_nodes(out_lines, node_lines, clash_path.name)

    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded, cached = _download_resources(resources, out_dir, fetcher, progress, force)

    config_path = out_dir / source.name
    config_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    return BuildResult(
        config_path=str(config_path),
        filter_count=sum(r.section == "filter_remote" for r in resources),
        rewrite_count=sum(r.section == "rewrite_remote" for r in resources),
        node_count=len(node_lines),
        downloaded_count=downloaded,
        cached_count=cached,
        skipped=skipped,
    )


def _rewrite_resource_lines(
    lines: list[str], base: str
) -> tuple[list[str], list[RemoteResource]]:
    out_lines: list[str] = []
    resources: list[RemoteResource] = []
    current: str | None = None

    for line in lines:
        header = section_name(line)
        if header is not None:
            current = header
            out_lines.append(line)
            continue

        if current in REMOTE_SECTIONS and is_resource_line(line):
            url = resource_url(line)
            relpath = url_to_relpath(url, REMOTE_SECTIONS[current])
            new_url = f"{base}/{relpath}"
            resources.append(
                RemoteResource(section=current, url=url, relpath=relpath, new_url=new_url)
            )
            out_lines.append(line.replace(url, new_url, 1))
            continue

        out_lines.append(line)

    return out_lines, resources


def _inject_nodes(out_lines: list[str], node_lines: list[str], clash_name: str) -> list[str]:
    block = [f"# Nodes injected from {clash_name}", *node_lines, ""]

    header_idx = next(
        (i for i, ln in enumerate(out_lines) if section_name(ln) == "server_local"),
        None,
    )
    if header_idx is None:
        return out_lines + ["", "[server_local]", *block]

    # Attach directly under the [server_local] header so the nodes are clearly
    # part of that section, leaving trailing comments (which belong to the next
    # section) in place.
    return out_lines[: header_idx + 1] + block + out_lines[header_idx + 1 :]


def _download_resources(
    resources: list[RemoteResource],
    out_dir: Path,
    fetcher: Fetcher,
    progress: Progress,
    force: bool,
) -> tuple[int, int]:
    """Fetch resources missing from ``out_dir``; return (downloaded, cached)."""
    unique: dict[str, RemoteResource] = {}
    for resource in resources:
        unique.setdefault(resource.relpath, resource)

    pending = [
        resource
        for resource in unique.values()
        if force or not (out_dir / resource.relpath).exists()
    ]
    cached = len(unique) - len(pending)

    for index, resource in enumerate(pending, start=1):
        progress(index, len(pending), resource.url)
        content = fetcher(resource.url)
        target = out_dir / resource.relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    return len(pending), cached
