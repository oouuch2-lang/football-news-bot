"""
Точка входа: один прогон бота — проверить RSS-ленты и опубликовать новые
новости в Telegram-канал. Запускается вручную (python main.py) или по
расписанию через .github/workflows/telegram_bot.yml.
"""
import asyncio
import html
import re
from datetime import datetime, timezone

from telegram import Bot

import config
import image_generator
import image_processor
import news_parser
import text_rewriter
from brand_config import build_image_prompt

MAX_CAPTION_LENGTH = 1024  # ограничение Telegram на подпись к фото


async def publish_news(bot: Bot, news_item: dict) -> None:
    """Готовит и публикует один пост: картинка (если получилось сгенерировать) + текст."""
    rewritten = text_rewriter.rewrite(news_item["title"], news_item["summary"])
    display_title, display_body = rewritten or (news_item["title"], news_item["summary"])

    caption = _build_caption(display_title, display_body, news_item["link"])

    # Промпт для картинки строим по ОРИГИНАЛЬНОМУ заголовку (обычно на английском —
    # ИИ-генераторы картинок точнее следуют промпту на английском, чем переводу от Gemini.
    image_bytes = image_generator.generate_image(build_image_prompt(news_item["title"]))
    if image_bytes:
        try:
            image_bytes = image_processor.apply_branding(image_bytes, display_title)
        except Exception as e:
            print(f"Не удалось наложить бренд-стиль на картинку: {e}")
            image_bytes = None

    if image_bytes:
        await bot.send_photo(chat_id=config.CHANNEL_ID, photo=image_bytes, caption=caption, parse_mode="HTML")
    else:
        await bot.send_message(chat_id=config.CHANNEL_ID, text=caption, parse_mode="HTML")


def _build_caption(title: str, summary: str, link: str) -> str:
    """Собирает подпись к посту: жирный заголовок, короткое описание и ссылка на источник.

    Telegram в режиме parse_mode="HTML" требует экранировать &, < и > везде,
    включая ссылку — а RSS-ссылки почти всегда содержат "&" в query-параметрах
    (?utm_source=rss&...), так что без html.escape отправка падала бы на
    большинстве новостей.
    """
    title = html.escape(title)
    link = html.escape(link)
    summary = html.escape(summary)
    caption = f"<b>{title}</b>\n\n{summary}\n\n<a href=\"{link}\">Источник</a>"

    if len(caption) > MAX_CAPTION_LENGTH:
        # обрезаем именно описание, а не заголовок и не ссылку
        overflow = len(caption) - MAX_CAPTION_LENGTH + 3
        summary = summary[:-overflow]
        summary = re.sub(r"&[#a-zA-Z0-9]*$", "", summary) + "..."  # не обрезать HTML-сущность (&amp; и т.п.) пополам
        caption = f"<b>{title}</b>\n\n{summary}\n\n<a href=\"{link}\">Источник</a>"

    return caption


async def main() -> None:
    news_items = news_parser.get_fresh_news()[:config.MAX_NEWS_PER_RUN]
    if not news_items:
        print("Новых новостей нет.")
        return

    history = news_parser.load_history()
    # async with обязателен: без него у Bot не инициализируется HTTP-клиент
    # правильно, и при отправке больше одного поста подряд соединения зависают
    # (пул на 1 соединение по умолчанию у python-telegram-bot).
    async with Bot(token=config.TELEGRAM_TOKEN) as bot:
        for item in news_items:
            try:
                await publish_news(bot, item)
                history[item["link"]] = datetime.now(timezone.utc).isoformat()
                print(f"Опубликовано: {item['title']}")
            except Exception as e:
                print(f"Не удалось опубликовать новость '{item['title']}': {e}")

    news_parser.save_history(history)


if __name__ == "__main__":
    asyncio.run(main())
