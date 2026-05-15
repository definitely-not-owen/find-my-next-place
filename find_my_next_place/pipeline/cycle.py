from __future__ import annotations
import logging
from dataclasses import dataclass, field
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.pipeline.rules import RuleFilter
from find_my_next_place.pipeline.llm import LLMFilter
from find_my_next_place.storage.db import Database
from find_my_next_place.notify.telegram import TelegramNotifier


log = logging.getLogger(__name__)


@dataclass
class CycleSummary:
    scraped: int = 0
    rule_passed: int = 0
    llm_approved: int = 0
    llm_unsure: int = 0
    llm_rejected: int = 0
    notified: int = 0
    errors: dict[str, str] = field(default_factory=dict)


def run_cycle(*, db: Database, scrapers, search,
              rule_filter: RuleFilter, llm_filter: LLMFilter,
              notifier: TelegramNotifier | None) -> CycleSummary:
    summary = CycleSummary()
    seen = set()
    for s in scrapers:
        seen.update(db.seen_keys(s.name))
    for scraper in scrapers:
        try:
            listings = scraper.fetch(search)
        except Exception as e:
            log.exception("scraper %s failed", scraper.name)
            summary.errors[scraper.name] = str(e)
            continue
        for listing in listings:
            summary.scraped += 1
            inserted = db.upsert_listing(listing)
            if not inserted:
                continue
            decision = rule_filter.evaluate(listing, seen=seen)
            if not decision.passes:
                continue
            summary.rule_passed += 1
            verdict = llm_filter.evaluate(listing)
            db.record_verdict(listing.dedup_key(), verdict.verdict, verdict.reasons)
            if verdict.verdict == "approve":
                summary.llm_approved += 1
            elif verdict.verdict == "unsure":
                summary.llm_unsure += 1
            else:
                summary.llm_rejected += 1
    if notifier is not None:
        for row in db.pending_notifications("telegram"):
            listing = db.get_listing(row.listing_id)
            verdict = db.get_verdict((row.source, row.source_id))
            photo = None
            try:
                import json
                photos = json.loads(listing["photos_json"] or "[]")
                photo = photos[0] if photos else None
            except (ValueError, KeyError, TypeError):
                pass
            try:
                notifier.send(
                    title=listing["title"], price=listing["price"],
                    url=listing["url"], rationale=verdict.llm_reasons or "",
                    photo_url=photo,
                )
                db.record_notification(row.listing_id, "telegram")
                summary.notified += 1
            except Exception as e:
                log.warning("telegram send failed for %s: %s", row.listing_id, e)
    log.info("cycle: %s", summary)
    return summary
