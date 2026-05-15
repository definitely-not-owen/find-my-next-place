from unittest.mock import MagicMock
from find_my_next_place.notify.telegram import TelegramNotifier


def test_sends_formatted_message():
    http = MagicMock()
    http.post.return_value.raise_for_status = lambda: None
    n = TelegramNotifier(bot_token="tok", chat_id="42", http=http)
    n.send(
        title="1BR Mission",
        price=3200,
        url="https://example.com/x",
        rationale="Has laundry, good light",
        photo_url="https://example.com/p.jpg",
    )
    http.post.assert_called_once()
    args, kwargs = http.post.call_args
    assert "tok" in args[0]
    payload = kwargs["json"]
    assert payload["chat_id"] == "42"
    assert "1BR Mission" in payload["caption"]
    assert "$3200" in payload["caption"]
    assert "example.com/x" in payload["caption"]


def test_falls_back_to_text_when_no_photo():
    http = MagicMock()
    http.post.return_value.raise_for_status = lambda: None
    n = TelegramNotifier(bot_token="tok", chat_id="42", http=http)
    n.send(title="t", price=2000, url="u", rationale="r", photo_url=None)
    args, _ = http.post.call_args
    assert "sendMessage" in args[0]


def test_raises_on_http_error():
    http = MagicMock()
    http.post.return_value.raise_for_status.side_effect = RuntimeError("400")
    n = TelegramNotifier(bot_token="tok", chat_id="42", http=http)
    import pytest
    with pytest.raises(RuntimeError):
        n.send(title="t", price=1, url="u", rationale="r", photo_url=None)
