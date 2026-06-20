#!/usr/bin/env python3
"""Thin entry point so the tool can be run as `uv run build-qxconf.py ...`."""

import os
import sys

# Allow running directly from the repo without installing the package.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qxconf.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
