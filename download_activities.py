#!/usr/bin/env python3
"""
Download existing activities from hallinta.lahella.fi.

Usage:
    uv run download_activities.py                    # List all activities
    uv run download_activities.py --json             # Output as JSON
    uv run download_activities.py --yaml             # Output as YAML (for merging into courses.yaml)
    uv run download_activities.py --id 12345         # Get single activity by ID
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, merge_attrib
from ruamel.yaml.mergevalue import MergeValue

from auth_helper import get_authenticated_session, load_auth_config, BASE_URL


COURSES_FILE = Path(__file__).parent / "courses.yaml"


class TemplateMatcher:
    """Matches downloaded data against templates from courses.yaml."""

    def __init__(self, courses_file: Path = COURSES_FILE):
        self.defaults = {}
        self.anchors = {}  # name -> CommentedMap with anchor
        self._load_defaults(courses_file)

    def _load_defaults(self, courses_file: Path) -> None:
        """Load defaults section from courses.yaml."""
        if not courses_file.exists():
            return

        yaml = YAML()
        with open(courses_file) as f:
            config = yaml.load(f)

        defaults = config.get("defaults", {})
        self.defaults = defaults

        # Extract key templates for matching
        self._extract_templates(defaults)

    def _extract_templates(self, defaults: dict) -> None:
        """Extract templates we can match against."""
        # Course defaults (type, required_locales, categories, demographics)
        if "course" in defaults:
            self.anchors["course_defaults"] = defaults["course"]

        # Location defaults
        if "location" in defaults:
            self.anchors["location_defaults"] = defaults["location"]

        # Schedule defaults
        if "schedule" in defaults:
            self.anchors["schedule_defaults"] = defaults["schedule"]

        # Pricing templates
        if "pricing" in defaults:
            if "paid" in defaults["pricing"]:
                self.anchors["pricing_paid"] = defaults["pricing"]["paid"]
            if "free" in defaults["pricing"]:
                self.anchors["pricing_free"] = defaults["pricing"]["free"]

        # Text blocks - store normalized versions for fuzzy matching
        if "text" in defaults:
            text = defaults["text"]
            if "course_summary" in text:
                self.anchors["summary_kurssi"] = text["course_summary"]
            if "course_description" in text:
                self.anchors["description_kurssi"] = text["course_description"]
            if "harjoitus_summary" in text:
                self.anchors["summary_harjoitus"] = text["harjoitus_summary"]
            if "harjoitus_description" in text:
                self.anchors["description_harjoitus"] = text["harjoitus_description"]
            if "ulko_description" in text:
                self.anchors["description_ulko"] = text["ulko_description"]

        # Registration
        if "registration" in defaults:
            if "harjoitus" in defaults["registration"]:
                self.anchors["registration_harjoitus"] = defaults["registration"]["harjoitus"]

        # Contacts
        if "contacts" in defaults:
            if "www" in defaults["contacts"]:
                self.anchors["contacts_www"] = defaults["contacts"]["www"]
            if "harjoitus" in defaults["contacts"]:
                self.anchors["contacts_harjoitus"] = defaults["contacts"]["harjoitus"]

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison (strip whitespace, lowercase)."""
        if not text:
            return ""
        # Remove extra whitespace, normalize
        return " ".join(text.lower().split())

    def _texts_match(self, text1: str | dict, text2: str | dict) -> bool:
        """Check if two text values match (fuzzy for strings)."""
        if isinstance(text1, dict) and isinstance(text2, dict):
            # Compare each language
            for lang in set(text1.keys()) | set(text2.keys()):
                if not self._texts_match(text1.get(lang, ""), text2.get(lang, "")):
                    return False
            return True
        elif isinstance(text1, str) and isinstance(text2, str):
            return self._normalize_text(text1) == self._normalize_text(text2)
        return False

    def _values_match(self, val1, val2) -> bool:
        """Check if two values match (deep comparison)."""
        # Allow dict vs CommentedMap comparison
        if isinstance(val1, dict) and isinstance(val2, dict):
            if set(val1.keys()) != set(val2.keys()):
                return False
            return all(self._values_match(val1[k], val2[k]) for k in val1)
        # Allow list vs CommentedSeq comparison
        if isinstance(val1, (list, CommentedSeq)) and isinstance(val2, (list, CommentedSeq)):
            if len(val1) != len(val2):
                return False
            return all(self._values_match(a, b) for a, b in zip(val1, val2))
        return val1 == val2

    def find_matching_anchor(self, field: str, value) -> str | None:
        """Find an anchor that matches the given value for a field."""
        # Map field names to relevant anchors
        field_anchors = {
            "summary": ["summary_kurssi", "summary_harjoitus"],
            "description": ["description_kurssi", "description_harjoitus", "description_ulko"],
            "pricing": ["pricing_paid", "pricing_free"],
            "registration": ["registration_harjoitus"],
            "contacts": ["contacts_www", "contacts_harjoitus"],
        }

        candidates = field_anchors.get(field, [])

        for anchor_name in candidates:
            if anchor_name not in self.anchors:
                continue
            anchor_val = self.anchors[anchor_name]

            # For text fields, use fuzzy matching
            if field in ("summary", "description"):
                if self._texts_match(value, anchor_val):
                    return anchor_name
            else:
                if self._values_match(value, anchor_val):
                    return anchor_name

        return None

    def matches_course_defaults(self, course: dict) -> bool:
        """Check if course matches course_defaults for merge key."""
        if "course_defaults" not in self.anchors:
            return False
        defaults = self.anchors["course_defaults"]

        # Check key fields
        checks = [
            course.get("type") == defaults.get("type"),
            self._values_match(
                course.get("required_locales", []),
                defaults.get("required_locales", [])
            ),
            self._values_match(
                course.get("categories", {}),
                defaults.get("categories", {})
            ),
            self._values_match(
                course.get("demographics", {}),
                defaults.get("demographics", {})
            ),
        ]
        return all(checks)

    def matches_location_defaults(self, location: dict) -> bool:
        """Check if location matches location_defaults."""
        if "location_defaults" not in self.anchors:
            return False
        defaults = self.anchors["location_defaults"]

        # Check non-varying fields
        address = location.get("address", {})
        def_address = defaults.get("address", {})

        # Compare regions as sets (order doesn't matter)
        loc_regions = set(location.get("regions", []))
        def_regions = set(defaults.get("regions", []))

        checks = [
            location.get("type") == defaults.get("type"),
            loc_regions == def_regions,  # Order-independent comparison
            self._values_match(location.get("accessibility", []), defaults.get("accessibility", [])),
            address.get("city") == def_address.get("city"),
            address.get("state") == def_address.get("state"),
            address.get("country") == def_address.get("country"),
        ]
        return all(checks)


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


