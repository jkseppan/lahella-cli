#!/usr/bin/env python3
"""
Test suite for field_mapping.py

Run with: uv run pytest test_field_mapping.py -v
"""

import pytest
from datetime import datetime

from field_mapping import (
    # Helper functions
    get_nested,
    set_nested,
    normalize_text,
    extract_html_text,
    html_texts_equal,
    # Transform functions
    date_to_timestamp,
    timestamp_to_date,
    Transforms,
    # Field specs
    FieldSpec,
    FIELD_MAPPINGS,
    LOCATION_MAPPINGS,
    SCHEDULE_MAPPINGS,
    REGISTRATION_MAPPINGS,
    # Special cases
    SpecialCases,
    # Transformer
    Transformer,
)


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================


class TestGetNested:
    """Tests for get_nested() function."""

    def test_simple_path(self):
        obj = {"a": {"b": {"c": 42}}}
        assert get_nested(obj, "a.b.c") == 42

    def test_missing_key_returns_default(self):
        obj = {"a": {"b": 1}}
        assert get_nested(obj, "a.c") is None
        assert get_nested(obj, "a.c", "default") == "default"

    def test_array_index(self):
        obj = {"items": [{"name": "first"}, {"name": "second"}]}
        assert get_nested(obj, "items[0].name") == "first"
        assert get_nested(obj, "items[1].name") == "second"

    def test_array_index_out_of_bounds(self):
        obj = {"items": [{"name": "only"}]}
        assert get_nested(obj, "items[5].name") is None
        assert get_nested(obj, "items[5].name", "default") == "default"

    def test_none_object(self):
        assert get_nested(None, "a.b") is None
        assert get_nested(None, "a.b", "default") == "default"

    def test_nested_arrays(self):
        obj = {"channels": [{"events": [{"start": 12345}]}]}
        assert get_nested(obj, "channels[0].events[0].start") == 12345

    def test_top_level_key(self):
        obj = {"name": "test"}
        assert get_nested(obj, "name") == "test"


class TestSetNested:
    """Tests for set_nested() function."""

    def test_simple_path(self):
        obj = {}
        set_nested(obj, "a.b.c", 42)
        assert obj == {"a": {"b": {"c": 42}}}

    def test_existing_structure(self):
        obj = {"a": {"existing": True}}
        set_nested(obj, "a.b.c", 42)
        assert obj == {"a": {"existing": True, "b": {"c": 42}}}

    def test_array_index(self):
        obj = {}
        set_nested(obj, "items[0].name", "first")
        assert obj == {"items": [{"name": "first"}]}

    def test_array_extend(self):
        obj = {"items": [{"name": "first"}]}
        set_nested(obj, "items[1].name", "second")
        assert obj == {"items": [{"name": "first"}, {"name": "second"}]}

    def test_nested_arrays(self):
        obj = {}
        set_nested(obj, "channels[0].events[0].start", 12345)
        assert obj == {"channels": [{"events": [{"start": 12345}]}]}

    def test_overwrite_value(self):
        obj = {"a": {"b": "old"}}
        set_nested(obj, "a.b", "new")
        assert obj == {"a": {"b": "new"}}


