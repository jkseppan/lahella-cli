#!/usr/bin/env python3
"""
Tests for download_activities.py and create_course.py with mocked API.

Run with: uv run pytest test_api.py -v
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest
from pytest_httpx import HTTPXMock
from ruamel.yaml import YAML

# Import modules under test
from download_activities import (
    fetch_activities,
    fetch_all_activities,
    fetch_activity_by_id,
    convert_activity_to_yaml_schema,
    get_activity_status,
    list_activities,
    TemplateMatcher,
    apply_template_matching,
)
from create_course import (
    load_courses,
    get_course_by_title,
    list_courses,
    build_activity_payload,
    create_activity,
    upload_image_for_course,
    BASE_URL,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_api_activity():
    """A realistic API activity response."""
    return {
        "_key": "12345",
        "status": "published",
        "traits": {
            "type": "hobby",
            "requiredLocales": ["fi", "en"],
            "translations": {
                "fi": {
                    "name": "Taiji-kurssi",
                    "summary": '<p dir="ltr">Peruskurssi</p>',
                    "description": '<p dir="ltr">Kuvaus kurssista</p>',
                    "pricing": '<p dir="ltr">100 euroa</p>',
                    "registration": '<p dir="ltr">Ilmoittaudu</p>',
                },
                "en": {
                    "name": "Tai chi course",
                    "summary": '<p dir="ltr">Basic course</p>',
                    "description": '<p dir="ltr">Course description</p>',
                },
            },
            "theme": ["ht_hyvinvointi", "ht_urheilu"],
            "format": ["hm_harrastukset"],
            "locale": ["fi-FI"],
            "demographic": ["ageGroup/range:18-29", "ageGroup/range:30-64", "gender/gender"],
            "region": ["city/FI/Helsinki"],
            "pricing": ["paid"],
            "photo": "photo123",
            "photoAlt": "Taiji image",
            "contacts": [
                {
                    "id": "contact-uuid-1",
                    "type": "www",
                    "value": "https://example.com",
                    "translations": {
                        "fi": {"description": "Lisätietoja"},
                        "en": {"description": "More info"},
                    },
                }
            ],
            "channels": [
                {
                    "id": "channel-uuid-1",
                    "type": ["place"],
                    "accessibility": ["ac_unknow"],
                    "map": {
                        "center": {"type": "Point", "coordinates": [24.9, 60.2]},
                        "zoom": 16,
                    },
                    "translations": {
                        "fi": {
                            "address": {
                                "street": "Testikatu 1",
                                "postalCode": "00100",
                                "city": "Helsinki",
                                "state": "Uusimaa",
                                "country": "FI",
                            },
                            "summary": '<p dir="ltr">Paikka</p>',
                            "registration": '<p dir="ltr">Ilmoittaudu</p>',
                        },
                    },
                    "events": [
                        {
                            "start": 1736899200000,  # 2025-01-15
                            "timeZone": "Europe/Helsinki",
                            "type": "4",
                            "recurrence": {
                                "period": "P1W",
                                "end": 1747267200000,  # 2025-05-15
                                "daySpecificTimes": [
                                    {"weekday": 2, "startTime": "18:00", "endTime": "19:30"}
                                ],
                                "exclude": [],
                            },
                        }
                    ],
                    "registrationRequired": True,
                    "registrationUrl": "https://example.com/register",
                    "registrationEmail": "test@example.com",
                }
            ],
        },
    }


@pytest.fixture
def sample_yaml_course():
    """A realistic YAML course definition."""
    return {
        "title": {"fi": "Taiji-kurssi", "en": "Tai chi course"},
        "type": "hobby",
        "required_locales": ["fi", "en"],
        "summary": {
            "fi": '<p dir="ltr">Peruskurssi</p>',
            "en": '<p dir="ltr">Basic course</p>',
        },
        "description": {
            "fi": '<p dir="ltr">Kuvaus kurssista</p>',
            "en": '<p dir="ltr">Course description</p>',
        },
        "categories": {
            "themes": ["ht_hyvinvointi", "ht_urheilu"],
            "formats": ["hm_harrastukset"],
            "locales": ["fi-FI"],
        },
        "demographics": {
            "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64"],
            "gender": ["gender/gender"],
        },
        "location": {
            "type": "place",
            "regions": ["city/FI/Helsinki"],
            "accessibility": ["ac_unknow"],
            "address": {
                "street": "Testikatu 1",
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
        "pricing": {
            "type": "paid",
            "info": {"fi": '<p dir="ltr">100 euroa</p>'},
        },
        "registration": {
            "required": True,
            "url": "https://example.com/register",
            "email": "test@example.com",
            "info": {"fi": '<p dir="ltr">Ilmoittaudu</p>'},
        },
        "contacts": {
            "list": [
                {
                    "type": "www",
                    "value": "https://example.com",
                    "description": {"fi": "Lisätietoja", "en": "More info"},
                }
            ]
        },
    }


@pytest.fixture
def mock_auth():
    """Mock auth configuration."""
    return {"group_id": "test-group-123", "cookies": "AUTH_TOKEN=abc123"}


@pytest.fixture
def sample_courses_yaml():
    """Sample courses.yaml content."""
    return {
        "defaults": {
            "course": {
                "type": "hobby",
                "required_locales": ["fi", "en"],
                "categories": {
                    "themes": ["ht_hyvinvointi", "ht_urheilu"],
                    "formats": ["hm_harrastukset"],
                    "locales": ["fi-FI"],
                },
                "demographics": {
                    "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64", "ageGroup/range:65-99"],
                    "gender": ["gender/gender"],
                },
            },
            "location": {
                "type": "place",
                "regions": ["city/FI/Helsinki", "city/FI/Espoo", "city/FI/Vantaa"],
                "accessibility": ["ac_unknow"],
                "address": {
                    "city": "Helsinki",
                    "state": "Uusimaa",
                    "country": "FI",
                    "zoom": 16,
                },
            },
        },
        "courses": [
            {
                "title": {"fi": "Taiji-kurssi", "en": "Tai chi course"},
                "type": "hobby",
            },
            {
                "title": {"fi": "Jooga-kurssi", "en": "Yoga course"},
                "type": "hobby",
            },
        ],
    }


# =============================================================================
# DOWNLOAD_ACTIVITIES.PY TESTS
# =============================================================================


class TestFetchActivities:
    """Tests for fetch_activities()."""

    def test_fetch_single_page(self, httpx_mock: HTTPXMock):
        """Test fetching a single page of activities."""
        mock_response = {
            "items": [{"_key": "1", "traits": {}}, {"_key": "2", "traits": {}}],
            "total": 2,
            "hasMore": False,
        }
        httpx_mock.add_response(
            url="https://hallinta.lahella.fi/v1/activities?groups%5B0%5D=test-group&links%5Bgroups%5D=true&total=true&limit=100&skip=0&text=",
            json=mock_response,
        )

        with httpx.Client() as client:
            result = fetch_activities(client, "test-group")

        assert result["items"] == mock_response["items"]
        assert result["total"] == 2
        assert result["hasMore"] is False

    def test_fetch_with_pagination_params(self, httpx_mock: HTTPXMock):
        """Test fetching with custom limit and skip."""
        mock_response = {"items": [], "total": 0, "hasMore": False}
        httpx_mock.add_response(json=mock_response)

        with httpx.Client() as client:
            result = fetch_activities(client, "test-group", limit=50, skip=100)

        request = httpx_mock.get_request()
        assert "limit=50" in str(request.url)
        assert "skip=100" in str(request.url)


class TestFetchAllActivities:
    """Tests for fetch_all_activities() with pagination."""

    def test_single_page(self, httpx_mock: HTTPXMock):
        """Test fetching when all items fit in one page."""
        mock_response = {
            "items": [{"_key": "1"}, {"_key": "2"}],
            "hasMore": False,
        }
        httpx_mock.add_response(json=mock_response)

        with httpx.Client() as client:
            result = fetch_all_activities(client, "test-group")

        assert len(result) == 2
        assert result[0]["_key"] == "1"

    def test_multiple_pages(self, httpx_mock: HTTPXMock):
        """Test pagination across multiple pages."""
        # First page
        httpx_mock.add_response(json={
            "items": [{"_key": "1"}, {"_key": "2"}],
            "hasMore": True,
        })
        # Second page
        httpx_mock.add_response(json={
            "items": [{"_key": "3"}],
            "hasMore": False,
        })

        with httpx.Client() as client:
            result = fetch_all_activities(client, "test-group")

        assert len(result) == 3
        assert [r["_key"] for r in result] == ["1", "2", "3"]


class TestFetchActivityById:
    """Tests for fetch_activity_by_id()."""

    def test_fetch_single_activity(self, httpx_mock: HTTPXMock, sample_api_activity):
        """Test fetching a single activity by ID."""
        httpx_mock.add_response(
            url="https://hallinta.lahella.fi/v1/activities/12345?links%5Bfiles%5D=true",
            json=sample_api_activity,
        )

        with httpx.Client() as client:
            result = fetch_activity_by_id(client, "12345")

        assert result["_key"] == "12345"
        assert result["traits"]["translations"]["fi"]["name"] == "Taiji-kurssi"

    def test_fetch_nonexistent_activity(self, httpx_mock: HTTPXMock):
        """Test fetching a nonexistent activity raises error."""
        httpx_mock.add_response(status_code=404)

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                fetch_activity_by_id(client, "nonexistent")


class TestConvertActivityToYaml:
    """Tests for convert_activity_to_yaml_schema()."""

    def test_basic_conversion(self, sample_api_activity):
        """Test converting API activity to YAML format."""
        result = convert_activity_to_yaml_schema(sample_api_activity)

        assert result["_key"] == "12345"
        assert result["_status"] == "published"
        assert result["title"]["fi"] == "Taiji-kurssi"
        assert result["type"] == "hobby"

    def test_schedule_conversion(self, sample_api_activity):
        """Test that schedule dates are converted."""
        result = convert_activity_to_yaml_schema(sample_api_activity)

        assert "schedule" in result
        assert result["schedule"]["start_date"] == "2025-01-15"
        assert result["schedule"]["end_date"] == "2025-05-15"
        assert result["schedule"]["weekly"][0]["weekday"] == 2

    def test_location_conversion(self, sample_api_activity):
        """Test that location is converted."""
        result = convert_activity_to_yaml_schema(sample_api_activity)

        assert "location" in result
        assert result["location"]["address"]["street"] == "Testikatu 1"
        assert result["location"]["address"]["postal_code"] == "00100"


class TestGetActivityStatus:
    """Tests for get_activity_status()."""

    def test_published_status(self):
        """Test activity with explicit status."""
        activity = {"status": "published"}
        assert get_activity_status(activity) == "published"

    def test_draft_status(self):
        """Test activity with draft status."""
        activity = {"status": "draft"}
        assert get_activity_status(activity) == "draft"

    def test_expired_by_visibility(self):
        """Test activity expired by visibility end date."""
        import time
        past_ms = (time.time() - 86400) * 1000  # 1 day ago
        activity = {
            "status": None,
            "tags": {"visibility": {"end": past_ms}},
        }
        assert get_activity_status(activity) == "expired"

    def test_pending_by_visibility(self):
        """Test activity pending by visibility start date."""
        import time
        future_ms = (time.time() + 86400) * 1000  # 1 day from now
        activity = {
            "status": None,
            "tags": {"visibility": {"start": future_ms}},
        }
        assert get_activity_status(activity) == "pending"


class TestTemplateMatcher:
    """Tests for TemplateMatcher class."""

    def test_load_defaults(self, sample_courses_yaml, tmp_path):
        """Test loading defaults from YAML file."""
        yaml = YAML()
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(sample_courses_yaml, f)

        matcher = TemplateMatcher(courses_file)

        assert "course_defaults" in matcher.anchors
        assert "location_defaults" in matcher.anchors

    def test_matches_course_defaults(self, sample_courses_yaml, tmp_path):
        """Test matching course against course_defaults."""
        yaml = YAML()
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(sample_courses_yaml, f)

        matcher = TemplateMatcher(courses_file)

        course = {
            "type": "hobby",
            "required_locales": ["fi", "en"],
            "categories": {
                "themes": ["ht_hyvinvointi", "ht_urheilu"],
                "formats": ["hm_harrastukset"],
                "locales": ["fi-FI"],
            },
            "demographics": {
                "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64", "ageGroup/range:65-99"],
                "gender": ["gender/gender"],
            },
        }

        assert matcher.matches_course_defaults(course) is True

    def test_does_not_match_different_type(self, sample_courses_yaml, tmp_path):
        """Test that different type doesn't match."""
        yaml = YAML()
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(sample_courses_yaml, f)

        matcher = TemplateMatcher(courses_file)

        course = {"type": "support"}  # Different type

        assert matcher.matches_course_defaults(course) is False

    def test_matches_location_defaults(self, sample_courses_yaml, tmp_path):
        """Test matching location against location_defaults."""
        yaml = YAML()
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(sample_courses_yaml, f)

        matcher = TemplateMatcher(courses_file)

        location = {
            "type": "place",
            "regions": ["city/FI/Helsinki", "city/FI/Espoo", "city/FI/Vantaa"],
            "accessibility": ["ac_unknow"],
            "address": {
                "city": "Helsinki",
                "state": "Uusimaa",
                "country": "FI",
            },
        }

        assert matcher.matches_location_defaults(location) is True

    def test_matches_html_text_semantically(self, tmp_path):
        """Test that HTML text matching ignores structural differences."""
        yaml = YAML()
        courses_yaml = {
            "defaults": {
                "text": {
                    "course_summary": {
                        "fi": '<p dir="ltr">Taiji-peruskurssi</p>',
                        "en": '<p dir="ltr">Tai chi course</p>',
                    }
                }
            }
        }
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(courses_yaml, f)

        matcher = TemplateMatcher(courses_file)

        # API might return slightly different HTML
        downloaded_summary = {
            "fi": '<p>Taiji-peruskurssi</p>',  # No dir attribute
            "en": '<p dir="ltr">Tai chi course</p>',
        }

        # The text content is the same, so it should match
        assert matcher._texts_match(
            downloaded_summary,
            courses_yaml["defaults"]["text"]["course_summary"]
        ) is True

    def test_does_not_match_different_html_content(self, tmp_path):
        """Test that HTML with different text content doesn't match."""
        yaml = YAML()
        courses_yaml = {
            "defaults": {
                "text": {
                    "course_summary": {
                        "fi": '<p dir="ltr">Taiji-peruskurssi</p>',
                    }
                }
            }
        }
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(courses_yaml, f)

        matcher = TemplateMatcher(courses_file)

        different_summary = {
            "fi": '<p dir="ltr">Jooga-peruskurssi</p>',  # Different content
        }

        assert matcher._texts_match(
            different_summary,
            courses_yaml["defaults"]["text"]["course_summary"]
        ) is False


