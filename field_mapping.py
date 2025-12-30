#!/usr/bin/env python3
"""
Declarative field mapping between YAML course format and Lähellä.fi API format.

This module provides bidirectional transformation between the user-friendly YAML
schema (courses.yaml) and the API JSON format used by hallinta.lahella.fi.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict, cast


# =============================================================================
# TYPE DEFINITIONS
# =============================================================================

Direction = Literal["to_api", "from_api"]


class DemographicsDict(TypedDict):
    """Demographics data from API (from_api direction)."""

    age_groups: list[str]
    gender: list[str]


class AddressDict(TypedDict, total=False):
    """Address data for a channel location."""

    street: str
    postal_code: str
    city: str
    state: str
    country: str
    coordinates: list[float]
    zoom: int


class LocationDict(TypedDict, total=False):
    """Location data for a channel."""

    type: str
    accessibility: list[str]
    address: AddressDict
    summary: dict[str, str]


class ScheduleDict(TypedDict, total=False):
    """Schedule data for a channel."""

    timezone: str
    start_date: str
    end_date: str
    weekly: list[dict[str, Any]]


class ChannelDataDict(TypedDict):
    """Channel data structure used when parsing multi-channel activities."""

    location: LocationDict
    schedule: ScheduleDict


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_nested(obj: dict, path: str, default: Any = None) -> Any:
    """
    Get a value from a nested dict using dot notation.

    Supports array indexing: "channels[0].type"
    """
    if obj is None:
        return default

    parts = _parse_path(path)
    current = obj

    for part in parts:
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return default
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]

    return current if current is not None else default


def set_nested(obj: dict, path: str, value: Any) -> None:
    """
    Set a value in a nested dict using dot notation, creating intermediate
    dicts/lists as needed.

    Supports array indexing: "channels[0].type"
    """
    parts = _parse_path(path)
    current: dict | list = obj  # Can be dict or list during traversal

    for i, part in enumerate(parts[:-1]):
        next_part = parts[i + 1]

        if isinstance(part, int):
            assert isinstance(current, list)
            while len(current) <= part:
                current.append({} if not isinstance(next_part, int) else [])
            current = current[part]
        else:
            assert isinstance(current, dict)
            if part not in current:
                current[part] = [] if isinstance(next_part, int) else {}
            current = current[part]

    final_part = parts[-1]
    if isinstance(final_part, int):
        assert isinstance(current, list)
        while len(current) <= final_part:
            current.append(None)
        current[final_part] = value
    else:
        assert isinstance(current, dict)
        current[final_part] = value


def _parse_path(path: str) -> list[str | int]:
    """Parse a dot-notation path with array indices into parts."""
    parts = []
    for segment in path.split("."):
        match = re.match(r"(\w+)\[(\d+)\]", segment)
        if match:
            parts.append(match.group(1))
            parts.append(int(match.group(2)))
        else:
            parts.append(segment)
    return parts


def normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, collapse whitespace)."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def extract_html_text(html: str) -> str:
    """
    Extract plain text content from HTML string.

    Uses html.parser to properly handle HTML entities and nested tags.
    Returns normalized text (lowercase, collapsed whitespace).
    """
    if not html:
        return ""

    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text_parts = []

        def handle_data(self, data):
            self.text_parts.append(data)

        def handle_entityref(self, name):
            from html.entities import name2codepoint
            if name in name2codepoint:
                self.text_parts.append(chr(name2codepoint[name]))

        def handle_charref(self, name):
            if name.startswith('x'):
                self.text_parts.append(chr(int(name[1:], 16)))
            else:
                self.text_parts.append(chr(int(name)))

    extractor = TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        # Fallback: just strip tags with regex
        return normalize_text(re.sub(r'<[^>]+>', '', html))

    return normalize_text("".join(extractor.text_parts))


def html_texts_equal(html1: str, html2: str) -> bool:
    """
    Compare two HTML strings semantically (by their text content).

    Ignores HTML structure differences like:
    - Different attribute order: <p dir="ltr"> vs <p>
    - Whitespace differences between tags
    - Entity encoding differences: &amp; vs &

    Returns True if the text content is semantically equivalent.
    """
    return extract_html_text(html1) == extract_html_text(html2)


# =============================================================================
# TRANSFORMS
# =============================================================================


def date_to_timestamp(date_str: str) -> int:
    """Convert YYYY-MM-DD to milliseconds timestamp."""
    if not date_str:
        return 0
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def timestamp_to_date(ts: int | None) -> str:
    """Convert milliseconds timestamp to YYYY-MM-DD."""
    if ts is None or ts == 0:
        return ""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")


class Transforms:
    """Registry of bidirectional transformations."""

    @staticmethod
    def apply(value: Any, transform_name: str | None, direction: str) -> Any:
        """
        Apply a named transform.

        Args:
            value: The value to transform
            transform_name: Name of transform ("date_timestamp", etc.)
            direction: "to_api" or "from_api"
        """
        if transform_name is None or value is None:
            return value

        if transform_name == "date_timestamp":
            if direction == "to_api":
                return date_to_timestamp(value)
            else:
                return timestamp_to_date(value)

        return value


# =============================================================================
# FIELD SPEC
# =============================================================================


@dataclass
class FieldSpec:
    """
    Specification for a single field mapping between YAML and API formats.

    Attributes:
        yaml_path: Dot-notation path in YAML (e.g., "title.fi", "schedule.start_date")
        api_path: Dot-notation path in API JSON (e.g., "traits.translations.fi.name")
        transform: Optional transform name (e.g., "date_timestamp")
        default: Default value if field is missing
        required: Whether field is required for validation
        array_wrap: If True, wrap scalar value in array for API (e.g., pricing -> ["paid"])
    """

    yaml_path: str
    api_path: str
    transform: str | None = None
    default: Any = None
    required: bool = False
    array_wrap: bool = False


# =============================================================================
# FIELD MAPPINGS
# =============================================================================

# Note: These mappings handle "simple" fields. Special cases like channels,
# demographics, and weekly schedules are handled separately in SpecialCases.

FIELD_MAPPINGS = [
    # --- Title & Translations ---
    # Note: Text fields (summary, description, pricing.info) are stored as HTML
    # and passed through without conversion. Use HTML in YAML files.
    FieldSpec("title.fi", "traits.translations.fi.name", required=True),
    FieldSpec("title.en", "traits.translations.en.name"),
    FieldSpec("summary.fi", "traits.translations.fi.summary"),
    FieldSpec("summary.en", "traits.translations.en.summary"),
    FieldSpec("description.fi", "traits.translations.fi.description"),
    FieldSpec("description.en", "traits.translations.en.description"),
    FieldSpec("pricing.info.fi", "traits.translations.fi.pricing"),
    FieldSpec("pricing.info.en", "traits.translations.en.pricing"),
    # --- Course Metadata ---
    FieldSpec("type", "traits.type", default="hobby"),
    FieldSpec("required_locales", "traits.requiredLocales", default=["fi", "en"]),
    FieldSpec("categories.themes", "traits.theme", default=[]),
    FieldSpec("categories.formats", "traits.format", default=[]),
    FieldSpec("categories.locales", "traits.locale", default=[]),
    # --- Pricing (type only, info handled above) ---
    FieldSpec("pricing.type", "traits.pricing", array_wrap=True, default="paid"),
    # --- Image ---
    # Note: image.path is handled specially (upload), image.id comes from download
    FieldSpec("image.alt", "traits.photoAlt"),
    FieldSpec("image.id", "traits.photo"),
    # --- Server metadata (download only) ---
    FieldSpec("_key", "_key"),
    FieldSpec("_status", "status"),
]

# Mappings for location fields (single-channel mode)
# These apply to traits.channels[0] when there's only one location
LOCATION_MAPPINGS = [
    FieldSpec(
        "location.type", "traits.channels[0].type", array_wrap=True, default="place"
    ),
    FieldSpec(
        "location.accessibility",
        "traits.channels[0].accessibility",
        default=["ac_unknow"],
    ),
    FieldSpec(
        "location.address.street", "traits.channels[0].translations.fi.address.street"
    ),
    FieldSpec(
        "location.address.postal_code",
        "traits.channels[0].translations.fi.address.postalCode",
    ),
    FieldSpec(
        "location.address.city",
        "traits.channels[0].translations.fi.address.city",
        default="Helsinki",
    ),
    FieldSpec(
        "location.address.state",
        "traits.channels[0].translations.fi.address.state",
        default="Uusimaa",
    ),
    FieldSpec(
        "location.address.country",
        "traits.channels[0].translations.fi.address.country",
        default="FI",
    ),
    FieldSpec(
        "location.address.coordinates", "traits.channels[0].map.center.coordinates"
    ),
    FieldSpec("location.address.zoom", "traits.channels[0].map.zoom", default=16),
    FieldSpec(
        "location.summary.fi",
        "traits.channels[0].translations.fi.summary",
    ),
    FieldSpec(
        "location.summary.en",
        "traits.channels[0].translations.en.summary",
    ),
    # Regions go at activity level, not channel level
    FieldSpec("location.regions", "traits.region", default=["city/FI/Helsinki"]),
]

# Mappings for schedule (in channel events)
SCHEDULE_MAPPINGS = [
    FieldSpec(
        "schedule.start_date",
        "traits.channels[0].events[0].start",
        "date_timestamp",
    ),
    FieldSpec(
        "schedule.end_date",
        "traits.channels[0].events[0].recurrence.end",
        "date_timestamp",
    ),
    FieldSpec(
        "schedule.timezone",
        "traits.channels[0].events[0].timeZone",
        default="Europe/Helsinki",
    ),
]

# Mappings for registration (in channel)
REGISTRATION_MAPPINGS = [
    FieldSpec(
        "registration.required", "traits.channels[0].registrationRequired", default=True
    ),
    FieldSpec("registration.url", "traits.channels[0].registrationUrl", default=""),
    FieldSpec("registration.email", "traits.channels[0].registrationEmail", default=""),
    FieldSpec(
        "registration.info.fi",
        "traits.channels[0].translations.fi.registration",
    ),
    FieldSpec(
        "registration.info.en",
        "traits.channels[0].translations.en.registration",
    ),
]


# =============================================================================
# SPECIAL CASES
# =============================================================================


class SpecialCases:
    """Handlers for complex transformations that can't be expressed as simple mappings."""

    @staticmethod
    def handle_demographics(data: dict, direction: Direction) -> DemographicsDict | list[str]:
        """
        Merge/split age_groups and gender into single demographic array.

        YAML format:
            demographics:
                age_groups: [ageGroup/range:18-29, ...]
                gender: [gender/gender]

        API format:
            traits.demographic: [ageGroup/range:18-29, ..., gender/gender]

        Returns:
            list[str] for to_api direction, DemographicsDict for from_api direction.
        """
        if direction == "to_api":
            demographics = data.get("demographics", {})
            age_groups = list(demographics.get("age_groups", []))
            gender = list(demographics.get("gender", []))
            return age_groups + gender
        else:
            # from_api: split by prefix
            demographic = get_nested(data, "traits.demographic", [])
            return DemographicsDict(
                age_groups=[d for d in demographic if d.startswith("ageGroup/")],
                gender=[d for d in demographic if d.startswith("gender/")],
            )

    @staticmethod
    def handle_weekly_schedule(data: dict, direction: Direction) -> list[dict]:
        """
        Transform weekly schedule between formats.

        YAML format:
            schedule:
                weekly:
                    - weekday: 2
                      start_time: "18:00"
                      end_time: "19:30"

        API format:
            events[0].recurrence.daySpecificTimes:
                - weekday: 2
                  startTime: "18:00"
                  endTime: "19:30"
        """
        if direction == "to_api":
            weekly = get_nested(data, "schedule.weekly", [])
            return [
                {
                    "weekday": w["weekday"],
                    "startTime": w["start_time"],
                    "endTime": w["end_time"],
                }
                for w in weekly
            ]
        else:
            # from_api
            day_times = get_nested(
                data, "traits.channels[0].events[0].recurrence.daySpecificTimes", []
            )
            return [
                {
                    "weekday": dt.get("weekday"),
                    "start_time": dt.get("startTime"),
                    "end_time": dt.get("endTime"),
                }
                for dt in day_times
            ]

    @staticmethod
    def handle_contacts(data: dict, direction: Direction) -> list[dict]:
        """
        Transform contacts, adding UUIDs on create.

        YAML format:
            contacts:
                list:
                    - type: email
                      value: info@example.com
                      description: {fi: "Lisätietoja", en: "Details"}

        API format:
            traits.contacts:
                - id: "uuid"
                  type: email
                  value: info@example.com
                  translations:
                      fi: {description: "Lisätietoja"}
                      en: {description: "Details"}
        """
        if direction == "to_api":
            contacts = get_nested(data, "contacts.list", [])
            result = []
            for contact in contacts:
                desc = contact.get("description", {})
                result.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": contact["type"],
                        "value": contact["value"],
                        "translations": {
                            "fi": {"description": desc.get("fi", "Lisätietoja")},
                            "en": {"description": desc.get("en", "Details")},
                            "sv": {"description": "Detaljer"},
                        },
                    }
                )
            return result
        else:
            # from_api
            contacts = get_nested(data, "traits.contacts", [])
            result = []
            for contact in contacts:
                trans = contact.get("translations", {})
                desc = {}
                for lang, t in trans.items():
                    if t.get("description"):
                        desc[lang] = t["description"]
                entry = {
                    "type": contact.get("type"),
                    "value": contact.get("value"),
                }
                if desc:
                    entry["description"] = desc
                result.append(entry)
            return result

    @staticmethod
    def build_channel_structure(
        location: dict, schedule: dict, registration: dict
    ) -> dict:
        """
        Build a complete channel structure for the API.

        This is used when creating activities - combines location, schedule,
        and registration into the channel format expected by the API.
        """
        address = location.get("address", {})

        address_fi = {
            "street": address.get("street", ""),
            "postalCode": address.get("postal_code", ""),
            "city": address.get("city", "Helsinki"),
            "state": address.get("state", "Uusimaa"),
            "country": address.get("country", "FI"),
        }
        address_en = {
            "postalCode": address.get("postal_code", ""),
            "city": address.get("city", "Helsinki"),
            "state": address.get("state", "Uusimaa"),
            "country": address.get("country", "FI"),
        }
        address_sv = {
            "postalCode": address.get("postal_code", ""),
            "city": address.get("city", "Helsinki"),
            "state": address.get("state", "Uusimaa"),
            "country": address.get("country", "FI"),
        }

        day_specific_times = [
            {
                "weekday": weekly["weekday"],
                "startTime": weekly["start_time"],
                "endTime": weekly["end_time"],
            }
            for weekly in schedule.get("weekly", [])
        ]

        recurrence = {
            "period": "P1W",
            "exclude": [],
            "end": date_to_timestamp(schedule.get("end_date", "")),
            "daySpecificTimes": day_specific_times,
        }

        reg_info = registration.get("info", {})

        return {
            "id": str(uuid.uuid4()),
            "type": [location.get("type", "place")],
            "events": [
                {
                    "start": date_to_timestamp(schedule.get("start_date", "")),
                    "timeZone": schedule.get("timezone", "Europe/Helsinki"),
                    "type": "4",  # Weekly recurring
                    "recurrence": recurrence,
                }
            ],
            "translations": {
                "fi": {
                    "summary": location.get("summary", {}).get("fi", ""),
                    "address": address_fi,
                    "registration": reg_info.get("fi", ""),
                },
                "en": {
                    "summary": location.get("summary", {}).get("en", ""),
                    "address": address_en,
                    "registration": reg_info.get("en", ""),
                },
                "sv": {
                    "address": address_sv,
                },
            },
            "map": {
                "center": {
                    "type": "Point",
                    "coordinates": list(
                        address.get("coordinates", [24.9384, 60.1699])
                    ),
                },
                "zoom": address.get("zoom", 16),
            },
            "accessibility": list(location.get("accessibility", ["ac_unknow"])),
            "registrationRequired": registration.get("required", True),
            "registrationUrl": registration.get("url", ""),
            "registrationEmail": registration.get("email", ""),
        }


