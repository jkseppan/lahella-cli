#!/usr/bin/env python3
"""
Download existing activities from hallinta.lahella.fi.

Usage:
    uv run download_activities.py                # List all activities
    uv run download_activities.py --json         # Output as JSON
    uv run download_activities.py --yaml         # Output as YAML
    uv run download_activities.py --id 12345     # Get single activity by ID
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, merge_attrib
from ruamel.yaml.mergevalue import MergeValue

from auth_helper import get_authenticated_session, load_auth_config, BASE_URL
from field_mapping import Transformer, html_texts_equal


EVENTS_FILE = Path(__file__).parent / "events.yaml"


class TemplateMatcher:
    """Matches downloaded data against templates from events.yaml."""

    def __init__(self, events_file: Path = EVENTS_FILE):
        self.defaults = {}
        self.anchors: dict[str, CommentedMap] = {}  # anchor_name -> CommentedMap
        self.events_key: str = "events"  # root key for events list
        self._template_defaults: CommentedMap | None = None
        self._load_defaults(events_file)

    def _load_defaults(self, events_file: Path) -> None:
        """Load defaults section from events.yaml."""
        if not events_file.exists():
            return

        yaml = YAML()
        with open(events_file) as f:
            config = yaml.load(f)

        defaults = config.get("defaults", {})
        self.defaults = defaults
        self._template_defaults = defaults  # store for output

        self._extract_all_anchors(defaults)

    def get_template_defaults(self) -> CommentedMap:
        """Return the template's defaults structure for use in output."""
        if self._template_defaults is None:
            return CommentedMap()
        # Ensure all anchors are set to always_dump for output
        self._ensure_anchors_dump(self._template_defaults)
        return self._template_defaults

    def _ensure_anchors_dump(self, obj) -> None:
        """Recursively ensure all anchors have always_dump=True."""
        if hasattr(obj, 'anchor') and obj.anchor and obj.anchor.value:
            obj.yaml_set_anchor(obj.anchor.value, always_dump=True)
        if isinstance(obj, dict):
            for value in obj.values():
                self._ensure_anchors_dump(value)
        elif isinstance(obj, list):
            for item in obj:
                self._ensure_anchors_dump(item)

    def _get_anchor_name(self, obj) -> str | None:
        """Get the anchor name from a ruamel.yaml object if it has one."""
        if hasattr(obj, 'anchor') and obj.anchor and obj.anchor.value:
            return obj.anchor.value
        return None

    def _extract_all_anchors(self, obj, path: str = "") -> None:
        """
        Recursively extract all anchors from the defaults structure.

        Preserves the actual anchor names from the YAML file.
        """
        anchor_name = self._get_anchor_name(obj)
        if anchor_name:
            self.anchors[anchor_name] = obj

        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                self._extract_all_anchors(value, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}[{i}]"
                self._extract_all_anchors(item, new_path)

    def _texts_match(self, text1: str | dict, text2: str | dict) -> bool:
        """
        Check if two text values match.

        For HTML strings, compares the extracted text content, ignoring
        HTML structure differences (tag attributes, whitespace between tags).
        For dicts (translations), compares each language key.
        """
        if isinstance(text1, dict) and isinstance(text2, dict):
            for lang in set(text1.keys()) | set(text2.keys()):
                if not self._texts_match(text1.get(lang, ""), text2.get(lang, "")):
                    return False
            return True
        elif isinstance(text1, str) and isinstance(text2, str):
            if "<" in text1 or "<" in text2:
                return html_texts_equal(text1, text2)
            return text1 == text2
        return False

    def _values_match(self, val1, val2) -> bool:
        """Check if two values match (deep comparison)."""
        if isinstance(val1, dict) and isinstance(val2, dict):
            if set(val1.keys()) != set(val2.keys()):
                return False
            return all(self._values_match(val1[k], val2[k]) for k in val1)
        if isinstance(val1, (list, CommentedSeq)) and isinstance(val2, (list, CommentedSeq)):
            if len(val1) != len(val2):
                return False
            # Try set comparison for hashable items, fall back to order-independent comparison
            return sorted(val1) == sorted(val2)
        return val1 == val2

    def try_match_any_anchor(self, value) -> CommentedMap | None:
        """
        Try to match value against any known anchor.

        Returns the anchor object if a match is found, None otherwise.
        """
        if not isinstance(value, dict) or not value:
            return None

        # Check if this looks like translatable text (has language keys)
        is_text = set(value) <= {"fi", "en", "sv"}

        for _anchor_name, anchor_obj in self.anchors.items():
            if not isinstance(anchor_obj, dict):
                continue

            if is_text:
                if self._texts_match(value, anchor_obj):
                    return anchor_obj
            else:
                if self._values_match(value, anchor_obj):
                    return anchor_obj

        return None

    def apply_anchors(self, obj):
        """
        Recursively walk an object and replace matching values with anchor refs.

        Returns a new object with anchor references where matches are found.
        Preserves merge keys (<<: *anchor) from the original object.
        """
        if isinstance(obj, dict):
            result = CommentedMap()
            # Preserve merge key if present
            if hasattr(obj, merge_attrib):
                setattr(result, merge_attrib, getattr(obj, merge_attrib))
            for key, value in obj.items():
                # Try to match this value to an anchor
                anchor_obj = self.try_match_any_anchor(value)
                if anchor_obj is not None:
                    result[key] = anchor_obj
                elif isinstance(value, (dict, list)):
                    result[key] = self.apply_anchors(value)
                else:
                    result[key] = value
            return result
        elif isinstance(obj, list):
            result = CommentedSeq()
            for item in obj:
                anchor_obj = self.try_match_any_anchor(item)
                if anchor_obj is not None:
                    result.append(anchor_obj)
                elif isinstance(item, (dict, list)):
                    result.append(self.apply_anchors(item))
                else:
                    result.append(item)
            return result
        return obj

    def find_partial_match(
            self, obj: dict, skip_fields: set | None = None
    ) -> tuple[CommentedMap | None, dict, set]:
        """
        Find the best anchor for partial matching (merge key usage).

        Returns (anchor_object, overrides, matched_fields) or (None, {}, set()).

        An anchor is a candidate if:
        1. If anchor has 'type', obj must have matching 'type'
        2. Using the merge key provides net benefit (matches > overrides)
        """
        if not isinstance(obj, dict) or not obj:
            return None, {}, set()

        if skip_fields is None:
            skip_fields = set()

        # Skip text-like objects (only have language keys)
        if set(obj.keys()) <= {"fi", "en", "sv"}:
            return None, {}, set()

        best_anchor = None
        best_overrides = {}
        best_matched = set()
        best_score = 0

        for _anchor_name, anchor_obj in self.anchors.items():
            if not isinstance(anchor_obj, dict):
                continue

            # Skip text-like anchors
            if set(anchor_obj.keys()) <= {"fi", "en", "sv"}:
                continue

            # If anchor has 'type', require matching type
            if "type" in anchor_obj and obj.get("type") != anchor_obj.get("type"):
                continue

            matched, overrides = self._calculate_partial_match(obj, anchor_obj, skip_fields)
            score = len(matched) - len(overrides)

            if score > best_score:
                best_score = score
                best_anchor = anchor_obj
                best_overrides = overrides
                best_matched = matched

        if best_score > 0:
            return best_anchor, best_overrides, best_matched
        return None, {}, set()

    def _calculate_partial_match(
            self, obj: dict, anchor: dict, skip_fields: set
    ) -> tuple[set, dict]:
        """
        Calculate which fields match and which need overriding.

        Returns (matched_fields, overrides_dict).
        Only counts as match if field exists in BOTH anchor and obj with same value.
        """
        matched = set()
        overrides = {}

        for key, anchor_val in anchor.items():
            if key in skip_fields:
                continue
            if key not in obj:
                # Anchor has field obj doesn't - using merge would add unwanted field
                continue
            if self._values_match(obj.get(key), anchor_val):
                matched.add(key)
            else:
                overrides[key] = obj[key]

        return matched, overrides

    def apply_partial_matching(self, obj, skip_fields: tuple | None = None):
        """
        Recursively apply merge keys for partial matches throughout object tree.

        Skip_fields are preserved in output but not considered for matching.
        """
        if skip_fields is None:
            skip_fields = ("_key", "_status", "title")

        if isinstance(obj, dict):
            anchor, overrides, matched = self.find_partial_match(obj, set(skip_fields))

            if anchor is not None:
                result = CommentedMap()

                for key in skip_fields:
                    if key in obj:
                        result[key] = obj[key]

                set_merge_key(result, anchor)

                for key, value in overrides.items():
                    if isinstance(value, (dict, list)):
                        result[key] = self.apply_partial_matching(value, skip_fields=())
                    else:
                        result[key] = value

                for key in obj:
                    if key in skip_fields or key in matched or key in overrides:
                        continue
                    value = obj[key]
                    if isinstance(value, (dict, list)):
                        result[key] = self.apply_partial_matching(value, skip_fields=())
                    else:
                        result[key] = value

                return result

            result = CommentedMap()
            if hasattr(obj, merge_attrib):
                setattr(result, merge_attrib, getattr(obj, merge_attrib))
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    result[key] = self.apply_partial_matching(value, skip_fields=())
                else:
                    result[key] = value
            return result

        elif isinstance(obj, list):
            result = CommentedSeq()
            for item in obj:
                if isinstance(item, (dict, list)):
                    result.append(self.apply_partial_matching(item, skip_fields=()))
                else:
                    result.append(item)
            return result

        return obj


