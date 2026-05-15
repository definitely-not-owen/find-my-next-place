import json
import os
import pytest
from find_my_next_place.config import load_config, ConfigError


def write_config(tmp_path, data):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    return p


def base_data():
    return {
        "search": {
            "city": "San Francisco, CA",
            "neighborhoods": ["Mission"],
            "radius_miles_from": None,
            "min_price": 2000, "max_price": 3800,
            "min_bedrooms": 1, "max_bedrooms": 2,
        },
        "preferences": {"must_haves": ["laundry"], "deal_breakers": ["top floor"]},
        "sources": ["craigslist"],
        "schedule_minutes": 30,
        "notify": {"telegram": {"bot_token": "literal-tok", "chat_id": "123"}},
        "llm": {"model": "claude-haiku-4-5-20251001", "api_key": "literal-key"},
    }


def test_loads_valid_config(tmp_path):
    cfg = load_config(write_config(tmp_path, base_data()))
    assert cfg.search.city == "San Francisco, CA"
    assert cfg.notify.telegram.bot_token == "literal-tok"
    assert cfg.llm.api_key == "literal-key"


def test_resolves_env_references(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-env")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-from-env")
    data = base_data()
    data["notify"]["telegram"]["bot_token"] = "env:TELEGRAM_BOT_TOKEN"
    data["llm"]["api_key"] = "env:ANTHROPIC_API_KEY"
    cfg = load_config(write_config(tmp_path, data))
    assert cfg.notify.telegram.bot_token == "from-env"
    assert cfg.llm.api_key == "key-from-env"


def test_rejects_both_neighborhoods_and_radius(tmp_path):
    data = base_data()
    data["search"]["radius_miles_from"] = {"lat": 37.7, "lng": -122.4, "miles": 2.0}
    with pytest.raises(ConfigError, match="mutually exclusive"):
        load_config(write_config(tmp_path, data))


def test_requires_neighborhoods_or_radius(tmp_path):
    data = base_data()
    data["search"]["neighborhoods"] = []
    with pytest.raises(ConfigError, match="at least one"):
        load_config(write_config(tmp_path, data))


def test_rejects_unknown_keys(tmp_path):
    data = base_data()
    data["search"]["mystery_key"] = "x"
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, data))


def test_missing_env_var_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    data = base_data()
    data["llm"]["api_key"] = "env:MISSING_VAR"
    with pytest.raises(ConfigError, match="MISSING_VAR"):
        load_config(write_config(tmp_path, data))


def test_loads_source_urls(tmp_path):
    data = base_data()
    data["source_urls"] = {
        "craigslist": {"rss_url": "https://nyc.example/rss"},
        "zillow": {"search_url": "https://example.com/nyc"},
    }
    cfg = load_config(write_config(tmp_path, data))
    assert cfg.source_urls["craigslist"].rss_url == "https://nyc.example/rss"
    assert cfg.source_urls["zillow"].search_url == "https://example.com/nyc"
