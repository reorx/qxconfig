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
    disable_rewrite_remote: bool = False,
    disable_task_local: bool = False,
    server_remote: str | None = None,
) -> BuildResult:
    source = Path(source)
    clash_path = Path(clash_path)
    out_dir = Path(out_dir)
    base = base_url.rstrip("/")
    progress = progress or (lambda *a: None)

    excluded = set()
    if disable_rewrite_remote:
        excluded.add("rewrite_remote")
    if disable_task_local:
        excluded.add("task_local")

    lines = source.read_text(encoding="utf-8").splitlines()
    out_lines, resources = _rewrite_resource_lines(lines, base, excluded)
    out_lines = _exclude_sections(out_lines, excluded)

    out_dir.mkdir(parents=True, exist_ok=True)

    if server_remote:
        out_lines, server_remote_url = _use_server_remote(
            out_lines, base, clash_path, out_dir, tag=server_remote
        )
        node_count, skipped = 0, []
    else:
        results = convert_proxies(load_proxies(clash_path.read_text(encoding="utf-8")))
        node_lines = [r.line for r in results if r.supported]
        skipped = [
            SkippedProxy(name=r.name, type=r.type, reason=r.reason or "")
            for r in results
            if not r.supported
        ]
        out_lines = _inject_nodes(out_lines, node_lines, clash_path.name)
        node_count, server_remote_url = len(node_lines), None

    downloaded, cached = _download_resources(resources, out_dir, fetcher, progress, force)

    config_path = out_dir / source.name
    config_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    return BuildResult(
        config_path=str(config_path),
        filter_count=sum(r.section == "filter_remote" for r in resources),
        rewrite_count=sum(r.section == "rewrite_remote" for r in resources),
        node_count=node_count,
        downloaded_count=downloaded,
        cached_count=cached,
        skipped=skipped,
        server_remote_url=server_remote_url,
    )


def _rewrite_resource_lines(
    lines: list[str], base: str, excluded: set[str] = frozenset()
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

        # Excluded sections are passed through here and dropped wholesale by
        # _exclude_sections later, so don't collect their rules for download.
        if (
            current in REMOTE_SECTIONS
            and current not in excluded
            and is_resource_line(line)
        ):
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


def _exclude_sections(lines: list[str], excluded: set[str]) -> list[str]:
    for name in excluded:
        lines = _remove_section(lines, name)
    return lines


def _remove_section(lines: list[str], name: str) -> list[str]:
    """Remove a whole section: its header, body, and own descriptive comment.

    A trailing run of comments/blanks before the next header belongs to that
    next section and is preserved.
    """
    header_idx = next(
        (i for i, ln in enumerate(lines) if section_name(ln) == name), None
    )
    if header_idx is None:
        return lines

    # Extend the start upward over the section's own comment header + the blank
    # separator above it.
    start = header_idx
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    while start > 0 and lines[start - 1].strip() == "":
        start -= 1

    # End at the next section header, then walk back so the comment/blank run
    # that introduces that next section is kept.
    end = next(
        (j for j in range(header_idx + 1, len(lines)) if section_name(lines[j])),
        len(lines),
    )
    while end - 1 > header_idx and (
        lines[end - 1].strip() == "" or lines[end - 1].lstrip().startswith("#")
    ):
        end -= 1

    return lines[:start] + lines[end:]


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


def _use_server_remote(
    out_lines: list[str], base: str, clash_path: Path, out_dir: Path, tag: str
) -> tuple[list[str], str]:
    """Copy the Clash config under clash/ and reference it from [server_remote]."""
    clash_dest = out_dir / "clash" / clash_path.name
    clash_dest.parent.mkdir(parents=True, exist_ok=True)
    clash_dest.write_bytes(clash_path.read_bytes())

    url = f"{base}/clash/{clash_path.name}"
    # QX [server_remote] syntax: a space before tag=, commas between the rest.
    line = f"{url} tag={tag}, update-interval=172800, opt-parser=true, enabled=true"
    return _inject_server_remote(out_lines, line, clash_path.name), url


def _inject_server_remote(
    out_lines: list[str], remote_line: str, clash_name: str
) -> list[str]:
    block = [f"# Subscription injected from {clash_name}", remote_line, ""]

    header_idx = next(
        (i for i, ln in enumerate(out_lines) if section_name(ln) == "server_remote"),
        None,
    )
    if header_idx is None:
        return out_lines + ["", "[server_remote]", *block]
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
