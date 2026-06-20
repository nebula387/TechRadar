import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch
from app.filter.llm_judge import judge_item, _extract_json
from app.models import RawItem, Source, Category


def _item(**kwargs) -> RawItem:
    defaults = dict(
        source=Source.GITHUB,
        title="Incredible ML Inference Engine",
        url="https://github.com/example/ml-engine",
        description="A breakthrough framework that makes transformer inference 10x faster using novel quantization",
        stars=8000,
        raw_data={},
        collected_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    return RawItem(**defaults)


def test_extract_json_clean():
    text = '{"approve": true, "score": 90}'
    assert _extract_json(text)["score"] == 90


def test_extract_json_with_fences():
    text = '```json\n{"approve": true, "score": 87}\n```'
    assert _extract_json(text)["approve"] is True


def test_extract_json_embedded():
    text = 'Here is my answer:\n{"approve": false, "score": 60, "reason": "generic"}'
    assert _extract_json(text)["approve"] is False


@pytest.mark.asyncio
async def test_judge_item_approved():
    response = json.dumps({
        "approve": True,
        "score": 92,
        "novelty": 9,
        "practical_value": 9,
        "wow_factor": 8,
        "category": "Developer Tool",
        "audience": "ML Engineers",
        "reason": "Genuinely novel quantization breakthrough",
        "emoji": "⚡",
        "accent_color": "#6366f1",
    })
    with patch("app.filter.llm_judge.groq_complete", AsyncMock(return_value=response)):
        result = await judge_item(_item())

    assert result is not None
    assert result.score == 92
    assert result.category == Category.DEVELOPER_TOOL
    assert result.is_interesting is True
    assert result.emoji == "⚡"


@pytest.mark.asyncio
async def test_judge_item_rejected_low_score():
    response = json.dumps({
        "approve": False,
        "score": 72,
        "novelty": 5,
        "practical_value": 6,
        "wow_factor": 4,
        "category": "Developer Tool",
        "audience": "Developers",
        "reason": "Another framework without clear differentiation",
        "emoji": "🔧",
        "accent_color": "#6366f1",
    })
    with patch("app.filter.llm_judge.groq_complete", AsyncMock(return_value=response)):
        result = await judge_item(_item())

    assert result is None


@pytest.mark.asyncio
async def test_judge_item_handles_invalid_category():
    response = json.dumps({
        "approve": True,
        "score": 88,
        "novelty": 7,
        "practical_value": 8,
        "wow_factor": 7,
        "category": "Unknown Category XYZ",
        "audience": "Engineers",
        "reason": "Very useful",
        "emoji": "🚀",
        "accent_color": "#8b5cf6",
    })
    with patch("app.filter.llm_judge.groq_complete", AsyncMock(return_value=response)):
        result = await judge_item(_item())

    assert result is not None
    assert result.category == Category.DEVELOPER_TOOL  # fallback


@pytest.mark.asyncio
async def test_judge_item_handles_llm_error():
    with patch("app.filter.llm_judge.groq_complete", AsyncMock(side_effect=Exception("API down"))):
        result = await judge_item(_item())
    assert result is None
