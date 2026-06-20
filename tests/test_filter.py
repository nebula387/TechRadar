import pytest
from datetime import datetime
from unittest.mock import MagicMock
from app.models import RawItem, Source
from app.filter.quality_gate import passes_quality_gate, filter_items


def _item(**kwargs) -> RawItem:
    defaults = dict(
        source=Source.GITHUB,
        title="Amazing AI Framework",
        url="https://github.com/example/amazing-ai",
        description="A genuinely novel framework that makes LLM inference 10x faster",
        stars=1500,
        raw_data={},
        collected_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    return RawItem(**defaults)


def _storage(published: bool = False) -> MagicMock:
    s = MagicMock()
    s.is_published.return_value = published
    return s


def test_good_item_passes():
    ok, reason = passes_quality_gate(_item(), _storage())
    assert ok


def test_rejects_already_published():
    ok, reason = passes_quality_gate(_item(), _storage(published=True))
    assert not ok
    assert "published" in reason


def test_rejects_short_description():
    ok, reason = passes_quality_gate(_item(description="Too short"), _storage())
    assert not ok
    assert "description" in reason


def test_rejects_tutorial_in_title():
    ok, reason = passes_quality_gate(_item(title="Tutorial: Using Python for ML"), _storage())
    assert not ok
    assert "tutorial" in reason


def test_rejects_awesome_list():
    ok, reason = passes_quality_gate(_item(title="awesome-llm-tools"), _storage())
    assert not ok


def test_rejects_low_stars_github():
    ok, reason = passes_quality_gate(_item(stars=100), _storage())
    assert not ok
    assert "threshold" in reason


def test_rejects_low_score_hackernews():
    ok, reason = passes_quality_gate(_item(source=Source.HACKERNEWS, stars=50), _storage())
    assert not ok


def test_arxiv_passes_without_stars():
    ok, reason = passes_quality_gate(
        _item(source=Source.ARXIV, stars=None, description="A detailed research paper about transformer architecture improvements"),
        _storage(),
    )
    assert ok


def test_filter_items_batch():
    storage = _storage()
    items = [
        _item(title="Great Tool", stars=2000),
        _item(title="Tutorial: Getting Started", stars=2000),
        _item(description="Short"),
    ]
    result = filter_items(items, storage)
    assert len(result) == 1
    assert result[0].title == "Great Tool"
