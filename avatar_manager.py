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

# Крупный план детали (мяч, бутсы, поле) — та же логика, что в brand_config.build_image_prompt:
# у бесплатных генераторов лица и командная форма с номерами выходят "нарисованными",
# а простая деталь при той же генерации выглядит как настоящее фото.
AVATAR_PROMPT = (
    f"Профессиональная спортивная фотография крупным планом для аватарки Telegram-канала: "
    f"мяч на траве или бутсы футболиста, без лиц и без формы с номерами. "
    f"Стиль: {brand_config.IMAGE_STYLE}. "
    f"Основной цвет в кадре: {brand_config.PRIMARY_COLOR}, тон фона: {brand_config.BACKGROUND_COLOR}. "
    f"Настоящее фото, снятое на камеру, высокая детализация. "
    f"НЕ рисунок, НЕ иллюстрация, НЕ мультфильм, НЕ логотип, НЕ эмблема. "
    f"Без текста и надписей. Хорошо читается в маленьком круглом кадре."
)


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