# =============================================================================
# TRANSFORMER
# =============================================================================


class Transformer:
    """
    Bidirectional transformer between YAML course format and API format.

    Usage:
        transformer = Transformer()
        api_payload = transformer.yaml_to_api(course_dict)
        yaml_course = transformer.api_to_yaml(api_response)
    """

    def __init__(
        self,
        mappings: list[FieldSpec] | None = None,
        include_location: bool = True,
        include_schedule: bool = True,
        include_registration: bool = True,
    ):
        """
        Initialize transformer with field mappings.

        Args:
            mappings: Custom field mappings (defaults to FIELD_MAPPINGS)
            include_location: Include single-channel location mappings
            include_schedule: Include schedule mappings
            include_registration: Include registration mappings
        """
        self.mappings = list(mappings or FIELD_MAPPINGS)
        if include_location:
            self.mappings.extend(LOCATION_MAPPINGS)
        if include_schedule:
            self.mappings.extend(SCHEDULE_MAPPINGS)
        if include_registration:
            self.mappings.extend(REGISTRATION_MAPPINGS)

    def validate_required(self, course: dict) -> None:
        """
        Validate that all required fields are present.

        Raises:
            ValueError: If required fields are missing
        """
        missing = []
        for spec in self.mappings:
            if spec.required:
                value = get_nested(course, spec.yaml_path)
                if value is None or value == "":
                    missing.append(spec.yaml_path)
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

    def yaml_to_api(self, course: dict, group_id: str | None = None) -> dict:
        """
        Convert YAML course to API payload.

        Args:
            course: Course dict from YAML
            group_id: Optional group ID to include in payload

        Returns:
            API payload dict ready for POST/PUT
        """
        self.validate_required(course)

        result: dict = {"traits": {}}
        if group_id:
            result["group"] = group_id

        for spec in self.mappings:
            value = get_nested(course, spec.yaml_path, spec.default)
            if value is None:
                continue

            value = Transforms.apply(value, spec.transform, "to_api")

            if spec.array_wrap and not isinstance(value, list):
                value = [value]

            set_nested(result, spec.api_path, value)

        demographics = SpecialCases.handle_demographics(course, "to_api")
        if demographics:
            set_nested(result, "traits.demographic", demographics)

        contacts = SpecialCases.handle_contacts(course, "to_api")
        if contacts:
            set_nested(result, "traits.contacts", contacts)

        if "channels" in course:
            channels = []
            registration = course.get("registration", {})
            for ch in course["channels"]:
                ch_loc = ch.get("location", {})
                ch_sched = ch.get("schedule", {})
                channels.append(
                    SpecialCases.build_channel_structure(ch_loc, ch_sched, registration)
                )
            set_nested(result, "traits.channels", channels)
        else:
            location = course.get("location", {})
            schedule = course.get("schedule", {})
            registration = course.get("registration", {})
            channel = SpecialCases.build_channel_structure(
                location, schedule, registration
            )
            set_nested(result, "traits.channels", [channel])

        return result

    def api_to_yaml(self, activity: dict) -> dict:
        """
        Convert API activity response to YAML format.

        Args:
            activity: Activity dict from API response

        Returns:
            Course dict in YAML format
        """
        result: dict = {}

        for spec in self.mappings:
            value = get_nested(activity, spec.api_path)
            if value is None:
                continue

            if spec.array_wrap and isinstance(value, list) and len(value) == 1:
                value = value[0]

            value = Transforms.apply(value, spec.transform, "from_api")

            set_nested(result, spec.yaml_path, value)

        # cast() because we know direction is from_api -> returns DemographicsDict
        demographics = cast(
            DemographicsDict, SpecialCases.handle_demographics(activity, "from_api")
        )
        if demographics.get("age_groups") or demographics.get("gender"):
            set_nested(result, "demographics", demographics)

        contacts = SpecialCases.handle_contacts(activity, "from_api")
        if contacts:
            set_nested(result, "contacts.list", contacts)

        weekly = SpecialCases.handle_weekly_schedule(activity, "from_api")
        if weekly:
            set_nested(result, "schedule.weekly", weekly)

        channels = get_nested(activity, "traits.channels", [])
        if len(channels) > 1:
            result_channels: list[ChannelDataDict] = []
            for ch in channels:
                ch_trans = ch.get("translations", {}).get("fi", {})
                ch_addr = ch_trans.get("address", {})

                address: AddressDict = {
                    "street": ch_addr.get("street", ""),
                    "postal_code": ch_addr.get("postalCode", ""),
                    "city": ch_addr.get("city", "Helsinki"),
                    "state": ch_addr.get("state", "Uusimaa"),
                    "country": ch_addr.get("country", "FI"),
                }

                map_data = ch.get("map", {})
                center = map_data.get("center", {})
                if center.get("coordinates"):
                    address["coordinates"] = center["coordinates"]
                    address["zoom"] = map_data.get("zoom", 16)

                summary: dict[str, str] = {}
                if ch_trans.get("summary"):
                    summary["fi"] = ch_trans["summary"]
                en_trans = ch.get("translations", {}).get("en", {})
                if en_trans.get("summary"):
                    summary["en"] = en_trans["summary"]

                location: LocationDict = {
                    "type": ch.get("type", ["place"])[0] if ch.get("type") else "place",
                    "accessibility": list(ch.get("accessibility", ["ac_unknow"])),
                    "address": address,
                    "summary": summary,
                }

                ch_data: ChannelDataDict = {
                    "location": location,
                    "schedule": {},
                }

                events = ch.get("events", [])
                if events:
                    event = events[0]
                    recurrence = event.get("recurrence", {})
                    day_times = recurrence.get("daySpecificTimes", [])

                    ch_data["schedule"] = {
                        "timezone": event.get("timeZone", "Europe/Helsinki"),
                        "start_date": timestamp_to_date(event.get("start", 0)),
                        "end_date": timestamp_to_date(recurrence.get("end", 0)),
                        "weekly": [
                            {
                                "weekday": dt.get("weekday"),
                                "start_time": dt.get("startTime"),
                                "end_time": dt.get("endTime"),
                            }
                            for dt in day_times
                        ],
                    }

                result_channels.append(ch_data)

            result["channels"] = result_channels

        return result
