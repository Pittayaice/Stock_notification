import base64
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.line_api import LineClient, text_message, verify_signature
from app.main import create_app

SECRET = "test-secret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


class FakeLine:
    def __init__(self):
        self.replies: list[tuple[str, list[dict]]] = []

    def reply(self, reply_token: str, messages: list[dict]) -> None:
        self.replies.append((reply_token, messages))

    def show_loading(self, user_id: str, seconds: int = 10) -> None:
        pass


@pytest.fixture
def line() -> FakeLine:
    return FakeLine()


@pytest.fixture
def client(prices, line) -> TestClient:
    return TestClient(create_app(Settings(SECRET, "token", "sqlite://"), prices=prices, line=line))


def post(client: TestClient, payload: dict, signature: str | None = None):
    body = json.dumps(payload).encode()
    return client.post("/callback", content=body, headers={"X-Line-Signature": signature or sign(body)})


def text_event(text: str, source_type: str = "user") -> dict:
    return {
        "type": "message",
        "replyToken": "reply-1",
        "source": {"type": source_type, "userId": "U1"},
        "message": {"type": "text", "text": text},
    }


def test_verify_signature():
    assert verify_signature(SECRET, b"body", sign(b"body"))
    assert not verify_signature(SECRET, b"body", sign(b"other"))
    assert not verify_signature("", b"body", sign(b"body", ""))


def test_rejects_bad_signature(client, line):
    assert post(client, {"events": [text_event("port")]}, signature="forged").status_code == 400
    assert line.replies == []


def test_line_verify_button(client):
    assert post(client, {"events": []}).status_code == 200


def test_text_message_gets_reply(client, line):
    assert post(client, {"events": [text_event("add PTT 100 33.90")]}).status_code == 200
    [(token, [message])] = line.replies
    assert token == "reply-1"
    assert "100 @ ฿33.90" in message["text"]


def test_follow_sends_welcome(client, line):
    post(client, {"events": [{"type": "follow", "replyToken": "r", "source": {"type": "user", "userId": "U1"}}]})
    assert "How to use" in line.replies[0][1][0]["text"]


def test_group_chats_are_ignored(client, line):
    post(client, {"events": [text_event("port", source_type="group")]})
    assert line.replies == []


def test_line_client_sends_reply():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={})

    LineClient("abc", transport=httpx.MockTransport(handler)).reply("rt", [text_message("hi", [("Yes", "yes")])])
    [request] = sent
    assert request.url == "https://api.line.me/v2/bot/message/reply"
    assert request.headers["Authorization"] == "Bearer abc"
    assert json.loads(request.content) == {
        "replyToken": "rt",
        "messages": [{
            "type": "text",
            "text": "hi",
            "quickReply": {"items": [{"type": "action", "action": {"type": "message", "label": "Yes", "text": "yes"}}]},
        }],
    }
