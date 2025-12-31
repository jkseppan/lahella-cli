#!/usr/bin/env python3
"""
Test suite for activity_diff.py - diff detection between local YAML and server state.

Run with: uv run pytest test_activity_diff.py -v
"""


from activity_diff import diff_activities, format_diffs, FieldDiff


class TestDiffActivities:
    """Tests for diff_activities() function."""

    def test_identical_activities_no_diff(self):
        """Identical activities should produce no diff."""
        local = {
            "title": {"fi": "Testikurssi", "en": "Test Course"},
            "type": "hobby",
        }
        server = {
            "title": {"fi": "Testikurssi", "en": "Test Course"},
            "type": "hobby",
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_title_changed(self):
        """Detect title changes."""
        local = {
            "title": {"fi": "Uusi nimi", "en": "New Name"},
            "type": "hobby",
        }
        server = {
            "title": {"fi": "Vanha nimi", "en": "Old Name"},
            "type": "hobby",
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 2
        fi_diff = next(d for d in diffs if d.path == "title.fi")
        assert fi_diff.local_value == "Uusi nimi"
        assert fi_diff.server_value == "Vanha nimi"

    def test_html_semantic_comparison(self):
        """HTML fields should be compared semantically, ignoring formatting."""
        local = {
            "summary": {"fi": '<p dir="ltr">Same content</p>'},
        }
        server = {
            "summary": {"fi": '<p>Same content</p>'},
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_html_different_content(self):
        """HTML fields with different content should produce diff."""
        local = {
            "summary": {"fi": '<p dir="ltr">New content</p>'},
        }
        server = {
            "summary": {"fi": '<p dir="ltr">Old content</p>'},
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "summary.fi"

    def test_array_compared_as_sets(self):
        """Category arrays should be compared as sets (order doesn't matter)."""
        local = {
            "categories": {"themes": ["ht_urheilu", "ht_hyvinvointi"]},
        }
        server = {
            "categories": {"themes": ["ht_hyvinvointi", "ht_urheilu"]},
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_array_different_content(self):
        """Category arrays with different content should produce diff."""
        local = {
            "categories": {"themes": ["ht_urheilu", "ht_hyvinvointi"]},
        }
        server = {
            "categories": {"themes": ["ht_urheilu"]},
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "categories.themes"

    def test_field_added_locally(self):
        """Detect fields that exist locally but not on server."""
        local = {
            "title": {"fi": "Test"},
            "summary": {"fi": "New summary"},
        }
        server = {
            "title": {"fi": "Test"},
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "summary.fi"
        assert diffs[0].server_value is None

    def test_field_removed_locally(self):
        """Detect fields that exist on server but not locally."""
        local = {
            "title": {"fi": "Test"},
        }
        server = {
            "title": {"fi": "Test"},
            "summary": {"fi": "Server summary"},
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "summary.fi"
        assert diffs[0].local_value is None

    def test_nested_field_change(self):
        """Detect changes in deeply nested fields."""
        local = {
            "location": {
                "address": {
                    "street": "New Street 1",
                    "postal_code": "00100",
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "street": "Old Street 1",
                    "postal_code": "00100",
                }
            }
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "location.address.street"

    def test_schedule_weekly_compared(self):
        """Schedule weekly entries should be compared properly."""
        local = {
            "schedule": {
                "weekly": [
                    {"weekday": 2, "start_time": "18:00", "end_time": "19:30"}
                ]
            }
        }
        server = {
            "schedule": {
                "weekly": [
                    {"weekday": 2, "start_time": "18:00", "end_time": "19:00"}
                ]
            }
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 1


class TestFieldDiff:
    """Tests for FieldDiff dataclass."""

    def test_field_diff_creation(self):
        """Test creating a FieldDiff."""
        diff = FieldDiff(
            path="title.fi",
            local_value="New",
            server_value="Old",
        )

        assert diff.path == "title.fi"
        assert diff.local_value == "New"
        assert diff.server_value == "Old"

    def test_field_diff_str(self):
        """Test string representation of FieldDiff."""
        diff = FieldDiff(
            path="title.fi",
            local_value="New",
            server_value="Old",
        )

        s = str(diff)

        assert "title.fi" in s
        assert "New" in s
        assert "Old" in s


class TestIgnoreMetadata:
    """Tests for ignoring metadata fields."""

    def test_ignores_key_by_default(self):
        """_key field should be ignored by default."""
        local = {
            "_key": "local-key",
            "title": {"fi": "Test"},
        }
        server = {
            "_key": "server-key",
            "title": {"fi": "Test"},
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_ignores_status_by_default(self):
        """_status field should be ignored by default."""
        local = {
            "_status": "draft",
            "title": {"fi": "Test"},
        }
        server = {
            "_status": "published",
            "title": {"fi": "Test"},
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_can_include_metadata(self):
        """Metadata can be included with ignore_metadata=False."""
        local = {
            "_key": "local-key",
            "title": {"fi": "Test"},
        }
        server = {
            "_key": "server-key",
            "title": {"fi": "Test"},
        }

        diffs = diff_activities(local, server, ignore_metadata=False)

        assert len(diffs) == 1
        assert diffs[0].path == "_key"


class TestFormatDiffs:
    """Tests for format_diffs() function."""

    def test_no_diffs(self):
        """Empty diff list should return appropriate message."""
        result = format_diffs([])

        assert result == "No changes detected."

    def test_added_field(self):
        """Added fields should show + prefix."""
        diffs = [FieldDiff(
            path="summary.fi",
            local_value="New summary",
            server_value=None,
        )]

        result = format_diffs(diffs)

        assert "+ summary.fi" in result
        assert "New summary" in result

    def test_removed_field(self):
        """Removed fields should show - prefix."""
        diffs = [FieldDiff(
            path="summary.fi",
            local_value=None,
            server_value="Old summary",
        )]

        result = format_diffs(diffs)

        assert "- summary.fi" in result
        assert "Old summary" in result

    def test_changed_field(self):
        """Changed fields should show ~ prefix with both values."""
        diffs = [FieldDiff(
            path="title.fi",
            local_value="New",
            server_value="Old",
        )]

        result = format_diffs(diffs)

        assert "~ title.fi" in result
        assert "server:" in result
        assert "local:" in result
        assert "New" in result
        assert "Old" in result

    def test_truncates_long_values(self):
        """Long string values should be truncated."""
        long_value = "A" * 100
        diffs = [FieldDiff(
            path="description.fi",
            local_value=long_value,
            server_value=None,
        )]

        result = format_diffs(diffs)

        assert "..." in result
        assert len(result) < 200


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_activities(self):
        """Empty activities should produce no diff."""
        diffs = diff_activities({}, {})

        assert diffs == []

    def test_empty_vs_nonempty(self):
        """Empty vs non-empty should detect all fields."""
        local = {"title": {"fi": "Test"}}
        server = {}

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "title.fi"

    def test_none_values(self):
        """None values should be handled correctly."""
        local = {"value": None}
        server = {"value": "something"}

        diffs = diff_activities(local, server)

        assert len(diffs) == 1

    def test_boolean_values(self):
        """Boolean values should be compared correctly."""
        local = {"registration": {"required": True}}
        server = {"registration": {"required": False}}

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "registration.required"

    def test_numeric_values(self):
        """Numeric values should be compared correctly."""
        local = {"location": {"address": {"zoom": 16}}}
        server = {"location": {"address": {"zoom": 14}}}

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "location.address.zoom"


class TestDefaultValues:
    """Tests for default value handling in comparisons."""

    def test_registration_required_default_true(self):
        """Missing registration.required should default to True."""
        local = {}
        server = {"registration": {"required": True}}

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_registration_required_explicit_true(self):
        """Explicit registration.required=True should match server."""
        local = {"registration": {"required": True}}
        server = {"registration": {"required": True}}

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_registration_required_false_differs_from_default(self):
        """Explicit registration.required=False should differ from server True."""
        local = {"registration": {"required": False}}
        server = {"registration": {"required": True}}

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "registration.required"

    def test_pricing_type_default_paid(self):
        """Missing pricing.type should default to 'paid'."""
        local = {}
        server = {"pricing": {"type": "paid"}}

        diffs = diff_activities(local, server)

        assert diffs == []


class TestImageHandling:
    """Tests for image.path/image.id special handling."""

    def test_image_path_ignored_when_id_matches(self):
        """image.path should not be reported if image.id matches."""
        local = {
            "image": {"path": "photo.jpg", "id": "12345"},
        }
        server = {
            "image": {"id": "12345"},
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_image_path_reported_when_id_differs(self):
        """image.path should be reported if image.id differs."""
        local = {
            "image": {"path": "photo.jpg", "id": "12345"},
        }
        server = {
            "image": {"id": "99999"},
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 2
        paths = {d.path for d in diffs}
        assert "image.path" in paths
        assert "image.id" in paths

    def test_image_path_reported_when_no_local_id(self):
        """image.path should be reported if local has no id."""
        local = {
            "image": {"path": "photo.jpg"},
        }
        server = {
            "image": {"id": "12345"},
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 2
        paths = {d.path for d in diffs}
        assert "image.path" in paths
        assert "image.id" in paths


class TestGeocodedCoordinates:
    """Tests for filtering geocoded coordinates (when street address is present)."""

    def test_ignores_coordinates_when_street_present_in_local(self):
        """Coordinate diffs should be ignored when local has street address."""
        local = {
            "location": {
                "address": {
                    "street": "Nervanderinkatu 8",
                    "postal_code": "00100",
                    "city": "Helsinki",
                    "coordinates": [24.93033, 60.17235],
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "street": "Nervanderinkatu 8",
                    "postal_code": "00100",
                    "city": "Helsinki",
                    "coordinates": [24.9384, 60.1699],  # Different (geocoded)
                }
            }
        }

        diffs = diff_activities(local, server)

        # Should not report coordinate diff when street is present
        assert not any(d.path == "location.address.coordinates" for d in diffs)

    def test_ignores_coordinates_when_street_present_in_server(self):
        """Coordinate diffs should be ignored when server has street address."""
        local = {
            "location": {
                "address": {
                    "postal_code": "00100",
                    "coordinates": [24.93033, 60.17235],
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "street": "Nervanderinkatu 8",
                    "postal_code": "00100",
                    "coordinates": [24.9384, 60.1699],  # Geocoded
                }
            }
        }

        diffs = diff_activities(local, server)

        # Should not report coordinate diff when server geocoded the address
        assert not any(d.path == "location.address.coordinates" for d in diffs)

    def test_reports_coordinates_when_street_is_null(self):
        """Coordinate diffs should be reported when street is null (user dragged marker)."""
        local = {
            "location": {
                "address": {
                    "street": None,
                    "postal_code": "00180",
                    "city": "Helsinki",
                    "coordinates": [24.883818, 60.174580],  # User dragged marker
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "street": None,
                    "postal_code": "00180",
                    "city": "Helsinki",
                    "coordinates": [24.9384, 60.1699],  # Different
                }
            }
        }

        diffs = diff_activities(local, server)

        # Should report coordinate diff when street is null (user-controlled)
        coord_diffs = [d for d in diffs if d.path == "location.address.coordinates"]
        assert len(coord_diffs) == 1

    def test_reports_coordinates_when_no_street_field(self):
        """Coordinate diffs should be reported when street field is absent."""
        local = {
            "location": {
                "address": {
                    "postal_code": "00180",
                    "coordinates": [24.883818, 60.174580],
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "postal_code": "00180",
                    "coordinates": [24.9384, 60.1699],
                }
            }
        }

        diffs = diff_activities(local, server)

        # Should report coordinate diff when no street (user-controlled)
        coord_diffs = [d for d in diffs if d.path == "location.address.coordinates"]
        assert len(coord_diffs) == 1


class TestServerGeneratedFields:
    """Tests for ignoring server-generated fields."""

    def test_ignores_coordinates_when_only_on_server(self):
        """coordinates added by server should be ignored if not in local."""
        local = {
            "location": {
                "address": {
                    "street": "Test 1",
                    "city": "Helsinki",
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "street": "Test 1",
                    "city": "Helsinki",
                    "coordinates": [24.9384, 60.1699],
                }
            }
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_ignores_zoom_when_only_on_server(self):
        """zoom added by server should be ignored if not in local."""
        local = {
            "location": {
                "address": {
                    "postal_code": "00100",
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "postal_code": "00100",
                    "zoom": 16,
                }
            }
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_reports_coordinates_when_both_have_them(self):
        """If local has coordinates, differences should be reported."""
        local = {
            "location": {
                "address": {
                    "coordinates": [25.0, 60.0],
                }
            }
        }
        server = {
            "location": {
                "address": {
                    "coordinates": [24.9384, 60.1699],
                }
            }
        }

        diffs = diff_activities(local, server)

        assert len(diffs) == 1
        assert diffs[0].path == "location.address.coordinates"

    def test_ignores_server_coordinates_in_channels(self):
        """Server-added coordinates in channels should be ignored."""
        local = {
            "channels": [
                {
                    "location": {
                        "address": {"street": "Test 1"},
                    }
                }
            ]
        }
        server = {
            "channels": [
                {
                    "location": {
                        "address": {
                            "street": "Test 1",
                            "coordinates": [24.9384, 60.1699],
                            "zoom": 16,
                        },
                    }
                }
            ]
        }

        diffs = diff_activities(local, server)

        assert diffs == []

    def test_real_world_multi_channel_scenario(self):
        """Real-world test: multiple channels with server-added fields."""
        local = {
            "channels": [
                {
                    "location": {
                        "type": "phone",
                        "address": {"street": None, "city": None},
                    }
                },
                {
                    "location": {
                        "type": "place",
                        "address": {"street": "Testikatu 1", "city": "Helsinki"},
                    }
                },
            ]
        }
        server = {
            "channels": [
                {
                    "location": {
                        "type": "phone",
                        "address": {
                            "street": None,
                            "city": None,
                            "coordinates": [24.9, 60.1],
                            "zoom": 16,
                        },
                    }
                },
                {
                    "location": {
                        "type": "place",
                        "address": {
                            "street": "Testikatu 1",
                            "city": "Helsinki",
                            "coordinates": [24.95, 60.17],
                            "zoom": 16,
                        },
                    }
                },
            ]
        }

        diffs = diff_activities(local, server)

        assert diffs == []
