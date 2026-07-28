"""
Смена аватарки Telegram-канала: генерирует картинку в стиле бренда
(brand_config.py) и ставит её через Bot API (setChatPhoto).

Отдельный скрипт, запускается по своему расписанию
(.github/workflows/avatar.yml) — раз в неделю или вручную кнопкой
"Run workflow" на вкладке Actions в GitHub.
"""
import asyncio

from telegram import Bot

import brand_config
import config
import image_generator
import image_processor

# Промпт вынесен в brand_config.build_avatar_prompt() — им же пользуется
# admin_agent.py при смене аватарки по просьбе в чате (там передаётся extra
# с уточнением от Gemini, здесь — прежний вариант по умолчанию).
AVATAR_PROMPT = brand_config.build_avatar_prompt()


async def set_channel_avatar() -> bool:
    """Генерирует и ставит новую аватарку канала. Возвращает True при успехе."""
    image_bytes = image_generator.generate_image(AVATAR_PROMPT)
    if not image_bytes:
        print("Не удалось сгенерировать картинку для аватарки — провайдер недоступен.")
        return False

    try:
        image_bytes = image_processor.apply_logo_only(image_bytes)
    except Exception as e:
        print(f"Не удалось наложить логотип на аватарку: {e}")
        # аватарка и без лого лучше, чем никакой — публикуем как есть

    async with Bot(token=config.TELEGRAM_TOKEN) as bot:
        await bot.set_chat_photo(chat_id=config.CHANNEL_ID, photo=image_bytes)

    print("Аватарка канала обновлена.")
    return True


if __name__ == "__main__":
    asyncio.run(set_channel_avatar())
