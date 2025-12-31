#!/usr/bin/env python3
"""
Test suite for update_payload.py - building update payloads for modified activities.

Run with: uv run pytest test_update_payload.py -v
"""

from lahella_cli.update_payload import build_update_payload


class TestBuildUpdatePayload:
    """Tests for build_update_payload() function."""

    def test_basic_payload_structure(self):
        """Update payload should have correct structure."""
        local = {
            "title": {"fi": "Testikurssi", "en": "Test Course"},
            "type": "hobby",
            "location": {
                "type": "place",
                "address": {
                    "street": "Testikatu 1",
                    "postal_code": "00100",
                    "city": "Helsinki",
                },
            },
            "schedule": {
                "start_date": "2025-01-15",
                "end_date": "2025-06-15",
                "weekly": [{"weekday": 2, "start_time": "18:00", "end_time": "19:30"}],
            },
        }
        server_activity = {"_key": "abc123", "traits": {"channels": [{"id": "ch-uuid"}]}}

        payload = build_update_payload(local, server_activity, group_id="group123")

        assert "traits" in payload
        assert payload["traits"]["translations"]["fi"]["name"] == "Testikurssi"
        assert payload["group"] == "group123"

    def test_preserves_channel_id_from_server(self):
        """Should preserve existing channel UUID from server."""
        local = {
            "title": {"fi": "Test"},
            "location": {"type": "place", "address": {"street": "Test 1"}},
            "schedule": {"start_date": "2025-01-15", "end_date": "2025-06-15"},
        }
        server_activity = {
            "_key": "abc123",
            "traits": {"channels": [{"id": "existing-channel-uuid"}]},
        }

        payload = build_update_payload(local, server_activity, group_id="g1")

        assert payload["traits"]["channels"][0]["id"] == "existing-channel-uuid"

    def test_preserves_contact_ids_from_server(self):
        """Should preserve existing contact UUIDs from server."""
        local = {
            "title": {"fi": "Test"},
            "contacts": {
                "list": [
                    {"type": "email", "value": "test@example.com"},
                    {"type": "phone", "value": "123456"},
                ]
            },
            "location": {"type": "place", "address": {"street": "Test 1"}},
            "schedule": {"start_date": "2025-01-15", "end_date": "2025-06-15"},
        }
        server_activity = {
            "_key": "abc123",
            "traits": {
                "contacts": [
                    {"id": "contact-uuid-1", "type": "email", "value": "test@example.com"},
                    {"id": "contact-uuid-2", "type": "phone", "value": "123456"},
                ],
                "channels": [{"id": "ch-uuid"}],
            },
        }

        payload = build_update_payload(local, server_activity, group_id="g1")

        contacts = payload["traits"]["contacts"]
        assert len(contacts) == 2
        email_contact = next(c for c in contacts if c["type"] == "email")
        assert email_contact["id"] == "contact-uuid-1"

    def test_generates_new_uuid_for_new_contact(self):
        """New contacts should get new UUIDs."""
        local = {
            "title": {"fi": "Test"},
            "contacts": {
                "list": [
                    {"type": "email", "value": "new@example.com"},
                ]
            },
            "location": {"type": "place", "address": {"street": "Test 1"}},
            "schedule": {"start_date": "2025-01-15", "end_date": "2025-06-15"},
        }
        server_activity = {
            "_key": "abc123",
            "traits": {
                "contacts": [
                    {"id": "old-uuid", "type": "email", "value": "old@example.com"},
                ],
                "channels": [{"id": "ch-uuid"}],
            },
        }

        payload = build_update_payload(local, server_activity, group_id="g1")

        contacts = payload["traits"]["contacts"]
        assert len(contacts) == 1
        assert contacts[0]["id"] != "old-uuid"
        assert len(contacts[0]["id"]) == 36  # UUID length

    def test_preserves_photo_id_when_not_changed(self):
        """Should preserve photo ID from server when not uploading new image."""
        local = {
            "title": {"fi": "Test"},
            "image": {"id": "photo123", "alt": "Test image"},
            "location": {"type": "place", "address": {"street": "Test 1"}},
            "schedule": {"start_date": "2025-01-15", "end_date": "2025-06-15"},
        }
        server_activity = {
            "_key": "abc123",
            "traits": {"photo": "photo123", "channels": [{"id": "ch-uuid"}]},
        }

        payload = build_update_payload(local, server_activity, group_id="g1")

        assert payload["traits"]["photo"] == "photo123"

    def test_uses_new_photo_id_when_provided(self):
        """Should use new photo ID when explicitly provided."""
        local = {
            "title": {"fi": "Test"},
            "image": {"path": "new.jpg", "alt": "New image"},
            "location": {"type": "place", "address": {"street": "Test 1"}},
            "schedule": {"start_date": "2025-01-15", "end_date": "2025-06-15"},
        }
        server_activity = {
            "_key": "abc123",
            "traits": {"photo": "old-photo", "channels": [{"id": "ch-uuid"}]},
        }

        payload = build_update_payload(
            local, server_activity, group_id="g1", new_photo_id="new-photo-id"
        )

        assert payload["traits"]["photo"] == "new-photo-id"

    def test_excludes_key_from_payload(self):
        """The _key should not be in the payload (it goes in the URL)."""
        local = {
            "_key": "abc123",
            "title": {"fi": "Test"},
            "location": {"type": "place", "address": {"street": "Test 1"}},
            "schedule": {"start_date": "2025-01-15", "end_date": "2025-06-15"},
        }
        server_activity = {
            "_key": "abc123",
            "traits": {"channels": [{"id": "ch-uuid"}]},
        }

        payload = build_update_payload(local, server_activity, group_id="g1")

        assert "_key" not in payload


class TestMultipleChannels:
    """Tests for activities with multiple channels/locations."""

    def test_preserves_all_channel_ids(self):
        """Should preserve all channel UUIDs when updating multi-channel activity."""
        local = {
            "title": {"fi": "Multi-location"},
            "channels": [
                {"location": {"address": {"street": "Location A"}}},
                {"location": {"address": {"street": "Location B"}}},
            ],
            "schedule": {"start_date": "2025-01-15", "end_date": "2025-06-15"},
        }
        server_activity = {
            "_key": "abc123",
            "traits": {
                "channels": [
                    {"id": "channel-uuid-1"},
                    {"id": "channel-uuid-2"},
                ],
            },
        }

        payload = build_update_payload(local, server_activity, group_id="g1")

        channels = payload["traits"]["channels"]
        assert len(channels) == 2
        assert channels[0]["id"] == "channel-uuid-1"
        assert channels[1]["id"] == "channel-uuid-2"
