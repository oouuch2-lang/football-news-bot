"""
Обработка сгенерированной картинки: наложение заголовка новости и логотипа
в едином стиле бренда (см. brand_config.py).
"""
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

import brand_config


def apply_branding(image_bytes: bytes, headline: str) -> bytes:
    """Накладывает заголовок и логотип на картинку, возвращает готовый JPEG."""
    image = Image.open(BytesIO(image_bytes)).convert("RGBA")

    image = _add_headline(image, headline)
    image = _add_logo(image)

    output = BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=90)
    return output.getvalue()


def apply_logo_only(image_bytes: bytes) -> bytes:
    """Накладывает только логотип, без заголовка — для аватарки канала
    (там не нужен текст конкретной новости)."""
    image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    image = _add_logo(image)

    output = BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=90)
    return output.getvalue()


def _add_logo(image: Image.Image) -> Image.Image:
    """Накладывает логотип в правый нижний угол. Если файла лого нет — картинка не меняется."""
    if not os.path.exists(brand_config.LOGO_PATH):
        return image

    logo = Image.open(brand_config.LOGO_PATH).convert("RGBA")
    logo_width = int(image.width * brand_config.LOGO_WIDTH_RATIO)
    logo_height = int(logo.height * (logo_width / logo.width))
    logo = logo.resize((logo_width, logo_height))

    x = image.width - logo_width - brand_config.LOGO_MARGIN
    y = image.height - logo_height - brand_config.LOGO_MARGIN
    image.paste(logo, (x, y), mask=logo)  # логотип накладывается по своей альфа-маске (прозрачный фон)
    return image


def _add_headline(image: Image.Image, headline: str) -> Image.Image:
    """Рисует заголовок новости на полупрозрачной плашке внизу картинки.

    ИИ-генераторы почти всегда рисуют текст на картинке нечитаемо, поэтому
    заголовок добавляется отдельно, поверх готового изображения.
    """
    draw = ImageDraw.Draw(image, "RGBA")
    font = _load_font()

    lines = _wrap_text(headline, font, max_width=image.width - 80)
    line_height = font.getbbox("Ag")[3] + 12
    band_height = line_height * len(lines) + 40

    draw.rectangle(
        [(0, image.height - band_height), (image.width, image.height)],
        fill=_hex_to_rgba(brand_config.BACKGROUND_COLOR, alpha=180),
    )

    y = image.height - band_height + 20
    for line in lines:
        draw.text((40, y), line, font=font, fill=brand_config.TEXT_COLOR)
        y += line_height

    return image


def _load_font() -> ImageFont.ImageFont:
    """Загружает шрифт бренда, если файл есть, иначе — стандартный шрифт Pillow."""
    if os.path.exists(brand_config.FONT_PATH):
        return ImageFont.truetype(brand_config.FONT_PATH, brand_config.FONT_SIZE)
    return ImageFont.load_default(size=brand_config.FONT_SIZE)


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list:
    """Переносит текст по словам, чтобы он помещался в ширину картинки."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _hex_to_rgba(hex_color: str, alpha: int) -> tuple:
    """Конвертирует HEX-цвет (#RRGGBB) в кортеж RGBA для Pillow."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)
