"""
Статистика по каналу: считает, сколько постов вышло за последние 7 дней,
и присылает сводку владельцу в личку.

Запускается вручную — кнопкой "Run workflow" на вкладке Actions в GitHub
(.github/workflows/stats.yml), заменяет живую Telegram-кнопку "Статистика".
"""
import asyncio
from datetime import datetime, timedelta, timezone

from telegram import Bot

import config
import news_parser


async def send_stats() -> None:
    history = news_parser.load_history()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    count_week = sum(
        1 for timestamp in history.values()
        if timestamp and datetime.fromisoformat(timestamp) >= week_ago
    )

    text = f"📊 Постов за последние 7 дней: {count_week}\nВсего в истории: {len(history)}"
    print(text)

    if not config.ADMIN_CHAT_ID:
        print("ADMIN_CHAT_ID не задан — статистика видна только здесь, в логах GitHub Actions.")
        return

    async with Bot(token=config.TELEGRAM_TOKEN) as bot:
        await bot.send_message(chat_id=config.ADMIN_CHAT_ID, text=text)


if __name__ == "__main__":
    asyncio.run(send_stats())
