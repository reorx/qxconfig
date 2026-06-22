"""Command-line entry point for build-qxconf."""

from __future__ import annotations

import argparse
import sys

from .builder import build
from .types import BuildResult


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build-qxconf",
        description=(
            "Turn a Quantumult X profile into a self-contained directory: "
            "mirror remote filter/rewrite rules locally and inject nodes "
            "converted from a Clash config."
        ),
    )
    parser.add_argument("--source", required=True, help="Path to the input QX .conf file")
    parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL the output directory will be served at, "
        "e.g. http://192.168.1.140:8888",
    )
    parser.add_argument(
        "--clash-nodes",
        required=True,
        help="Path to the Clash config whose proxies become [server_local] nodes",
    )
    parser.add_argument(
        "-o", "--output", required=True, help="Output directory to create"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download rules even if already present in the output directory",
    )
    parser.add_argument(
        "--server-remote",
        nargs="?",
        const="lan",
        default=None,
        metavar="TAG",
        help=(
            "Instead of converting nodes into [server_local], copy the Clash "
            "config to <output>/clash/ and reference it from [server_remote] "
            "(served at <base-url>/clash/<file>). Optional TAG, default 'lan'."
        ),
    )
    args = parser.parse_args(argv)

    def progress(index: int, total: int, url: str) -> None:
        print(f"  [{index}/{total}] {url}", file=sys.stderr)

    print("Mirroring remote resources (cached files skipped; --force to refresh)...", file=sys.stderr)
    try:
        result = build(
            source=args.source,
            base_url=args.base_url,
            clash_path=args.clash_nodes,
            out_dir=args.output,
            progress=progress,
            force=args.force,
            server_remote=args.server_remote,
        )
    except Exception as exc:  # noqa: BLE001 - top-level boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _report(result)
    return 0


def _report(result: BuildResult) -> None:
    print(f"\n✓ Built {result.config_path}")
    print(f"  filter rules mirrored : {result.filter_count}")
    print(f"  rewrite rules mirrored: {result.rewrite_count}")
    print(f"    downloaded          : {result.downloaded_count}")
    print(f"    reused (cached)     : {result.cached_count}")
    if result.server_remote_url:
        print(f"  node subscription     : {result.server_remote_url}")
        return
    print(f"  nodes injected        : {result.node_count}")
    if result.skipped:
        print(f"  nodes skipped         : {len(result.skipped)}")
        for item in result.skipped:
            print(f"      - {item.name} ({item.type}): {item.reason}")


if __name__ == "__main__":
    raise SystemExit(main())
