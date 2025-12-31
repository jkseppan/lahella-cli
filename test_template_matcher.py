#!/usr/bin/env python3
"""
Test suite for TemplateMatcher in download_activities.py

Tests that downloaded courses preserve anchor names and structure from template.

Run with: uv run pytest test_template_matcher.py -v
"""

import io
import pytest
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from download_activities import TemplateMatcher


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def yaml_parser():
    """Create a YAML parser that preserves anchors."""
    yaml = YAML()
    return yaml


@pytest.fixture
def simple_template(tmp_path, yaml_parser):
    """Create a simple template file with anchors."""
    content = """\
defaults:
  course: &event_defaults
    type: hobby
    required_locales: [fi, en]

courses:
  - title:
      fi: Testikurssi
    <<: *event_defaults
"""
    template_file = tmp_path / "template.yaml"
    template_file.write_text(content)
    return template_file


@pytest.fixture
def full_template(tmp_path):
    """Create a template file matching courses.yaml structure."""
    content = """\
defaults:
  course: &event_defaults
    type: hobby
    required_locales: [fi, en]
    categories:
      themes: [ht_hyvinvointi, ht_urheilu]
      formats: [hm_harrastukset]
      locales: [fi-FI]
    demographics:
      age_groups: [ageGroup/range:18-29, ageGroup/range:30-64]
      gender: [gender/gender]

  text:
    course_summary: &summary_peruskurssi
      fi: '<p dir="ltr">Taiji-peruskurssi</p>'
      en: '<p dir="ltr">Tai chi basic course</p>'
    course_description: &description_peruskurssi
      fi: '<p dir="ltr">Peruskurssit on tarkoitettu vasta-alkajille.</p>'
      en: '<p dir="ltr">Basic courses for beginners.</p>'

  address: &address_defaults
    city: Helsinki
    state: Uusimaa
    country: FI
    zoom: 16

  location: &location_defaults
    type: place
    regions: [city/FI/Helsinki, city/FI/Espoo, city/FI/Vantaa]
    accessibility: [ac_unknow]

  pricing:
    kurssi_info: &pricing_195
      fi: '<p dir="ltr">195 euroa</p>'
      en: '<p dir="ltr">€195</p>'

  image:
    kurssi: &image_kurssi
      path: taijikuva.jpg
      alt: Oppilaita kurssilla

courses:
  - title:
      fi: Taiji-kurssi
      en: Tai chi course
    <<: *event_defaults
    summary: *summary_peruskurssi
    description: *description_peruskurssi
    location:
      <<: *location_defaults
      address:
        <<: *address_defaults
        street: Testikatu 1
        postal_code: "00100"
    image: *image_kurssi
"""
    template_file = tmp_path / "template.yaml"
    template_file.write_text(content)
    return template_file


# =============================================================================
# PHASE 1: PRESERVE ANCHOR NAMES
# =============================================================================


class TestAnchorNamePreservation:
    """Tests that anchor names from template are preserved exactly."""

    def test_extracts_course_anchor_name(self, simple_template):
        """Should extract anchor name 'event_defaults' not 'course_defaults'."""
        matcher = TemplateMatcher(simple_template)

        # The anchor should be stored with its original name
        assert "event_defaults" in matcher.anchors
        assert "course_defaults" not in matcher.anchors

    def test_extracts_text_anchor_names(self, full_template):
        """Should extract text anchors with their original names."""
        matcher = TemplateMatcher(full_template)

        # Should preserve original anchor names like &summary_peruskurssi
        assert "summary_peruskurssi" in matcher.anchors
        assert "description_peruskurssi" in matcher.anchors

        # Should NOT use mapped names like summary_kurssi
        assert "summary_kurssi" not in matcher.anchors
        assert "description_kurssi" not in matcher.anchors

    def test_extracts_address_anchor(self, full_template):
        """Should extract address_defaults anchor."""
        matcher = TemplateMatcher(full_template)

        assert "address_defaults" in matcher.anchors
        assert matcher.anchors["address_defaults"]["city"] == "Helsinki"

    def test_extracts_location_anchor(self, full_template):
        """Should extract location_defaults anchor."""
        matcher = TemplateMatcher(full_template)

        assert "location_defaults" in matcher.anchors
        assert matcher.anchors["location_defaults"]["type"] == "place"

    def test_extracts_pricing_anchor(self, full_template):
        """Should extract pricing anchors with original names."""
        matcher = TemplateMatcher(full_template)

        # Original name is &pricing_195, not &pricing_paid
        assert "pricing_195" in matcher.anchors

    def test_extracts_image_anchor(self, full_template):
        """Should extract image anchors."""
        matcher = TemplateMatcher(full_template)

        assert "image_kurssi" in matcher.anchors
        assert matcher.anchors["image_kurssi"]["alt"] == "Oppilaita kurssilla"


class TestAnchorMatching:
    """Tests that content is matched to correct anchors."""

    def test_finds_partial_match_for_course(self, full_template):
        """Should find partial match for course with same type as event_defaults."""
        matcher = TemplateMatcher(full_template)

        course = {
            "type": "hobby",
            "required_locales": ["fi", "en"],
            "categories": {
                "themes": ["ht_hyvinvointi", "ht_urheilu"],
                "formats": ["hm_harrastukset"],
                "locales": ["fi-FI"],
            },
            "demographics": {
                "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64"],
                "gender": ["gender/gender"],
            },
        }

        anchor, overrides, _matched = matcher.find_partial_match(course)
        assert anchor is not None
        assert anchor.anchor.value == "event_defaults"
        # All fields match, so no overrides needed
        assert overrides == {}


