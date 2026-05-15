from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass
from find_my_next_place.scrapers.base import Listing


SYSTEM_PROMPT = """You evaluate rental listings against a user's preferences.
Reply with strict JSON only: {"verdict":"approve"|"reject"|"unsure","reasons":"..."}
- "approve": clearly matches must-haves and violates no deal-breakers
- "reject": clearly violates a deal-breaker
- "unsure": ambiguous or insufficient information
Keep reasons under 200 characters."""


@dataclass
class Verdict:
    verdict: str
    reasons: str


def _build_user_prompt(listing: Listing, must_haves: list[str], deal_breakers: list[str]) -> str:
    return (
        f"Listing:\n"
        f"  Title: {listing.title}\n"
        f"  Price: {listing.price}\n"
        f"  Beds/Baths: {listing.beds}/{listing.baths}\n"
        f"  Description: {listing.raw_text}\n\n"
        f"User must-haves: {must_haves}\n"
        f"User deal-breakers: {deal_breakers}\n"
    )


_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_verdict(text: str) -> Verdict:
    match = _JSON_RE.search(text)
    if not match:
        return Verdict("unsure", "llm_error: malformed response")
    try:
        data = json.loads(match.group(0))
        v = data.get("verdict")
        r = data.get("reasons", "")
        if v not in ("approve", "reject", "unsure"):
            return Verdict("unsure", "llm_error: bad verdict")
        return Verdict(v, str(r))
    except json.JSONDecodeError:
        return Verdict("unsure", "llm_error: malformed response")


class LLMFilter:
    def __init__(self, client, model: str, must_haves: list[str], deal_breakers: list[str],
                 max_retries: int = 3, sleep=time.sleep):
        self.client = client
        self.model = model
        self.must_haves = must_haves
        self.deal_breakers = deal_breakers
        self.max_retries = max_retries
        self.sleep = sleep

    def evaluate(self, listing: Listing) -> Verdict:
        user = _build_user_prompt(listing, self.must_haves, self.deal_breakers)
        backoff = 1.0
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=300,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user}],
                )
                text = resp.content[0].text
                return _parse_verdict(text)
            except Exception as e:
                last_err = e
                self.sleep(backoff)
                backoff *= 2
        return Verdict("unsure", f"llm_error: {last_err}")
