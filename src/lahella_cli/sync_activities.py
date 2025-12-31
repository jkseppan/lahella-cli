#!/usr/bin/env python3
"""
Show diff between local YAML events and server state, and optionally apply changes.

Usage:
    uv run sync_activities.py                           # Show usage
    uv run sync_activities.py --course 1                # Show diff for course #1
    uv run sync_activities.py --title "Taiji"           # Show diff by title match
    uv run sync_activities.py --all                     # Show diff for all events
    uv run sync_activities.py --course 1 --apply        # Show diff and apply changes
    uv run sync_activities.py --all --apply             # Apply all changes (with confirmation)
"""

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

import httpx

from .activity_diff import diff_activities, format_diffs
from .auth_helper import get_authenticated_session, load_auth_config
from .create_course import update_activity
from .download_activities import (
    fetch_all_activities,
    fetch_activity_by_id,
    convert_activity_to_yaml_schema,
)
from .field_mapping import normalize_text
from .update_payload import build_update_payload


EVENTS_FILE = Path(__file__).parent / "events.yaml"


def load_local_events(events_file: Path = EVENTS_FILE) -> list[dict]:
    """Load events from local YAML file."""
    if not events_file.exists():
        print(f"Events file not found: {events_file}", file=sys.stderr)
        sys.exit(1)

    yaml = YAML()
    with open(events_file) as f:
        config = yaml.load(f)

    events = config.get("events", [])
    return [dict(e) for e in events]


def find_local_by_key(events: list[dict], key: str) -> dict | None:
    """Find a local event by its _key."""
    for event in events:
        if event.get("_key") == key:
            return event
    return None


def find_local_by_title(events: list[dict], title: str) -> dict | None:
    """Find a local event by title (partial match, case-insensitive)."""
    title_lower = normalize_text(title)
    for event in events:
        event_title = event.get("title", {})
        fi_title = normalize_text(event_title.get("fi", ""))
        en_title = normalize_text(event_title.get("en", ""))
        if title_lower in fi_title or title_lower in en_title:
            return event
    return None


def find_server_by_title(
    activities: list[dict], title: str
) -> dict | None:
    """Find a server activity by title (partial match)."""
    title_lower = normalize_text(title)
    for activity in activities:
        traits = activity.get("traits", {})
        translations = traits.get("translations", {})
        fi_name = normalize_text(translations.get("fi", {}).get("name", ""))
        en_name = normalize_text(translations.get("en", {}).get("name", ""))
        if title_lower in fi_name or title_lower in en_name:
            return activity
    return None


def show_diff(local: dict, server_yaml: dict, title: str) -> bool:
    """
    Show diff between local and server state.

    Returns True if there are differences, False if identical.
    """
    diffs = diff_activities(local, server_yaml)

    if not diffs:
        print(f"\n{title}: No changes")
        return False

    print(f"\n{title}: {len(diffs)} change(s)")
    print(format_diffs(diffs))
    return True


def apply_update(
    session: httpx.Client,
    local: dict,
    server_activity: dict,
    group_id: str,
) -> dict:
    """
    Apply local changes to server.

    Args:
        session: Authenticated HTTP client
        local: Local event dict from YAML
        server_activity: Current server activity (raw API format)
        group_id: Group ID for the payload

    Returns:
        API response from update
    """
    activity_id = local.get("_key") or server_activity.get("_key")
    if not activity_id:
        raise ValueError("No activity ID found in local or server data")

    payload = build_update_payload(local, server_activity, group_id)
    return update_activity(session, activity_id, payload)