# =============================================================================
# PHASE 2: USE ALIASES IN OUTPUT
# =============================================================================


class TestAliasOutput:
    """Tests that output uses aliases when content matches anchors."""

    def test_apply_template_uses_alias_for_summary(self, full_template, yaml_parser):
        """When summary matches anchor, output should use alias not inline text."""
        from download_activities import apply_template_matching

        matcher = TemplateMatcher(full_template)

        course = {
            "_key": "12345",
            "_status": "published",
            "title": {"fi": "Testikurssi", "en": "Test course"},
            "type": "hobby",
            "required_locales": ["fi", "en"],
            "summary": {
                "fi": '<p dir="ltr">Taiji-peruskurssi</p>',
                "en": '<p dir="ltr">Tai chi basic course</p>',
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
        }

        defaults, processed = apply_template_matching([course], matcher)

        # Serialize to YAML and check that alias is used
        yaml = YAML()
        stream = io.StringIO()
        result = CommentedMap()
        result["defaults"] = defaults
        result["courses"] = processed
        yaml.dump(result, stream)
        output = stream.getvalue()

        # The output should contain the alias reference
        assert "*summary_peruskurssi" in output
        # And NOT contain the full inline text in the course
        # (it should be in defaults, but not repeated in course)
        lines = output.split('\n')
        course_section_started = False
        for line in lines:
            if 'courses:' in line:
                course_section_started = True
            if course_section_started and 'Taiji-peruskurssi' in line:
                # If we see the text in course section, it should be via alias
                assert '*summary_peruskurssi' in line or 'summary_peruskurssi' in line

    def test_apply_template_uses_alias_for_description(self, full_template):
        """When description matches anchor, output should use alias."""
        from download_activities import apply_template_matching

        matcher = TemplateMatcher(full_template)

        course = {
            "_key": "12345",
            "title": {"fi": "Testikurssi"},
            "type": "hobby",
            "required_locales": ["fi", "en"],
            "description": {
                "fi": '<p dir="ltr">Peruskurssit on tarkoitettu vasta-alkajille.</p>',
                "en": '<p dir="ltr">Basic courses for beginners.</p>',
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
        }

        defaults, processed = apply_template_matching([course], matcher)

        yaml = YAML()
        stream = io.StringIO()
        result = CommentedMap()
        result["defaults"] = defaults
        result["courses"] = processed
        yaml.dump(result, stream)
        output = stream.getvalue()

        assert "*description_peruskurssi" in output

    def test_apply_template_uses_merge_key_with_correct_anchor(self, full_template):
        """Merge key should use the template's anchor name, not hardcoded."""
        from download_activities import apply_template_matching

        matcher = TemplateMatcher(full_template)

        course = {
            "_key": "12345",
            "title": {"fi": "Testikurssi"},
            "type": "hobby",
            "required_locales": ["fi", "en"],
            "categories": {
                "themes": ["ht_hyvinvointi", "ht_urheilu"],
                "formats": ["hm_harrastukset"],
                "locales": ["fi-FI"],
            },
            "demographics": {
                "age_groups": ["ageGroup/range:18-29", "ageGroup/range:30-64"],
                "gender": ["gender/gender"],
            },
        }

        defaults, processed = apply_template_matching([course], matcher)

        yaml = YAML()
        stream = io.StringIO()
        result = CommentedMap()
        result["defaults"] = defaults
        result["courses"] = processed
        yaml.dump(result, stream)
        output = stream.getvalue()

        # Should use *event_defaults (from template), not *course_defaults
        assert "*event_defaults" in output
        assert "*course_defaults" not in output


# =============================================================================
# PHASE 3: PRESERVE DEFAULTS STRUCTURE
# =============================================================================


class TestDefaultsStructure:
    """Tests that output defaults structure matches template structure."""

    def test_preserves_address_defaults_anchor(self, full_template):
        """Should preserve address_defaults as separate anchor."""
        from download_activities import apply_template_matching

        matcher = TemplateMatcher(full_template)
        defaults, _ = apply_template_matching([], matcher)

        yaml = YAML()
        stream = io.StringIO()
        yaml.dump({"defaults": defaults}, stream)
        output = stream.getvalue()

        # Template has &address_defaults as separate anchor
        assert "&address_defaults" in output

    def test_preserves_pricing_info_anchors(self, full_template):
        """Should preserve pricing info anchors like &pricing_195."""
        from download_activities import apply_template_matching

        matcher = TemplateMatcher(full_template)
        defaults, _ = apply_template_matching([], matcher)

        yaml = YAML()
        stream = io.StringIO()
        yaml.dump({"defaults": defaults}, stream)
        output = stream.getvalue()

        # Template has &pricing_195 for course pricing info
        assert "&pricing_195" in output

    def test_preserves_image_anchors(self, full_template):
        """Should preserve image anchors like &image_kurssi."""
        from download_activities import apply_template_matching

        matcher = TemplateMatcher(full_template)
        defaults, _ = apply_template_matching([], matcher)

        yaml = YAML()
        stream = io.StringIO()
        yaml.dump({"defaults": defaults}, stream)
        output = stream.getvalue()

        # Template has &image_kurssi
        assert "&image_kurssi" in output

    def test_preserves_nested_text_structure(self, full_template):
        """Should preserve template's text section structure with anchors."""
        from download_activities import apply_template_matching

        matcher = TemplateMatcher(full_template)
        defaults, _ = apply_template_matching([], matcher)

        # Text section should exist and contain the template's keys
        assert "text" in defaults
        assert "course_summary" in defaults["text"]
        assert "course_description" in defaults["text"]