def fetch_activities(session, group_id: str, limit: int = 100, skip: int = 0) -> dict:
    """Fetch activities from the API with pagination."""
    url = f"{BASE_URL}/v1/activities"
    params = {
        "groups[0]": group_id,
        "links[groups]": "true",
        "total": "true",
        "limit": limit,
        "skip": skip,
        "text": "",
    }

    response = session.get(url, params=params)
    response.raise_for_status()
    return response.json()


def fetch_all_activities(session, group_id: str) -> list:
    """Fetch all activities with automatic pagination."""
    all_items = []
    skip = 0
    limit = 100

    while True:
        result = fetch_activities(session, group_id, limit=limit, skip=skip)
        items = result.get("items", [])
        all_items.extend(items)

        if not result.get("hasMore", False):
            break

        skip += limit
        print(f"Fetched {len(all_items)} activities...", file=sys.stderr)

    return all_items


def fetch_activity_by_id(session, activity_id: str) -> dict:
    """Fetch a single activity by ID."""
    url = f"{BASE_URL}/v1/activities/{activity_id}"
    params = {"links[files]": "true"}

    response = session.get(url, params=params)
    response.raise_for_status()
    return response.json()


def convert_activity_to_yaml_schema(activity: dict) -> dict:
    """Convert API activity response to our YAML schema format using Transformer."""
    transformer = Transformer()
    return transformer.api_to_yaml(activity)