class TestNormalizeText:
    """Tests for normalize_text() function."""

    def test_lowercase(self):
        assert normalize_text("Hello World") == "hello world"

    def test_collapse_whitespace(self):
        assert normalize_text("hello   world") == "hello world"
        assert normalize_text("hello\n\nworld") == "hello world"
        assert normalize_text("  hello  \t  world  ") == "hello world"

    def test_empty_string(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_preserves_content(self):
        assert normalize_text("Taiji-kurssi") == "taiji-kurssi"


class TestExtractHtmlText:
    """Tests for extract_html_text() function."""

    def test_simple_paragraph(self):
        html = '<p dir="ltr">Hello world</p>'
        assert extract_html_text(html) == "hello world"

    def test_multiple_paragraphs(self):
        html = '<p dir="ltr">First paragraph</p><p dir="ltr">Second paragraph</p>'
        # Adjacent paragraphs don't get spaces between them (consistent for comparison)
        assert extract_html_text(html) == "first paragraphsecond paragraph"

    def test_strips_formatting_tags(self):
        html = '<p><strong>Bold</strong> and <em>italic</em></p>'
        assert extract_html_text(html) == "bold and italic"

    def test_strips_links(self):
        html = '<a href="https://example.com" rel="noopener">Link text</a>'
        assert extract_html_text(html) == "link text"

    def test_handles_lists(self):
        html = '<ul><li><p>Item 1</p></li><li><p>Item 2</p></li></ul>'
        # Adjacent list items don't get spaces (consistent for comparison)
        assert extract_html_text(html) == "item 1item 2"

    def test_handles_nested_tags(self):
        html = '<p dir="ltr"><strong><em>Bold italic</em></strong> text</p>'
        assert extract_html_text(html) == "bold italic text"

    def test_empty_string(self):
        assert extract_html_text("") == ""
        assert extract_html_text(None) == ""

    def test_plain_text_passthrough(self):
        """Plain text without HTML should work too."""
        assert extract_html_text("Hello world") == "hello world"

    def test_html_entities(self):
        """Should decode HTML entities."""
        html = '<p>Hello &amp; goodbye</p>'
        assert extract_html_text(html) == "hello & goodbye"

    def test_numeric_entities(self):
        """Should decode numeric character references."""
        html = '<p>&#60;less than&#62;</p>'  # < and >
        assert extract_html_text(html) == "<less than>"


class TestHtmlTextsEqual:
    """Tests for html_texts_equal() function."""

    def test_identical_html(self):
        html = '<p dir="ltr">Hello world</p>'
        assert html_texts_equal(html, html) is True

    def test_different_attributes(self):
        """Should match despite different tag attributes."""
        html1 = '<p dir="ltr">Hello world</p>'
        html2 = '<p>Hello world</p>'
        assert html_texts_equal(html1, html2) is True

    def test_different_whitespace(self):
        """Should match despite whitespace differences."""
        html1 = '<p dir="ltr">Hello world</p>'
        html2 = '<p dir="ltr">Hello   world</p>'
        assert html_texts_equal(html1, html2) is True

    def test_same_text_different_structure(self):
        """Same text split into different paragraph structures is not equal."""
        html1 = '<p>Hello</p><p>world</p>'  # helloworld
        html2 = '<p>Hello world</p>'  # hello world
        # These have different text after normalization (helloworld vs hello world)
        assert html_texts_equal(html1, html2) is False

    def test_same_text_same_structure(self):
        """Same structure and text should match."""
        html1 = '<p dir="ltr">Hello world</p>'
        html2 = '<p>Hello world</p>'
        assert html_texts_equal(html1, html2) is True

    def test_different_text_content(self):
        """Should NOT match if text content differs."""
        html1 = '<p>Hello world</p>'
        html2 = '<p>Goodbye world</p>'
        assert html_texts_equal(html1, html2) is False

    def test_mixed_plain_and_html(self):
        """Should work when one is plain text."""
        html = '<p dir="ltr">Hello world</p>'
        plain = 'Hello world'
        assert html_texts_equal(html, plain) is True

    def test_complex_formatting(self):
        """Should match complex formatted text."""
        html1 = '<p dir="ltr"><strong>Taiji</strong>-kurssi Lauttasaaressa</p>'
        html2 = '<p>Taiji-kurssi Lauttasaaressa</p>'
        assert html_texts_equal(html1, html2) is True

    def test_real_world_example(self):
        """Test with realistic course description HTML."""
        yaml_html = '<p dir="ltr">Peruskurssit on tarkoitettu uusille vasta-alkajille.</p>'
        api_html = '<p dir="ltr">Peruskurssit on tarkoitettu uusille vasta-alkajille.</p>'
        assert html_texts_equal(yaml_html, api_html) is True

    def test_real_world_with_slight_differences(self):
        """Test that minor differences are tolerated."""
        yaml_html = '<p dir="ltr">Peruskurssit on tarkoitettu uusille vasta-alkajille.</p>'
        # API might have slightly different formatting
        api_html = '<p>Peruskurssit  on tarkoitettu  uusille vasta-alkajille.</p>'
        assert html_texts_equal(yaml_html, api_html) is True


# =============================================================================
# TRANSFORM FUNCTION TESTS
# =============================================================================


class TestDateTimestamp:
    """Tests for date/timestamp conversion functions."""

    def test_date_to_timestamp(self):
        # 2025-01-15 00:00:00 in local time
        ts = date_to_timestamp("2025-01-15")
        # Verify it's a reasonable timestamp (milliseconds)
        assert ts > 1700000000000  # After 2023
        assert ts < 2000000000000  # Before 2033

    def test_date_to_timestamp_empty(self):
        assert date_to_timestamp("") == 0
        assert date_to_timestamp(None) == 0

    def test_timestamp_to_date(self):
        # Use a known timestamp
        ts = 1736899200000  # 2025-01-15 00:00:00 UTC
        date = timestamp_to_date(ts)
        assert date == "2025-01-15" or date == "2025-01-14"  # TZ dependent

    def test_timestamp_to_date_zero(self):
        assert timestamp_to_date(0) == ""
        assert timestamp_to_date(None) == ""

    def test_roundtrip(self):
        # Convert date to timestamp and back
        original = "2025-06-15"
        ts = date_to_timestamp(original)
        result = timestamp_to_date(ts)
        assert result == original


class TestTransforms:
    """Tests for Transforms.apply() method."""

    def test_date_timestamp_to_api(self):
        result = Transforms.apply("2025-01-15", "date_timestamp", "to_api")
        assert isinstance(result, int)
        assert result > 0

    def test_date_timestamp_from_api(self):
        ts = 1736899200000
        result = Transforms.apply(ts, "date_timestamp", "from_api")
        assert isinstance(result, str)
        assert result.startswith("2025-01")

    def test_none_transform(self):
        assert Transforms.apply("value", None, "to_api") == "value"
        assert Transforms.apply(42, None, "from_api") == 42

    def test_none_value(self):
        assert Transforms.apply(None, "date_timestamp", "to_api") is None


# =============================================================================
# FIELD SPEC TESTS
# =============================================================================


class TestFieldSpec:
    """Tests for FieldSpec dataclass."""

    def test_basic_spec(self):
        spec = FieldSpec("title.fi", "traits.translations.fi.name")
        assert spec.yaml_path == "title.fi"
        assert spec.api_path == "traits.translations.fi.name"
        assert spec.transform is None
        assert spec.default is None
        assert spec.required is False
        assert spec.array_wrap is False

    def test_spec_with_options(self):
        spec = FieldSpec(
            "pricing.type",
            "traits.pricing",
            transform=None,
            default="paid",
            required=True,
            array_wrap=True,
        )
        assert spec.default == "paid"
        assert spec.required is True
        assert spec.array_wrap is True

    def test_mappings_exist(self):
        assert len(FIELD_MAPPINGS) > 0
        assert len(LOCATION_MAPPINGS) > 0
        assert len(SCHEDULE_MAPPINGS) > 0
        assert len(REGISTRATION_MAPPINGS) > 0

    def test_required_title_fi(self):
        title_spec = next(
            (s for s in FIELD_MAPPINGS if s.yaml_path == "title.fi"), None
        )
        assert title_spec is not None
        assert title_spec.required is True


# =============================================================================
# SPECIAL CASES TESTS
# =============================================================================


class TestSpecialCasesDemographics:
    """Tests for SpecialCases.handle_demographics()."""

    def test_to_api_combines_arrays(self):
        course = {
            "demographics": {
                "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64"],
                "gender": ["gender/gender"],
            }
        }
        result = SpecialCases.handle_demographics(course, "to_api")
        assert result == [
            "ageGroup/range:18-29",
            "ageGroup/range:30-64",
            "gender/gender",
        ]

    def test_from_api_splits_by_prefix(self):
        activity = {
            "traits": {
                "demographic": [
                    "ageGroup/range:18-29",
                    "gender/gender",
                    "ageGroup/range:65-99",
                ]
            }
        }
        result = SpecialCases.handle_demographics(activity, "from_api")
        assert result["age_groups"] == ["ageGroup/range:18-29", "ageGroup/range:65-99"]
        assert result["gender"] == ["gender/gender"]

    def test_empty_demographics(self):
        course = {"demographics": {}}
        result = SpecialCases.handle_demographics(course, "to_api")
        assert result == []

    def test_missing_demographics(self):
        course = {}
        result = SpecialCases.handle_demographics(course, "to_api")
        assert result == []