def timestamp_to_date(ts: int | None) -> str:
    """Convert milliseconds timestamp to YYYY-MM-DD."""
    if ts is None or ts == 0:
        return ""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")


def html_to_text(html: str | None) -> str:
    """Strip basic HTML tags to get plain text."""
    if not html:
        return ""
    import re
    # Remove HTML tags but keep content
    text = re.sub(r'<[^>]+>', '', html)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def convert_activity_to_yaml_schema(activity: dict) -> dict:
    """Convert API activity response to our YAML schema format."""
    traits = activity.get("traits", {})
    translations = traits.get("translations", {})
    channels = traits.get("channels", [])

    # Build course dict matching courses.yaml schema
    course = {
        "_key": activity.get("_key"),  # Server ID for sync
        "_status": activity.get("status"),
        "title": {},
        "type": traits.get("type", "hobby"),
        "required_locales": traits.get("requiredLocales", ["fi", "en"]),
    }

    # Translations for title, summary, description
    for lang, trans in translations.items():
        if "name" in trans and trans["name"]:
            if "title" not in course:
                course["title"] = {}
            course["title"][lang] = trans["name"]
        if "summary" in trans and trans["summary"]:
            if "summary" not in course:
                course["summary"] = {}
            course["summary"][lang] = html_to_text(trans["summary"])
        if "description" in trans and trans["description"]:
            if "description" not in course:
                course["description"] = {}
            course["description"][lang] = html_to_text(trans["description"])
        if "pricing" in trans and trans["pricing"]:
            if "pricing" not in course:
                course["pricing"] = {"info": {}}
            if "info" not in course["pricing"]:
                course["pricing"]["info"] = {}
            course["pricing"]["info"][lang] = html_to_text(trans["pricing"])

    # Categories
    course["categories"] = {
        "themes": list(traits.get("theme", [])),
        "formats": list(traits.get("format", [])),
        "locales": list(traits.get("locale", [])),
    }

    # Demographics
    age_groups = []
    gender = []
    for demo in traits.get("demographic", []):
        if demo.startswith("ageGroup/"):
            age_groups.append(demo)
        elif demo.startswith("gender/"):
            gender.append(demo)
    course["demographics"] = {
        "age_groups": age_groups,
        "gender": gender,
    }

    # Pricing type
    pricing_types = traits.get("pricing", ["paid"])
    if "pricing" not in course:
        course["pricing"] = {}
    course["pricing"]["type"] = pricing_types[0] if pricing_types else "paid"

    # Regions (from traits, not channel)
    course["location"] = {
        "regions": list(traits.get("region", [])),
    }

    # Contacts
    contacts_list = []
    for contact in traits.get("contacts", []):
        contact_entry = {
            "type": contact.get("type"),
            "value": contact.get("value"),
        }
        trans = contact.get("translations", {})
        if trans:
            desc = {}
            for lang, t in trans.items():
                if t.get("description"):
                    desc[lang] = t["description"]
            if desc:
                contact_entry["description"] = desc
        contacts_list.append(contact_entry)
    if contacts_list:
        course["contacts"] = {"list": contacts_list}

    # Image
    if traits.get("photo"):
        course["image"] = {
            "id": traits["photo"],
            "alt": traits.get("photoAlt", ""),
        }

    # Channels
    if len(channels) == 1:
        # Single location mode
        ch = channels[0]
        ch_trans = ch.get("translations", {})
        fi_trans = ch_trans.get("fi", {})
        en_trans = ch_trans.get("en", {})
        address = fi_trans.get("address", {})

        course["location"].update({
            "type": ch.get("type", ["place"])[0] if ch.get("type") else "place",
            "accessibility": list(ch.get("accessibility", ["ac_unknow"])),
            "address": {
                "street": address.get("street", ""),
                "postal_code": address.get("postalCode", ""),
                "city": address.get("city", "Helsinki"),
                "state": address.get("state", "Uusimaa"),
                "country": address.get("country", "FI"),
            },
            "summary": {},
        })

        # Coordinates from map
        map_data = ch.get("map", {})
        center = map_data.get("center", {})
        if center.get("coordinates"):
            course["location"]["address"]["coordinates"] = center["coordinates"]
            course["location"]["address"]["zoom"] = map_data.get("zoom", 16)

        # Location summary
        if fi_trans.get("summary"):
            course["location"]["summary"]["fi"] = html_to_text(fi_trans["summary"])
        if en_trans.get("summary"):
            course["location"]["summary"]["en"] = html_to_text(en_trans["summary"])

        # Registration info from channel
        course["registration"] = {
            "required": ch.get("registrationRequired", False),
            "url": ch.get("registrationUrl") or "",
            "email": ch.get("registrationEmail") or "",
            "info": {},
        }
        if fi_trans.get("registration"):
            course["registration"]["info"]["fi"] = html_to_text(fi_trans["registration"])
        if en_trans.get("registration"):
            course["registration"]["info"]["en"] = html_to_text(en_trans["registration"])

        # Schedule from events
        events = ch.get("events", [])
        if events:
            event = events[0]
            recurrence = event.get("recurrence", {})
            day_times = recurrence.get("daySpecificTimes", [])

            course["schedule"] = {
                "timezone": event.get("timeZone", "Europe/Helsinki"),
                "start_date": timestamp_to_date(event.get("start", 0)),
                "end_date": timestamp_to_date(recurrence.get("end", 0)),
                "weekly": [],
            }

            for dt in day_times:
                course["schedule"]["weekly"].append({
                    "weekday": dt.get("weekday"),
                    "start_time": dt.get("startTime"),
                    "end_time": dt.get("endTime"),
                })
    else:
        # Multi-channel mode
        course["channels"] = []
        for ch in channels:
            ch_trans = ch.get("translations", {})
            fi_trans = ch_trans.get("fi", {})
            en_trans = ch_trans.get("en", {})
            address = fi_trans.get("address", {})

            channel_data = {
                "location": {
                    "type": ch.get("type", ["place"])[0] if ch.get("type") else "place",
                    "accessibility": list(ch.get("accessibility", ["ac_unknow"])),
                    "address": {
                        "street": address.get("street", ""),
                        "postal_code": address.get("postalCode", ""),
                        "city": address.get("city", "Helsinki"),
                        "state": address.get("state", "Uusimaa"),
                        "country": address.get("country", "FI"),
                    },
                    "summary": {},
                },
            }

            # Coordinates
            map_data = ch.get("map", {})
            center = map_data.get("center", {})
            if center.get("coordinates"):
                channel_data["location"]["address"]["coordinates"] = center["coordinates"]
                channel_data["location"]["address"]["zoom"] = map_data.get("zoom", 16)

            # Location summary
            if fi_trans.get("summary"):
                channel_data["location"]["summary"]["fi"] = html_to_text(fi_trans["summary"])
            if en_trans.get("summary"):
                channel_data["location"]["summary"]["en"] = html_to_text(en_trans["summary"])

            # Schedule
            events = ch.get("events", [])
            if events:
                event = events[0]
                recurrence = event.get("recurrence", {})
                day_times = recurrence.get("daySpecificTimes", [])

                channel_data["schedule"] = {
                    "timezone": event.get("timeZone", "Europe/Helsinki"),
                    "start_date": timestamp_to_date(event.get("start", 0)),
                    "end_date": timestamp_to_date(recurrence.get("end", 0)),
                    "weekly": [],
                }

                for dt in day_times:
                    channel_data["schedule"]["weekly"].append({
                        "weekday": dt.get("weekday"),
                        "start_time": dt.get("startTime"),
                        "end_time": dt.get("endTime"),
                    })

            course["channels"].append(channel_data)

        # Registration from first channel for multi-channel
        if channels:
            ch = channels[0]
            ch_trans = ch.get("translations", {}).get("fi", {})
            course["registration"] = {
                "required": ch.get("registrationRequired", False),
                "url": ch.get("registrationUrl") or "",
                "email": ch.get("registrationEmail") or "",
                "info": {},
            }
            if ch_trans.get("registration"):
                course["registration"]["info"]["fi"] = html_to_text(ch_trans["registration"])

    return course


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


