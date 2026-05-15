from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.pipeline.llm import LLMFilter, Verdict


def L(text="Bright 1BR with in-unit laundry"):
    return Listing(
        source="craigslist", source_id="x", url="u", title="1BR",
        price=3000, beds=1.0, baths=1.0, sqft=None,
        lat=None, lng=None,
        posted_at=datetime.now(timezone.utc),
        raw_text=text, photos=[],
    )


def mock_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_parses_approve_verdict():
    client = MagicMock()
    client.messages.create.return_value = mock_response(
        '{"verdict":"approve","reasons":"Has laundry; matches taste"}'
    )
    f = LLMFilter(client=client, model="m", must_haves=["laundry"], deal_breakers=["top floor"])
    v = f.evaluate(L())
    assert v.verdict == "approve"
    assert "laundry" in v.reasons


def test_parses_reject_verdict():
    client = MagicMock()
    client.messages.create.return_value = mock_response(
        '{"verdict":"reject","reasons":"top floor"}'
    )
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=["top floor"])
    v = f.evaluate(L("Penthouse on the top floor"))
    assert v.verdict == "reject"


def test_unsure_on_malformed_json():
    client = MagicMock()
    client.messages.create.return_value = mock_response("not json at all")
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=[])
    v = f.evaluate(L())
    assert v.verdict == "unsure"
    assert v.reasons == "llm_error: malformed response"


def test_unsure_on_api_exception():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=[],
                  max_retries=2, sleep=lambda s: None)
    v = f.evaluate(L())
    assert v.verdict == "unsure"
    assert v.reasons.startswith("llm_error")
    assert client.messages.create.call_count == 2


def test_extracts_json_from_surrounding_prose():
    client = MagicMock()
    client.messages.create.return_value = mock_response(
        'Sure thing! {"verdict":"approve","reasons":"ok"} Hope this helps.'
    )
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=[])
    assert f.evaluate(L()).verdict == "approve"