class TestSpecialCasesWeeklySchedule:
    """Tests for SpecialCases.handle_weekly_schedule()."""

    def test_to_api_converts_keys(self):
        course = {
            "schedule": {
                "weekly": [
                    {"weekday": 2, "start_time": "18:00", "end_time": "19:30"}
                ]
            }
        }
        result = SpecialCases.handle_weekly_schedule(course, "to_api")
        assert result == [{"weekday": 2, "startTime": "18:00", "endTime": "19:30"}]

    def test_from_api_converts_keys(self):
        activity = {
            "traits": {
                "channels": [
                    {
                        "events": [
                            {
                                "recurrence": {
                                    "daySpecificTimes": [
                                        {
                                            "weekday": 5,
                                            "startTime": "17:00",
                                            "endTime": "18:30",
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = SpecialCases.handle_weekly_schedule(activity, "from_api")
        assert result == [{"weekday": 5, "start_time": "17:00", "end_time": "18:30"}]

    def test_multiple_days(self):
        course = {
            "schedule": {
                "weekly": [
                    {"weekday": 2, "start_time": "18:00", "end_time": "19:30"},
                    {"weekday": 5, "start_time": "17:00", "end_time": "18:30"},
                ]
            }
        }
        result = SpecialCases.handle_weekly_schedule(course, "to_api")
        assert len(result) == 2


class TestSpecialCasesContacts:
    """Tests for SpecialCases.handle_contacts()."""

    def test_to_api_adds_uuid_and_translations(self):
        course = {
            "contacts": {
                "list": [
                    {
                        "type": "email",
                        "value": "test@example.com",
                        "description": {"fi": "Yhteystiedot", "en": "Contact"},
                    }
                ]
            }
        }
        result = SpecialCases.handle_contacts(course, "to_api")
        assert len(result) == 1
        assert "id" in result[0]  # UUID added
        assert result[0]["type"] == "email"
        assert result[0]["value"] == "test@example.com"
        assert result[0]["translations"]["fi"]["description"] == "Yhteystiedot"
        assert result[0]["translations"]["en"]["description"] == "Contact"
        assert result[0]["translations"]["sv"]["description"] == "Detaljer"  # Default

    def test_from_api_extracts_description(self):
        activity = {
            "traits": {
                "contacts": [
                    {
                        "id": "some-uuid",
                        "type": "www",
                        "value": "https://example.com",
                        "translations": {
                            "fi": {"description": "Kotisivu"},
                            "en": {"description": "Homepage"},
                        },
                    }
                ]
            }
        }
        result = SpecialCases.handle_contacts(activity, "from_api")
        assert len(result) == 1
        assert result[0]["type"] == "www"
        assert result[0]["value"] == "https://example.com"
        assert result[0]["description"]["fi"] == "Kotisivu"
        assert result[0]["description"]["en"] == "Homepage"

    def test_empty_contacts(self):
        course = {"contacts": {"list": []}}
        result = SpecialCases.handle_contacts(course, "to_api")
        assert result == []


class TestSpecialCasesBuildChannel:
    """Tests for SpecialCases.build_channel_structure()."""

    def test_builds_complete_channel(self):
        location = {
            "type": "place",
            "accessibility": ["ac_wheelchair"],
            "address": {
                "street": "Test Street 1",
                "postal_code": "00100",
                "city": "Helsinki",
                "state": "Uusimaa",
                "country": "FI",
                "coordinates": [24.9, 60.2],
                "zoom": 16,
            },
            "summary": {"fi": "Paikka", "en": "Location"},
        }
        schedule = {
            "start_date": "2025-01-15",
            "end_date": "2025-05-15",
            "timezone": "Europe/Helsinki",
            "weekly": [{"weekday": 2, "start_time": "18:00", "end_time": "19:30"}],
        }
        registration = {
            "required": True,
            "url": "https://example.com/register",
            "email": "register@example.com",
            "info": {"fi": "Ilmoittaudu", "en": "Register"},
        }

        result = SpecialCases.build_channel_structure(location, schedule, registration)

        assert "id" in result  # UUID generated
        assert result["type"] == ["place"]
        assert result["accessibility"] == ["ac_wheelchair"]
        assert len(result["events"]) == 1
        assert result["events"][0]["timeZone"] == "Europe/Helsinki"
        assert result["events"][0]["type"] == "4"
        assert result["registrationRequired"] is True
        assert result["registrationUrl"] == "https://example.com/register"
        assert result["map"]["center"]["coordinates"] == [24.9, 60.2]


# =============================================================================
# TRANSFORMER TESTS
# =============================================================================


class TestTransformerValidation:
    """Tests for Transformer validation."""

    def test_validates_required_fields(self):
        transformer = Transformer()
        course = {}  # Missing title.fi
        with pytest.raises(ValueError) as exc_info:
            transformer.validate_required(course)
        assert "title.fi" in str(exc_info.value)

    def test_passes_with_required_fields(self):
        transformer = Transformer()
        course = {"title": {"fi": "Test Course"}}
        # Should not raise
        transformer.validate_required(course)


class TestTransformerYamlToApi:
    """Tests for Transformer.yaml_to_api()."""

    def test_basic_conversion(self):
        transformer = Transformer()
        course = {
            "title": {"fi": "Testikurssi", "en": "Test Course"},
            "type": "hobby",
            "location": {
                "type": "place",
                "address": {
                    "street": "Test Street",
                    "postal_code": "00100",
                },
            },
            "schedule": {
                "start_date": "2025-01-15",
                "end_date": "2025-05-15",
                "weekly": [{"weekday": 2, "start_time": "18:00", "end_time": "19:30"}],
            },
            "registration": {"required": True, "info": {"fi": "Info", "en": "Info"}},
        }

        result = transformer.yaml_to_api(course, group_id="123")

        assert result["group"] == "123"
        assert result["traits"]["translations"]["fi"]["name"] == "Testikurssi"
        assert result["traits"]["translations"]["en"]["name"] == "Test Course"
        assert result["traits"]["type"] == "hobby"
        assert len(result["traits"]["channels"]) == 1

    def test_summary_passed_through_unchanged(self):
        """Summary should be stored as HTML in YAML and passed through unchanged."""
        transformer = Transformer()
        course = {
            "title": {"fi": "Test"},
            "summary": {"fi": '<p dir="ltr">Kurssin kuvaus</p>'},
            "location": {"address": {"postal_code": "00100"}},
            "schedule": {
                "start_date": "2025-01-15",
                "end_date": "2025-05-15",
                "weekly": [],
            },
            "registration": {"info": {"fi": "", "en": ""}},
        }

        result = transformer.yaml_to_api(course)

        assert result["traits"]["translations"]["fi"]["summary"] == '<p dir="ltr">Kurssin kuvaus</p>'

    def test_pricing_array_wrapped(self):
        transformer = Transformer()
        course = {
            "title": {"fi": "Test"},
            "pricing": {"type": "free"},
            "location": {"address": {"postal_code": "00100"}},
            "schedule": {
                "start_date": "2025-01-15",
                "end_date": "2025-05-15",
                "weekly": [],
            },
            "registration": {"info": {"fi": "", "en": ""}},
        }

        result = transformer.yaml_to_api(course)

        assert result["traits"]["pricing"] == ["free"]

    def test_demographics_merged(self):
        transformer = Transformer()
        course = {
            "title": {"fi": "Test"},
            "demographics": {
                "age_groups": ["ageGroup/range:18-29"],
                "gender": ["gender/gender"],
            },
            "location": {"address": {"postal_code": "00100"}},
            "schedule": {
                "start_date": "2025-01-15",
                "end_date": "2025-05-15",
                "weekly": [],
            },
            "registration": {"info": {"fi": "", "en": ""}},
        }

        result = transformer.yaml_to_api(course)

        assert "ageGroup/range:18-29" in result["traits"]["demographic"]
        assert "gender/gender" in result["traits"]["demographic"]

    def test_multi_channel_mode(self):
        transformer = Transformer()
        course = {
            "title": {"fi": "Test"},
            "channels": [
                {
                    "location": {"address": {"street": "Street 1", "postal_code": "00100"}},
                    "schedule": {
                        "start_date": "2025-01-15",
                        "end_date": "2025-05-15",
                        "weekly": [{"weekday": 2, "start_time": "18:00", "end_time": "19:30"}],
                    },
                },
                {
                    "location": {"address": {"street": "Street 2", "postal_code": "00200"}},
                    "schedule": {
                        "start_date": "2025-01-16",
                        "end_date": "2025-05-16",
                        "weekly": [{"weekday": 5, "start_time": "17:00", "end_time": "18:30"}],
                    },
                },
            ],
            "registration": {"info": {"fi": "", "en": ""}},
        }

        result = transformer.yaml_to_api(course)

        assert len(result["traits"]["channels"]) == 2


class TestTransformerApiToYaml:
    """Tests for Transformer.api_to_yaml()."""

    def test_basic_conversion(self):
        transformer = Transformer()
        activity = {
            "_key": "12345",
            "status": "published",
            "traits": {
                "type": "hobby",
                "requiredLocales": ["fi", "en"],
                "translations": {
                    "fi": {
                        "name": "Testikurssi",
                        "summary": '<p dir="ltr">Kuvaus</p>',
                    },
                    "en": {
                        "name": "Test Course",
                        "summary": '<p dir="ltr">Description</p>',
                    },
                },
                "theme": ["ht_urheilu"],
                "format": ["hm_harrastukset"],
                "pricing": ["paid"],
                "channels": [
                    {
                        "type": ["place"],
                        "accessibility": ["ac_unknow"],
                        "translations": {
                            "fi": {
                                "address": {
                                    "street": "Test Street",
                                    "postalCode": "00100",
                                    "city": "Helsinki",
                                    "state": "Uusimaa",
                                    "country": "FI",
                                }
                            }
                        },
                        "events": [
                            {
                                "start": 1736899200000,
                                "timeZone": "Europe/Helsinki",
                                "recurrence": {
                                    "end": 1747267200000,
                                    "daySpecificTimes": [
                                        {"weekday": 2, "startTime": "18:00", "endTime": "19:30"}
                                    ],
                                },
                            }
                        ],
                    }
                ],
            },
        }

        result = transformer.api_to_yaml(activity)

        assert result["_key"] == "12345"
        assert result["_status"] == "published"
        assert result["title"]["fi"] == "Testikurssi"
        assert result["summary"]["fi"] == '<p dir="ltr">Kuvaus</p>'  # HTML preserved
        assert result["pricing"]["type"] == "paid"  # Array unwrapped

    def test_html_preserved_in_yaml(self):
        """HTML content should be preserved when converting from API to YAML."""
        transformer = Transformer()
        activity = {
            "traits": {
                "translations": {
                    "fi": {
                        "name": "Test",
                        "description": '<p dir="ltr"><strong>Bold</strong> text</p>',
                    }
                },
                "channels": [],
            }
        }

        result = transformer.api_to_yaml(activity)

        assert result["description"]["fi"] == '<p dir="ltr"><strong>Bold</strong> text</p>'

    def test_multi_channel_detection(self):
        transformer = Transformer()
        activity = {
            "traits": {
                "translations": {"fi": {"name": "Test"}},
                "channels": [
                    {
                        "type": ["place"],
                        "accessibility": ["ac_unknow"],
                        "translations": {
                            "fi": {"address": {"postalCode": "00100", "city": "Helsinki", "state": "Uusimaa", "country": "FI"}}
                        },
                        "events": [{"start": 1736899200000, "recurrence": {"end": 1747267200000, "daySpecificTimes": []}}],
                    },
                    {
                        "type": ["place"],
                        "accessibility": ["ac_unknow"],
                        "translations": {
                            "fi": {"address": {"postalCode": "00200", "city": "Helsinki", "state": "Uusimaa", "country": "FI"}}
                        },
                        "events": [{"start": 1736899200000, "recurrence": {"end": 1747267200000, "daySpecificTimes": []}}],
                    },
                ],
            }
        }

        result = transformer.api_to_yaml(activity)

        assert "channels" in result
        assert len(result["channels"]) == 2


class TestTransformerRoundTrip:
    """Tests for round-trip conversion (YAML -> API -> YAML)."""

    def test_simple_roundtrip(self):
        """Test YAML -> API -> YAML roundtrip preserves data."""
        transformer = Transformer()
        original = {
            "title": {"fi": "Testikurssi", "en": "Test Course"},
            "type": "hobby",
            "required_locales": ["fi", "en"],
            "summary": {"fi": '<p dir="ltr">Kuvaus</p>', "en": '<p dir="ltr">Description</p>'},
            "categories": {
                "themes": ["ht_urheilu"],
                "formats": ["hm_harrastukset"],
                "locales": ["fi-FI"],
            },
            "demographics": {
                "age_groups": ["ageGroup/range:18-29"],
                "gender": ["gender/gender"],
            },
            "pricing": {"type": "paid"},
            "location": {
                "type": "place",
                "regions": ["city/FI/Helsinki"],
                "accessibility": ["ac_unknow"],
                "address": {
                    "street": "Test Street 1",
                    "postal_code": "00100",
                    "city": "Helsinki",
                    "state": "Uusimaa",
                    "country": "FI",
                    "coordinates": [24.9, 60.2],
                    "zoom": 16,
                },
                "summary": {"fi": '<p dir="ltr">Paikka</p>'},
            },
            "schedule": {
                "timezone": "Europe/Helsinki",
                "start_date": "2025-01-15",
                "end_date": "2025-05-15",
                "weekly": [{"weekday": 2, "start_time": "18:00", "end_time": "19:30"}],
            },
            "registration": {
                "required": True,
                "url": "https://example.com",
                "email": "test@example.com",
                "info": {"fi": '<p dir="ltr">Ilmoittaudu</p>', "en": '<p dir="ltr">Register</p>'},
            },
        }

        # Convert to API format
        api_format = transformer.yaml_to_api(original)

        # Convert back to YAML format
        result = transformer.api_to_yaml(api_format)

        # Check key fields are preserved
        assert result["title"]["fi"] == original["title"]["fi"]
        assert result["type"] == original["type"]
        assert result["pricing"]["type"] == original["pricing"]["type"]
        assert result["schedule"]["start_date"] == original["schedule"]["start_date"]
        assert result["schedule"]["end_date"] == original["schedule"]["end_date"]


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests with realistic data."""

    @pytest.fixture
    def sample_course(self):
        """A realistic course definition with HTML content (no text conversion)."""
        return {
            "title": {
                "fi": "Taiji-kurssi Lauttasaaressa",
                "en": "Tai chi course in Lauttasaari",
            },
            "type": "hobby",
            "required_locales": ["fi", "en"],
            "summary": {
                "fi": '<p dir="ltr">Taiji-peruskurssi: kehon ja mielen rentoutusta</p>',
                "en": '<p dir="ltr">An elementary course in tai chi</p>',
            },
            "description": {
                "fi": '<p dir="ltr">Peruskurssit on tarkoitettu uusille vasta-alkajille.</p><p dir="ltr">Liikkeet tehdään rauhallisesti.</p>',
                "en": '<p dir="ltr">Elementary courses for beginners.</p><p dir="ltr">Movements are performed slowly.</p>',
            },
            "categories": {
                "themes": ["ht_hyvinvointi", "ht_urheilu"],
                "formats": ["hm_harrastukset"],
                "locales": ["fi-FI"],
            },
            "demographics": {
                "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64", "ageGroup/range:65-99"],
                "gender": ["gender/gender"],
            },
            "location": {
                "type": "place",
                "regions": ["city/FI/Helsinki", "city/FI/Espoo", "city/FI/Vantaa"],
                "accessibility": ["ac_unknow"],
                "address": {
                    "street": "Myllykalliontie 3",
                    "postal_code": "00200",
                    "city": "Helsinki",
                    "state": "Uusimaa",
                    "country": "FI",
                    "coordinates": [24.87076, 60.16061],
                    "zoom": 16,
                },
                "summary": {
                    "fi": '<p dir="ltr">Kurssi järjestetään Lauttasaaren ala-asteella</p>',
                    "en": '<p dir="ltr">The course meets at Lauttasaari primary school</p>',
                },
            },
            "schedule": {
                "timezone": "Europe/Helsinki",
                "start_date": "2026-01-11",
                "end_date": "2026-05-24",
                "weekly": [{"weekday": 7, "start_time": "11:00", "end_time": "12:00"}],
            },
            "pricing": {
                "type": "paid",
                "info": {
                    "fi": '<p dir="ltr">195 euroa</p>',
                    "en": '<p dir="ltr">€195</p>',
                },
            },
            "registration": {
                "required": True,
                "url": "https://taichichuan.fi/kurssit",
                "email": "teacher@example.com",
                "info": {
                    "fi": '<p dir="ltr">Ilmoittautumiset opettajalle</p>',
                    "en": '<p dir="ltr">Contact the teacher to enrol</p>',
                },
            },
            "contacts": {
                "list": [
                    {
                        "type": "www",
                        "value": "https://taichichuan.fi/kurssit",
                        "description": {"fi": "Lisätietoja", "en": "Details"},
                    },
                    {
                        "type": "email",
                        "value": "teacher@example.com",
                        "description": {"fi": "Lisätietoja", "en": "Details"},
                    },
                ]
            },
        }

    def test_full_course_to_api(self, sample_course):
        """Test converting a full course to API format."""
        transformer = Transformer()
        result = transformer.yaml_to_api(sample_course, group_id="test-group")

        # Check structure
        assert result["group"] == "test-group"
        assert "traits" in result

        traits = result["traits"]

        # Check translations (HTML passed through unchanged)
        assert traits["translations"]["fi"]["name"] == "Taiji-kurssi Lauttasaaressa"
        assert traits["translations"]["fi"]["summary"] == '<p dir="ltr">Taiji-peruskurssi: kehon ja mielen rentoutusta</p>'
        assert traits["translations"]["fi"]["description"] == '<p dir="ltr">Peruskurssit on tarkoitettu uusille vasta-alkajille.</p><p dir="ltr">Liikkeet tehdään rauhallisesti.</p>'

        # Check categories
        assert traits["theme"] == ["ht_hyvinvointi", "ht_urheilu"]
        assert traits["format"] == ["hm_harrastukset"]
        assert traits["locale"] == ["fi-FI"]

        # Check demographics
        assert len(traits["demographic"]) == 4  # 3 age groups + 1 gender

        # Check region
        assert "city/FI/Helsinki" in traits["region"]

        # Check pricing (HTML passed through unchanged)
        assert traits["pricing"] == ["paid"]
        assert traits["translations"]["fi"]["pricing"] == '<p dir="ltr">195 euroa</p>'

        # Check channels
        assert len(traits["channels"]) == 1
        channel = traits["channels"][0]
        assert channel["type"] == ["place"]
        assert channel["registrationRequired"] is True
        assert channel["registrationUrl"] == "https://taichichuan.fi/kurssit"

        # Check events
        assert len(channel["events"]) == 1
        event = channel["events"][0]
        assert event["timeZone"] == "Europe/Helsinki"
        assert event["type"] == "4"
        assert len(event["recurrence"]["daySpecificTimes"]) == 1

        # Check contacts
        assert len(traits["contacts"]) == 2
