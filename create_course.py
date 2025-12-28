#!/usr/bin/env python3
"""
Create a course listing on lahella.fi using their API.

Usage:
    python create_course.py course_config.toml

The user must be logged in via browser and provide auth cookies in the config.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import httpx

import tomllib


BASE_URL = "https://hallinta.lahella.fi"


def load_config(config_path: Path) -> dict:
    """Load TOML configuration file."""
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def parse_cookies(cookie_string: str) -> dict:
    """Parse cookie string into dict."""
    cookies = {}
    if cookie_string:
        for item in cookie_string.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
    return cookies


def text_to_html(text: str) -> str:
    """Convert plain text to HTML paragraphs."""
    paragraphs = text.strip().split("\n\n")
    html_parts = []
    for p in paragraphs:
        # Replace single newlines with spaces within paragraphs
        p = p.replace("\n", " ").strip()
        if p:
            html_parts.append(f'<p dir="ltr">{p}</p>')
    return "".join(html_parts)


def date_to_timestamp(date_str: str) -> int:
    """Convert YYYY-MM-DD to milliseconds timestamp."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def upload_image(session: httpx.Session, config: dict, image_path: Path) -> str:
    """Upload an image and return the file ID."""
    group_id = config["auth"]["group_id"]
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


def build_activity_payload(config: dict, photo_id: str | None) -> dict:
    """Build the activity JSON payload from config."""
    course = config["course"]
    location = config["location"]
    schedule = config["schedule"]
    pricing = config["pricing"]
    registration = config["registration"]
    contacts = config.get("contacts", {})
    image = config.get("image", {})

    # Generate a channel ID
    channel_id = str(uuid.uuid4())

    # Build weekly schedule
    day_specific_times = []
    for weekly in schedule.get("weekly", []):
        day_specific_times.append({
            "weekday": weekly["weekday"],
            "startTime": weekly["start_time"],
            "endTime": weekly["end_time"],
        })

    # Build recurrence
    recurrence = {
        "period": "P1W",
        "exclude": [],
        "end": date_to_timestamp(schedule["end_date"]),
        "daySpecificTimes": day_specific_times,
    }

    # Build channel (location/event info)
    channel = {
        "id": channel_id,
        "type": [location["type"]],
        "events": [{
            "start": date_to_timestamp(schedule["start_date"]),
            "timeZone": schedule["timezone"],
            "type": "4",  # recurring event
            "recurrence": recurrence,
        }],
        "translations": {
            "fi": {
                "summary": text_to_html(location["summary"]["fi"]),
                "address": {
                    "street": location["address"]["street"],
                    "postalCode": location["address"]["postal_code"],
                    "city": location["address"]["city"],
                    "state": location["address"]["state"],
                    "country": location["address"]["country"],
                },
                "registration": text_to_html(registration["info"]["fi"]),
            },
            "en": {
                "summary": text_to_html(location["summary"]["en"]),
                "address": {
                    "postalCode": location["address"]["postal_code"],
                    "city": location["address"]["city"],
                    "state": location["address"]["state"],
                    "country": location["address"]["country"],
                },
                "registration": text_to_html(registration["info"]["en"]),
            },
            "sv": {
                "address": {
                    "postalCode": location["address"]["postal_code"],
                    "city": location["address"]["city"],
                    "state": "Nyland" if location["address"]["state"] == "Uusimaa" else location["address"]["state"],
                    "country": location["address"]["country"],
                },
            },
        },
        "map": {
            "center": {
                "type": "Point",
                "coordinates": location["address"]["coordinates"],
            },
            "zoom": location["address"]["zoom"],
        },
        "accessibility": location.get("accessibility", ["ac_unknow"]),
        "registrationRequired": registration["required"],
        "registrationUrl": registration["url"],
        "registrationEmail": registration["email"],
    }

    # Build contacts list
    contact_list = []
    for contact in contacts.get("list", []):
        contact_list.append({
            "type": contact["type"],
            "value": contact["value"],
            "id": str(uuid.uuid4()),
            "translations": {
                "fi": {"description": contact.get("description_fi", "Lisätietoja")},
                "en": {"description": contact.get("description_en", "Details")},
                "sv": {"description": "Detaljer"},
            },
        })

    # Build main traits
    traits = {
        "type": course["type"],
        "requiredLocales": course["required_locales"],
        "channels": [channel],
        "translations": {
            "fi": {
                "name": course["title"]["fi"],
                "summary": text_to_html(course["summary"]["fi"]),
                "description": text_to_html(course["description"]["fi"]),
                "pricing": text_to_html(pricing["info"]["fi"]),
            },
            "en": {
                "name": course["title"]["en"],
                "summary": text_to_html(course["summary"]["en"]),
                "description": text_to_html(course["description"]["en"]),
                "pricing": text_to_html(pricing["info"]["en"]),
            },
        },
        "theme": course["categories"]["themes"],
        "demographic": course["demographics"]["age_groups"] + course["demographics"]["gender"],
        "format": course["categories"]["formats"],
        "locale": course["categories"]["locales"],
        "region": location["regions"],
        "pricing": [pricing["type"]],
        "contacts": contact_list,
    }

    if photo_id:
        traits["photo"] = photo_id
        traits["photoAlt"] = image.get("alt", "")

    # Build full payload
    payload = {
        "group": config["auth"]["group_id"],
        "traits": traits,
        "lockedAt": int(datetime.now().timestamp() * 1000),
        "lockedBy": f"{config['auth']['group_id']}:{int(datetime.now().timestamp() * 1000)}",
    }

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
        help="Path to TOML configuration file",
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

    config = load_config(args.config)

    # Validate auth
    if not config.get("auth", {}).get("cookies"):
        print("Error: No auth cookies configured.")
        print("Please log in via browser and copy cookies to the config file.")
        sys.exit(1)

    # Create session with cookies
    session = httpx.Client()
    session.cookies.update(parse_cookies(config["auth"]["cookies"]))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/activities?_key=new&type=hobby",
    })

    # Upload image if configured
    photo_id = None
    image_config = config.get("image", {})
    if image_config.get("path"):
        image_path = args.config.parent / image_config["path"]
        if image_path.exists():
            if args.dry_run:
                print(f"Would upload image: {image_path}")
                photo_id = "DRY_RUN_PHOTO_ID"
            else:
                photo_id = upload_image(session, config, image_path)
        else:
            print(f"Warning: Image not found: {image_path}")

    # Build payload
    payload = build_activity_payload(config, photo_id)

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