def prompt_and_apply(
    session: httpx.Client,
    local: dict,
    server_activity: dict,
    group_id: str,
    title: str,
) -> bool:
    """
    Prompt user for confirmation and apply update.

    Returns True if update was applied, False if skipped.
    """
    response = input(f"\nApply changes to '{title}'? [y/N] ").strip().lower()
    if response not in ("y", "yes"):
        print("Skipped.")
        return False

    try:
        result = apply_update(session, local, server_activity, group_id)
        print(f"Updated successfully. (key: {result.get('_key')})")
        return True
    except Exception as e:
        print(f"Error applying update: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Show diff between local YAML and server state"
    )
    parser.add_argument(
        "--course", "-c",
        type=int,
        help="Course number (1-indexed) from events.yaml",
    )
    parser.add_argument(
        "--title", "-t",
        type=str,
        help="Find course by title (partial match)",
    )
    parser.add_argument(
        "--id",
        type=str,
        help="Server activity ID to compare against",
    )
    parser.add_argument(
        "--events-file", "-f",
        type=Path,
        default=EVENTS_FILE,
        help="Path to local events YAML file",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Show diff for all events with _key",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to server after showing diff (with confirmation)",
    )
    args = parser.parse_args()

    local_events = load_local_events(args.events_file)
    print(f"Loaded {len(local_events)} local events.", file=sys.stderr)

    auth = load_auth_config()
    session = get_authenticated_session(auto_refresh=True)
    group_id = auth["group_id"]

    if args.course:
        if args.course < 1 or args.course > len(local_events):
            print(f"Invalid course number. Valid range: 1-{len(local_events)}")
            sys.exit(1)

        local = local_events[args.course - 1]
        title = local.get("title", {}).get("fi", f"Course {args.course}")

        if args.id:
            server_key = args.id
        elif local.get("_key"):
            server_key = local["_key"]
        else:
            print(f"Course {args.course} has no _key. Use --id to specify server ID.")
            sys.exit(1)

        print(f"Fetching activity {server_key}...", file=sys.stderr)
        server_activity = fetch_activity_by_id(session, server_key)
        server_yaml = convert_activity_to_yaml_schema(server_activity)

        has_changes = show_diff(local, server_yaml, title)

        if has_changes and args.apply:
            prompt_and_apply(session, local, server_activity, group_id, title)

    elif args.title:
        local = find_local_by_title(local_events, args.title)
        if not local:
            print(f"No local event found matching: {args.title}")
            sys.exit(1)

        assert local is not None  # type narrowing: sys.exit() above never returns
        title = local.get("title", {}).get("fi", args.title)

        if args.id:
            server_key = args.id
        elif local.get("_key"):
            server_key = local["_key"]
        else:
            print("Fetching all activities to find match...", file=sys.stderr)
            activities = fetch_all_activities(session, group_id)
            server_activity = find_server_by_title(activities, args.title)
            if not server_activity:
                print(f"No server activity found matching: {args.title}")
                sys.exit(1)
            assert server_activity is not None  # type narrowing
            server_key = server_activity["_key"]

        print(f"Fetching activity {server_key}...", file=sys.stderr)
        server_activity = fetch_activity_by_id(session, server_key)
        server_yaml = convert_activity_to_yaml_schema(server_activity)

        has_changes = show_diff(local, server_yaml, title)

        if has_changes and args.apply:
            prompt_and_apply(session, local, server_activity, group_id, title)

    elif args.all:
        events_with_key = [e for e in local_events if e.get("_key")]
        if not events_with_key:
            print("No local events have _key. Nothing to compare.")
            sys.exit(0)

        print(
            f"Comparing {len(events_with_key)} events with server...",
            file=sys.stderr
        )

        changed_events: list[tuple[dict, dict, str]] = []
        unchanged = 0

        for local in events_with_key:
            server_key = local["_key"]
            title = local.get("title", {}).get("fi", server_key)

            try:
                server_activity = fetch_activity_by_id(session, server_key)
                server_yaml = convert_activity_to_yaml_schema(server_activity)

                if show_diff(local, server_yaml, title):
                    changed_events.append((local, server_activity, title))
                else:
                    unchanged += 1
            except Exception as e:
                print(f"\n{title}: Error fetching - {e}", file=sys.stderr)

        print(f"\nSummary: {len(changed_events)} changed, {unchanged} unchanged")

        if changed_events and args.apply:
            print(f"\nReady to apply {len(changed_events)} update(s).")
            applied = 0
            for local, server_activity, title in changed_events:
                if prompt_and_apply(session, local, server_activity, group_id, title):
                    applied += 1
            print(f"\nApplied {applied}/{len(changed_events)} update(s).")

    else:
        print("Usage: sync_activities.py [--course N | --title TEXT | --all] [--apply]")
        print("\nOptions:")
        print("  --course N    Compare course N from events.yaml")
        print("  --title TEXT  Find and compare course by title")
        print("  --all         Compare all events that have _key")
        print("  --id ID       Specify server activity ID manually")
        print("  --apply       Apply changes to server (with confirmation)")
        sys.exit(1)


if __name__ == "__main__":
    main()
