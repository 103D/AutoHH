"""Unit tests for HH sync parsing primitives (ADR-001 milestone 3)."""

import pytest

from app.integrations.hh.exceptions import HHParseError
from app.integrations.hh.negotiations import parse_negotiation_item
from app.integrations.hh.resumes import parse_resume_item
from app.integrations.hh.sync_base import content_hash, extract_items, parse_remote_datetime

# -- content hash -------------------------------------------------------------


def test_content_hash_is_order_insensitive():
    a = {"id": 1, "title": "Backend", "status": {"id": "published"}}
    b = {"status": {"id": "published"}, "title": "Backend", "id": 1}
    assert content_hash(a) == content_hash(b)
    assert len(content_hash(a)) == 64


def test_content_hash_detects_changes():
    a = {"id": 1, "title": "Backend"}
    b = {"id": 1, "title": "Backend Sr."}
    assert content_hash(a) != content_hash(b)


# -- datetime -------------------------------------------------------------------


def test_parse_remote_datetime_variants():
    assert parse_remote_datetime("2026-09-06T10:00:00+0300") is not None
    assert parse_remote_datetime("2026-09-06T10:00:00Z") is not None
    assert parse_remote_datetime("") is None
    assert parse_remote_datetime(None) is None
    assert parse_remote_datetime("not-a-date") is None
    assert parse_remote_datetime(42) is None


# -- resume items -----------------------------------------------------------------


def test_parse_resume_item_full():
    parsed = parse_resume_item(
        {
            "id": "resume-1",
            "title": "Data Analyst",
            "status": {"id": "published", "name": "Published"},
            "updated_at": "2026-09-01T12:00:00+0300",
            "alternate_url": "https://hh.ru/resume/x",
        }
    )
    assert parsed is not None
    assert parsed["remote_resume_id"] == "resume-1"
    assert parsed["title"] == "Data Analyst"
    assert parsed["status"] == "published"
    assert parsed["remote_updated_at"] is not None
    assert parsed["raw_data"]["id"] == "resume-1"
    assert len(parsed["content_hash"]) == 64


def test_parse_resume_item_quarantines_malformed():
    assert parse_resume_item({"no_id": True}) is None
    assert parse_resume_item("a string") is None
    assert parse_resume_item(None) is None
    assert parse_resume_item([]) is None


# -- negotiation items ---------------------------------------------------------------


def _negotiation(item_id="n-1", **overrides):
    item = {
        "id": item_id,
        "state": {"id": "active", "name": "Active"},
        "vacancy": {"id": "vac-9", "name": "Backend"},
        "resume": {"id": "res-7"},
        "created_at": "2026-08-01T09:00:00+0300",
        "updated_at": "2026-09-01T09:00:00+0300",
    }
    item.update(overrides)
    return item


def test_parse_negotiation_item_extracts_ids_and_state():
    parsed = parse_negotiation_item(_negotiation())
    assert parsed is not None
    assert parsed["remote_negotiation_id"] == "n-1"
    assert parsed["remote_resume_id"] == "res-7"
    assert parsed["remote_vacancy_id"] == "vac-9"
    assert parsed["state_id"] == "active"
    assert parsed["state_name"] == "Active"
    assert parsed["messages_metadata"] == {}


def test_parse_negotiation_item_fallbacks_and_messages():
    parsed = parse_negotiation_item(
        _negotiation(
            vacancy=None,
            resume=None,
            vacancy_id="vac-flat",
            resume_id="res-flat",
            messages=[{"created_at": "2026-09-02T10:00:00+0300", "text": "hi"}],
        )
    )
    assert parsed is not None
    assert parsed["remote_vacancy_id"] == "vac-flat"
    assert parsed["remote_resume_id"] == "res-flat"
    assert parsed["messages_metadata"]["count"] == 1
    assert parsed["messages_metadata"]["last_message_at"] is not None


def test_parse_negotiation_item_quarantines_missing_state():
    assert parse_negotiation_item({"id": "n-2"}) is None
    assert parse_negotiation_item({"id": "n-2", "state": {}}) is None
    assert parse_negotiation_item(_negotiation(state=None)) is None
    assert parse_negotiation_item("garbage") is None


# -- batch envelope -------------------------------------------------------------------


def test_extract_items_accepts_dict_and_list():
    assert extract_items({"items": [1, 2]}, what="x") == [1, 2]
    assert extract_items([1], what="x") == [1]
    with pytest.raises(HHParseError):
        extract_items({"unexpected": True}, what="x")
    with pytest.raises(HHParseError):
        extract_items("nope", what="x")
