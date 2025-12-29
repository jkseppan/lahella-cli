#!/usr/bin/env python3
"""
Create a course listing on lahella.fi using their API.

Usage:
    python create_course.py courses.yaml [--course TITLE]

The user must be logged in via browser and provide auth cookies in auth.yaml.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
from ruamel.yaml import YAML

from auth_helper import get_authenticated_session, load_auth_config
from field_mapping import Transformer


BASE_URL = "https://hallinta.lahella.fi"


def load_courses(courses_path: Path) -> dict:
    """Load courses from YAML file. Returns full config with defaults resolved."""
    yaml = YAML()
    with open(courses_path) as f:
        config = yaml.load(f)
    return config


def get_course_by_title(config: dict, title: str) -> dict | None:
    """Find a course by its Finnish title (partial match) or by index (1-based)."""
    courses = config.get("courses", [])

    # Try numeric index first (1-based)
    if title.isdigit():
        idx = int(title) - 1
        if 0 <= idx < len(courses):
            return courses[idx]
        return None

    # Exact match first
    for course in courses:
        if title.lower() == course.get("title", {}).get("fi", "").lower():
            return course

    # Then partial match
    for course in courses:
        if title.lower() in course.get("title", {}).get("fi", "").lower():
            return course

    return None


def list_courses(config: dict) -> None:
    """Print all available courses."""
    print("Available courses:")
    for i, course in enumerate(config.get("courses", []), 1):
        title = course.get("title", {}).get("fi", "Untitled")
        print(f"  {i}. {title}")


def upload_image_for_course(session: httpx.Client, auth: dict, image_path: Path) -> str:
    """Upload an image and return the file ID."""
    group_id = auth["group_id"]
    url = f"{BASE_URL}/v1/files"
    params = {
        "group": group_id,
        "cacheControl": "public, max-age=3600, s-maxage=3600",
    }

    with open(image_path, "rb") as f:
        files = {"file": (image_path.name, f, "image/jpeg")}
        response = session.post(url, params=params, files=files)

    response.raise_for_status()
    result = response.json()
    print(f"Uploaded image: {result.get('_key', 'unknown')}")
    return result["_key"]


def build_activity_payload(course: dict, auth: dict, photo_id: str | None) -> dict:
    """Build the activity JSON payload from course data using Transformer."""
    transformer = Transformer()
    payload = transformer.yaml_to_api(course, group_id=auth["group_id"])

    # Add photo if uploaded
    if photo_id:
        payload["traits"]["photo"] = photo_id
        payload["traits"]["photoAlt"] = course.get("image", {}).get("alt", "")

    return payload


def create_activity(session: httpx.Session, payload: dict) -> dict:
    """Create the activity via API."""
    url = f"{BASE_URL}/v1/activities"
    headers = {"Content-Type": "application/json"}

    response = session.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        print(f"Error creating activity: {response.status_code}")
        print(response.text)
        response.raise_for_status()

    return response.json()


def main():
    parser = argparse.ArgumentParser(
        description="Create a course listing on lahella.fi"
    )
    parser.add_argument(
        "config",
        type=Path,
        nargs="?",
        default=Path(__file__).parent / "courses.yaml",
        help="Path to YAML configuration file (default: courses.yaml)",
    )
    parser.add_argument(
        "--course", "-c",
        type=str,
        help="Course title to create (partial match)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available courses",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload without sending it",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    config = load_courses(args.config)

    # List courses mode
    if args.list:
        list_courses(config)
        return

    # Find the course to create
    if not args.course:
        print("Error: Please specify a course with --course TITLE")
        print()
        list_courses(config)
        sys.exit(1)

    course = get_course_by_title(config, args.course)
    if not course:
        print(f"Error: No course found matching '{args.course}'")
        print()
        list_courses(config)
        sys.exit(1)

    print(f"Creating course: {course['title']['fi']}")

    # Load auth config
    auth = load_auth_config()

    # Get authenticated session (will auto-refresh token if needed)
    session = get_authenticated_session(auto_refresh=True)
    session.headers.update({
        "Referer": f"{BASE_URL}/activities?_key=new&type=hobby",
    })

    # Test authentication in dry-run mode
    if args.dry_run:
        print("Authentication successful!\n")

    # Upload image if configured
    photo_id = None
    image_config = course.get("image", {})
    if image_config.get("path"):
        image_path = args.config.parent / image_config["path"]
        if image_path.exists():
            if args.dry_run:
                print(f"Would upload image: {image_path}")
                photo_id = "DRY_RUN_PHOTO_ID"
            else:
                photo_id = upload_image_for_course(session, auth, image_path)
        else:
            print(f"Warning: Image not found: {image_path}")

    # Build payload
    payload = build_activity_payload(course, auth, photo_id)

    if args.dry_run:
        print("\n=== DRY RUN - Would send this payload ===\n")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    # Create the activity
    print("Creating activity...")
    result = create_activity(session, payload)

    print(f"\nSuccess! Activity created with ID: {result.get('_key')}")
    print(f"View at: {BASE_URL}/activities?_key={result.get('_key')}")


if __name__ == "__main__":
    main()
