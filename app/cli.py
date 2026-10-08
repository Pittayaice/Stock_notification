"""Try the bot in your terminal, no LINE needed.

    python -m app.cli                    # interactive
    python -m app.cli add PTT 100 33.90  # one command
"""

import sys

from app.bot import Bot
from app.config import get_settings
from app.db import make_session_factory
from app.line_api import message_text
from app.prices import YFinanceProvider

CLI_USER = "local-cli-user"


def show(messages: list[dict]) -> None:
    for message in messages:
        print(message_text(message))
        for item in message.get("quickReply", {}).get("items", []):
            action = item["action"]
            print(f"  [button] {action['label']} → {action['text']}")
        print()


def main() -> None:
    bot = Bot(make_session_factory(get_settings().database_url), YFinanceProvider())
    if len(sys.argv) > 1:
        show(bot.handle_text(CLI_USER, " ".join(sys.argv[1:])))
        return
    print("Type a command (help, add PTT 100 33.90, port, ...). Ctrl+D to quit.\n")
    while True:
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.strip():
            show(bot.handle_text(CLI_USER, text))


if __name__ == "__main__":
    main()
