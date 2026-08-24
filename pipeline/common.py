#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
common.py — Shared utilities for factcheck pipeline scripts.

Used by:
  - factcheck_crawl4ai.py  (Ур.2)
  - factcheck_openalex.py  (Ур.0.5)
  - factcheck_scrapling.py (Ур.3)

Eliminates code duplication of: PREFIX_PATTERN, PREFIX_FORBIDDEN,
_read_targets, _validate_prefix, and the Windows Unicode console fix.
"""

import io
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Prefix validation constants
# ---------------------------------------------------------------------------

PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
PREFIX_FORBIDDEN = {".", ".."}  # only . and .. parent-relative; ... and beyond are just filenames


# ---------------------------------------------------------------------------
# Windows Unicode console fix
# ---------------------------------------------------------------------------

def fix_windows_console():
    """Fix Unicode output on Windows: replace unencodable chars instead of crashing."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ---------------------------------------------------------------------------
# targets.json parsing
# ---------------------------------------------------------------------------

def read_targets(path, validate_url_https=True):
    """Read and validate a targets.json file.

    Args:
        path: Path to the targets JSON file.
        validate_url_https: If True, require url to start with http:// or https://.
                            Set False for OpenAlex (DOI-based targets may omit the
                            http prefix — e.g. a bare DOI as the url field).

    Returns:
        list of target dicts.

    Exits with code 2 on validation failure.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FATAL: invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, list):
        print("FATAL: targets JSON must be a list at top level", file=sys.stderr)
        sys.exit(2)
    required = {"id", "fact", "url"}
    for i, t in enumerate(data):
        missing = required - set(t.keys())
        if missing:
            print(f"FATAL: target #{i} missing fields: {missing}", file=sys.stderr)
            sys.exit(2)
        if validate_url_https:
            if not isinstance(t["url"], str) or not t["url"].startswith(("http://", "https://")):
                print(f"FATAL: target #{i} url must start with http:// or https://, got: {t['url']!r}",
                      file=sys.stderr)
                sys.exit(2)
    return data


# ---------------------------------------------------------------------------
# Prefix validation
# ---------------------------------------------------------------------------

def validate_prefix(prefix: str):
    """Validate --prefix argument value. Exits with code 2 on unsafe values."""
    if prefix in PREFIX_FORBIDDEN:
        print(f"FATAL: --prefix '{prefix}' is reserved/unsafe", file=sys.stderr)
        sys.exit(2)
    if "/" in prefix or "\\" in prefix:
        print(f"FATAL: --prefix must not contain path separator, got: {prefix!r}", file=sys.stderr)
        sys.exit(2)
    if not PREFIX_PATTERN.match(prefix):
        print(f"FATAL: --prefix must match [A-Za-z0-9_.-]+, got: {prefix!r}", file=sys.stderr)
        sys.exit(2)