class TestApplyTemplateMatching:
    """Tests for apply_template_matching()."""

    def test_returns_defaults_and_courses(self, sample_courses_yaml, tmp_path):
        """Test that apply_template_matching returns correct structure."""
        yaml = YAML()
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(sample_courses_yaml, f)

        matcher = TemplateMatcher(courses_file)
        courses = [
            {"title": {"fi": "Test"}, "type": "hobby"},
        ]

        defaults, processed = apply_template_matching(courses, matcher)

        assert "course" in defaults
        assert "location" in defaults
        assert "schedule" in defaults
        assert len(processed) == 1


# =============================================================================
# CREATE_COURSE.PY TESTS
# =============================================================================


class TestLoadCourses:
    """Tests for load_courses()."""

    def test_load_valid_yaml(self, sample_courses_yaml, tmp_path):
        """Test loading a valid YAML file."""
        yaml = YAML()
        courses_file = tmp_path / "courses.yaml"
        with open(courses_file, "w") as f:
            yaml.dump(sample_courses_yaml, f)

        result = load_courses(courses_file)

        assert "courses" in result
        assert len(result["courses"]) == 2


class TestGetCourseByTitle:
    """Tests for get_course_by_title()."""

    def test_exact_match(self, sample_courses_yaml):
        """Test finding course by exact title."""
        result = get_course_by_title(sample_courses_yaml, "Taiji-kurssi")
        assert result is not None
        assert result["title"]["fi"] == "Taiji-kurssi"

    def test_partial_match(self, sample_courses_yaml):
        """Test finding course by partial title."""
        result = get_course_by_title(sample_courses_yaml, "jooga")
        assert result is not None
        assert result["title"]["fi"] == "Jooga-kurssi"

    def test_case_insensitive(self, sample_courses_yaml):
        """Test case-insensitive matching."""
        result = get_course_by_title(sample_courses_yaml, "TAIJI")
        assert result is not None
        assert result["title"]["fi"] == "Taiji-kurssi"

    def test_by_index(self, sample_courses_yaml):
        """Test finding course by 1-based index."""
        result = get_course_by_title(sample_courses_yaml, "1")
        assert result is not None
        assert result["title"]["fi"] == "Taiji-kurssi"

        result = get_course_by_title(sample_courses_yaml, "2")
        assert result is not None
        assert result["title"]["fi"] == "Jooga-kurssi"

    def test_not_found(self, sample_courses_yaml):
        """Test returns None for non-existent course."""
        result = get_course_by_title(sample_courses_yaml, "nonexistent")
        assert result is None


