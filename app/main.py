"""LINE webhook server. Run with: uvicorn app.main:create_app --factory --reload"""

import json
import logging

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from app.bot import HINT, Bot
from app.config import Settings, get_settings
from app.db import make_session_factory
from app.line_api import LineClient, text_message, verify_signature
from app.prices import PriceProvider, YFinanceProvider

log = logging.getLogger(__name__)

ERROR_REPLY = "😵 เกิดข้อผิดพลาด ลองใหม่อีกครั้ง · Something went wrong, please try again"


def handle_event(bot: Bot, line: LineClient, event: dict) -> None:
    source = event.get("source", {})
    user_id = source.get("userId")
    if source.get("type") != "user" or not user_id:
        return  # 1:1 chats only, portfolios shouldn't be shown in groups

    kind = event.get("type")
    reply_token = event.get("replyToken")
    try:
        if kind == "unfollow":
            bot.deactivate(user_id)
            return
        if kind == "follow":
            messages = bot.welcome(user_id)
        elif kind == "message" and event["message"].get("type") == "text":
            try:
                line.show_loading(user_id)
            except httpx.HTTPError:
                log.warning("Loading animation failed", exc_info=True)
            messages = bot.handle_text(user_id, event["message"]["text"])
        elif kind == "message":
            messages = [text_message(HINT)]  # sticker, image, ...
        else:
            return
        line.reply(reply_token, messages)
    except Exception:
        log.exception("Failed to handle %s event", kind)
        if reply_token:
            try:
                line.reply(reply_token, [text_message(ERROR_REPLY)])
            except Exception:
                log.exception("Failed to send error reply")


def create_app(
    settings: Settings | None = None,
    prices: PriceProvider | None = None,
    line: LineClient | None = None,
) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = settings or get_settings()
    if not settings.line_channel_secret or not settings.line_channel_access_token:
        log.warning("LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN not set, check your .env file")

    bot = Bot(make_session_factory(settings.database_url), prices or YFinanceProvider())
    line = line or LineClient(settings.line_channel_access_token)
    app = FastAPI(title="Stock Notification Bot")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/callback")
    async def callback(request: Request, background: BackgroundTasks) -> str:
        body = await request.body()
        if not verify_signature(settings.line_channel_secret, body, request.headers.get("X-Line-Signature", "")):
            raise HTTPException(status_code=400, detail="Invalid signature")
        # Answer LINE right away; fetching prices happens after the response is sent
        for event in json.loads(body).get("events", []):
            background.add_task(handle_event, bot, line, event)
        return "OK"

    return app
