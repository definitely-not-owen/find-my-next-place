from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from find_my_next_place.storage.db import Database

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=ROOT / "templates")


def create_app(db: Database) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def queue(request: Request):
        listings = _surface_pending(db)
        return templates.TemplateResponse(
            request, "queue.html", {"listings": listings},
        )

    @app.get("/listing/{listing_id}")
    def detail(request: Request, listing_id: int):
        listing = db.get_listing(listing_id)
        verdict = db.get_verdict((listing["source"], listing["source_id"]))
        return templates.TemplateResponse(
            request, "listing.html", {"listing": listing, "verdict": verdict},
        )

    @app.post("/listing/{listing_id}/action")
    def action(listing_id: int, action: str = Form(...)):
        listing = db.get_listing(listing_id)
        key = (listing["source"], listing["source_id"])
        db.set_user_action(key, action)
        return RedirectResponse("/", status_code=303)

    return app


def _surface_pending(db: Database):
    rows = db.list_pending()
    # Re-include snoozed rows whose snooze has expired.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    db._conn.execute(  # noqa: SLF001
        """
        UPDATE verdicts SET user_action='pending', user_action_at=NULL
        WHERE user_action='snoozed' AND user_action_at < ?
        """,
        (cutoff,),
    )
    db._conn.commit()
    return rows
