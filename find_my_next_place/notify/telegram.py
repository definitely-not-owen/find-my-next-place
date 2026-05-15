from __future__ import annotations
import httpx


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, http: httpx.Client | None = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.http = http or httpx.Client(timeout=15)

    def send(self, *, title: str, price: int, url: str, rationale: str, photo_url: str | None):
        caption = f"*{title}*\n${price}\n{url}\n\n_{rationale}_"
        if photo_url:
            api = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            payload = {"chat_id": self.chat_id, "photo": photo_url,
                       "caption": caption, "parse_mode": "Markdown"}
        else:
            api = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": caption,
                       "parse_mode": "Markdown", "disable_web_page_preview": False}
        resp = self.http.post(api, json=payload)
        resp.raise_for_status()