class TestBuildActivityPayload:
    """Tests for build_activity_payload()."""

    def test_basic_payload(self, sample_yaml_course, mock_auth):
        """Test building basic payload from course."""
        result = build_activity_payload(sample_yaml_course, mock_auth, None)

        assert result["group"] == "test-group-123"
        assert "traits" in result
        assert result["traits"]["type"] == "hobby"
        assert result["traits"]["translations"]["fi"]["name"] == "Taiji-kurssi"

    def test_with_photo(self, sample_yaml_course, mock_auth):
        """Test payload includes photo when provided."""
        sample_yaml_course["image"] = {"alt": "Test image"}

        result = build_activity_payload(sample_yaml_course, mock_auth, "photo-123")

        assert result["traits"]["photo"] == "photo-123"
        assert result["traits"]["photoAlt"] == "Test image"

    def test_channels_created(self, sample_yaml_course, mock_auth):
        """Test that channels are created from location/schedule."""
        result = build_activity_payload(sample_yaml_course, mock_auth, None)

        assert "channels" in result["traits"]
        assert len(result["traits"]["channels"]) == 1
        channel = result["traits"]["channels"][0]
        assert channel["type"] == ["place"]
        assert channel["registrationRequired"] is True


class TestCreateActivity:
    """Tests for create_activity()."""

    def test_successful_creation(self, httpx_mock: HTTPXMock):
        """Test successful activity creation."""
        mock_response = {"_key": "new-activity-123", "status": "draft"}
        httpx_mock.add_response(
            url="https://hallinta.lahella.fi/v1/activities",
            json=mock_response,
        )

        payload = {"group": "test", "traits": {"type": "hobby"}}

        with httpx.Client() as client:
            result = create_activity(client, payload)

        assert result["_key"] == "new-activity-123"

    def test_creation_error(self, httpx_mock: HTTPXMock):
        """Test handling of creation error."""
        httpx_mock.add_response(
            url="https://hallinta.lahella.fi/v1/activities",
            status_code=400,
            json={"error": "Invalid payload"},
        )

        payload = {"group": "test", "traits": {}}

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                create_activity(client, payload)