def get_activity_status(activity: dict) -> str:
    """Get a human-readable status for an activity."""
    status = activity.get("status")
    if status:
        return status

    # status is None - check visibility dates
    tags = activity.get("tags", {})
    visibility = tags.get("visibility", {})
    vis_start = visibility.get("start", 0)
    vis_end = visibility.get("end", 0)

    now_ms = datetime.now().timestamp() * 1000

    if vis_end and vis_end < now_ms:
        return "expired"
    elif vis_start and vis_start > now_ms:
        return "pending"
    else:
        return "unknown"


def list_activities(activities: list) -> None:
    """Print a summary list of activities."""
    print(f"Found {len(activities)} activities:\n")
    for i, activity in enumerate(activities, 1):
        key = activity.get("_key", "?")
        status = get_activity_status(activity)
        traits = activity.get("traits", {})
        translations = traits.get("translations", {})
        name = translations.get("fi", {}).get("name", "Untitled")
        print(f"  {i}. [{key}] {name} ({status})")


def set_merge_key(target: CommentedMap, source: CommentedMap, position: int = 0) -> None:
    """Set a merge key (<<: *anchor) on a CommentedMap."""
    mv = MergeValue()
    mv.merge_pos = position
    mv.append(source)
    setattr(target, merge_attrib, mv)


def apply_template_matching(events: list, matcher: TemplateMatcher) -> tuple[CommentedMap, list]:
    """
    Apply template matching to events and return structure with anchors/aliases.

    Returns:
        (defaults_section, events_list) - defaults with anchors, events with aliases
    """
    defaults = matcher.get_template_defaults()
    processed_events = CommentedSeq()

    for event in events:
        # Apply partial matching (merge keys) then exact matching (aliases)
        cm = matcher.apply_partial_matching(event)
        cm = matcher.apply_anchors(cm)
        processed_events.append(cm)

    return defaults, processed_events


def main():
    parser = argparse.ArgumentParser(
        description="Download activities from hallinta.lahella.fi"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw API response as JSON",
    )
    parser.add_argument(
        "--yaml",
        action="store_true",
        help="Output in YAML format (matching events.yaml schema)",
    )
    parser.add_argument(
        "--id",
        type=str,
        help="Fetch a single activity by its ID",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file (default: stdout)",
    )
    parser.add_argument(
        "--templates", "-t",
        type=Path,
        default=EVENTS_FILE,
        help="YAML file with defaults/templates for matching (default: events.yaml)",
    )
    args = parser.parse_args()

    auth = load_auth_config()
    session = get_authenticated_session(auto_refresh=True)
    group_id = auth["group_id"]

    if args.id:
        print(f"Fetching activity {args.id}...", file=sys.stderr)
        activities = [fetch_activity_by_id(session, args.id)]
    else:
        print(f"Fetching activities for group {group_id}...", file=sys.stderr)
        activities = fetch_all_activities(session, group_id)

    print(f"Downloaded {len(activities)} activities.", file=sys.stderr)

    if args.json:
        output = json.dumps(activities, indent=2, ensure_ascii=False)
    elif args.yaml:
        events = [convert_activity_to_yaml_schema(a) for a in activities]
        matcher = TemplateMatcher(args.templates)
        defaults, processed_events = apply_template_matching(events, matcher)

        result = CommentedMap()
        result["$schema"] = "./schema.json"
        result["defaults"] = defaults
        result[matcher.events_key] = processed_events

        yaml = YAML()
        yaml.default_flow_style = False
        yaml.indent(mapping=2, sequence=4, offset=2)

        if args.output:
            with open(args.output, "w") as f:
                yaml.dump(result, f)
            print(f"Wrote {len(events)} events to {args.output}", file=sys.stderr)
            return
        else:
            import io
            stream = io.StringIO()
            yaml.dump(result, stream)
            output = stream.getvalue()
    else:
        list_activities(activities)
        return

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Wrote output to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
