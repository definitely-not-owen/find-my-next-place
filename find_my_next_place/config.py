from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator, ValidationError


class ConfigError(Exception):
    pass


class RadiusFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float
    lng: float
    miles: float


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str
    neighborhoods: list[str] = []
    radius_miles_from: RadiusFrom | None = None
    min_price: int
    max_price: int
    min_bedrooms: float
    max_bedrooms: float

    @model_validator(mode="after")
    def _exactly_one_geo(self):
        if self.neighborhoods and self.radius_miles_from:
            raise ValueError("neighborhoods and radius_miles_from are mutually exclusive")
        if not self.neighborhoods and not self.radius_miles_from:
            raise ValueError("at least one of neighborhoods or radius_miles_from required")
        return self


class PreferencesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_haves: list[str] = []
    deal_breakers: list[str] = []


class TelegramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot_token: str
    chat_id: str


class NotifyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telegram: TelegramConfig


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    api_key: str


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: SearchConfig
    preferences: PreferencesConfig
    sources: list[Literal["craigslist", "zillow"]]
    schedule_minutes: int
    notify: NotifyConfig
    llm: LLMConfig


def _resolve_env(value):
    if isinstance(value, str) and value.startswith("env:"):
        var = value[4:]
        resolved = os.environ.get(var)
        if resolved is None:
            raise ConfigError(f"environment variable {var} is not set")
        return resolved
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_config(path: str | Path) -> AppConfig:
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"failed to read config: {e}") from e
    resolved = _resolve_env(raw)
    try:
        return AppConfig.model_validate(resolved)
    except ValidationError as e:
        raise ConfigError(str(e)) from e
