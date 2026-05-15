from __future__ import annotations
import logging
import threading
from pathlib import Path
from anthropic import Anthropic
from apscheduler.schedulers.blocking import BlockingScheduler
from find_my_next_place.config import AppConfig
from find_my_next_place.notify.telegram import TelegramNotifier
from find_my_next_place.pipeline.cycle import run_cycle
from find_my_next_place.pipeline.geo import GeoResolver
from find_my_next_place.pipeline.llm import LLMFilter
from find_my_next_place.pipeline.rules import RuleFilter
from find_my_next_place.scrapers.craigslist import CraigslistScraper
from find_my_next_place.scrapers.zillow import ZillowScraper
from find_my_next_place.storage.db import Database


log = logging.getLogger(__name__)


def build_scrapers(cfg: AppConfig) -> list:
    out = []
    for name in cfg.sources:
        url_cfg = cfg.source_urls.get(name)
        if name == "craigslist":
            rss = url_cfg.rss_url if url_cfg else None
            out.append(CraigslistScraper(rss_url=rss))
        elif name == "zillow":
            search = url_cfg.search_url if url_cfg else None
            out.append(ZillowScraper(search_url=search))
    return out


def build_search_arg(cfg: AppConfig):
    return cfg.search


def build_rule_filter(cfg: AppConfig, geo: GeoResolver) -> RuleFilter:
    if cfg.search.neighborhoods:
        polys = geo.resolve(cfg.search.city, cfg.search.neighborhoods)
        radius = None
    else:
        polys = []
        r = cfg.search.radius_miles_from
        radius = (r.lat, r.lng, r.miles)
    return RuleFilter(
        min_price=cfg.search.min_price, max_price=cfg.search.max_price,
        min_beds=cfg.search.min_bedrooms, max_beds=cfg.search.max_bedrooms,
        polygons=polys, radius=radius,
    )


def start_web(db: Database, host: str = "127.0.0.1", port: int = 8765):
    import uvicorn
    from find_my_next_place.web.app import create_app
    app = create_app(db)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()


def run(cfg: AppConfig, *, data_dir: Path, once: bool = False):
    db = Database(data_dir / "fmnp.db")
    geo = GeoResolver(cache_path=data_dir / "geo_cache.json")
    rule_filter = build_rule_filter(cfg, geo)
    llm_client = Anthropic(api_key=cfg.llm.api_key)
    llm_filter = LLMFilter(
        client=llm_client, model=cfg.llm.model,
        must_haves=cfg.preferences.must_haves,
        deal_breakers=cfg.preferences.deal_breakers,
    )
    notifier = TelegramNotifier(
        bot_token=cfg.notify.telegram.bot_token,
        chat_id=cfg.notify.telegram.chat_id,
    )
    scrapers = build_scrapers(cfg)
    search = build_search_arg(cfg)

    def job():
        run_cycle(db=db, scrapers=scrapers, search=search,
                  rule_filter=rule_filter, llm_filter=llm_filter,
                  notifier=notifier)

    if once:
        job()
        return

    start_web(db)
    job()  # immediate run

    scheduler = BlockingScheduler()
    scheduler.add_job(job, "interval", minutes=cfg.schedule_minutes)
    log.info("scheduler started; cadence=%dm", cfg.schedule_minutes)
    scheduler.start()