class TestUploadImage:
    """Tests for upload_image_for_course()."""

    def test_successful_upload(self, httpx_mock: HTTPXMock, mock_auth, tmp_path):
        """Test successful image upload."""
        mock_response = {"_key": "uploaded-image-123"}
        httpx_mock.add_response(
            method="POST",
            json=mock_response,
        )

        # Create a test image file
        image_path = tmp_path / "test.jpg"
        image_path.write_bytes(b"fake image data")

        with httpx.Client() as client:
            result = upload_image_for_course(client, mock_auth, image_path)

        assert result == "uploaded-image-123"

    def test_upload_includes_group_param(self, httpx_mock: HTTPXMock, mock_auth, tmp_path):
        """Test that upload includes correct parameters."""
        httpx_mock.add_response(json={"_key": "123"})

        image_path = tmp_path / "test.jpg"
        image_path.write_bytes(b"fake image data")

        with httpx.Client() as client:
            upload_image_for_course(client, mock_auth, image_path)

        request = httpx_mock.get_request()
        assert "group=test-group-123" in str(request.url)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestRoundTrip:
    """Integration tests for YAML -> API -> YAML round-trip."""

    def test_convert_and_back(self, sample_yaml_course, mock_auth):
        """Test that converting to API and back preserves key data."""
        from field_mapping import Transformer

        transformer = Transformer()

        # YAML -> API
        api_payload = transformer.yaml_to_api(sample_yaml_course, group_id=mock_auth["group_id"])

        # Simulate what API returns (add _key, status)
        api_payload["_key"] = "12345"
        api_payload["status"] = "published"

        # API -> YAML
        result = transformer.api_to_yaml(api_payload)

        # Check key fields preserved
        assert result["title"]["fi"] == sample_yaml_course["title"]["fi"]
        assert result["type"] == sample_yaml_course["type"]
        assert result["schedule"]["start_date"] == sample_yaml_course["schedule"]["start_date"]
        assert result["schedule"]["end_date"] == sample_yaml_course["schedule"]["end_date"]