def apply_template_matching(courses: list, matcher: TemplateMatcher) -> tuple[CommentedMap, list]:
    """
    Apply template matching to courses and return structure with anchors/aliases.

    Returns:
        (defaults_section, courses_list) - defaults with anchors, courses with aliases
    """
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    from ruamel.yaml.scalarstring import LiteralScalarString

    # Build defaults section with anchors
    defaults = CommentedMap()

    # Course defaults
    course_def = CommentedMap()
    course_def["type"] = "hobby"
    course_def["required_locales"] = ["fi", "en"]
    course_def["categories"] = CommentedMap({
        "themes": ["ht_hyvinvointi", "ht_urheilu"],
        "formats": ["hm_harrastukset"],
        "locales": ["fi-FI"],
    })
    course_def["demographics"] = CommentedMap({
        "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64", "ageGroup/range:65-99"],
        "gender": ["gender/gender"],
    })
    course_def.yaml_set_anchor("course_defaults", always_dump=True)
    defaults["course"] = course_def

    # Location defaults
    loc_def = CommentedMap()
    loc_def["type"] = "place"
    loc_def["regions"] = ["city/FI/Helsinki", "city/FI/Espoo", "city/FI/Vantaa"]
    loc_def["accessibility"] = ["ac_unknow"]
    loc_def["address"] = CommentedMap({
        "city": "Helsinki",
        "state": "Uusimaa",
        "country": "FI",
        "zoom": 16,
    })
    loc_def.yaml_set_anchor("location_defaults", always_dump=True)
    defaults["location"] = loc_def

    # Schedule defaults
    sched_def = CommentedMap({"timezone": "Europe/Helsinki"})
    sched_def.yaml_set_anchor("schedule_defaults", always_dump=True)
    defaults["schedule"] = sched_def

    # Pricing
    pricing_section = CommentedMap()
    pricing_paid = CommentedMap({"type": "paid"})
    pricing_paid.yaml_set_anchor("pricing_paid", always_dump=True)
    pricing_section["paid"] = pricing_paid
    pricing_free = CommentedMap({"type": "free"})
    pricing_free.yaml_set_anchor("pricing_free", always_dump=True)
    pricing_section["free"] = pricing_free
    defaults["pricing"] = pricing_section

    # Process courses
    processed_courses = CommentedSeq()

    for course in courses:
        cm = CommentedMap()

        # Always include _key and title first
        if "_key" in course:
            cm["_key"] = course["_key"]
        if "_status" in course:
            cm["_status"] = course["_status"]
        cm["title"] = course.get("title", {})

        # Check if matches course_defaults - use merge key
        if matcher.matches_course_defaults(course):
            # Add merge key reference
            set_merge_key(cm, course_def)
        else:
            # Include individual fields
            if "type" in course:
                cm["type"] = course["type"]
            if "required_locales" in course:
                cm["required_locales"] = list(course["required_locales"])
            if "categories" in course:
                cm["categories"] = dict(course["categories"])
            if "demographics" in course:
                cm["demographics"] = dict(course["demographics"])

        # Summary - check for alias
        if "summary" in course:
            anchor = matcher.find_matching_anchor("summary", course["summary"])
            if anchor:
                cm.yaml_add_eol_comment(f"matches *{anchor}", "summary")
            cm["summary"] = dict(course["summary"])

        # Description - check for alias
        if "description" in course:
            anchor = matcher.find_matching_anchor("description", course["description"])
            if anchor:
                cm.yaml_add_eol_comment(f"matches *{anchor}", "description")
            cm["description"] = dict(course["description"])

        # Location
        if "location" in course:
            loc = course["location"]
            loc_cm = CommentedMap()

            if matcher.matches_location_defaults(loc):
                set_merge_key(loc_cm, loc_def)
                # Only add non-default fields
                if "address" in loc:
                    addr = loc["address"]
                    addr_cm = CommentedMap()
                    if addr.get("street"):
                        addr_cm["street"] = addr["street"]
                    if addr.get("postal_code"):
                        addr_cm["postal_code"] = addr["postal_code"]
                    if "coordinates" in addr:
                        addr_cm["coordinates"] = list(addr["coordinates"])
                    if addr_cm:
                        loc_cm["address"] = addr_cm
                if "summary" in loc:
                    loc_cm["summary"] = dict(loc["summary"])
            else:
                # Full location
                for k, v in loc.items():
                    if isinstance(v, dict):
                        loc_cm[k] = dict(v)
                    elif isinstance(v, list):
                        loc_cm[k] = list(v)
                    else:
                        loc_cm[k] = v

            cm["location"] = loc_cm

        # Schedule
        if "schedule" in course:
            sched = course["schedule"]
            sched_cm = CommentedMap()
            # Always merge schedule defaults for timezone
            set_merge_key(sched_cm, sched_def)
            if "start_date" in sched:
                sched_cm["start_date"] = sched["start_date"]
            if "end_date" in sched:
                sched_cm["end_date"] = sched["end_date"]
            if "weekly" in sched:
                weekly_seq = CommentedSeq()
                for w in sched["weekly"]:
                    weekly_seq.append(dict(w))
                sched_cm["weekly"] = weekly_seq
            cm["schedule"] = sched_cm

        # Channels (multi-location)
        if "channels" in course:
            channels_seq = CommentedSeq()
            for ch in course["channels"]:
                ch_cm = CommentedMap()
                if "location" in ch:
                    ch_loc = ch["location"]
                    ch_loc_cm = CommentedMap()
                    if matcher.matches_location_defaults(ch_loc):
                        set_merge_key(ch_loc_cm, loc_def)
                        if "address" in ch_loc:
                            addr = ch_loc["address"]
                            addr_cm = CommentedMap()
                            if addr.get("street"):
                                addr_cm["street"] = addr["street"]
                            if addr.get("postal_code"):
                                addr_cm["postal_code"] = addr["postal_code"]
                            if "coordinates" in addr:
                                addr_cm["coordinates"] = list(addr["coordinates"])
                            if addr_cm:
                                ch_loc_cm["address"] = addr_cm
                        if "summary" in ch_loc:
                            ch_loc_cm["summary"] = dict(ch_loc["summary"])
                    else:
                        for k, v in ch_loc.items():
                            if isinstance(v, dict):
                                ch_loc_cm[k] = dict(v)
                            elif isinstance(v, list):
                                ch_loc_cm[k] = list(v)
                            else:
                                ch_loc_cm[k] = v
                    ch_cm["location"] = ch_loc_cm

                if "schedule" in ch:
                    ch_sched = ch["schedule"]
                    ch_sched_cm = CommentedMap()
                    set_merge_key(ch_sched_cm, sched_def)
                    if "start_date" in ch_sched:
                        ch_sched_cm["start_date"] = ch_sched["start_date"]
                    if "end_date" in ch_sched:
                        ch_sched_cm["end_date"] = ch_sched["end_date"]
                    if "weekly" in ch_sched:
                        weekly_seq = CommentedSeq()
                        for w in ch_sched["weekly"]:
                            weekly_seq.append(dict(w))
                        ch_sched_cm["weekly"] = weekly_seq
                    ch_cm["schedule"] = ch_sched_cm

                channels_seq.append(ch_cm)
            cm["channels"] = channels_seq

        # Pricing
        if "pricing" in course:
            pricing = course["pricing"]
            pricing_type = pricing.get("type", "paid")
            if pricing_type == "paid" and "info" not in pricing:
                cm["pricing"] = pricing_paid
            elif pricing_type == "free" and "info" not in pricing:
                cm["pricing"] = pricing_free
            else:
                pricing_cm = CommentedMap()
                if pricing_type == "paid":
                    set_merge_key(pricing_cm, pricing_paid)
                else:
                    set_merge_key(pricing_cm, pricing_free)
                if "info" in pricing:
                    pricing_cm["info"] = dict(pricing["info"])
                cm["pricing"] = pricing_cm

        # Registration
        if "registration" in course:
            cm["registration"] = dict(course["registration"])

        # Image
        if "image" in course:
            cm["image"] = dict(course["image"])

        # Contacts
        if "contacts" in course:
            cm["contacts"] = dict(course["contacts"])

        processed_courses.append(cm)

    return defaults, processed_courses


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
        help="Output in YAML format (matching courses.yaml schema)",
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
        default=COURSES_FILE,
        help="YAML file with defaults/templates for matching (default: courses.yaml)",
    )
    args = parser.parse_args()

    # Load auth and get session
    auth = load_auth_config()
    session = get_authenticated_session(auto_refresh=True)

    group_id = auth["group_id"]

    # Fetch data
    if args.id:
        print(f"Fetching activity {args.id}...", file=sys.stderr)
        activities = [fetch_activity_by_id(session, args.id)]
    else:
        print(f"Fetching activities for group {group_id}...", file=sys.stderr)
        activities = fetch_all_activities(session, group_id)

    print(f"Downloaded {len(activities)} activities.", file=sys.stderr)

    # Output
    if args.json:
        output = json.dumps(activities, indent=2, ensure_ascii=False)
    elif args.yaml:
        # Convert to YAML schema
        courses = [convert_activity_to_yaml_schema(a) for a in activities]

        # Apply template matching
        matcher = TemplateMatcher(args.templates)
        defaults, processed_courses = apply_template_matching(courses, matcher)

        # Build final structure
        result = CommentedMap()
        result["defaults"] = defaults
        result["downloaded_courses"] = processed_courses

        yaml = YAML()
        yaml.default_flow_style = False
        yaml.indent(mapping=2, sequence=4, offset=2)

        if args.output:
            with open(args.output, "w") as f:
                yaml.dump(result, f)
            print(f"Wrote {len(courses)} courses to {args.output}", file=sys.stderr)
            return
        else:
            import io
            stream = io.StringIO()
            yaml.dump(result, stream)
            output = stream.getvalue()
    else:
        # Default: list summary
        list_activities(activities)
        return

    # Write output
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Wrote output to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
