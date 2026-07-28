"""
Бренд-бук канала: единый визуальный стиль для всех публикуемых картинок.
Все значения переопределяются через переменные окружения — стиль можно
поменять без правки кода.
"""
import os

# --- Цвета (HEX) ---
PRIMARY_COLOR = os.environ.get("BRAND_PRIMARY_COLOR", "#1E3A8A")
BACKGROUND_COLOR = os.environ.get("BRAND_BACKGROUND_COLOR", "#0F172A")
TEXT_COLOR = os.environ.get("BRAND_TEXT_COLOR", "#FFFFFF")

# --- Шрифт для заголовка, который рисуется поверх картинки ---
# По умолчанию используется вшитый в проект PT Sans (assets/fonts/brand_font.ttf) —
# он поддерживает кириллицу. Стандартный шрифт Pillow кириллицу не умеет и
# рисует русский текст квадратиками, поэтому используется только как
# аварийный запасной вариант, если файл шрифта вообще пропадёт.
FONT_PATH = os.environ.get("BRAND_FONT_PATH", "assets/fonts/brand_font.ttf")
FONT_SIZE = int(os.environ.get("BRAND_FONT_SIZE", "48"))

# --- Логотип / водяной знак ---
# PNG с прозрачным фоном. Если файла нет — логотип просто не накладывается.
LOGO_PATH = os.environ.get("BRAND_LOGO_PATH", "assets/logo.png")
LOGO_WIDTH_RATIO = float(os.environ.get("BRAND_LOGO_WIDTH_RATIO", "0.18"))  # ширина лого = 18% ширины картинки
LOGO_MARGIN = int(os.environ.get("BRAND_LOGO_MARGIN", "24"))  # отступ от края, px

# --- Стиль изображений (описание для промпта ИИ-генератора) ---
IMAGE_STYLE = os.environ.get("BRAND_IMAGE_STYLE", "динамичный спортивный стиль, яркий свет, драматичный ракурс")


def build_image_prompt(headline: str) -> str:
    """Собирает промпт для генерации картинки из заголовка новости и настроек бренд-бука.

    Явно просим ИИ не рисовать текст на картинке: диффузионные модели рисуют
    надписи почти всегда нечитаемо, поэтому заголовок накладывается отдельно
    в image_processor.py уже нормальным шрифтом.
    """
    return (
        f"Спортивная новость: {headline}. "
        f"Стиль: {IMAGE_STYLE}. "
        f"Основной цвет: {PRIMARY_COLOR}, фон: {BACKGROUND_COLOR}. "
        f"Без текста и надписей на изображении, фотореалистично, высокое качество."
    )