class TestEndToEndDownload:
    """End-to-end tests for download workflow."""

    def test_full_download_workflow(self, httpx_mock: HTTPXMock, sample_api_activity, tmp_path):
        """Test complete download and conversion workflow."""
        # Mock API response
        httpx_mock.add_response(json={
            "items": [sample_api_activity],
            "hasMore": False,
        })

        with httpx.Client() as client:
            # Fetch activities
            activities = fetch_all_activities(client, "test-group")

        # Convert to YAML
        courses = [convert_activity_to_yaml_schema(a) for a in activities]

        assert len(courses) == 1
        course = courses[0]

        assert course["_key"] == "12345"
        assert course["title"]["fi"] == "Taiji-kurssi"
        assert course["schedule"]["start_date"] == "2025-01-15"
        assert course["location"]["address"]["street"] == "Testikatu 1"


class TestEndToEndCreate:
    """End-to-end tests for create workflow."""

    def test_full_create_workflow(self, httpx_mock: HTTPXMock, sample_yaml_course, mock_auth, tmp_path):
        """Test complete course creation workflow."""
        # Mock successful creation
        httpx_mock.add_response(
            method="POST",
            json={"_key": "created-123", "status": "draft"},
        )

        # Build payload
        payload = build_activity_payload(sample_yaml_course, mock_auth, None)

        # Create activity
        with httpx.Client() as client:
            result = create_activity(client, payload)

        assert result["_key"] == "created-123"

        # Verify the request
        request = httpx_mock.get_request()
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body["group"] == "test-group-123"
        assert body["traits"]["translations"]["fi"]["name"] == "Taiji-kurssi"
