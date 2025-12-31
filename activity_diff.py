#!/usr/bin/env python3
"""
Diff detection between local YAML activities and server state.

This module compares activities to detect meaningful differences,
handling HTML content semantically and treating certain arrays as sets.
"""

from dataclasses import dataclass
from typing import Any

from field_mapping import html_texts_equal


@dataclass
class FieldDiff:
    """Represents a difference in a single field between local and server state."""

    path: str
    local_value: Any
    server_value: Any

    def __str__(self) -> str:
        return f"{self.path}: {self.server_value!r} -> {self.local_value!r}"


# Fields where HTML content should be compared semantically
HTML_FIELDS = {
    "summary.fi",
    "summary.en",
    "description.fi",
    "description.en",
    "pricing.info.fi",
    "pricing.info.en",
    "registration.info.fi",
    "registration.info.en",
    "location.summary.fi",
    "location.summary.en",
}

# Fields where arrays should be compared as sets (order doesn't matter)
SET_FIELDS = {
    "categories.themes",
    "categories.formats",
    "categories.locales",
    "demographics.age_groups",
    "demographics.gender",
    "location.regions",
    "location.accessibility",
}


def _compare_values(
    path: str, local_val: Any, server_val: Any
) -> bool:
    """
    Compare two values at the given path.

    Returns True if values are equivalent, False if different.
    """
    if local_val == server_val:
        return True

    if path in HTML_FIELDS:
        local_str = local_val if isinstance(local_val, str) else ""
        server_str = server_val if isinstance(server_val, str) else ""
        return html_texts_equal(local_str, server_str)

    if path in SET_FIELDS and isinstance(local_val, list) and isinstance(server_val, list):
        return set(local_val) == set(server_val)

    return False


def _flatten_dict(d: dict, prefix: str = "") -> dict[str, Any]:
    """
    Flatten a nested dict into dot-notation paths.

    Example:
        {"a": {"b": 1, "c": 2}} -> {"a.b": 1, "a.c": 2}
    """
    result = {}
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_dict(value, path))
        else:
            result[path] = value
    return result


# Fields to ignore when comparing (metadata, UUIDs, etc.)
IGNORED_FIELDS = {
    "_key",
    "_status",
}


def diff_activities(
    local: dict,
    server: dict,
    ignore_metadata: bool = True,
) -> list[FieldDiff]:
    """
    Compare local and server activity and return list of differences.

    Args:
        local: Activity dict from local YAML
        server: Activity dict from server
        ignore_metadata: If True, ignore _key, _status fields

    Returns:
        List of FieldDiff objects describing each difference
    """
    diffs: list[FieldDiff] = []

    local_flat = _flatten_dict(local)
    server_flat = _flatten_dict(server)

    all_paths = set(local_flat.keys()) | set(server_flat.keys())

    for path in sorted(all_paths):
        if ignore_metadata and path in IGNORED_FIELDS:
            continue

        local_val = local_flat.get(path)
        server_val = server_flat.get(path)

        if not _compare_values(path, local_val, server_val):
            diffs.append(FieldDiff(
                path=path,
                local_value=local_val,
                server_value=server_val,
            ))

    # If image.id matches, don't report image.path as a diff
    # (the image is already uploaded correctly)
    local_image_id = local_flat.get("image.id")
    server_image_id = server_flat.get("image.id")
    if local_image_id and server_image_id and local_image_id == server_image_id:
        diffs = [d for d in diffs if d.path != "image.path"]

    return diffs


def format_diffs(diffs: list[FieldDiff]) -> str:
    """
    Format a list of diffs for display to users.

    Returns a human-readable string showing what changed.
    """
    if not diffs:
        return "No changes detected."

    lines = []
    for diff in diffs:
        if diff.server_value is None:
            lines.append(f"  + {diff.path}: {_format_value(diff.local_value)}")
        elif diff.local_value is None:
            lines.append(f"  - {diff.path}: {_format_value(diff.server_value)}")
        else:
            lines.append(f"  ~ {diff.path}:")
            lines.append(f"      server: {_format_value(diff.server_value)}")
            lines.append(f"      local:  {_format_value(diff.local_value)}")

    return "\n".join(lines)


def _format_value(value: Any) -> str:
    """Format a value for display, truncating long strings."""
    if value is None:
        return "(none)"
    if isinstance(value, str):
        if len(value) > 60:
            return f'"{value[:57]}..."'
        return f'"{value}"'
    if isinstance(value, list):
        return repr(value)
    return repr(value)
