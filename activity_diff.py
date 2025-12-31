#!/usr/bin/env python3
"""
Diff detection between local YAML activities and server state.

This module compares activities to detect meaningful differences,
handling HTML content semantically and treating certain arrays as sets.
"""

from dataclasses import dataclass
from typing import Any

from field_mapping import (
    html_texts_equal,
    FIELD_MAPPINGS,
    REGISTRATION_MAPPINGS,
    LOCATION_MAPPINGS,
    SCHEDULE_MAPPINGS,
)


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


def _build_default_values() -> dict[str, Any]:
    """
    Build a mapping from YAML field paths to their default values.

    Returns a dict like {"registration.required": True, "pricing.type": "paid", ...}
    """
    defaults = {}
    all_mappings = (
        FIELD_MAPPINGS + REGISTRATION_MAPPINGS + LOCATION_MAPPINGS + SCHEDULE_MAPPINGS
    )
    for mapping in all_mappings:
        if mapping.default is not None:
            defaults[mapping.yaml_path] = mapping.default
    return defaults


DEFAULT_VALUES = _build_default_values()


def _compare_values(
    path: str, local_val: Any, server_val: Any
) -> bool:
    """
    Compare two values at the given path.

    Returns True if values are equivalent, False if different.
    Applies default values when local_val is None and a default exists.
    """
    if local_val is None and path in DEFAULT_VALUES:
        local_val = DEFAULT_VALUES[path]

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

# Server-generated fields: ignore if they only exist on server (local_value is None)
# These use suffix matching (endswith)
SERVER_GENERATED_SUFFIXES = {
    ".coordinates",
    ".zoom",
}


def _is_server_generated_field(path: str) -> bool:
    """Check if a field path matches a server-generated field pattern."""
    return any(path.endswith(suffix) for suffix in SERVER_GENERATED_SUFFIXES)


def _filter_geocoded_coordinates(
    diffs: list[FieldDiff],
    local_flat: dict[str, Any],
    server_flat: dict[str, Any],
) -> list[FieldDiff]:
    """
    Filter out coordinate diffs when street address is present.

    Server geocodes street addresses and overrides coordinates.
    Only report coordinate diffs when street is null (user can drag marker).
    """
    filtered = []
    for diff in diffs:
        if not diff.path.endswith(".coordinates"):
            filtered.append(diff)
            continue

        # Get the street field path (replace .coordinates with .street)
        street_path = diff.path.replace(".coordinates", ".street")

        # Check if either local or server has a street address
        local_street = local_flat.get(street_path)
        server_street = server_flat.get(street_path)

        # If either side has a street address, server will geocode it
        # So ignore coordinate differences (user can't control them)
        if local_street or server_street:
            continue

        # No street address on either side - coordinates are user-controlled
        filtered.append(diff)

    return filtered


def _strip_server_only_fields(local_obj: Any, server_obj: Any) -> tuple[Any, Any]:
    """
    Strip server-generated fields from server that don't exist in local.

    Returns (local_stripped, server_stripped) where server has coordinates/zoom
    removed only if local doesn't have them.
    """
    if isinstance(local_obj, dict) and isinstance(server_obj, dict):
        local_result = {}
        server_result = {}
        all_keys = set(local_obj.keys()) | set(server_obj.keys())

        for key in all_keys:
            local_val = local_obj.get(key)
            server_val = server_obj.get(key)

            # Skip server-only generated fields
            if key in ("coordinates", "zoom") and key not in local_obj:
                continue

            if local_val is not None and server_val is not None:
                local_stripped, server_stripped = _strip_server_only_fields(
                    local_val, server_val
                )
                local_result[key] = local_stripped
                server_result[key] = server_stripped
            elif local_val is not None:
                local_result[key] = local_val
            elif server_val is not None:
                server_result[key] = server_val

        return local_result, server_result

    if isinstance(local_obj, list) and isinstance(server_obj, list):
        if len(local_obj) != len(server_obj):
            return local_obj, server_obj
        local_result = []
        server_result = []
        for local_item, server_item in zip(local_obj, server_obj, strict=False):
            l_stripped, s_stripped = _strip_server_only_fields(local_item, server_item)
            local_result.append(l_stripped)
            server_result.append(s_stripped)
        return local_result, server_result

    return local_obj, server_obj


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

    # Strip server-only generated fields for fair comparison
    local_stripped, server_stripped = _strip_server_only_fields(local, server)

    local_flat = _flatten_dict(local_stripped)
    server_flat = _flatten_dict(server_stripped)

    all_paths = set(local_flat.keys()) | set(server_flat.keys())

    for path in sorted(all_paths):
        if ignore_metadata and path in IGNORED_FIELDS:
            continue

        local_val = local_flat.get(path)
        server_val = server_flat.get(path)

        # Skip server-generated fields that don't exist locally
        if local_val is None and _is_server_generated_field(path):
            continue

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

    # Filter out coordinate diffs when street address is present
    # (server geocodes street addresses and overrides coordinates)
    diffs = _filter_geocoded_coordinates(diffs, local_flat, server_flat)

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
