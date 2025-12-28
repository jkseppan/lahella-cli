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


def merge_configs(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence.

    - Arrays are concatenated (base + override)
    - Dicts are recursively merged
    - Other values are replaced
    """
    result = base.copy()
    for key, value in override.items():
        if key in result:
            # Concatenate arrays
            if isinstance(result[key], list) and isinstance(value, list):
                result[key] = result[key] + value
            # Recursively merge dictionaries
            elif isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_configs(result[key], value)
            # Otherwise override
            else:
                result[key] = value
        else:
            result[key] = value
    return result


def load_config(config_path: Path) -> dict:
    """Load TOML configuration file with support for auth and defaults."""
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # Look for auth.toml in the same directory
    auth_path = config_path.parent / "auth.toml"
    if auth_path.exists():
        with open(auth_path, "rb") as f:
            auth_config = tomllib.load(f)
            config = merge_configs(auth_config, config)

    # Look for defaults.toml in the same directory
    defaults_path = config_path.parent / "defaults.toml"
    if defaults_path.exists():
        with open(defaults_path, "rb") as f:
            defaults_config = tomllib.load(f)
            # Merge order: auth < defaults < course-specific
            config = merge_configs(defaults_config, config)

    return config


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


def build_channel(channel_config: dict, registration: dict, defaults: dict) -> dict:
    """Build a single channel from config."""
    location = channel_config.get("location", {})
    schedule = channel_config.get("schedule", {})

    # Merge with defaults
    address = {**defaults.get("address", {}), **location.get("address", {})}

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

    return {
        "id": str(uuid.uuid4()),
        "type": [location.get("type", "place")],
        "events": [{
            "start": date_to_timestamp(schedule["start_date"]),
            "timeZone": schedule.get("timezone", "Europe/Helsinki"),
            "type": "4",  # recurring event
            "recurrence": recurrence,
        }],
        "translations": {
            "fi": {
                "summary": text_to_html(location.get("summary", {}).get("fi", "")),
                "address": {
                    "street": address.get("street", ""),
                    "postalCode": address.get("postal_code", ""),
                    "city": address.get("city", "Helsinki"),
                    "state": address.get("state", "Uusimaa"),
                    "country": address.get("country", "FI"),
                },
                "registration": text_to_html(registration["info"]["fi"]),
            },
            "en": {
                "summary": text_to_html(location.get("summary", {}).get("en", "")),
                "address": {
                    "postalCode": address.get("postal_code", ""),
                    "city": address.get("city", "Helsinki"),
                    "state": address.get("state", "Uusimaa"),
                    "country": address.get("country", "FI"),
                },
                "registration": text_to_html(registration["info"]["en"]),
            },
            "sv": {
                "address": {
                    "postalCode": address.get("postal_code", ""),
                    "city": address.get("city", "Helsinki"),
                    "state": "Nyland" if address.get("state") == "Uusimaa" else address.get("state", "Uusimaa"),
                    "country": address.get("country", "FI"),
                },
            },
        },
        "map": {
            "center": {
                "type": "Point",
                "coordinates": address.get("coordinates", [24.9, 60.2]),
            },
            "zoom": address.get("zoom", 16),
        },
        "accessibility": location.get("accessibility", ["ac_unknow"]),
        "registrationRequired": registration["required"],
        "registrationUrl": registration["url"],
        "registrationEmail": registration["email"],
    }


def build_activity_payload(config: dict, photo_id: str | None) -> dict:
    """Build the activity JSON payload from config."""
    course = config["course"]
    pricing = config["pricing"]
    registration = config["registration"]
    contacts = config.get("contacts", {})
    image = config.get("image", {})

    # Build channels - support both single location and multiple channels
    channels = []
    if "channels" in config:
        # Multi-channel mode
        defaults = {"address": config.get("location", {}).get("address", {})}
        for ch_config in config["channels"]:
            channels.append(build_channel(ch_config, registration, defaults))
        # Collect regions from all channels
        regions = config.get("location", {}).get("regions", ["city/FI/Helsinki"])
    else:
        # Single location mode (backwards compatible)
        location = config["location"]
        schedule = config["schedule"]
        channels.append(build_channel(
            {"location": location, "schedule": schedule},
            registration,
            {"address": location.get("address", {})}
        ))
        regions = location.get("regions", ["city/FI/Helsinki"])

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
        "channels": channels,
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
        "region": regions,
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
    session = httpx.Client(timeout=60.0)  # 60s timeout for image uploads
    session.cookies.update(parse_cookies(config["auth"]["cookies"]))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/activities?_key=new&type=hobby",
    })

    # Test authentication
    if args.dry_run:
        print("Testing authentication...")
        test_url = f"{BASE_URL}/v1/activities"
        try:
            response = session.get(test_url, params={"group": config["auth"]["group_id"], "limit": 1})
            if response.status_code == 200:
                print("✓ Authentication successful!\n")
            elif response.status_code == 401:
                print("✗ Authentication failed - invalid or expired cookies")
                sys.exit(1)
            else:
                print(f"✗ Unexpected response: {response.status_code}")
                print(response.text)
                sys.exit(1)
        except Exception as e:
            print(f"✗ Error testing auth: {e}")
            sys.exit(1)

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
