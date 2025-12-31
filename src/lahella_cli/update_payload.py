#!/usr/bin/env python3
"""
Build API payloads for creating and updating activities.

This module creates API payloads for POST/PUT requests, with optional
preservation of server-generated UUIDs for updates.
"""

from .field_mapping import Transformer, get_nested


def build_payload(
    local: dict,
    group_id: str,
    photo_id: str | None = None,
    server_activity: dict | None = None,
) -> dict:
    """
    Build an API payload from local YAML.

    Args:
        local: Activity dict from local YAML
        group_id: Group ID to include in payload
        photo_id: Photo ID (from upload or existing). If None, uses image.id from local.
        server_activity: If provided, preserve channel/contact UUIDs from server (for updates)

    Returns:
        API payload dict ready for POST (create) or PUT (update) request
    """
    transformer = Transformer()
    payload = transformer.yaml_to_api(local, group_id=group_id)

    if server_activity:
        _preserve_channel_ids(payload, server_activity)
        _preserve_contact_ids(payload, server_activity)

    if photo_id:
        payload["traits"]["photo"] = photo_id

    if "_key" in payload:
        del payload["_key"]

    return payload


def build_update_payload(
    local: dict,
    server_activity: dict,
    group_id: str,
    new_photo_id: str | None = None,
) -> dict:
    """
    Build an update payload from local YAML, preserving server UUIDs.

    This is a convenience wrapper around build_payload for updates.

    Args:
        local: Activity dict from local YAML
        server_activity: Current activity from server (for preserving UUIDs)
        group_id: Group ID to include in payload
        new_photo_id: New photo ID if image was uploaded, None to preserve existing

    Returns:
        API payload dict ready for PUT request
    """
    photo_id = new_photo_id
    if not photo_id:
        photo_id = get_nested(server_activity, "traits.photo")

    return build_payload(
        local=local,
        group_id=group_id,
        photo_id=photo_id,
        server_activity=server_activity,
    )


def _preserve_channel_ids(payload: dict, server_activity: dict) -> None:
    """Preserve channel UUIDs from server in the payload."""
    server_channels = get_nested(server_activity, "traits.channels", [])
    payload_channels = get_nested(payload, "traits.channels", [])

    for i, channel in enumerate(payload_channels):
        if i < len(server_channels) and server_channels[i].get("id"):
            channel["id"] = server_channels[i]["id"]


def _preserve_contact_ids(payload: dict, server_activity: dict) -> None:
    """Preserve contact UUIDs from server, matching by type+value."""
    server_contacts = get_nested(server_activity, "traits.contacts", [])
    payload_contacts = get_nested(payload, "traits.contacts", [])

    server_contact_map = {
        (c.get("type"), c.get("value")): c.get("id") for c in server_contacts
    }

    for contact in payload_contacts:
        key = (contact.get("type"), contact.get("value"))
        if key in server_contact_map:
            contact["id"] = server_contact_map[key]
