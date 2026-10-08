"""Minimal LINE Messaging API client: signature check, reply, push, loading animation."""

import base64
import hashlib
import hmac
import logging

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://api.line.me/v2/bot"
MAX_MESSAGES = 5  # LINE accepts up to 5 message objects per reply/push


def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """Check the X-Line-Signature header so only LINE can call the webhook."""
    if not channel_secret or not signature:
        return False
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def text_message(text: str, quick_replies: list[tuple[str, str]] | None = None) -> dict:
    """A text message. Each quick reply is (button label, text sent when tapped)."""
    message: dict = {"type": "text", "text": text}
    if quick_replies:
        message["quickReply"] = {
            "items": [
                {"type": "action", "action": {"type": "message", "label": label, "text": sent}}
                for label, sent in quick_replies
            ]
        }
    return message


def message_text(message: dict) -> str:
    """Plain-text view of a message for the terminal and tests. Flex cards are flattened."""
    if message["type"] == "text":
        return message["text"]
    return _flex_text(message["contents"])


def _flex_text(node: dict) -> str:
    kind = node["type"]
    if kind == "text":
        return node["text"]
    if kind == "button":
        return f"[{node['action']['label']}]"
    if kind == "separator":
        return "─" * 20
    if kind == "carousel":
        return "\n\n".join(_flex_text(bubble) for bubble in node["contents"])
    if kind == "bubble":
        return "\n".join(_flex_text(node[part]) for part in ("header", "hero", "body", "footer") if part in node)
    if kind == "box":
        parts = [t for t in (_flex_text(child) for child in node["contents"]) if t]
        if node["layout"] == "vertical":
            return "\n".join(parts)
        return "  ".join(p.replace("\n", " ") for p in parts)
    return ""


class LineClient:
    def __init__(self, access_token: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
            transport=transport,
        )

    def reply(self, reply_token: str, messages: list[dict]) -> None:
        """Answer a user's message. Replies are free and don't use the monthly push quota."""
        self._post("/message/reply", {"replyToken": reply_token, "messages": messages[:MAX_MESSAGES]})

    def push(self, to: str, messages: list[dict]) -> None:
        """Send without a user message first. Counts against the monthly push quota."""
        self._post("/message/push", {"to": to, "messages": messages[:MAX_MESSAGES]})

    def show_loading(self, user_id: str, seconds: int = 10) -> None:
        """Show the typing animation while prices are fetched."""
        self._post("/chat/loading/start", {"chatId": user_id, "loadingSeconds": seconds})

    def _post(self, path: str, payload: dict) -> None:
        response = self._http.post(path, json=payload)
        if response.is_error:
            log.error("LINE API %s failed: %s %s", path, response.status_code, response.text)
        response.raise_for_status()
